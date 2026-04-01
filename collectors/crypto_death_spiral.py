"""
Crypto Death Spiral Detector — temporal progression of crypto collapse patterns.

Collector ID: 34 (Crypto Death Spiral Detector)
Table:        raw_crypto_death_spiral

Tracks the multi-phase collapse pattern for crypto projects: price collapse,
volume death, social abandonment, developer exodus, sustained selling pressure.
Each phase represents an escalating probability of irreversible failure.

Phase ladder:
  healthy      → score < 0.15
  warning      → score 0.15–0.29
  deteriorating → score 0.30–0.49
  critical     → score 0.50–0.69
  terminal     → score >= 0.70

Data sources:
  - raw_market_data (90-day price history, volume trends)
  - raw_crypto_social (LunarCrush galaxy score, social volume, sentiment)
  - raw_santiment_metrics (daily_active_addresses, exchange_inflow, dev_activity)
  - CoinGecko market_chart (historical prices/volumes for gap-filling)
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

log = logging.getLogger("crypto_death_spiral")

TICKER_TO_COINGECKO = {
    "BTC-USD": "bitcoin",
    "BTC":     "bitcoin",
    "ETH-USD": "ethereum",
    "ETH":     "ethereum",
}

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def classify_phase(drawdown_pct, volume_trend, social_trend, dev_active, exchange_inflow_trend):
    """
    Classify the death spiral phase based on multiple indicators.

    Returns (phase, score, indicators_list).
    """
    score = 0.0
    indicators = []

    # Price collapse
    if drawdown_pct > 80:
        score += 0.30
        indicators.append("price_collapse_80pct")
    elif drawdown_pct > 50:
        score += 0.20
        indicators.append("price_collapse_50pct")
    elif drawdown_pct > 30:
        score += 0.10
        indicators.append("price_decline_30pct")

    # Volume dying
    if volume_trend == "collapsing":
        score += 0.20
        indicators.append("volume_collapse")
    elif volume_trend == "declining":
        score += 0.10
        indicators.append("volume_declining")

    # Social abandonment
    if social_trend == "collapsed":
        score += 0.15
        indicators.append("social_abandoned")
    elif social_trend == "declining":
        score += 0.08
        indicators.append("social_declining")

    # Developer abandonment
    if not dev_active:
        score += 0.20
        indicators.append("dev_abandoned")

    # Sustained exchange inflows (selling pressure)
    if exchange_inflow_trend == "sustained":
        score += 0.15
        indicators.append("sustained_selling")

    # Classify phase
    if score >= 0.70:
        phase = "terminal"
    elif score >= 0.50:
        phase = "critical"
    elif score >= 0.30:
        phase = "deteriorating"
    elif score >= 0.15:
        phase = "warning"
    else:
        phase = "healthy"

    return phase, round(score, 3), indicators


class CryptoDeathSpiralCollector(BaseCollector):

    COLLECTOR_ID = 34
    COLLECTOR_NAME = "Crypto Death Spiral Detector"
    COLLECTOR_TYPE = "blockchain"
    SECURITY_TYPE_FILTER = "crypto"

    def setup(self):
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_crypto_death_spiral (
                        spiral_id           SERIAL PRIMARY KEY,
                        security_id         INT NOT NULL REFERENCES securities(security_id),
                        detection_date      DATE NOT NULL,
                        phase               VARCHAR(20) NOT NULL,
                        phase_score         NUMERIC(5,3) NOT NULL,
                        indicators_triggered TEXT,
                        price_from_peak_pct NUMERIC(8,4),
                        days_since_peak     INT,
                        volume_trend        VARCHAR(20),
                        social_trend        VARCHAR(20),
                        dev_activity_trend  VARCHAR(20),
                        collected_at        TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, detection_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rcds_security_date
                        ON raw_crypto_death_spiral (security_id, detection_date DESC);
                """)

    def _coingecko_get(self, path, params=None):
        """Rate-limited GET against CoinGecko free API."""
        url = f"{COINGECKO_BASE}/{path}"
        for attempt in range(config.HTTP_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
                if resp.status_code == 429:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("CoinGecko rate limited, waiting %.1fs...", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt < config.HTTP_RETRIES - 1:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("CoinGecko request error (attempt %d): %s — retrying in %.1fs",
                                     attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    self.log.error("CoinGecko request failed after %d attempts: %s",
                                   config.HTTP_RETRIES, e)
                    raise
        return None

    def _get_price_metrics(self, security_id, coin_id):
        """
        Get 90-day price metrics: drawdown from peak, days since peak, volume trend.
        Tries raw_market_data first, falls back to CoinGecko market_chart.
        """
        today = datetime.now(timezone.utc).date()
        ninety_ago = today - timedelta(days=90)

        # Try database first
        prices = []
        volumes = []
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT trade_date, close_price, volume
                        FROM raw_market_data
                        WHERE security_id = %s
                          AND trade_date >= %s
                        ORDER BY trade_date ASC
                    """, (security_id, ninety_ago))
                    for row in cur.fetchall():
                        if row[1] is not None:
                            prices.append((row[0], float(row[1])))
                        if row[2] is not None:
                            volumes.append((row[0], float(row[2])))
        except Exception:
            pass

        # Fall back to CoinGecko if not enough data
        if len(prices) < 7:
            self.log.info("  Insufficient DB price data (%d rows), using CoinGecko...", len(prices))
            try:
                data = self._coingecko_get(
                    f"coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": "90"},
                )
                if data:
                    cg_prices = data.get("prices", [])
                    cg_volumes = data.get("total_volumes", [])
                    prices = [
                        (datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc).date(), p[1])
                        for p in cg_prices if len(p) == 2
                    ]
                    volumes = [
                        (datetime.fromtimestamp(v[0] / 1000, tz=timezone.utc).date(), v[1])
                        for v in cg_volumes if len(v) == 2
                    ]
                    # Be polite to free API
                    time.sleep(2.5)
            except Exception as e:
                self.log.warning("  CoinGecko market_chart error: %s", e)

        if not prices:
            return None, None, None, "unknown"

        # Compute drawdown from 90-day peak
        peak_price = max(p[1] for p in prices)
        peak_date = max((p for p in prices), key=lambda x: x[1])[0]
        current_price = prices[-1][1]
        drawdown_pct = ((peak_price - current_price) / peak_price) * 100 if peak_price > 0 else 0
        days_since_peak = (today - peak_date).days

        # Volume trend: compare last 7d average vs 30d average
        volume_trend = "stable"
        if len(volumes) >= 30:
            vol_values = [v[1] for v in volumes]
            avg_7d = sum(vol_values[-7:]) / 7
            avg_30d = sum(vol_values[-30:]) / 30
            if avg_30d > 0:
                vol_ratio = avg_7d / avg_30d
                if vol_ratio < 0.3:
                    volume_trend = "collapsing"
                elif vol_ratio < 0.7:
                    volume_trend = "declining"
                elif vol_ratio > 1.5:
                    volume_trend = "increasing"

        return drawdown_pct, days_since_peak, current_price, volume_trend

    def _get_social_trend(self, security_id):
        """Get social trend from raw_crypto_social (LunarCrush)."""
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    today = datetime.now(timezone.utc).date()
                    thirty_ago = today - timedelta(days=30)
                    seven_ago = today - timedelta(days=7)

                    # Galaxy score: 7d avg vs 30d avg
                    cur.execute("""
                        SELECT
                            AVG(CASE WHEN snapshot_date >= %s THEN galaxy_score END) AS avg_7d,
                            AVG(galaxy_score) AS avg_30d,
                            AVG(CASE WHEN snapshot_date >= %s THEN social_volume END) AS vol_7d,
                            AVG(social_volume) AS vol_30d
                        FROM raw_crypto_social
                        WHERE security_id = %s
                          AND snapshot_date >= %s
                          AND source = 'lunarcrush'
                    """, (seven_ago, seven_ago, security_id, thirty_ago))
                    row = cur.fetchone()

                    if not row or row[1] is None:
                        return "unknown"

                    galaxy_7d = float(row[0] or 0)
                    galaxy_30d = float(row[1] or 0)
                    vol_7d = float(row[2] or 0)
                    vol_30d = float(row[3] or 0)

                    if galaxy_30d > 0:
                        galaxy_ratio = galaxy_7d / galaxy_30d
                        if galaxy_ratio < 0.3:
                            return "collapsed"
                        elif galaxy_ratio < 0.7:
                            return "declining"
                    if vol_30d > 0:
                        vol_ratio = vol_7d / vol_30d
                        if vol_ratio < 0.3:
                            return "collapsed"
                        elif vol_ratio < 0.7:
                            return "declining"

                    return "stable"
        except Exception:
            return "unknown"

    def _get_dev_active(self, security_id):
        """Check if there has been any dev activity in the last 90 days."""
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    ninety_ago = datetime.now(timezone.utc).date() - timedelta(days=90)
                    cur.execute("""
                        SELECT COALESCE(SUM(value), 0) AS total_dev
                        FROM raw_santiment_metrics
                        WHERE security_id = %s
                          AND metric_name = 'dev_activity'
                          AND observation_date >= %s
                    """, (security_id, ninety_ago))
                    row = cur.fetchone()
                    total = float(row[0]) if row else 0
                    return total > 0
        except Exception:
            return True  # Assume active if we can't determine

    def _get_exchange_inflow_trend(self, security_id):
        """Check if exchange inflows have been sustained (selling pressure)."""
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    today = datetime.now(timezone.utc).date()
                    seven_ago = today - timedelta(days=7)
                    thirty_ago = today - timedelta(days=30)

                    cur.execute("""
                        SELECT
                            AVG(CASE WHEN observation_date >= %s THEN value END) AS avg_7d,
                            AVG(value) AS avg_30d
                        FROM raw_santiment_metrics
                        WHERE security_id = %s
                          AND metric_name = 'exchange_inflow'
                          AND observation_date >= %s
                    """, (seven_ago, security_id, thirty_ago))
                    row = cur.fetchone()

                    if not row or row[1] is None:
                        return "unknown"

                    avg_7d = float(row[0] or 0)
                    avg_30d = float(row[1] or 0)

                    if avg_30d > 0 and avg_7d / avg_30d > 1.5:
                        return "sustained"
                    return "normal"
        except Exception:
            return "unknown"

    def fetch(self, securities):
        rows = []
        today = datetime.now(timezone.utc).date()

        for sec in securities:
            ticker = sec["ticker"]
            coin_id = TICKER_TO_COINGECKO.get(ticker)
            if not coin_id:
                self.log.debug("No CoinGecko mapping for %s, skipping", ticker)
                self.stats["skipped"] += 1
                continue

            self.log.info("Running death spiral analysis for %s (%s)...", ticker, coin_id)

            try:
                # Step 1: Price metrics
                drawdown_pct, days_since_peak, current_price, volume_trend = \
                    self._get_price_metrics(sec["security_id"], coin_id)

                if drawdown_pct is None:
                    self.log.warning("  No price data for %s, skipping", ticker)
                    self.stats["skipped"] += 1
                    continue

                # Step 2: Social trend
                social_trend = self._get_social_trend(sec["security_id"])

                # Step 3: Dev activity
                dev_active = self._get_dev_active(sec["security_id"])

                # Step 4: Exchange inflow trend
                exchange_inflow_trend = self._get_exchange_inflow_trend(sec["security_id"])

                # Classify phase
                phase, phase_score, indicators = classify_phase(
                    drawdown_pct, volume_trend, social_trend, dev_active, exchange_inflow_trend
                )

                dev_trend = "active" if dev_active else "abandoned"

                row = {
                    "security_id":        sec["security_id"],
                    "detection_date":     today,
                    "phase":              phase,
                    "phase_score":        phase_score,
                    "indicators_triggered": ",".join(indicators) if indicators else None,
                    "price_from_peak_pct": round(drawdown_pct, 4),
                    "days_since_peak":    days_since_peak,
                    "volume_trend":       volume_trend,
                    "social_trend":       social_trend,
                    "dev_activity_trend": dev_trend,
                }
                rows.append(row)
                self.stats["fetched"] += 1

                self.log.info("  %s: phase=%s  score=%.3f  drawdown=%.1f%%  days_since_peak=%d  "
                              "vol=%s  social=%s  dev=%s  indicators=%s",
                              coin_id, phase, phase_score, drawdown_pct,
                              days_since_peak or 0, volume_trend, social_trend,
                              dev_trend, indicators)

            except Exception as e:
                self.log.warning("Error analyzing %s: %s", ticker, e)
                self.stats["errors"] += 1

        return rows

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d death spiral records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_crypto_death_spiral
                           (security_id, detection_date, phase, phase_score,
                            indicators_triggered, price_from_peak_pct,
                            days_since_peak, volume_trend, social_trend,
                            dev_activity_trend)
                       VALUES %s
                       ON CONFLICT (security_id, detection_date)
                       DO UPDATE SET phase                = EXCLUDED.phase,
                                     phase_score          = EXCLUDED.phase_score,
                                     indicators_triggered = EXCLUDED.indicators_triggered,
                                     price_from_peak_pct  = EXCLUDED.price_from_peak_pct,
                                     days_since_peak      = EXCLUDED.days_since_peak,
                                     volume_trend         = EXCLUDED.volume_trend,
                                     social_trend         = EXCLUDED.social_trend,
                                     dev_activity_trend   = EXCLUDED.dev_activity_trend""",
                    [(r["security_id"], r["detection_date"], r["phase"],
                      r["phase_score"], r["indicators_triggered"],
                      r["price_from_peak_pct"], r["days_since_peak"],
                      r["volume_trend"], r["social_trend"], r["dev_activity_trend"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        if hasattr(self, "_session"):
            self._session.close()
        self.log.info("Death spiral: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(CryptoDeathSpiralCollector)
