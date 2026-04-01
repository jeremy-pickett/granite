"""
LunarCrush Social Sentiment — crypto social media metrics via LunarCrush V4.

Collector ID: 29 (LunarCrush Social Sentiment)
Table:        raw_crypto_social

Tracks social volume, galaxy score, sentiment, and alt rank for BTC/ETH.
Social sentiment spikes or galaxy score drops are leading indicators of
volatility and price movement in crypto markets.

Data sources:
  - LunarCrush V4 API (requires API key)
    - GET /coins/list — coin directory
    - GET /coins/{coin}/v1 — per-coin social metrics
"""

import sys
import os
import time
import logging
import requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

log = logging.getLogger("lunarcrush_social")

# Map our ticker symbols to LunarCrush coin identifiers
TICKER_TO_COIN = {
    "BTC-USD": "bitcoin",
    "BTC":     "bitcoin",
    "ETH-USD": "ethereum",
    "ETH":     "ethereum",
}

BASE_URL = "https://lunarcrush.com/api4/public"


class LunarCrushSocialCollector(BaseCollector):

    COLLECTOR_ID = 29
    COLLECTOR_NAME = "LunarCrush Social Sentiment"
    COLLECTOR_TYPE = "social"
    SECURITY_TYPE_FILTER = "crypto"

    def setup(self):
        if not config.LUNARCRUSH_API_KEY:
            raise RuntimeError("LUNARCRUSH_API_KEY not set — cannot run LunarCrush collector")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {config.LUNARCRUSH_API_KEY}"
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_crypto_social (
                        social_id       SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        source          VARCHAR(30) NOT NULL,
                        social_volume   INT,
                        social_score    NUMERIC(8,2),
                        sentiment_score NUMERIC(5,3),
                        galaxy_score    NUMERIC(8,2),
                        volatility_score NUMERIC(5,3),
                        alt_rank        INT,
                        snapshot_date   DATE NOT NULL,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, source, snapshot_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rcs_security_date
                        ON raw_crypto_social (security_id, snapshot_date DESC);
                """)

    def _api_get(self, path, params=None):
        """Make a rate-limited GET request to LunarCrush V4."""
        url = f"{BASE_URL}/{path}"
        for attempt in range(config.HTTP_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
                if resp.status_code == 429:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("Rate limited, waiting %.1fs...", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
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

        for sec in securities:
            ticker = sec["ticker"]
            coin = TICKER_TO_COIN.get(ticker)
            if not coin:
                self.log.debug("No LunarCrush mapping for %s, skipping", ticker)
                self.stats["skipped"] += 1
                continue

            self.log.info("Fetching LunarCrush data for %s (%s)...", ticker, coin)
            try:
                data = self._api_get(f"coins/{coin}/v1")
                if not data or "data" not in data:
                    self.log.warning("No data returned for %s", coin)
                    self.stats["skipped"] += 1
                    continue

                coin_data = data["data"]
                rows.append({
                    "security_id":    sec["security_id"],
                    "source":         "lunarcrush",
                    "social_volume":  coin_data.get("social_volume"),
                    "social_score":   coin_data.get("social_score"),
                    "sentiment_score": coin_data.get("sentiment"),
                    "galaxy_score":   coin_data.get("galaxy_score"),
                    "volatility_score": coin_data.get("volatility"),
                    "alt_rank":       coin_data.get("alt_rank"),
                    "snapshot_date":  today,
                })
                self.stats["fetched"] += 1
                self.log.info("  %s: galaxy=%.1f  sentiment=%.3f  social_vol=%s  alt_rank=%s",
                              coin,
                              float(coin_data.get("galaxy_score") or 0),
                              float(coin_data.get("sentiment") or 0),
                              coin_data.get("social_volume"),
                              coin_data.get("alt_rank"))

                # Be polite to the API
                time.sleep(0.5)

            except Exception as e:
                self.log.warning("Error fetching %s: %s", coin, e)
                self.stats["errors"] += 1

        return rows

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d crypto social records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_crypto_social
                           (security_id, source, social_volume, social_score,
                            sentiment_score, galaxy_score, volatility_score,
                            alt_rank, snapshot_date)
                       VALUES %s
                       ON CONFLICT (security_id, source, snapshot_date)
                       DO UPDATE SET social_volume    = EXCLUDED.social_volume,
                                     social_score     = EXCLUDED.social_score,
                                     sentiment_score  = EXCLUDED.sentiment_score,
                                     galaxy_score     = EXCLUDED.galaxy_score,
                                     volatility_score = EXCLUDED.volatility_score,
                                     alt_rank         = EXCLUDED.alt_rank,
                                     last_updated     = now()""",
                    [(r["security_id"], r["source"], r["social_volume"],
                      r["social_score"], r["sentiment_score"], r["galaxy_score"],
                      r["volatility_score"], r["alt_rank"], r["snapshot_date"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        if hasattr(self, "_session"):
            self._session.close()
        self.log.info("LunarCrush: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


# ── Signal extraction ────────────────────────────────────────────────────
# Called by blockchain_signals.py (or standalone) to derive blockchain_anomaly
# signals from social sentiment data.

def run_signals():
    """
    Derive blockchain_anomaly signals from raw_crypto_social data.

    Triggers:
      - galaxy_score drops >20% day-over-day → bearish sentiment collapse
      - social_volume spikes >3x day-over-day → volatility incoming
    """
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Get today vs yesterday for each security
            cur.execute("""
                SELECT t.security_id,
                       t.galaxy_score   AS today_galaxy,
                       y.galaxy_score   AS yest_galaxy,
                       t.social_volume  AS today_vol,
                       y.social_volume  AS yest_vol,
                       t.sentiment_score AS today_sentiment
                FROM raw_crypto_social t
                LEFT JOIN raw_crypto_social y
                    ON y.security_id = t.security_id
                   AND y.source = t.source
                   AND y.snapshot_date = %s
                WHERE t.snapshot_date = %s
                  AND t.source = 'lunarcrush'
            """, (yesterday, today))
            rows = cur.fetchall()

    for sid, today_galaxy, yest_galaxy, today_vol, yest_vol, today_sentiment in rows:
        today_galaxy = float(today_galaxy or 0)
        yest_galaxy = float(yest_galaxy or 0)
        today_vol = int(today_vol or 0)
        yest_vol = int(yest_vol or 0)
        today_sentiment = float(today_sentiment or 0)

        # Galaxy score drop >20% day-over-day
        if yest_galaxy > 0 and today_galaxy > 0:
            pct_change = (today_galaxy - yest_galaxy) / yest_galaxy
            if pct_change < -0.20:
                contribution = min(abs(pct_change), 0.5)
                signals.append({
                    "security_id": sid,
                    "signal_type": "blockchain_anomaly",
                    "contribution": round(contribution, 4),
                    "confidence": 0.65,
                    "direction": "bearish",
                    "magnitude": "strong" if pct_change < -0.35 else "moderate",
                    "raw_value": round(pct_change, 4),
                    "description": (f"LunarCrush galaxy score dropped {pct_change*100:.1f}% "
                                    f"({yest_galaxy:.0f} → {today_galaxy:.0f})"),
                    "detected_at": now,
                })

        # Social volume spike >3x day-over-day
        if yest_vol > 0 and today_vol > yest_vol * 3:
            spike_ratio = today_vol / yest_vol
            contribution = min(spike_ratio / 10, 0.4)
            signals.append({
                "security_id": sid,
                "signal_type": "blockchain_anomaly",
                "contribution": round(contribution, 4),
                "confidence": 0.60,
                "direction": "neutral",  # volume spike alone is directionally ambiguous
                "magnitude": "strong" if spike_ratio > 5 else "moderate",
                "raw_value": round(spike_ratio, 2),
                "description": (f"LunarCrush social volume spike {spike_ratio:.1f}x "
                                f"({yest_vol:,} → {today_vol:,})"),
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

    log.info("LunarCrush signals: %d signals fired", len(signals))
    return len(signals)


if __name__ == "__main__":
    run_collector(LunarCrushSocialCollector)
