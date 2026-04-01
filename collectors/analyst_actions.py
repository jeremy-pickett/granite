"""
Analyst Actions Collector — consensus recommendation trends via Finnhub.

Collector ID: 8 (Analyst Revision Tracker)
Table:        raw_analyst_actions

Finnhub endpoint: /api/v1/stock/recommendation?symbol=TICKER
Returns monthly aggregates: strongBuy, buy, hold, sell, strongSell counts.
"""

import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db


class AnalystActionsCollector(BaseCollector):

    # ── identity ──────────────────────────────────────────────────────
    COLLECTOR_ID = 8
    COLLECTOR_NAME = "Analyst Revision Tracker"
    COLLECTOR_TYPE = "market_data"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        if not config.FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY not set")
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_analyst_actions (
                        action_id       SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        period          DATE NOT NULL,
                        strong_buy      INT DEFAULT 0,
                        buy             INT DEFAULT 0,
                        hold            INT DEFAULT 0,
                        sell            INT DEFAULT 0,
                        strong_sell     INT DEFAULT 0,
                        total_analysts  INT DEFAULT 0,
                        collected_at    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, period)
                    );
                    CREATE INDEX IF NOT EXISTS idx_raa_security ON raw_analyst_actions (security_id, period DESC);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Fetch analyst recommendation trends from Finnhub."""
        raw = {}
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Fetching analyst recommendations for %d equities...", total)

        for i, s in enumerate(equities):
            ticker = s["ticker"]
            try:
                resp = requests.get(
                    "https://finnhub.io/api/v1/stock/recommendation",
                    params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        raw[ticker] = data
                        self.stats["fetched"] += 1
                    else:
                        self.stats["skipped"] += 1
                elif resp.status_code == 429:
                    self.log.warning("Rate limited at %d/%d, sleeping 60s...", i, total)
                    time.sleep(62)
                else:
                    self.stats["skipped"] += 1
            except requests.RequestException as e:
                self.log.debug("Fetch error %s: %s", ticker, e)
                self.stats["errors"] += 1

            if (i + 1) % 55 == 0:
                self.log.info("  Progress: %d/%d, pausing for rate limit...", i + 1, total)
                time.sleep(62)

        return raw

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        rows = []

        for ticker, recs in raw_data.items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            for r in recs[:6]:  # last 6 months
                sb = int(r.get("strongBuy", 0))
                b = int(r.get("buy", 0))
                h = int(r.get("hold", 0))
                s = int(r.get("sell", 0))
                ss = int(r.get("strongSell", 0))
                rows.append({
                    "security_id": sid,
                    "period": r.get("period"),
                    "strong_buy": sb,
                    "buy": b,
                    "hold": h,
                    "sell": s,
                    "strong_sell": ss,
                    "total_analysts": sb + b + h + s + ss,
                })

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        self.log.info("Writing %d analyst recommendation periods...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_analyst_actions
                           (security_id, period, strong_buy, buy, hold, sell,
                            strong_sell, total_analysts)
                       VALUES %s
                       ON CONFLICT (security_id, period)
                       DO UPDATE SET strong_buy = EXCLUDED.strong_buy,
                                     buy = EXCLUDED.buy, hold = EXCLUDED.hold,
                                     sell = EXCLUDED.sell, strong_sell = EXCLUDED.strong_sell,
                                     total_analysts = EXCLUDED.total_analysts,
                                     collected_at = now()""",
                    [(r["security_id"], r["period"], r["strong_buy"], r["buy"],
                      r["hold"], r["sell"], r["strong_sell"], r["total_analysts"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "Analyst actions: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(AnalystActionsCollector)
