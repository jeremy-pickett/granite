"""
Material Weakness Scanner — SOX material weakness disclosures via EDGAR EFTS.

Collector ID: 9 (Material Weakness Scanner)
Table:        raw_material_weaknesses

Searches SEC EDGAR full-text search for 10-K, 10-K/A, 10-Q, 10-Q/A,
and NT (notification of late filing) forms that contain the phrase
"material weakness". Matches filing CIKs back to our securities universe.

This is the quintessential pre-collapse signal. Enron, WorldCom, and
WeWork all disclosed material weaknesses before catastrophic failure.

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

FORMS = "10-K,10-K/A,10-Q,10-Q/A,NT 10-K,NT 10-Q"
QUERY = '"material weakness"'
PAGE_SIZE = 100


class MaterialWeaknessCollector(BaseCollector):

    COLLECTOR_ID = 9
    COLLECTOR_NAME = "Material Weakness Scanner"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        load_cik_map()
        # Build reverse map: CIK → security_id
        self._cik_to_sid: dict[str, int] = {}

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_material_weaknesses (
                        weakness_id     SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(20) NOT NULL,
                        accession       TEXT NOT NULL,
                        filer_name      TEXT,
                        filing_url      TEXT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rmw_security
                        ON raw_material_weaknesses (security_id, filing_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rmw_date
                        ON raw_material_weaknesses (filing_date DESC);
                """)

    def fetch(self, securities):
        """
        Bulk search EDGAR EFTS for "material weakness" in 10-K/10-Q filings,
        then match CIKs back to our securities universe.
        """
        # Build CIK → security_id lookup
        for s in securities:
            if s["security_type"] != "equity":
                continue
            cik = get_cik(s["ticker"])
            if cik:
                self._cik_to_sid[cik] = s["security_id"]

        self.log.info("Mapped %d securities to CIKs", len(self._cik_to_sid))

        all_hits = []
        offset = 0

        while True:
            try:
                resp = requests.get(
                    EFTS_URL,
                    params={
                        "q": QUERY,
                        "forms": FORMS,
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
                    self.log.warning("EFTS returned %d at offset %d, stopping", resp.status_code, offset)
                    break

                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                total = data.get("hits", {}).get("total", {}).get("value", 0)

                if not hits:
                    break

                for h in hits:
                    src = h.get("_source", {})
                    ciks = src.get("ciks", [])
                    # Match any CIK in the filing to our securities
                    for cik in ciks:
                        padded = cik.zfill(10)
                        if padded in self._cik_to_sid:
                            all_hits.append({
                                "security_id": self._cik_to_sid[padded],
                                "filing_date": src.get("file_date"),
                                "form_type": (src.get("form") or "")[:20],
                                "accession": src.get("adsh", ""),
                                "filer_name": (src.get("display_names") or [""])[0][:300],
                            })

                self.stats["fetched"] += len(hits)
                offset += PAGE_SIZE

                if offset % 500 == 0:
                    self.log.info("  EFTS progress: %d/%d hits scanned, %d matched our universe",
                                  offset, total, len(all_hits))

                if offset >= total:
                    break

                # SEC fair access
                time.sleep(0.2)

            except requests.RequestException as e:
                self.log.warning("EFTS request error at offset %d: %s", offset, e)
                self.stats["errors"] += 1
                time.sleep(2)
                offset += PAGE_SIZE

        self.log.info("EFTS scan complete: %d total hits, %d matched our securities",
                      self.stats["fetched"], len(all_hits))
        return all_hits

    # Patterns that indicate the filing does NOT have a material weakness
    _NEGATION_PATTERNS = [
        "no material weakness",
        "did not identify any material weakness",
        "did not identify a material weakness",
        "not identified any material weakness",
        "no material weaknesses were identified",
        "no material weaknesses have been identified",
        "remediated the material weakness",
        "remediation of the material weakness",
        "material weakness has been remediated",
        "material weakness was remediated",
        "previously reported material weakness",
        "corrected the material weakness",
    ]

    def _is_negated(self, filing_url):
        """Download first 15KB of filing text and check for negation patterns."""
        try:
            resp = requests.get(
                filing_url,
                headers={"User-Agent": EDGAR_UA, "Range": "bytes=0-15000"},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code not in (200, 206):
                return False  # can't determine — keep it
            text = resp.text.lower()
            for pat in self._NEGATION_PATTERNS:
                if pat in text:
                    return True
            return False
        except requests.RequestException:
            return False  # network error — keep the record

    def transform(self, raw_data, securities):
        # raw_data is already a list of dicts — dedupe by (security_id, accession)
        seen = set()
        rows = []
        negated = 0
        for r in raw_data:
            key = (r["security_id"], r["accession"])
            if key in seen:
                continue
            seen.add(key)
            acc = r["accession"]
            # Best-effort filing URL
            cik_num = ""
            for cik, sid in self._cik_to_sid.items():
                if sid == r["security_id"]:
                    cik_num = cik.lstrip("0") or "0"
                    break
            acc_clean = acc.replace("-", "")
            r["filing_url"] = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{acc}-index.htm"

            # Negation check: skip filings that say "no material weakness"
            if self._is_negated(r["filing_url"]):
                negated += 1
                continue
            # Rate limit: SEC fair access
            time.sleep(0.15)

            rows.append(r)
        if negated:
            self.log.info("Filtered %d negated 'no material weakness' mentions", negated)
        return rows

    def store(self, rows):
        self.log.info("Writing %d material weakness records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_material_weaknesses
                           (security_id, filing_date, form_type, accession, filer_name, filing_url)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["accession"], r["filer_name"], r["filing_url"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info(
            "Material weaknesses: %d scanned, %d stored, %d errors",
            self.stats["fetched"], self.stats["stored"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(MaterialWeaknessCollector)
