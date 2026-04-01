"""
C-Suite Departure Tracker — SEC 8-K Item 5.02 filings via EDGAR.

Collector ID: 11 (C-Suite Departure Tracker)
Table:        raw_csuite_departures

Monitors executive departures and appointments from 8-K filings that
include Item 5.02 (Departure of Directors or Certain Officers; Election
of Directors; Appointment of Certain Officers).

Data source: SEC EDGAR (free, no API key — requires User-Agent header).
Rate limit: 10 requests/second per SEC fair access policy.
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

from edgar_utils import EDGAR_UA, EDGAR_SUBMISSIONS, get_cik, load_cik_map


class CSuiteDepartureCollector(BaseCollector):

    COLLECTOR_ID = 11
    COLLECTOR_NAME = "C-Suite Departure Tracker"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        load_cik_map()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_csuite_departures (
                        departure_id    SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(10),
                        accession       TEXT NOT NULL,
                        items           TEXT,
                        filing_url      TEXT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rcd_security
                        ON raw_csuite_departures (security_id, filing_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rcd_date
                        ON raw_csuite_departures (filing_date DESC);
                """)

    def fetch(self, securities):
        raw = {}
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Scanning %d equities for C-suite departures...", total)

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
                    filings = self._extract_502_filings(resp.json())
                    if filings:
                        raw[ticker] = filings
                        self.stats["fetched"] += 1
                        self.log.info("  %s: found %d departure filings", ticker, len(filings))
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
                self.log.info("  Progress: %d/%d", i + 1, total)

        return raw

    def _extract_502_filings(self, submissions: dict) -> list[dict]:
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        items_list = recent.get("items", [])
        cik = submissions.get("cik", "")

        results = []
        for form, fdate, acc, items in zip(forms, dates, accessions, items_list):
            if form not in ("8-K", "8-K/A"):
                continue
            if "5.02" not in items:
                continue
            acc_clean = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc}-index.htm"
            results.append({
                "filing_date": fdate,
                "form_type": form,
                "accession": acc,
                "items": items,
                "filing_url": url,
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
                rows.append({
                    "security_id": sid,
                    "filing_date": f["filing_date"],
                    "form_type": f["form_type"],
                    "accession": f["accession"],
                    "items": f["items"],
                    "filing_url": f["filing_url"],
                })
        return rows

    def store(self, rows):
        self.log.info("Writing %d C-suite departure records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_csuite_departures
                           (security_id, filing_date, form_type, accession, items, filing_url)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["accession"], r["items"], r["filing_url"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info(
            "C-Suite departures: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(CSuiteDepartureCollector)
