"""
PE Activity Monitor — going-private transactions, tender offers, and LBO filings.

Collector ID: 31
Table:        raw_pe_activity

Detects PE predatory behavior via EDGAR EFTS full-text search:
  - Going-private transactions (SC 13E-3, 8-K)
  - Tender offers (SC TO-T, SC TO-C)
  - Merger / definitive agreements (8-K, PREM14A, DEFM14A)
  - Debt offerings and credit facilities (8-K Item 1.01)
  - Asset sales and dispositions (8-K Item 2.01)

The going-private + debt loading combination is the classic PE strip-and-dump
playbook: acquire via leveraged buyout, load the target with debt, extract
dividends, sell off assets, let the carcass file for bankruptcy.

Data source: SEC EDGAR EFTS (free, no API key — requires User-Agent header).
"""

import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
from edgar_utils import EDGAR_UA, get_cik, load_cik_map
import config
import db

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
PAGE_SIZE = 100

# Each search pass: (query, forms, event_type)
SEARCH_PASSES = [
    ('"going private"', "SC 13E-3,8-K", "going_private"),
    ('"tender offer"', "SC TO-T,SC TO-C", "tender_offer"),
    ('"merger agreement" OR "definitive agreement"', "8-K,PREM14A,DEFM14A", "merger_agreement"),
    ('"debt offering" OR "credit facility" OR "term loan"', "8-K", "debt_offering"),
    ('"asset sale" OR "disposition"', "8-K", "asset_sale"),
]


class PEActivityCollector(BaseCollector):

    COLLECTOR_ID = 31
    COLLECTOR_NAME = "PE Activity Monitor"
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
                    CREATE TABLE IF NOT EXISTS raw_pe_activity (
                        event_id        SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(20) NOT NULL,
                        event_type      VARCHAR(30) NOT NULL,
                        accession       TEXT NOT NULL,
                        filer_name      TEXT,
                        description     TEXT,
                        filing_url      TEXT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpa_security
                        ON raw_pe_activity (security_id, filing_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rpa_event_type
                        ON raw_pe_activity (event_type, filing_date DESC);
                """)

    def fetch(self, securities):
        """Bulk search EDGAR EFTS for PE-related filings across multiple passes."""
        # Build CIK -> security_id lookup
        for s in securities:
            if s["security_type"] != "equity":
                continue
            cik = get_cik(s["ticker"])
            if cik:
                self._cik_to_sid[cik] = s["security_id"]

        self.log.info("Mapped %d securities to CIKs", len(self._cik_to_sid))

        all_hits = []

        for query, forms, event_type in SEARCH_PASSES:
            self.log.info("EFTS pass: %s (forms=%s)", event_type, forms)
            offset = 0
            pass_hits = 0

            while True:
                try:
                    resp = requests.get(
                        EFTS_URL,
                        params={
                            "q": query,
                            "forms": forms,
                            "dateRange": "custom",
                            "startdt": "2018-01-01",
                            "enddt": "2026-12-31",
                            "from": offset,
                            "size": PAGE_SIZE,
                        },
                        headers={"User-Agent": EDGAR_UA},
                        timeout=config.HTTP_TIMEOUT,
                    )

                    if resp.status_code == 429:
                        self.log.warning("Rate limited, sleeping 12s...")
                        time.sleep(12)
                        continue

                    if resp.status_code != 200:
                        self.log.warning("EFTS returned %d at offset %d, stopping pass", resp.status_code, offset)
                        break

                    data = resp.json()
                    hits = data.get("hits", {}).get("hits", [])
                    total = data.get("hits", {}).get("total", {}).get("value", 0)

                    if not hits:
                        break

                    for h in hits:
                        src = h.get("_source", {})
                        ciks = src.get("ciks", [])
                        for cik in ciks:
                            padded = cik.zfill(10)
                            if padded in self._cik_to_sid:
                                all_hits.append({
                                    "security_id": self._cik_to_sid[padded],
                                    "filing_date": src.get("file_date"),
                                    "form_type": (src.get("form") or "")[:20],
                                    "event_type": event_type,
                                    "accession": src.get("adsh", ""),
                                    "filer_name": (src.get("display_names") or [""])[0][:300],
                                    "description": f"{event_type}: {(src.get('display_names') or [''])[0][:200]}",
                                })
                                pass_hits += 1

                    self.stats["fetched"] += len(hits)
                    offset += PAGE_SIZE

                    if offset >= total:
                        break

                    # SEC fair access
                    time.sleep(0.2)

                except requests.RequestException as e:
                    self.log.warning("EFTS request error at offset %d: %s", offset, e)
                    self.stats["errors"] += 1
                    time.sleep(2)
                    offset += PAGE_SIZE

            self.log.info("  %s: %d matched our universe", event_type, pass_hits)

        self.log.info("EFTS scan complete: %d total hits, %d matched our securities",
                      self.stats["fetched"], len(all_hits))
        return all_hits

    def transform(self, raw_data, securities):
        """Deduplicate by (security_id, accession) and build filing URLs."""
        seen = set()
        rows = []
        for r in raw_data:
            key = (r["security_id"], r["accession"])
            if key in seen:
                continue
            seen.add(key)

            # Build filing URL from CIK + accession
            cik_num = ""
            for cik, sid in self._cik_to_sid.items():
                if sid == r["security_id"]:
                    cik_num = cik.lstrip("0") or "0"
                    break
            acc_clean = r["accession"].replace("-", "")
            r["filing_url"] = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_num}/"
                f"{acc_clean}/{r['accession']}-index.htm"
            )
            rows.append(r)

        self.log.info("Deduplicated: %d raw → %d unique records", len(raw_data), len(rows))
        return rows

    def store(self, rows):
        if not rows:
            self.log.info("No PE activity records to store")
            super().store(rows)
            return

        self.log.info("Writing %d PE activity records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_pe_activity
                           (security_id, filing_date, form_type, event_type,
                            accession, filer_name, description, filing_url)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["event_type"], r["accession"], r["filer_name"],
                      r.get("description", ""), r["filing_url"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info(
            "PE activity: %d scanned, %d stored, %d errors",
            self.stats["fetched"], self.stats["stored"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(PEActivityCollector)
