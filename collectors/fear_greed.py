"""
Fear & Greed Index Collector — crypto market sentiment from Alternative.me.

Collector ID: 39 (Fear & Greed Index)
Table:        raw_fear_greed

Source: https://api.alternative.me/fng/?limit=30&format=json (free, no auth)

Returns a daily 0-100 index for crypto market sentiment.
Extreme values trigger contrarian blockchain_anomaly signals:
  - Extreme Fear (<20): bullish (buy when others are fearful)
  - Extreme Greed (>80): bearish (sell when others are greedy)
"""

import sys
import os
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

FNG_URL = "https://api.alternative.me/fng/?limit=30&format=json"


class FearGreedCollector(BaseCollector):

    COLLECTOR_ID = 39
    COLLECTOR_NAME = "Fear & Greed Index"
    COLLECTOR_TYPE = "analytics"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_fear_greed (
                        fg_id              SERIAL PRIMARY KEY,
                        observation_date   DATE NOT NULL,
                        value              INT NOT NULL,
                        classification     VARCHAR(20) NOT NULL,
                        collected_at       TIMESTAMP DEFAULT now(),
                        UNIQUE(observation_date)
                    );
                """)

    def fetch(self, securities):
        self.log.info("Fetching Fear & Greed Index (last 30 days)...")
        try:
            resp = requests.get(FNG_URL, timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            self.stats["fetched"] = len(data)
            self.log.info("  Got %d data points", len(data))
            return data
        except requests.RequestException as e:
            self.log.error("Alternative.me API error: %s", e)
            self.stats["errors"] += 1
            return []

    def transform(self, raw_data, securities):
        rows = []
        for entry in raw_data:
            try:
                ts = int(entry.get("timestamp", 0))
                obs_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                value = int(entry.get("value", 50))
                classification = entry.get("value_classification", "Neutral")

                # Find BTC-USD security for signal mapping
                btc_sec = next(
                    (s for s in securities
                     if s["ticker"] == "BTC-USD" or s["ticker"] == "BTC"),
                    None,
                )
                sid = btc_sec["security_id"] if btc_sec else None

                rows.append({
                    "security_id": sid,
                    "observation_date": obs_date,
                    "value": value,
                    "classification": classification,
                })
            except (ValueError, KeyError, TypeError) as e:
                self.log.debug("Skipping entry: %s", e)
                self.stats["skipped"] += 1
        return rows

    def store(self, rows):
        self.log.info("Writing %d fear/greed records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_fear_greed
                           (observation_date, value, classification)
                       VALUES %s
                       ON CONFLICT (observation_date)
                       DO UPDATE SET value = EXCLUDED.value,
                                     classification = EXCLUDED.classification""",
                    [(r["observation_date"], r["value"], r["classification"])
                     for r in rows],
                    template="(%s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Fear & Greed: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


# ── Signal extraction ─────────────────────────────────────────────────

def run_signals():
    """Fire blockchain_anomaly signals on extreme fear/greed readings."""
    import logging
    logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
    log = logging.getLogger("fear_greed_signals")

    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Get today's or most recent reading
            try:
                cur.execute("""
                    SELECT fg.observation_date, fg.value, fg.classification
                    FROM raw_fear_greed fg
                    ORDER BY fg.observation_date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
            except Exception as e:
                log.warning("Query error: %s", e)
                row = None

            if not row:
                log.info("No fear/greed data found")
                return 0

            obs_date, value, classification = row

            # Look up BTC-USD security_id
            try:
                cur.execute("""
                    SELECT security_id FROM securities
                    WHERE ticker IN ('BTC-USD', 'BTC')
                    LIMIT 1
                """)
                sec_row = cur.fetchone()
            except Exception:
                sec_row = None

            if not sec_row:
                log.warning("No BTC security found")
                return 0

            btc_sid = sec_row[0]

            # Extreme Fear: value < 20 → contrarian bullish
            if value < 20:
                contribution = round((20 - value) / 20.0, 4)
                signals.append({
                    "security_id": btc_sid,
                    "signal_type": "blockchain_anomaly",
                    "contribution": contribution,
                    "confidence": 0.65,
                    "direction": "bullish",
                    "magnitude": "extreme" if value < 10 else "strong",
                    "raw_value": float(value),
                    "description": f"Crypto Fear & Greed Index: {value} ({classification}) — extreme fear, contrarian buy signal",
                    "detected_at": now,
                })

            # Extreme Greed: value > 80 → contrarian bearish
            elif value > 80:
                contribution = round((value - 80) / 20.0, 4)
                signals.append({
                    "security_id": btc_sid,
                    "signal_type": "blockchain_anomaly",
                    "contribution": contribution,
                    "confidence": 0.65,
                    "direction": "bearish",
                    "magnitude": "extreme" if value > 90 else "strong",
                    "raw_value": float(value),
                    "description": f"Crypto Fear & Greed Index: {value} ({classification}) — extreme greed, contrarian sell signal",
                    "detected_at": now,
                })

    if signals:
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

    log.info("Fear & Greed signals: %d fired (value=%s)", len(signals), value)
    return len(signals)


if __name__ == "__main__":
    run_collector(FearGreedCollector)
