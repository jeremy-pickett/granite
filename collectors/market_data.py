"""
Market Data Collector — daily OHLCV via yfinance.

Collector ID: 3 (Earnings Calendar row, repurposed as Market Data Daily)
Table:        raw_market_data
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
import pandas as pd
from psycopg2.extras import execute_values

from base import BaseCollector, run_collector
import config
import db


# Our DB ticker → Yahoo Finance symbol (crypto needs -USD suffix)
CRYPTO_MAP = {
    "1INCH": "1INCH-USD",
    "AAVE":  "AAVE-USD",
    "ADA":   "ADA-USD",
}


class MarketDataCollector(BaseCollector):

    # ── identity (must match `collectors` table) ──────────────────────
    COLLECTOR_ID = 3
    COLLECTOR_NAME = "Market Data (Daily)"
    COLLECTOR_TYPE = "market_data"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_market_data (
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        trade_date      DATE NOT NULL,
                        open            NUMERIC(14,4),
                        high            NUMERIC(14,4),
                        low             NUMERIC(14,4),
                        close           NUMERIC(14,4),
                        volume          BIGINT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        PRIMARY KEY (security_id, trade_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rmd_date ON raw_market_data (trade_date);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Batch-download 5-day OHLCV from Yahoo Finance."""
        ticker_map = {}  # yf_symbol → our ticker
        for s in securities:
            t = s["ticker"]
            ticker_map[CRYPTO_MAP.get(t, t)] = t

        yf_symbols = list(ticker_map.keys())
        self.log.info("Downloading %d tickers from Yahoo Finance...", len(yf_symbols))

        all_data = {}
        chunk_size = config.BATCH_SIZE
        total_batches = (len(yf_symbols) + chunk_size - 1) // chunk_size

        for i in range(0, len(yf_symbols), chunk_size):
            chunk = yf_symbols[i:i + chunk_size]
            batch_num = i // chunk_size + 1
            self.log.info("  Batch %d/%d (%d tickers)...", batch_num, total_batches, len(chunk))
            try:
                df = yf.download(
                    chunk,
                    period="5d",
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )
                if df is not None and not df.empty:
                    all_data[i] = (df, chunk)
                    self.stats["fetched"] += len(chunk)
            except Exception as e:
                self.log.warning("  Batch failed: %s", e)
                self.stats["errors"] += 1

        return {"frames": all_data, "ticker_map": ticker_map}

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        """Flatten batch DataFrames into row dicts."""
        ticker_map = raw_data["ticker_map"]
        frames = raw_data["frames"]

        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}

        rows = []
        for _batch_idx, (df, chunk) in frames.items():
            for yf_sym in chunk:
                our_ticker = ticker_map.get(yf_sym, yf_sym)
                sid = sec_lookup.get(our_ticker)
                if not sid:
                    self.stats["skipped"] += 1
                    continue

                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        if yf_sym not in df.columns.get_level_values(0):
                            self.stats["skipped"] += 1
                            continue
                        tdf = df[yf_sym].dropna(how="all")
                    elif len(chunk) == 1:
                        tdf = df.dropna(how="all")
                    else:
                        self.stats["skipped"] += 1
                        continue

                    for date, row in tdf.iterrows():
                        trade_date = date.date() if hasattr(date, "date") else date
                        c = float(row.get("Close", 0) or 0)
                        if c == 0:
                            continue
                        rows.append({
                            "security_id": sid,
                            "trade_date": trade_date,
                            "open": round(float(row.get("Open", 0) or 0), 4),
                            "high": round(float(row.get("High", 0) or 0), 4),
                            "low": round(float(row.get("Low", 0) or 0), 4),
                            "close": round(c, 4),
                            "volume": int(row.get("Volume", 0) or 0),
                        })
                except Exception as e:
                    self.log.debug("Transform error for %s: %s", our_ticker, e)
                    self.stats["errors"] += 1

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        """Write to raw_market_data, then update coverage via base class."""
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
            "Market data: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(MarketDataCollector)
