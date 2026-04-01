"""
Analyst Ratings Collector — individual analyst ratings + price targets via Finnhub.

Collector ID: 36 (Analyst Ratings Detail)
Tables:
  - raw_analyst_ratings: individual upgrade/downgrade events with firm, action, price targets
  - raw_analyst_consensus: computed cohort summary per security (mean rating, mode, mean PT)

Supplements the existing analyst_actions.py (which collects monthly aggregates only).

Data sources:
  - Finnhub /stock/upgrade-downgrade — individual analyst actions
  - Finnhub /stock/price-target — consensus price target
  - Finnhub /stock/recommendation — monthly aggregate (already collected, used for consensus calc)

Schedule: daily, after analyst_actions.py
"""

import sys
import os
import time
import requests
from datetime import datetime, timezone, timedelta, date
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

FINNHUB_UPGRADES = "https://finnhub.io/api/v1/stock/upgrade-downgrade"
FINNHUB_PRICE_TARGET = "https://finnhub.io/api/v1/stock/price-target"

# Numeric mapping for rating calculations
RATING_MAP = {
    "strong buy": 5, "strong_buy": 5, "outperform": 5, "overweight": 5,
    "buy": 4, "accumulate": 4, "positive": 4, "sector outperform": 4,
    "hold": 3, "neutral": 3, "equal-weight": 3, "market perform": 3,
    "in-line": 3, "sector perform": 3, "peer perform": 3, "equal weight": 3,
    "sell": 2, "underperform": 2, "underweight": 2, "reduce": 2,
    "sector underperform": 2, "negative": 2,
    "strong sell": 1, "strong_sell": 1,
}

RATING_LABELS = {5: "Strong Buy", 4: "Buy", 3: "Hold", 2: "Sell", 1: "Strong Sell"}


def _normalize_rating(raw):
    """Map raw analyst rating string to numeric 1-5 scale."""
    if not raw:
        return None
    return RATING_MAP.get(raw.lower().strip())


class AnalystRatingsCollector(BaseCollector):

    COLLECTOR_ID = 36
    COLLECTOR_NAME = "Analyst Ratings Detail"
    COLLECTOR_TYPE = "market_data"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        if not config.FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY not set")
        self._ensure_tables()

    def _ensure_tables(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_analyst_ratings (
                        rating_id       SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        rating_date     DATE NOT NULL,
                        company         VARCHAR(200),
                        analyst_name    VARCHAR(200),
                        action          VARCHAR(30),
                        from_rating     VARCHAR(50),
                        to_rating       VARCHAR(50),
                        from_rating_num SMALLINT,
                        to_rating_num   SMALLINT,
                        price_target    NUMERIC(14,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, rating_date, company, action)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rar_security
                        ON raw_analyst_ratings (security_id, rating_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rar_date
                        ON raw_analyst_ratings (rating_date DESC);

                    CREATE TABLE IF NOT EXISTS raw_analyst_consensus (
                        consensus_id    SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        snapshot_date   DATE NOT NULL,
                        total_analysts  INT DEFAULT 0,
                        mean_rating     NUMERIC(4,2),
                        median_rating   NUMERIC(4,2),
                        mode_rating     SMALLINT,
                        mode_label      VARCHAR(20),
                        strong_buy_pct  NUMERIC(5,2),
                        buy_pct         NUMERIC(5,2),
                        hold_pct        NUMERIC(5,2),
                        sell_pct        NUMERIC(5,2),
                        strong_sell_pct NUMERIC(5,2),
                        mean_price_target   NUMERIC(14,4),
                        high_price_target   NUMERIC(14,4),
                        low_price_target    NUMERIC(14,4),
                        median_price_target NUMERIC(14,4),
                        n_price_targets     INT DEFAULT 0,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, snapshot_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rac2_security
                        ON raw_analyst_consensus (security_id, snapshot_date DESC);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Fetching analyst ratings for %d equities...", total)

        ratings = {}
        price_targets = {}

        for i, s in enumerate(equities):
            ticker = s["ticker"]

            # Individual upgrades/downgrades
            try:
                resp = requests.get(
                    FINNHUB_UPGRADES,
                    params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        ratings[ticker] = data
                        self.stats["fetched"] += 1
                elif resp.status_code == 429:
                    self.log.warning("Rate limited at %d/%d, sleeping...", i, total)
                    time.sleep(62)
            except requests.RequestException as e:
                self.log.debug("Upgrade fetch error %s: %s", ticker, e)
                self.stats["errors"] += 1

            time.sleep(0.5)

            # Consensus price target
            try:
                resp = requests.get(
                    FINNHUB_PRICE_TARGET,
                    params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data.get("targetMean"):
                        price_targets[ticker] = data
            except requests.RequestException:
                pass

            time.sleep(0.5)

            if (i + 1) % 28 == 0:
                self.log.info("  Progress: %d/%d, rate limit pause...", i + 1, total)
                time.sleep(62)

        return {"ratings": ratings, "price_targets": price_targets}

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        cutoff = (date.today() - timedelta(days=365)).isoformat()

        rating_rows = []
        consensus_rows = []

        for ticker, actions in raw_data["ratings"].items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            # Individual ratings (last 12 months)
            recent_ratings = []
            for a in actions:
                rd = a.get("gradeDate", "")
                if rd < cutoff:
                    continue

                from_num = _normalize_rating(a.get("fromGrade"))
                to_num = _normalize_rating(a.get("toGrade"))

                rating_rows.append({
                    "security_id": sid,
                    "rating_date": rd,
                    "company": (a.get("company") or "")[:200],
                    "analyst_name": "",  # Finnhub doesn't provide individual names
                    "action": (a.get("action") or "")[:30],
                    "from_rating": (a.get("fromGrade") or "")[:50],
                    "to_rating": (a.get("toGrade") or "")[:50],
                    "from_rating_num": from_num,
                    "to_rating_num": to_num,
                    "price_target": None,  # not in upgrade endpoint
                })

                if to_num is not None:
                    recent_ratings.append(to_num)

            # Build consensus from recent ratings
            if recent_ratings:
                pt_data = raw_data["price_targets"].get(ticker, {})

                cnt = Counter(recent_ratings)
                total = len(recent_ratings)
                mean_r = sum(recent_ratings) / total
                sorted_r = sorted(recent_ratings)
                mid = total // 2
                median_r = sorted_r[mid] if total % 2 else (sorted_r[mid-1] + sorted_r[mid]) / 2
                mode_r = cnt.most_common(1)[0][0]

                consensus_rows.append({
                    "security_id": sid,
                    "snapshot_date": date.today(),
                    "total_analysts": total,
                    "mean_rating": round(mean_r, 2),
                    "median_rating": round(median_r, 2),
                    "mode_rating": mode_r,
                    "mode_label": RATING_LABELS.get(mode_r, "Unknown"),
                    "strong_buy_pct": round(cnt.get(5, 0) / total * 100, 2),
                    "buy_pct": round(cnt.get(4, 0) / total * 100, 2),
                    "hold_pct": round(cnt.get(3, 0) / total * 100, 2),
                    "sell_pct": round(cnt.get(2, 0) / total * 100, 2),
                    "strong_sell_pct": round(cnt.get(1, 0) / total * 100, 2),
                    "mean_price_target": pt_data.get("targetMean"),
                    "high_price_target": pt_data.get("targetHigh"),
                    "low_price_target": pt_data.get("targetLow"),
                    "median_price_target": pt_data.get("targetMedian"),
                    "n_price_targets": pt_data.get("lastUpdated") and 1 or 0,
                })

        # Tag rows so store() can split them; return flat list for BaseCollector coverage tracking
        for r in rating_rows:
            r["_row_type"] = "rating"
        for c in consensus_rows:
            c["_row_type"] = "consensus"
        return rating_rows + consensus_rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        rating_rows = [r for r in rows if r.get("_row_type") == "rating"]
        consensus_rows = [r for r in rows if r.get("_row_type") == "consensus"]

        self.log.info("Writing %d individual ratings, %d consensus snapshots...",
                      len(rating_rows), len(consensus_rows))

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                if rating_rows:
                    execute_values(
                        cur,
                        """INSERT INTO raw_analyst_ratings
                               (security_id, rating_date, company, analyst_name,
                                action, from_rating, to_rating, from_rating_num,
                                to_rating_num, price_target)
                           VALUES %s
                           ON CONFLICT (security_id, rating_date, company, action)
                           DO UPDATE SET to_rating = EXCLUDED.to_rating,
                                         to_rating_num = EXCLUDED.to_rating_num,
                                         price_target = EXCLUDED.price_target,
                                         last_updated = now()""",
                        [(r["security_id"], r["rating_date"], r["company"],
                          r["analyst_name"], r["action"], r["from_rating"],
                          r["to_rating"], r["from_rating_num"], r["to_rating_num"],
                          r["price_target"])
                         for r in rating_rows],
                        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        page_size=config.DB_BATCH_SIZE,
                    )

                if consensus_rows:
                    execute_values(
                        cur,
                        """INSERT INTO raw_analyst_consensus
                               (security_id, snapshot_date, total_analysts,
                                mean_rating, median_rating, mode_rating, mode_label,
                                strong_buy_pct, buy_pct, hold_pct, sell_pct, strong_sell_pct,
                                mean_price_target, high_price_target, low_price_target,
                                median_price_target, n_price_targets)
                           VALUES %s
                           ON CONFLICT (security_id, snapshot_date)
                           DO UPDATE SET total_analysts = EXCLUDED.total_analysts,
                                         mean_rating = EXCLUDED.mean_rating,
                                         median_rating = EXCLUDED.median_rating,
                                         mode_rating = EXCLUDED.mode_rating,
                                         mode_label = EXCLUDED.mode_label,
                                         strong_buy_pct = EXCLUDED.strong_buy_pct,
                                         buy_pct = EXCLUDED.buy_pct,
                                         hold_pct = EXCLUDED.hold_pct,
                                         sell_pct = EXCLUDED.sell_pct,
                                         strong_sell_pct = EXCLUDED.strong_sell_pct,
                                         mean_price_target = EXCLUDED.mean_price_target,
                                         high_price_target = EXCLUDED.high_price_target,
                                         low_price_target = EXCLUDED.low_price_target,
                                         median_price_target = EXCLUDED.median_price_target,
                                         n_price_targets = EXCLUDED.n_price_targets,
                                         last_updated = now()""",
                        [(c["security_id"], c["snapshot_date"], c["total_analysts"],
                          c["mean_rating"], c["median_rating"], c["mode_rating"],
                          c["mode_label"], c["strong_buy_pct"], c["buy_pct"],
                          c["hold_pct"], c["sell_pct"], c["strong_sell_pct"],
                          c["mean_price_target"], c["high_price_target"],
                          c["low_price_target"], c["median_price_target"],
                          c["n_price_targets"])
                         for c in consensus_rows],
                        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        page_size=config.DB_BATCH_SIZE,
                    )

                self.stats["stored"] = len(rating_rows) + len(consensus_rows)

        # Coverage from consensus (one per security)
        coverage = {c["security_id"]: 1 for c in consensus_rows}
        if coverage:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    db.upsert_coverage_batch(cur, self.COLLECTOR_ID,
                                             list(coverage.items()))

    def teardown(self):
        self.log.info("Analyst ratings: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(AnalystRatingsCollector)
