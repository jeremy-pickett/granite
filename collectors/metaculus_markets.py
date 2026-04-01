"""
Metaculus Prediction Market Collector — community forecasting data.

Collector ID: 24 (Metaculus Prediction Markets)
Table:        raw_prediction_markets (shared with Polymarket/Kalshi)

Metaculus is a forecasting platform where calibrated predictors assign
probabilities to real-world questions. When hundreds of forecasters agree
that a recession is likely or a rate cut is coming, that signal has value.

Data source:
  - Metaculus API v2 (requires API token)
  - Endpoint: /api2/questions/?status=open&type=forecast
"""

import sys
import os
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

METACULUS_API = "https://www.metaculus.com/api2"

# Map question keywords to our security tickers
TOPIC_TICKER_MAP = {
    # Crypto
    "bitcoin": ["BTC-USD"],
    "btc": ["BTC-USD"],
    "ethereum": ["ETH-USD"],
    "eth": ["ETH-USD"],
    # Indices
    "s&p": ["SPY", "VOO"],
    "s&p 500": ["SPY", "VOO"],
    "sp500": ["SPY", "VOO"],
    "nasdaq": ["QQQ", "TQQQ"],
    "dow jones": ["DIA"],
    # Macro / rates
    "fed": ["TLT", "SHY"],
    "federal reserve": ["TLT", "SHY"],
    "interest rate": ["TLT", "SHY"],
    "rate cut": ["TLT", "SHY"],
    "rate hike": ["TLT", "SHY"],
    "inflation": ["TIP"],
    "cpi": ["TIP", "SPY"],
    "recession": ["SPY"],
    "gdp": ["SPY"],
    "unemployment": ["SPY"],
    "treasury": ["TLT", "SHY"],
    # Commodities
    "gold": ["GLD", "GOLD"],
    "crude oil": ["USO", "XLE"],
    "oil price": ["USO", "XLE"],
    "natural gas": ["UNG"],
    # Equities
    "tesla": ["TSLA"],
    "apple": ["AAPL"],
    "nvidia": ["NVDA"],
    "google": ["GOOGL"],
    "amazon": ["AMZN"],
    "meta": ["META"],
    "microsoft": ["MSFT"],
    "bankruptcy": [],
}


def match_tickers(text: str, sec_lookup: dict) -> list[int]:
    """Match question text to our security IDs."""
    text_lower = text.lower()
    matched = set()
    for keyword, tickers in TOPIC_TICKER_MAP.items():
        if keyword in text_lower:
            for t in tickers:
                if t in sec_lookup:
                    matched.add(sec_lookup[t])
    return list(matched)


class MetaculusMarketCollector(BaseCollector):

    COLLECTOR_ID = 24
    COLLECTOR_NAME = "Metaculus Prediction Markets"
    COLLECTOR_TYPE = "analytics"

    def setup(self):
        if not config.METACULUS_API_KEY:
            raise RuntimeError("METACULUS_API_KEY not set")
        self._ensure_table()

    def _ensure_table(self):
        """Ensure raw_prediction_markets exists (same table as Polymarket/Kalshi)."""
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_prediction_markets (
                        market_id       SERIAL PRIMARY KEY,
                        security_id     INT REFERENCES securities(security_id),
                        source          VARCHAR(20) NOT NULL,
                        event_title     TEXT NOT NULL,
                        market_question TEXT,
                        market_ticker   TEXT,
                        probability     NUMERIC(6,4),
                        volume          NUMERIC(16,2),
                        event_url       TEXT,
                        fetched_date    DATE NOT NULL,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(source, market_ticker, fetched_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpm_security
                        ON raw_prediction_markets (security_id, fetched_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rpm_date
                        ON raw_prediction_markets (fetched_date DESC);
                """)

    def fetch(self, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        today = datetime.now(timezone.utc).date()
        rows = []

        headers = {
            "Authorization": f"Token {config.METACULUS_API_KEY}",
            "Accept": "application/json",
        }

        self.log.info("Fetching Metaculus open forecast questions...")

        try:
            resp = requests.get(
                f"{METACULUS_API}/questions/",
                params={
                    "limit": 50,
                    "status": "open",
                    "type": "forecast",
                    "order_by": "-activity",
                },
                headers=headers,
                timeout=config.HTTP_TIMEOUT,
            )

            if resp.status_code == 401:
                self.log.warning("Metaculus 401 — API token may be invalid")
                return rows
            if resp.status_code != 200:
                self.log.warning("Metaculus returned %d", resp.status_code)
                return rows

            data = resp.json()
            questions = data.get("results", data) if isinstance(data, dict) else data
            if not isinstance(questions, list):
                self.log.warning("Unexpected response format from Metaculus")
                return rows

            for q in questions:
                title = q.get("title", "")
                sids = match_tickers(title, sec_lookup)
                if not sids:
                    continue

                # Extract community prediction median
                prob = None
                cp = q.get("community_prediction")
                if isinstance(cp, dict):
                    prob = cp.get("full", {}).get("q2") or cp.get("q2")
                elif isinstance(cp, (int, float)):
                    prob = float(cp)

                # Number of forecasters as volume proxy
                forecasters = q.get("number_of_forecasters") or q.get("forecasts_count") or 0

                question_id = str(q.get("id", ""))
                question_url = q.get("url") or f"https://www.metaculus.com/questions/{question_id}/"

                for sid in sids:
                    rows.append({
                        "security_id": sid,
                        "source": "metaculus",
                        "event_title": title[:200],
                        "market_question": title[:500],
                        "market_ticker": question_id[:100],
                        "probability": prob,
                        "volume": forecasters,
                        "event_url": question_url,
                        "fetched_date": today,
                    })

            self.stats["fetched"] += len(rows)
            self.log.info("Metaculus: %d relevant questions matched from %d total",
                          len(rows), len(questions))

        except requests.RequestException as e:
            self.log.warning("Metaculus error: %s", e)
            self.stats["errors"] += 1

        return rows

    def transform(self, raw_data, securities):
        """Deduplicate by (source, market_ticker, fetched_date)."""
        seen = set()
        rows = []
        for r in raw_data:
            key = (r["source"], r["market_ticker"], str(r["fetched_date"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
        return rows

    def store(self, rows):
        self.log.info("Writing %d Metaculus prediction market records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_prediction_markets
                           (security_id, source, event_title, market_question,
                            market_ticker, probability, volume, event_url, fetched_date)
                       VALUES %s
                       ON CONFLICT (source, market_ticker, fetched_date)
                       DO UPDATE SET probability = EXCLUDED.probability,
                                     volume = EXCLUDED.volume,
                                     last_updated = now()""",
                    [(r["security_id"], r["source"], r["event_title"],
                      r["market_question"], r["market_ticker"], r["probability"],
                      r["volume"], r["event_url"], r["fetched_date"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Metaculus markets: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(MetaculusMarketCollector)
