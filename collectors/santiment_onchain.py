"""
Santiment On-Chain Analytics — deep on-chain metrics via Santiment GraphQL API.

Collector ID: 30 (Santiment On-Chain Analytics)
Table:        raw_santiment_metrics

Tracks daily active addresses, exchange inflow/outflow, network growth,
whale transaction counts, social volume, and developer activity for BTC/ETH.
These metrics provide deeper on-chain intelligence than basic block explorers.

Data sources:
  - Santiment GraphQL API (requires API key)
    - https://api.santiment.net/graphql
"""

import sys
import os
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

log = logging.getLogger("santiment_onchain")

# Map our ticker symbols to Santiment slugs
TICKER_TO_SLUG = {
    "BTC-USD": "bitcoin",
    "BTC":     "bitcoin",
    "ETH-USD": "ethereum",
    "ETH":     "ethereum",
}

# Metrics to fetch for each coin
METRICS = [
    "daily_active_addresses",
    "exchange_inflow",
    "exchange_outflow",
    "network_growth",
    "whale_transaction_count",
    "social_volume_total",
    "dev_activity",
]

GRAPHQL_URL = "https://api.santiment.net/graphql"


class SantimentOnchainCollector(BaseCollector):

    COLLECTOR_ID = 30
    COLLECTOR_NAME = "Santiment On-Chain Analytics"
    COLLECTOR_TYPE = "blockchain"
    SECURITY_TYPE_FILTER = "crypto"

    def setup(self):
        if not config.SANTIMENT_API_KEY:
            raise RuntimeError("SANTIMENT_API_KEY not set — cannot run Santiment collector")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Apikey {config.SANTIMENT_API_KEY}"
        self._session.headers["Content-Type"] = "application/json"
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_santiment_metrics (
                        metric_id       SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        metric_name     VARCHAR(50) NOT NULL,
                        observation_date DATE NOT NULL,
                        value           NUMERIC(20,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, metric_name, observation_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rsm_security_metric
                        ON raw_santiment_metrics (security_id, metric_name, observation_date DESC);
                """)

    def _graphql_query(self, query):
        """Execute a GraphQL query against Santiment API with retries."""
        for attempt in range(config.HTTP_RETRIES):
            try:
                resp = self._session.post(
                    GRAPHQL_URL,
                    json={"query": query},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 429:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("Rate limited, waiting %.1fs...", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                result = resp.json()
                if "errors" in result:
                    self.log.warning("GraphQL errors: %s", result["errors"])
                    return None
                return result.get("data")
            except requests.RequestException as e:
                if attempt < config.HTTP_RETRIES - 1:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("Request error (attempt %d): %s — retrying in %.1fs",
                                     attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    self.log.error("Request failed after %d attempts: %s", config.HTTP_RETRIES, e)
                    raise
        return None

    def fetch(self, securities):
        rows = []
        today = datetime.now(timezone.utc).date()
        from_date = (today - timedelta(days=7)).isoformat()
        to_date = today.isoformat()

        for sec in securities:
            ticker = sec["ticker"]
            slug = TICKER_TO_SLUG.get(ticker)
            if not slug:
                self.log.debug("No Santiment mapping for %s, skipping", ticker)
                self.stats["skipped"] += 1
                continue

            self.log.info("Fetching Santiment metrics for %s (%s)...", ticker, slug)

            for metric in METRICS:
                try:
                    query = """
                    {
                        getMetric(metric: "%s") {
                            timeseriesData(
                                slug: "%s"
                                from: "%s"
                                to: "%s"
                                interval: "1d"
                            ) {
                                datetime
                                value
                            }
                        }
                    }
                    """ % (metric, slug, from_date, to_date)

                    data = self._graphql_query(query)
                    if not data or "getMetric" not in data:
                        self.log.warning("  No data for %s/%s", slug, metric)
                        continue

                    timeseries = data["getMetric"].get("timeseriesData", [])
                    for point in timeseries:
                        dt_str = point.get("datetime", "")
                        value = point.get("value")
                        if value is None:
                            continue

                        # Parse datetime to date
                        try:
                            obs_date = datetime.fromisoformat(
                                dt_str.replace("Z", "+00:00")
                            ).date()
                        except (ValueError, AttributeError):
                            continue

                        rows.append({
                            "security_id":    sec["security_id"],
                            "metric_name":    metric,
                            "observation_date": obs_date,
                            "value":          value,
                        })

                    if timeseries:
                        latest = timeseries[-1]
                        self.log.info("  %s/%s: %d points, latest=%.2f",
                                      slug, metric, len(timeseries),
                                      float(latest.get("value", 0)))
                    self.stats["fetched"] += len(timeseries)

                    # Be polite — Santiment rate limits are strict
                    time.sleep(0.3)

                except Exception as e:
                    self.log.warning("  Error fetching %s/%s: %s", slug, metric, e)
                    self.stats["errors"] += 1

        return rows

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d Santiment metric records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_santiment_metrics
                           (security_id, metric_name, observation_date, value)
                       VALUES %s
                       ON CONFLICT (security_id, metric_name, observation_date)
                       DO UPDATE SET value        = EXCLUDED.value,
                                     last_updated = now()""",
                    [(r["security_id"], r["metric_name"],
                      r["observation_date"], r["value"])
                     for r in rows],
                    template="(%s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        if hasattr(self, "_session"):
            self._session.close()
        self.log.info("Santiment: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


# ── Signal extraction ────────────────────────────────────────────────────
# Called by blockchain_signals.py (or standalone) to derive blockchain_anomaly
# signals from Santiment on-chain metrics.

def run_signals():
    """
    Derive blockchain_anomaly signals from raw_santiment_metrics data.

    Triggers:
      - exchange_inflow spike (>2x 7d avg) → bearish selling pressure
      - whale_transaction_count spike (>2x 7d avg) → whale activity alert
      - daily_active_addresses drop (>30% below 7d avg) → bearish network health
    """
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # For each metric we care about, get today's value vs 7d average
            for metric, threshold_mult, direction, desc_template in [
                ("exchange_inflow", 2.0, "bearish",
                 "Santiment exchange inflow spike {ratio:.1f}x above 7d avg ({today_val:,.0f} vs {avg_val:,.0f})"),
                ("whale_transaction_count", 2.0, "neutral",
                 "Santiment whale tx count spike {ratio:.1f}x above 7d avg ({today_val:,.0f} vs {avg_val:,.0f})"),
                ("daily_active_addresses", None, "bearish",
                 "Santiment active addresses dropped {pct:.1f}% below 7d avg ({today_val:,.0f} vs {avg_val:,.0f})"),
            ]:
                try:
                    cur.execute("""
                        SELECT security_id,
                               (SELECT value FROM raw_santiment_metrics m2
                                WHERE m2.security_id = m1.security_id
                                  AND m2.metric_name = %s
                                  AND m2.observation_date = %s
                                LIMIT 1) AS today_val,
                               AVG(value) AS avg_7d
                        FROM raw_santiment_metrics m1
                        WHERE metric_name = %s
                          AND observation_date >= %s
                          AND observation_date < %s
                        GROUP BY security_id
                    """, (metric, today, metric, week_ago, today))
                    rows = cur.fetchall()
                except Exception:
                    continue

                for sid, today_val, avg_7d in rows:
                    if today_val is None or avg_7d is None or float(avg_7d) == 0:
                        continue
                    today_val = float(today_val)
                    avg_val = float(avg_7d)

                    if metric == "daily_active_addresses":
                        # Drop detection: today < 70% of 7d average
                        if today_val < avg_val * 0.70:
                            pct_drop = (1 - today_val / avg_val) * 100
                            contribution = min(pct_drop / 100, 0.4)
                            signals.append({
                                "security_id": sid,
                                "signal_type": "blockchain_anomaly",
                                "contribution": round(contribution, 4),
                                "confidence": 0.65,
                                "direction": direction,
                                "magnitude": "strong" if pct_drop > 40 else "moderate",
                                "raw_value": round(-pct_drop, 2),
                                "description": desc_template.format(
                                    pct=pct_drop, today_val=today_val, avg_val=avg_val
                                )[:300],
                                "detected_at": now,
                            })
                    else:
                        # Spike detection: today > threshold * 7d average
                        ratio = today_val / avg_val
                        if ratio > threshold_mult:
                            contribution = min(ratio / 5, 0.4)
                            signals.append({
                                "security_id": sid,
                                "signal_type": "blockchain_anomaly",
                                "contribution": round(contribution, 4),
                                "confidence": 0.65,
                                "direction": direction,
                                "magnitude": "strong" if ratio > 3.0 else "moderate",
                                "raw_value": round(ratio, 2),
                                "description": desc_template.format(
                                    ratio=ratio, today_val=today_val, avg_val=avg_val
                                )[:300],
                                "detected_at": now,
                            })

    if signals:
        from psycopg2.extras import execute_values
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO signals
                           (security_id, signal_type, contribution, confidence,
                            direction, magnitude, raw_value, description, detected_at)
                       VALUES %s
                       ON CONFLICT (security_id, signal_type, detected_at)
                       DO UPDATE SET contribution = GREATEST(EXCLUDED.contribution, signals.contribution),
                                     confidence = GREATEST(EXCLUDED.confidence, signals.confidence)""",
                    [(s["security_id"], s["signal_type"], s["contribution"],
                      s["confidence"], s["direction"], s["magnitude"],
                      s["raw_value"], s["description"], s["detected_at"])
                     for s in signals],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                )

    log.info("Santiment signals: %d signals fired", len(signals))
    return len(signals)


if __name__ == "__main__":
    run_collector(SantimentOnchainCollector)
