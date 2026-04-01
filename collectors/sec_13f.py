"""
SEC 13F Monitor — Institutional holdings from quarterly 13F filings via EDGAR.

Collector ID: 2 (SEC 13F Monitor)
Table:        raw_13f_holdings

13F filings show what the big money (hedge funds, pension funds, banks)
are holding each quarter. When major institutions dump a position or
a new activist shows up — that's signal.

Data source: SEC EDGAR submissions endpoint (free).
"""

import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
from edgar_utils import EDGAR_UA, EDGAR_SUBMISSIONS, get_cik, load_cik_map
import config
import db

_13F_FORMS = {"13F-HR", "13F-HR/A"}


class SEC13FCollector(BaseCollector):

    COLLECTOR_ID = 2
    COLLECTOR_NAME = "SEC 13F Monitor"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        load_cik_map()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_13f_holdings (
                        holding_id      SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(20) NOT NULL,
                        accession       TEXT NOT NULL,
                        period_of_report DATE,
                        filing_url      TEXT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_r13f_security
                        ON raw_13f_holdings (security_id, filing_date DESC);
                """)

    def fetch(self, securities):
        raw = {}
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Scanning %d equities for 13F filings...", total)

        for i, s in enumerate(equities):
            ticker = s["ticker"]
            cik = get_cik(ticker)
            if not cik:
                self.stats["skipped"] += 1
                continue

            try:
                resp = requests.get(
                    EDGAR_SUBMISSIONS.format(cik=cik),
                    headers={"User-Agent": EDGAR_UA},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    filings = self._extract_13f(resp.json())
                    if filings:
                        raw[ticker] = filings
                        self.stats["fetched"] += 1
                    else:
                        self.stats["skipped"] += 1
                elif resp.status_code == 429:
                    self.log.warning("Rate limited at %d/%d, sleeping 12s...", i, total)
                    time.sleep(12)
                else:
                    self.stats["skipped"] += 1
            except requests.RequestException as e:
                self.log.debug("Fetch error %s: %s", ticker, e)
                self.stats["errors"] += 1

            time.sleep(0.15)
            if (i + 1) % 50 == 0:
                self.log.info("  Progress: %d/%d (%d found)", i + 1, total, self.stats["fetched"])

        return raw

    def _extract_13f(self, submissions: dict) -> list[dict]:
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        cik = submissions.get("cik", "")

        results = []
        for form, fdate, acc in zip(forms, dates, accessions):
            if form not in _13F_FORMS:
                continue
            acc_clean = acc.replace("-", "")
            results.append({
                "filing_date": fdate,
                "form_type": form[:20],
                "accession": acc,
                "filing_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc}-index.htm",
            })
        return results

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        rows = []
        for ticker, filings in raw_data.items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue
            for f in filings:
                rows.append({"security_id": sid, **f})
        return rows

    def store(self, rows):
        self.log.info("Writing %d 13F holding records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_13f_holdings
                           (security_id, filing_date, form_type, accession, filing_url)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["accession"], r["filing_url"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("13F holdings: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(SEC13FCollector)
