"""
Late Filing Collector — NT 10-K and NT 10-Q notifications via EDGAR.

Feeds into: material_weakness signal
Table:       raw_late_filings

When a company files NT 10-K or NT 10-Q, they're telling the SEC they
can't get their financials ready on time. This preceded SMCI's crisis,
Enron's collapse, and dozens of other blowups. Often the first visible
crack in the foundation.

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

NT_FORMS = {"NT 10-K", "NT 10-K/A", "NT 10-Q", "NT 10-Q/A"}


class LateFilingCollector(BaseCollector):

    COLLECTOR_ID = 9  # shares Material Weakness Scanner ID — same signal family
    COLLECTOR_NAME = "Late Filing Scanner"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        load_cik_map()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_late_filings (
                        late_id         SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(20) NOT NULL,
                        accession       TEXT NOT NULL,
                        filing_url      TEXT,
                        is_consecutive  BOOLEAN DEFAULT false,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rlf_security
                        ON raw_late_filings (security_id, filing_date DESC);
                    -- Add is_consecutive column if missing (migration)
                    ALTER TABLE raw_late_filings
                        ADD COLUMN IF NOT EXISTS is_consecutive BOOLEAN DEFAULT false;
                """)

    def fetch(self, securities):
        raw = {}
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Scanning %d equities for late filings (NT 10-K/10-Q)...", total)

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
                    filings = self._extract_nt(resp.json())
                    if filings:
                        raw[ticker] = filings
                        self.stats["fetched"] += 1
                        self.log.info("  %s: found %d late filings", ticker, len(filings))
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

    def _extract_nt(self, submissions: dict) -> list[dict]:
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        cik = submissions.get("cik", "")

        results = []
        for form, fdate, acc in zip(forms, dates, accessions):
            if form not in NT_FORMS:
                continue
            acc_clean = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc}-index.htm"
            results.append({
                "filing_date": fdate,
                "form_type": form[:20],
                "accession": acc,
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
                rows.append({"security_id": sid, **f})
        return rows

    def store(self, rows):
        self.log.info("Writing %d late filing records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_late_filings
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
                # Mark consecutive NT filings: any filing where the same
                # security has another late filing within 180 days prior.
                cur.execute("""
                    UPDATE raw_late_filings f
                    SET is_consecutive = true
                    WHERE EXISTS (
                        SELECT 1 FROM raw_late_filings prior
                        WHERE prior.security_id = f.security_id
                          AND prior.late_id != f.late_id
                          AND prior.filing_date >= f.filing_date - interval '180 days'
                          AND prior.filing_date < f.filing_date
                    )
                """)
        super().store(rows)

    def teardown(self):
        self.log.info("Late filings: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(LateFilingCollector)
