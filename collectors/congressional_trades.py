"""
Congressional Trades Collector — Congress member stock trades via QuiverQuant.

Collector ID: 17 (Congressional Trade Feed)
Table:        raw_congressional_trades
Signals:      congressional (S/A tier — highest weight signals)

QuiverQuant endpoint: /beta/historical/congresstrading/TICKER
                      /beta/live/congresstrading (recent trades, all tickers)
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


class CongressionalTradesCollector(BaseCollector):

    # ── identity ──────────────────────────────────────────────────────
    COLLECTOR_ID = 17
    COLLECTOR_NAME = "Congressional Trade Feed"
    COLLECTOR_TYPE = "political"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        if not config.QUIVERQUANT_API_KEY:
            raise RuntimeError("QUIVERQUANT_API_KEY not set")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {config.QUIVERQUANT_API_KEY}"
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_congressional_trades (
                        trade_id          SERIAL PRIMARY KEY,
                        security_id       INT REFERENCES securities(security_id),
                        ticker            VARCHAR(20) NOT NULL,
                        trade_date        DATE,
                        disclosure_date   DATE,
                        representative    TEXT,
                        chamber           VARCHAR(10),
                        transaction_type  VARCHAR(20),
                        amount_low        BIGINT,
                        amount_high       BIGINT,
                        party             VARCHAR(1),
                        state             VARCHAR(2),
                        district          VARCHAR(10),
                        collected_at      TIMESTAMP DEFAULT now(),
                        last_updated      TIMESTAMP DEFAULT now(),
                        UNIQUE(ticker, trade_date, representative, transaction_type)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rct_ticker ON raw_congressional_trades (ticker, trade_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rct_date ON raw_congressional_trades (trade_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rct_security ON raw_congressional_trades (security_id, trade_date DESC);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Fetch recent congressional trades from QuiverQuant live endpoint."""
        # Try the bulk/live endpoint first (all recent trades at once)
        self.log.info("Fetching recent congressional trades (bulk)...")
        raw = []

        try:
            resp = self.session.get(
                "https://api.quiverquant.com/beta/live/congresstrading",
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    raw = data
                    self.stats["fetched"] = len(data)
                    self.log.info("  Got %d trades from bulk endpoint", len(data))
            elif resp.status_code == 403:
                self.log.warning("  Bulk endpoint returned 403 — trying per-ticker...")
            else:
                self.log.warning("  Bulk endpoint returned %d", resp.status_code)
        except requests.RequestException as e:
            self.log.warning("  Bulk fetch failed: %s", e)

        # Fallback: per-ticker for our securities
        if not raw:
            self.log.info("Falling back to per-ticker fetch...")
            sec_tickers = {s["ticker"] for s in securities if s["security_type"] == "equity"}
            for i, ticker in enumerate(sorted(sec_tickers)):
                try:
                    resp = self.session.get(
                        f"https://api.quiverquant.com/beta/historical/congresstrading/{ticker}",
                        timeout=config.HTTP_TIMEOUT,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and data:
                            for d in data:
                                d["Ticker"] = d.get("Ticker", ticker)
                            raw.extend(data[:10])
                            self.stats["fetched"] += 1
                    elif resp.status_code == 429:
                        self.log.warning("Rate limited at %d tickers, sleeping...", i)
                        time.sleep(5)
                except requests.RequestException:
                    pass

                if (i + 1) % 50 == 0:
                    self.log.info("  Progress: %d tickers...", i + 1)
                    time.sleep(0.5)

        return raw

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}

        # Parse QuiverQuant amount strings like "$1,001 - $15,000"
        def parse_amount(s):
            if not s:
                return None, None
            s = s.replace("$", "").replace(",", "")
            if " - " in s:
                parts = s.split(" - ")
                try:
                    return int(float(parts[0])), int(float(parts[1]))
                except ValueError:
                    return None, None
            return None, None

        rows = []
        for t in raw_data:
            ticker = (t.get("Ticker") or t.get("ticker") or "").upper()
            if not ticker:
                continue

            sid = sec_lookup.get(ticker)

            low, high = parse_amount(t.get("Amount") or t.get("Range"))

            rows.append({
                "security_id": sid,
                "ticker": ticker,
                "trade_date": t.get("TransactionDate") or t.get("Date"),
                "disclosure_date": t.get("DisclosureDate") or t.get("ReportDate"),
                "representative": (t.get("Representative") or t.get("Name") or "unknown")[:200],
                "chamber": (t.get("House") or t.get("Chamber") or "")[:10],
                "transaction_type": (t.get("Transaction") or t.get("Type") or "")[:20],
                "amount_low": low,
                "amount_high": high,
                "party": (t.get("Party") or "")[:1],
                "state": (t.get("State") or "")[:2],
                "district": (t.get("District") or "")[:10],
            })

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        self.log.info("Writing %d congressional trades...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_congressional_trades
                           (security_id, ticker, trade_date, disclosure_date,
                            representative, chamber, transaction_type,
                            amount_low, amount_high, party, state, district)
                       VALUES %s
                       ON CONFLICT (ticker, trade_date, representative, transaction_type)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["ticker"], r["trade_date"],
                      r["disclosure_date"], r["representative"], r["chamber"],
                      r["transaction_type"], r["amount_low"], r["amount_high"],
                      r["party"], r["state"], r["district"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.session.close()
        self.log.info(
            "Congressional trades: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(CongressionalTradesCollector)
