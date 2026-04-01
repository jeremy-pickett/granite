"""
Insider Trades Collector — SEC Form 4 filings via Finnhub.

Collector ID: 1 (SEC Form 4 Parser)
Table:        raw_insider_trades

Finnhub endpoint: /api/v1/stock/insider-transactions?symbol=TICKER
Free tier: 60 calls/min
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


class InsiderTradesCollector(BaseCollector):

    # ── identity ──────────────────────────────────────────────────────
    COLLECTOR_ID = 1
    COLLECTOR_NAME = "SEC Form 4 Parser"
    COLLECTOR_TYPE = "sec_filing"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        if not config.FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY not set")
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_insider_trades (
                        trade_id        SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE,
                        reporter_name   TEXT,
                        transaction_type VARCHAR(20),
                        shares_changed  BIGINT,
                        shares_after    BIGINT,
                        is_derivative   BOOLEAN DEFAULT false,
                        source_id       TEXT,
                        insider_title   VARCHAR(100),
                        price_per_share NUMERIC(12,4),
                        total_value     NUMERIC(16,2),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, filing_date, reporter_name, transaction_type)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rit_security ON raw_insider_trades (security_id, filing_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rit_date ON raw_insider_trades (filing_date DESC);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Fetch insider transactions from Finnhub, respecting 60/min rate limit."""
        raw = {}
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Fetching insider trades for %d equities...", total)

        for i, s in enumerate(equities):
            ticker = s["ticker"]
            try:
                resp = requests.get(
                    "https://finnhub.io/api/v1/stock/insider-transactions",
                    params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        raw[ticker] = data
                        self.stats["fetched"] += 1
                    else:
                        self.stats["skipped"] += 1
                elif resp.status_code == 429:
                    self.log.warning("Rate limited at %d/%d, sleeping 60s...", i, total)
                    time.sleep(62)
                    i -= 1  # retry
                else:
                    self.stats["skipped"] += 1
            except requests.RequestException as e:
                self.log.debug("Fetch error %s: %s", ticker, e)
                self.stats["errors"] += 1

            # Rate limit: 60/min
            if (i + 1) % 55 == 0:
                self.log.info("  Progress: %d/%d, pausing for rate limit...", i + 1, total)
                time.sleep(62)

        return raw

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        rows = []

        for ticker, trades in raw_data.items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            for t in trades[:20]:
                tx_code = t.get("transactionCode", "")
                # P=Purchase, S=Sale, A=Grant, M=Exercise, G=Gift
                tx_type = {"P": "purchase", "S": "sale", "A": "grant",
                           "M": "exercise", "G": "gift"}.get(tx_code, tx_code)[:20]

                shares = int(t.get("change") or 0)
                price = float(t.get("transactionPrice") or 0)
                total_val = abs(shares * price) if price else None

                rows.append({
                    "security_id": sid,
                    "filing_date": t.get("filingDate"),
                    "reporter_name": (t.get("name") or "unknown")[:200],
                    "transaction_type": tx_type,
                    "shares_changed": shares,
                    "shares_after": int(t.get("share") or 0),
                    "is_derivative": bool(t.get("isDerivative")),
                    "source_id": (t.get("id") or "")[:100],
                    "insider_title": (t.get("officerTitle") or "")[:100] or None,
                    "price_per_share": price if price else None,
                    "total_value": total_val,
                })

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        self.log.info("Writing %d insider trades...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_insider_trades
                           (security_id, filing_date, reporter_name, transaction_type,
                            shares_changed, shares_after, is_derivative, source_id,
                            insider_title, price_per_share, total_value)
                       VALUES %s
                       ON CONFLICT (security_id, filing_date, reporter_name, transaction_type)
                       DO UPDATE SET last_updated = now(),
                                     insider_title = COALESCE(EXCLUDED.insider_title, raw_insider_trades.insider_title),
                                     price_per_share = COALESCE(EXCLUDED.price_per_share, raw_insider_trades.price_per_share),
                                     total_value = COALESCE(EXCLUDED.total_value, raw_insider_trades.total_value)""",
                    [(r["security_id"], r["filing_date"], r["reporter_name"],
                      r["transaction_type"], r["shares_changed"], r["shares_after"],
                      r["is_derivative"], r["source_id"],
                      r["insider_title"], r["price_per_share"], r["total_value"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "Insider trades: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(InsiderTradesCollector)
