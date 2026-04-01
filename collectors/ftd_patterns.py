"""
FTD Pattern Analyzer — Fail-to-deliver data from SEC.

Collector ID: 12 (FTD Pattern Analyzer)
Table:        raw_ftd_data

Fail-to-deliver = someone sold shares they didn't actually have, and
settlement failed. Persistent FTDs are a smoking gun for naked short
selling. Bear Stearns, Lehman, and GameStop all had massive FTD spikes
before their respective crises.

Data source: SEC FTD data files (free, published twice monthly as CSVs).
URL pattern: https://www.sec.gov/files/data/fails-deliver-data/cnsfailsYYYYMMa.zip
             (a = first half, b = second half of month)
"""

import sys
import os
import io
import time
import zipfile
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

EDGAR_UA = "Alidade/1.0 (contact@signaldelta.io)"
FTD_URL = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails{period}.zip"


def _generate_periods(months_back=6):
    """Generate period codes like 202603a, 202603b, 202602a, etc."""
    now = datetime.now(timezone.utc)
    periods = []
    for m in range(months_back):
        dt = now - timedelta(days=30 * m)
        ym = dt.strftime("%Y%m")
        periods.append(f"{ym}b")
        periods.append(f"{ym}a")
    return periods


class FTDPatternCollector(BaseCollector):

    COLLECTOR_ID = 12
    COLLECTOR_NAME = "FTD Pattern Analyzer"
    COLLECTOR_TYPE = "market_data"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_ftd_data (
                        ftd_id          SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        settlement_date DATE NOT NULL,
                        quantity        BIGINT NOT NULL,
                        price           NUMERIC(12,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, settlement_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rftd_security
                        ON raw_ftd_data (security_id, settlement_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rftd_date
                        ON raw_ftd_data (settlement_date DESC);
                """)

    def fetch(self, securities):
        # Build ticker → security_id lookup
        ticker_to_sid = {}
        for s in securities:
            if s["security_type"] == "equity":
                ticker_to_sid[s["ticker"]] = s["security_id"]

        all_rows = []
        periods = _generate_periods(months_back=6)
        self.log.info("Downloading FTD data for %d periods...", len(periods))

        for period in periods:
            url = FTD_URL.format(period=period)
            try:
                resp = requests.get(url, headers={"User-Agent": EDGAR_UA}, timeout=config.HTTP_TIMEOUT)
                if resp.status_code == 200:
                    rows = self._parse_zip(resp.content, ticker_to_sid)
                    all_rows.extend(rows)
                    self.stats["fetched"] += 1
                    self.log.info("  %s: %d matching FTD records", period, len(rows))
                elif resp.status_code == 404:
                    self.log.debug("  %s: not published yet", period)
                    self.stats["skipped"] += 1
                else:
                    self.stats["skipped"] += 1
            except requests.RequestException as e:
                self.log.debug("FTD download error %s: %s", period, e)
                self.stats["errors"] += 1

            time.sleep(0.3)

        self.log.info("Total FTD records matched to our universe: %d", len(all_rows))
        return all_rows

    def _parse_zip(self, content, ticker_to_sid):
        rows = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            for name in zf.namelist():
                with zf.open(name) as f:
                    text = f.read().decode("utf-8", errors="replace")
                    for line in text.strip().split("\n")[1:]:  # skip header
                        parts = line.strip().split("|")
                        if len(parts) < 6:
                            continue
                        date_str, cusip, symbol, qty_str, desc, price_str = parts[:6]
                        symbol = symbol.strip().upper()
                        if symbol not in ticker_to_sid:
                            continue
                        try:
                            qty = int(qty_str)
                            price = float(price_str) if price_str.strip() else None
                            sdate = datetime.strptime(date_str.strip(), "%Y%m%d").date()
                        except (ValueError, TypeError):
                            continue
                        # Only care about meaningful FTDs (>1000 shares)
                        if qty < 1000:
                            continue
                        rows.append({
                            "security_id": ticker_to_sid[symbol],
                            "settlement_date": sdate,
                            "quantity": qty,
                            "price": price,
                        })
        except zipfile.BadZipFile:
            pass
        return rows

    def transform(self, raw_data, securities):
        # Dedupe: keep the row with highest quantity per (security_id, date)
        best = {}
        for r in raw_data:
            key = (r["security_id"], r["settlement_date"])
            if key not in best or r["quantity"] > best[key]["quantity"]:
                best[key] = r
        return list(best.values())

    def store(self, rows):
        self.log.info("Writing %d FTD records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_ftd_data
                           (security_id, settlement_date, quantity, price)
                       VALUES %s
                       ON CONFLICT (security_id, settlement_date)
                       DO UPDATE SET quantity = EXCLUDED.quantity,
                                     price = EXCLUDED.price,
                                     last_updated = now()""",
                    [(r["security_id"], r["settlement_date"], r["quantity"], r["price"])
                     for r in rows],
                    template="(%s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("FTD data: %d periods fetched, %d records stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(FTDPatternCollector)
