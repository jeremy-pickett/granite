"""
Tiingo Market Data Collector — daily OHLCV via Tiingo REST API.

Collector ID: 27
Table:        raw_market_data (supplements yfinance data)
API:          https://api.tiingo.com/tiingo/daily/{ticker}/prices
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
import requests
from datetime import datetime, timedelta
from psycopg2.extras import execute_values

from base import BaseCollector, run_collector
import config
import db


class TiingoDataCollector(BaseCollector):

    # ── identity (must match `collectors` table) ──────────────────────
    COLLECTOR_ID = 27
    COLLECTOR_NAME = "Tiingo Market Data"
    COLLECTOR_TYPE = "market_data"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        if not config.TIINGO_API_KEY:
            raise RuntimeError("TIINGO_API_KEY is not set — cannot proceed")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Token {config.TIINGO_API_KEY}",
        })

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Fetch 5-day OHLCV per equity ticker from Tiingo daily endpoint."""
        start_date = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
        raw_results = {}

        equities = [s for s in securities if s["security_type"] == "equity"]
        self.log.info("Fetching %d equity tickers from Tiingo...", len(equities))

        for i, sec in enumerate(equities):
            ticker = sec["ticker"]
            url = (
                f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
                f"?startDate={start_date}&token={config.TIINGO_API_KEY}"
            )

            for attempt in range(1, config.HTTP_RETRIES + 1):
                try:
                    resp = self.session.get(url, timeout=config.HTTP_TIMEOUT)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data:
                            raw_results[ticker] = {
                                "security_id": sec["security_id"],
                                "prices": data,
                            }
                            self.stats["fetched"] += 1
                        else:
                            self.stats["skipped"] += 1
                        break
                    elif resp.status_code == 404:
                        self.log.debug("Ticker %s not found on Tiingo", ticker)
                        self.stats["skipped"] += 1
                        break
                    elif resp.status_code == 429:
                        wait = config.HTTP_BACKOFF ** attempt
                        self.log.warning("Rate limited, sleeping %.1fs...", wait)
                        time.sleep(wait)
                    else:
                        self.log.debug(
                            "Tiingo %s returned %d on attempt %d",
                            ticker, resp.status_code, attempt,
                        )
                        if attempt == config.HTTP_RETRIES:
                            self.stats["errors"] += 1
                        else:
                            time.sleep(config.HTTP_BACKOFF ** attempt)
                except requests.RequestException as e:
                    self.log.debug("Request error for %s (attempt %d): %s", ticker, attempt, e)
                    if attempt == config.HTTP_RETRIES:
                        self.stats["errors"] += 1
                    else:
                        time.sleep(config.HTTP_BACKOFF ** attempt)

            # Rate limit: 500 req/hour ≈ 1 every 7.2s; 0.5s is conservative for bursts
            time.sleep(0.5)

            if (i + 1) % 50 == 0:
                self.log.info("  Progress: %d/%d tickers fetched", i + 1, len(equities))

        return raw_results

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        """Normalize Tiingo daily price JSON into raw_market_data rows."""
        rows = []
        for ticker, payload in raw_data.items():
            sid = payload["security_id"]
            for day in payload["prices"]:
                try:
                    trade_date = datetime.strptime(
                        day["date"][:10], "%Y-%m-%d"
                    ).date()

                    close = float(day.get("adjClose") or day.get("close") or 0)
                    if close == 0:
                        continue

                    rows.append({
                        "security_id": sid,
                        "trade_date": trade_date,
                        "open": round(float(day.get("adjOpen") or day.get("open") or 0), 4),
                        "high": round(float(day.get("adjHigh") or day.get("high") or 0), 4),
                        "low": round(float(day.get("adjLow") or day.get("low") or 0), 4),
                        "close": round(close, 4),
                        "volume": int(day.get("adjVolume") or day.get("volume") or 0),
                    })
                except (KeyError, ValueError, TypeError) as e:
                    self.log.debug("Transform error for %s: %s", ticker, e)
                    self.stats["errors"] += 1

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        """Write to raw_market_data with upsert, then update coverage."""
        self.log.info("Writing %d rows to raw_market_data...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_market_data
                           (security_id, trade_date, open, high, low, close, volume)
                       VALUES %s
                       ON CONFLICT (security_id, trade_date)
                       DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high,
                                     low = EXCLUDED.low, close = EXCLUDED.close,
                                     volume = EXCLUDED.volume, collected_at = now()""",
                    [(r["security_id"], r["trade_date"],
                      r["open"], r["high"], r["low"], r["close"], r["volume"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "Tiingo data: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )
        if hasattr(self, "session"):
            self.session.close()


if __name__ == "__main__":
    run_collector(TiingoDataCollector)
