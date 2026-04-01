"""
Options Flow Scanner — unusual options activity via Polygon.io.

Collector ID: 4 (Options Flow Scanner)
Table:        raw_options_flow

Fetches active options contracts and their previous-day trading data.
Detects volume/OI spikes and unusual activity — the kind of positioning
that preceded Enron puts, Bear Stearns puts, and the GME call wave.

Polygon free tier: 5 calls/min. We batch ~50 high-priority equities
per run and rotate through the universe over multiple days.

Data source: Polygon.io API (requires POLYGON_API_KEY).
"""

import sys
import os
import time
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

POLYGON_BASE = "https://api.polygon.io"
# Free tier: 5 calls/min → 12s between calls
RATE_DELAY = 13.0
# Contracts per ticker to scan (most active near-term)
CONTRACTS_PER_TICKER = 30
# Tickers per daily run (at 2-3 API calls per ticker + rate limit)
TICKERS_PER_RUN = 50


class OptionsFlowCollector(BaseCollector):

    COLLECTOR_ID = 4
    COLLECTOR_NAME = "Options Flow Scanner"
    COLLECTOR_TYPE = "market_data"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        if not config.POLYGON_API_KEY:
            raise RuntimeError("POLYGON_API_KEY not set")
        self._ensure_table()
        self._api_key = config.POLYGON_API_KEY

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_options_flow (
                        flow_id         SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        option_ticker   TEXT NOT NULL,
                        contract_type   VARCHAR(10),
                        strike_price    NUMERIC(14,4),
                        expiration_date DATE,
                        trade_date      DATE NOT NULL,
                        volume          INT,
                        open_price      NUMERIC(14,4),
                        close_price     NUMERIC(14,4),
                        high_price      NUMERIC(14,4),
                        low_price       NUMERIC(14,4),
                        vwap            NUMERIC(14,4),
                        num_trades      INT,
                        underlying_close NUMERIC(14,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(option_ticker, trade_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rof_security
                        ON raw_options_flow (security_id, trade_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rof_volume
                        ON raw_options_flow (volume DESC);
                """)

    def fetch(self, securities):
        equities = [s for s in securities if s["security_type"] == "equity"]

        # Prioritize: rotate through universe using day-of-year as offset
        day_offset = (datetime.now(timezone.utc).timetuple().tm_yday * TICKERS_PER_RUN) % len(equities)
        batch = equities[day_offset:day_offset + TICKERS_PER_RUN]
        if len(batch) < TICKERS_PER_RUN:
            batch += equities[:TICKERS_PER_RUN - len(batch)]

        self.log.info("Scanning %d equities (batch offset %d)...", len(batch), day_offset)

        all_rows = []
        for i, s in enumerate(batch):
            ticker = s["ticker"]
            sid = s["security_id"]

            try:
                # Step 1: Get underlying price
                underlying_close = self._get_underlying_price(ticker)
                time.sleep(RATE_DELAY)

                # Step 2: Get active contracts
                contracts = self._get_contracts(ticker)
                time.sleep(RATE_DELAY)

                if not contracts:
                    self.stats["skipped"] += 1
                    continue

                # Step 3: Get prev-day aggregates for high-activity contracts
                for contract in contracts[:CONTRACTS_PER_TICKER]:
                    opt_ticker = contract.get("ticker")
                    if not opt_ticker:
                        continue

                    agg = self._get_prev_day(opt_ticker)
                    time.sleep(RATE_DELAY)

                    if not agg:
                        continue

                    vol = agg.get("v", 0)
                    if vol < 50:  # skip very low volume
                        continue

                    all_rows.append({
                        "security_id": sid,
                        "option_ticker": opt_ticker,
                        "contract_type": contract.get("contract_type", ""),
                        "strike_price": contract.get("strike_price"),
                        "expiration_date": contract.get("expiration_date"),
                        "trade_date": datetime.fromtimestamp(agg["t"] / 1000).date() if agg.get("t") else None,
                        "volume": vol,
                        "open_price": agg.get("o"),
                        "close_price": agg.get("c"),
                        "high_price": agg.get("h"),
                        "low_price": agg.get("l"),
                        "vwap": agg.get("vw"),
                        "num_trades": agg.get("n"),
                        "underlying_close": underlying_close,
                    })

                self.stats["fetched"] += 1
                if all_rows:
                    self.log.info("  %s: %d options with volume", ticker, sum(1 for r in all_rows if r["security_id"] == sid))

            except Exception as e:
                self.log.warning("Error processing %s: %s", ticker, e)
                self.stats["errors"] += 1

            if (i + 1) % 10 == 0:
                self.log.info("  Progress: %d/%d tickers", i + 1, len(batch))

        return all_rows

    def _get_underlying_price(self, ticker):
        try:
            resp = requests.get(
                f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/prev",
                params={"apiKey": self._api_key},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return results[0].get("c")
        except requests.RequestException:
            pass
        return None

    def _get_contracts(self, ticker):
        try:
            resp = requests.get(
                f"{POLYGON_BASE}/v3/reference/options/contracts",
                params={
                    "underlying_ticker": ticker,
                    "expired": "false",
                    "limit": CONTRACTS_PER_TICKER,
                    "apiKey": self._api_key,
                },
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except requests.RequestException:
            pass
        return []

    def _get_prev_day(self, option_ticker):
        try:
            resp = requests.get(
                f"{POLYGON_BASE}/v2/aggs/ticker/{option_ticker}/prev",
                params={"apiKey": self._api_key},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return results[0]
        except requests.RequestException:
            pass
        return None

    def transform(self, raw_data, securities):
        # Dedupe by (option_ticker, trade_date)
        seen = set()
        rows = []
        for r in raw_data:
            if not r.get("trade_date"):
                continue
            key = (r["option_ticker"], r["trade_date"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
        return rows

    def store(self, rows):
        self.log.info("Writing %d options flow records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_options_flow
                           (security_id, option_ticker, contract_type, strike_price,
                            expiration_date, trade_date, volume, open_price, close_price,
                            high_price, low_price, vwap, num_trades, underlying_close)
                       VALUES %s
                       ON CONFLICT (option_ticker, trade_date)
                       DO UPDATE SET volume = EXCLUDED.volume,
                                     close_price = EXCLUDED.close_price,
                                     last_updated = now()""",
                    [(r["security_id"], r["option_ticker"], r["contract_type"],
                      r["strike_price"], r["expiration_date"], r["trade_date"],
                      r["volume"], r["open_price"], r["close_price"],
                      r["high_price"], r["low_price"], r["vwap"],
                      r["num_trades"], r["underlying_close"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Options flow: %d tickers scanned, %d records stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(OptionsFlowCollector)
