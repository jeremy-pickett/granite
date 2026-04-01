"""
Going Concern Collector — auditor going concern opinions via EDGAR EFTS.

Feeds into: material_weakness signal
Table:       raw_going_concern

When an auditor issues a "going concern" opinion, they're saying the
company may not survive another 12 months. This is the most severe
auditor warning short of refusing to sign. For a company in our
universe to have this — that's defcon 1.

Data source: SEC EDGAR EFTS full-text search (free).
"""

import sys
import os
import re
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
from edgar_utils import EDGAR_UA, get_cik, load_cik_map
import config
import db

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"


class GoingConcernCollector(BaseCollector):

    COLLECTOR_ID = 9  # shares Material Weakness Scanner ID — same signal family
    COLLECTOR_NAME = "Going Concern Scanner"
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
                    CREATE TABLE IF NOT EXISTS raw_going_concern (
                        concern_id      SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(20) NOT NULL,
                        accession       TEXT NOT NULL,
                        filer_name      TEXT,
                        filing_url      TEXT,
                        section_type    VARCHAR(30),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rgc_security
                        ON raw_going_concern (security_id, filing_date DESC);
                """)
                # Add section_type column if table already exists without it
                try:
                    cur.execute("""
                        ALTER TABLE raw_going_concern
                        ADD COLUMN IF NOT EXISTS section_type VARCHAR(30)
                    """)
                except Exception:
                    pass

    def fetch(self, securities):
        for s in securities:
            if s["security_type"] != "equity":
                continue
            cik = get_cik(s["ticker"])
            if cik:
                self._cik_to_sid[cik] = s["security_id"]

        self.log.info("Mapped %d securities to CIKs", len(self._cik_to_sid))

        # Search for "going concern" AND "substantial doubt" — the legal language
        # that auditors must use. Just "going concern" alone is too noisy (appears
        # in boilerplate discussions). The combination is the actual warning.
        all_hits = []

        for query, label in [
            ('"substantial doubt" "going concern"', "going_concern"),
            ('"going concern" "ability to continue"', "going_concern_alt"),
        ]:
            hits = self._efts_search(query, label)
            all_hits.extend(hits)

        return all_hits

    def _efts_search(self, query, label):
        hits = []
        offset = 0
        self.log.info("EFTS searching: %s", query)

        while True:
            try:
                resp = requests.get(
                    EFTS_URL,
                    params={
                        "q": query,
                        "forms": "10-K,10-K/A,10-Q,10-Q/A",
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
                                "filer_name": (src.get("display_names") or [""])[0][:300],
                            })

                self.stats["fetched"] += len(page_hits)
                offset += 100

                if offset % 500 == 0:
                    self.log.info("  %s progress: %d/%d scanned, %d matched", label, offset, total, len(hits))
                if offset >= total:
                    break
                time.sleep(0.2)

            except requests.RequestException as e:
                self.log.warning("EFTS error at offset %d: %s", offset, e)
                self.stats["errors"] += 1
                offset += 100

        self.log.info("  %s: %d hits in our universe", label, len(hits))
        return hits

    # C3: Section classification patterns for "going concern" mentions
    _AUDITOR_PATTERNS = re.compile(
        r"(auditor|independent registered|report of independent|opinion of independent)",
        re.IGNORECASE,
    )
    _MDA_PATTERNS = re.compile(
        r"(management.s discussion|md&a|management discussion)",
        re.IGNORECASE,
    )

    def _classify_section(self, filing_url):
        """Download first 15KB of filing text and classify going concern section."""
        try:
            resp = requests.get(
                filing_url,
                headers={"User-Agent": EDGAR_UA, "Range": "bytes=0-15000"},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code not in (200, 206):
                return None
            text = resp.text.lower()

            # Find "going concern" mentions and check surrounding context
            for match in re.finditer(r"going concern", text):
                # Look at 500 chars before the match for section headers
                start = max(0, match.start() - 500)
                context = text[start:match.start()]
                if self._AUDITOR_PATTERNS.search(context):
                    return "auditor_report"
                if self._MDA_PATTERNS.search(context):
                    return "mda"

            # If we found the text but no section matched, it's likely risk factors
            if "going concern" in text:
                return "risk_factors"
            return None
        except requests.RequestException:
            return None

    def transform(self, raw_data, securities):
        seen = set()
        rows = []
        for r in raw_data:
            key = (r["security_id"], r["accession"])
            if key in seen:
                continue
            seen.add(key)
            cik_num = ""
            for cik, sid in self._cik_to_sid.items():
                if sid == r["security_id"]:
                    cik_num = cik.lstrip("0") or "0"
                    break
            acc_clean = r["accession"].replace("-", "")
            r["filing_url"] = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{r['accession']}-index.htm"

            # C3: Classify which section contains the going concern language
            r["section_type"] = self._classify_section(r["filing_url"])
            # Rate limit: SEC fair access
            time.sleep(0.15)

            rows.append(r)
        return rows

    def store(self, rows):
        self.log.info("Writing %d going concern records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_going_concern
                           (security_id, filing_date, form_type, accession, filer_name,
                            filing_url, section_type)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now(),
                                     section_type = COALESCE(EXCLUDED.section_type, raw_going_concern.section_type)""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["accession"], r["filer_name"], r["filing_url"],
                      r.get("section_type"))
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Going concern: %d scanned, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(GoingConcernCollector)
