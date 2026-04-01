"""
Auditor Change Monitor — SEC 8-K Item 4.01 filings via EDGAR.

Collector ID: 10 (Auditor Change Monitor)
Table:        raw_auditor_changes

Monitors auditor appointments, resignations, and disagreements from
8-K filings that include Item 4.01 (Changes in Registrant's Certifying Accountant).

Data source: SEC EDGAR (free, no API key — requires User-Agent header).
Rate limit: 10 requests/second per SEC fair access policy.
"""

import sys
import os
import re
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

from edgar_utils import EDGAR_UA, EDGAR_SUBMISSIONS, get_cik, load_cik_map


class AuditorChangeCollector(BaseCollector):

    # ── identity ──────────────────────────────────────────────────────
    COLLECTOR_ID = 10
    COLLECTOR_NAME = "Auditor Change Monitor"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_auditor_changes (
                        change_id       SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        filing_date     DATE NOT NULL,
                        form_type       VARCHAR(10),
                        accession       TEXT NOT NULL,
                        items           TEXT,
                        filing_url      TEXT,
                        has_disagreement BOOLEAN DEFAULT false,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, accession)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rac_security
                        ON raw_auditor_changes (security_id, filing_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rac_date
                        ON raw_auditor_changes (filing_date DESC);
                """)
                # Migrate existing tables: add has_disagreement if missing
                cur.execute("""
                    ALTER TABLE raw_auditor_changes
                    ADD COLUMN IF NOT EXISTS has_disagreement BOOLEAN DEFAULT false;
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """
        For each equity, pull recent filings from EDGAR and find 8-Ks
        containing Item 4.01 (auditor change disclosure).
        """
        raw = {}
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Scanning %d equities for auditor changes...", total)

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
                    data = resp.json()
                    filings = self._extract_401_filings(data)
                    if filings:
                        raw[ticker] = filings
                        self.stats["fetched"] += 1
                        self.log.info("  %s: found %d auditor-change filings", ticker, len(filings))
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

            # SEC fair-access: ~10 req/s → sleep 0.15s between requests
            time.sleep(0.15)

            if (i + 1) % 50 == 0:
                self.log.info("  Progress: %d/%d", i + 1, total)

        return raw

    def _extract_401_filings(self, submissions: dict) -> list[dict]:
        """Pull 8-K/8-K/A filings that include Item 4.01."""
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
            if "4.01" not in items:
                continue
            # Build filing URL
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

    # ── transform ─────────────────────────────────────────────────────

    # ── disagreement keywords ────────────────────────────────────────
    _DISAGREE_RE = re.compile(
        r"disagreement|reportable\s+event|reportable\s+condition|resignation",
        re.IGNORECASE,
    )

    def _check_disagreement(self, filing_url: str) -> bool:
        """Download first 10KB of filing text and scan for disagreement indicators."""
        if not filing_url:
            return False
        try:
            resp = requests.get(
                filing_url,
                headers={"User-Agent": EDGAR_UA},
                timeout=config.HTTP_TIMEOUT,
                stream=True,
            )
            if resp.status_code != 200:
                return False
            # Read only the first 10KB
            chunk = resp.raw.read(10240)
            text = chunk.decode("utf-8", errors="replace")
            return bool(self._DISAGREE_RE.search(text))
        except Exception:
            return False

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        rows = []

        for ticker, filings in raw_data.items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            for f in filings:
                has_disagreement = self._check_disagreement(f.get("filing_url"))
                if has_disagreement:
                    self.log.info("  %s accession %s: DISAGREEMENT detected", ticker, f["accession"])

                rows.append({
                    "security_id": sid,
                    "filing_date": f["filing_date"],
                    "form_type": f["form_type"],
                    "accession": f["accession"],
                    "items": f["items"],
                    "filing_url": f["filing_url"],
                    "has_disagreement": has_disagreement,
                })
                # Respect SEC rate limit between filing downloads
                time.sleep(0.15)

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        self.log.info("Writing %d auditor change records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_auditor_changes
                           (security_id, filing_date, form_type, accession, items, filing_url, has_disagreement)
                       VALUES %s
                       ON CONFLICT (security_id, accession)
                       DO UPDATE SET last_updated = now(),
                                     has_disagreement = EXCLUDED.has_disagreement""",
                    [(r["security_id"], r["filing_date"], r["form_type"],
                      r["accession"], r["items"], r["filing_url"],
                      r.get("has_disagreement", False))
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "Auditor changes: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(AuditorChangeCollector)
