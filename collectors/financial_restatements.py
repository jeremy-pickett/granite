"""
Financial Restatement Collector — 8-K Item 4.02 + restatement amendments via EDGAR.

Feeds into: material_weakness signal
Table:       raw_financial_restatements

Two sources:
  1. 8-K Item 4.02 — "Non-Reliance on Previously Issued Financial Statements"
     The company is telling you their old numbers were wrong.
  2. EFTS search for "restatement" in 10-K/A and 10-Q/A amendments.

Both are flashing red. A restatement means the books were cooked (or
incompetently kept) and now need fixing retroactively.

Data source: SEC EDGAR (free).
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

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"


class FinancialRestatementCollector(BaseCollector):

    COLLECTOR_ID = 9  # shares Material Weakness Scanner ID — same signal family
    COLLECTOR_NAME = "Financial Restatement Scanner"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        load_cik_map()
        self._cik_to_sid: dict[str, int] = {}

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_financial_restatements (
                        restatement_id  SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(20) NOT NULL,
                        accession       TEXT NOT NULL,
                        source_type     VARCHAR(20) NOT NULL,
                        filer_name      TEXT,
                        filing_url      TEXT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rfr_security
                        ON raw_financial_restatements (security_id, filing_date DESC);
                """)

    def fetch(self, securities):
        equities = [s for s in securities if s["security_type"] == "equity"]

        # Build CIK reverse map
        for s in equities:
            cik = get_cik(s["ticker"])
            if cik:
                self._cik_to_sid[cik] = s["security_id"]

        # Source 1: 8-K Item 4.02 via submissions endpoint
        item_402_hits = self._fetch_item_402(equities)

        # Source 2: EFTS "restatement" in amended filings
        restatement_hits = self._fetch_efts_restatements()

        return item_402_hits + restatement_hits

    def _fetch_item_402(self, equities):
        """Scan each company's 8-K filings for Item 4.02."""
        hits = []
        total = len(equities)
        self.log.info("Source 1: Scanning %d equities for 8-K Item 4.02...", total)

        for i, s in enumerate(equities):
            ticker = s["ticker"]
            cik = get_cik(ticker)
            if not cik:
                continue

            try:
                resp = requests.get(
                    EDGAR_SUBMISSIONS.format(cik=cik),
                    headers={"User-Agent": EDGAR_UA},
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    recent = resp.json().get("filings", {}).get("recent", {})
                    forms = recent.get("form", [])
                    dates = recent.get("filingDate", [])
                    accessions = recent.get("accessionNumber", [])
                    items_list = recent.get("items", [])
                    filing_cik = resp.json().get("cik", "")

                    for form, fdate, acc, items in zip(forms, dates, accessions, items_list):
                        if form not in ("8-K", "8-K/A"):
                            continue
                        if "4.02" not in items:
                            continue
                        acc_clean = acc.replace("-", "")
                        hits.append({
                            "security_id": s["security_id"],
                            "filing_date": fdate,
                            "form_type": form[:20],
                            "accession": acc,
                            "source_type": "item_4.02",
                            "filer_name": ticker,
                            "filing_url": f"https://www.sec.gov/Archives/edgar/data/{filing_cik}/{acc_clean}/{acc}-index.htm",
                        })

                    if any("4.02" in (items_list[j] if j < len(items_list) else "")
                           for j in range(len(forms)) if forms[j] in ("8-K", "8-K/A")):
                        self.stats["fetched"] += 1
                        self.log.info("  %s: found Item 4.02 (non-reliance) filing", ticker)

                elif resp.status_code == 429:
                    time.sleep(12)

            except requests.RequestException as e:
                self.log.debug("Fetch error %s: %s", ticker, e)
                self.stats["errors"] += 1

            time.sleep(0.15)
            if (i + 1) % 50 == 0:
                self.log.info("  Item 4.02 progress: %d/%d", i + 1, total)

        self.log.info("Source 1 complete: %d Item 4.02 hits", len(hits))
        return hits

    def _fetch_efts_restatements(self):
        """Bulk search EFTS for 'restatement' in amended 10-K/A and 10-Q/A."""
        self.log.info("Source 2: EFTS search for 'restatement' in amended filings...")
        hits = []
        offset = 0

        while True:
            try:
                resp = requests.get(
                    EFTS_URL,
                    params={
                        "q": '"restatement"',
                        "forms": "10-K/A,10-Q/A",
                        "dateRange": "custom",
                        "startdt": "2018-01-01",
                        "enddt": "2026-12-31",
                        "from": offset,
                        "size": 100,
                    },
                    headers={"User-Agent": EDGAR_UA},
                    timeout=config.HTTP_TIMEOUT,
                )

                if resp.status_code == 429:
                    time.sleep(12)
                    continue
                if resp.status_code != 200:
                    self.log.warning("EFTS returned %d at offset %d, stopping", resp.status_code, offset)
                    break

                data = resp.json()
                page_hits = data.get("hits", {}).get("hits", [])
                total = data.get("hits", {}).get("total", {}).get("value", 0)

                if not page_hits:
                    break

                for h in page_hits:
                    src = h.get("_source", {})
                    for cik in src.get("ciks", []):
                        padded = cik.zfill(10)
                        if padded in self._cik_to_sid:
                            hits.append({
                                "security_id": self._cik_to_sid[padded],
                                "filing_date": src.get("file_date"),
                                "form_type": (src.get("form") or "")[:20],
                                "accession": src.get("adsh", ""),
                                "source_type": "restatement",
                                "filer_name": (src.get("display_names") or [""])[0][:300],
                                "filing_url": "",
                            })

                offset += 100
                if offset % 500 == 0:
                    self.log.info("  EFTS restatement progress: %d/%d scanned, %d matched", offset, total, len(hits))
                if offset >= total:
                    break
                time.sleep(0.2)

            except requests.RequestException as e:
                self.log.warning("EFTS error at offset %d: %s", offset, e)
                self.stats["errors"] += 1
                offset += 100

        self.log.info("Source 2 complete: %d restatement hits in our universe", len(hits))
        return hits

    def transform(self, raw_data, securities):
        seen = set()
        rows = []
        for r in raw_data:
            key = (r["security_id"], r["accession"])
            if key in seen:
                continue
            seen.add(key)
            if not r.get("filing_url"):
                cik_num = ""
                for cik, sid in self._cik_to_sid.items():
                    if sid == r["security_id"]:
                        cik_num = cik.lstrip("0") or "0"
                        break
                acc_clean = r["accession"].replace("-", "")
                r["filing_url"] = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{r['accession']}-index.htm"
            rows.append(r)
        return rows

    def store(self, rows):
        self.log.info("Writing %d financial restatement records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_financial_restatements
                           (security_id, filing_date, form_type, accession, source_type, filer_name, filing_url)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["accession"], r["source_type"], r["filer_name"], r["filing_url"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Financial restatements: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(FinancialRestatementCollector)
