"""
Executive Profiles Collector — Board of Directors & C-Suite

Two-source strategy:
  1. Seed from raw_insider_trades (Form 4 reporter_name — already collected)
  2. Enrich from SEC EDGAR submissions API (company JSON has officer names)

Writes to raw_executives with timestamps for historical tracking.

Collector ID: 42
"""

import sys
import os
import re
import time
import logging
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
import config
import db

log = logging.getLogger(__name__)

# CIK cache
_cik_cache: dict[str, str] = {}


class ExecutiveProfilesCollector(BaseCollector):

    COLLECTOR_ID = 42
    COLLECTOR_NAME = "Executive Profiles"
    COLLECTOR_TYPE = "sec_filing"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "Alidade/1.0 (research@signaldelta.com)"
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_executives (
                        id              SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        name            TEXT NOT NULL,
                        title           TEXT,
                        age             INT,
                        since           INT,
                        compensation    BIGINT,
                        currency        TEXT,
                        sex             TEXT,
                        headshot_url    TEXT,
                        role_type       TEXT,
                        collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                        last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
                        batch_id        TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(security_id, name, title)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_raw_exec_security
                    ON raw_executives(security_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_raw_exec_batch
                    ON raw_executives(batch_id)
                """)

    def fetch(self, securities):
        results = []
        batch_time = time.strftime("%Y-%m-%d %H:%M:%S+00")
        seen = set()  # (security_id, name) dedup

        # ── Source 1: Seed from existing Form 4 insider trades ────────
        log.info("Seeding from raw_insider_trades...")
        sid_map = {sec["security_id"]: sec for sec in securities}
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT security_id, reporter_name
                        FROM raw_insider_trades
                        WHERE reporter_name IS NOT NULL
                        ORDER BY security_id
                    """)
                    for sid, name in cur.fetchall():
                        name = name.strip()
                        if not name or sid not in sid_map:
                            continue
                        key = (sid, name.lower())
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append({
                            "security_id": sid,
                            "name": name,
                            "title": "Insider (Form 4)",
                            "age": None,
                            "since": None,
                            "compensation": None,
                            "currency": "USD",
                            "sex": None,
                            "headshot_url": None,
                            "role_type": self._classify_role("insider"),
                            "batch_time": batch_time,
                        })
                        self.stats["fetched"] += 1
        except Exception as e:
            log.warning("Failed to seed from insider trades: %s", e)

        log.info("Seeded %d insiders from Form 4 data", len(results))

        # ── Source 2: SEC EDGAR submissions API ──────────────────────
        log.info("Enriching from SEC EDGAR submissions...")
        for sec in securities:
            ticker = sec["ticker"]
            sid = sec["security_id"]

            try:
                cik = self._lookup_cik(ticker)
                if not cik:
                    continue

                resp = self._session.get(
                    f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json",
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()

                # Some EDGAR submission JSONs include officer info
                # Check the recent filings for DEF 14A proxy statements
                recent = data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                accessions = recent.get("accessionNumber", [])
                dates = recent.get("filingDate", [])
                primary_docs = recent.get("primaryDocument", [])

                for i, form in enumerate(forms[:30]):
                    if form in ("DEF 14A", "DEF 14A/A"):
                        # Found a proxy statement — try to extract officer names
                        accession = accessions[i].replace("-", "")
                        doc = primary_docs[i] if i < len(primary_docs) else None
                        if doc:
                            officers = self._extract_officers_from_proxy(cik, accession, doc)
                            for name, title in officers:
                                key = (sid, name.lower())
                                if key in seen:
                                    continue
                                seen.add(key)
                                results.append({
                                    "security_id": sid,
                                    "name": name,
                                    "title": title,
                                    "age": None,
                                    "since": None,
                                    "compensation": None,
                                    "currency": "USD",
                                    "sex": None,
                                    "headshot_url": None,
                                    "role_type": self._classify_role(title),
                                    "batch_time": batch_time,
                                })
                                self.stats["fetched"] += 1
                        break  # only need the latest proxy

                time.sleep(0.2)  # SEC rate limit: 10 req/sec

            except Exception as e:
                log.debug("%s: EDGAR fetch failed: %s", ticker, e)

        self._batch_time = batch_time
        log.info("Total executives found: %d", len(results))
        return results

    def _lookup_cik(self, ticker: str) -> str | None:
        """Look up CIK for a ticker via SEC EDGAR."""
        if ticker in _cik_cache:
            return _cik_cache[ticker]
        try:
            resp = self._session.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={"company": "", "CIK": ticker, "type": "10-K",
                        "dateb": "", "owner": "include", "count": "1",
                        "action": "getcompany"},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                match = re.search(r"CIK=(\d+)", resp.text)
                if match:
                    _cik_cache[ticker] = match.group(1)
                    return match.group(1)
        except Exception:
            pass
        return None

    def _extract_officers_from_proxy(self, cik: str, accession: str, doc: str) -> list:
        """Extract officer/director names from a DEF 14A proxy statement."""
        officers = []
        try:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
            resp = self._session.get(url, timeout=config.HTTP_TIMEOUT)
            if resp.status_code != 200:
                return officers

            text = resp.text[:300000]
            # Strip HTML tags for text extraction
            clean = re.sub(r'<[^>]+>', ' ', text)
            clean = re.sub(r'\s+', ' ', clean)

            # Pattern: Name followed by common executive titles
            title_pattern = r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[,\-—]\s*((?:Chief|President|Vice|Chairman|Director|Secretary|Treasurer|General\s+Counsel|CEO|CFO|COO|CTO|CIO)[^.;,\n]{0,60})'
            matches = re.findall(title_pattern, clean)

            seen_names = set()
            for name, title in matches:
                name = name.strip()
                title = title.strip().rstrip(',;.')
                if name.lower() not in seen_names and len(name) > 4:
                    seen_names.add(name.lower())
                    officers.append((name, title))

        except Exception:
            pass

        return officers[:30]  # cap at 30

    def _classify_role(self, title: str) -> str:
        title_lower = (title or "").lower()
        if any(k in title_lower for k in ["ceo", "chief executive", "president"]):
            return "c-suite"
        if any(k in title_lower for k in ["cfo", "chief financial", "coo", "chief operating",
                                            "cto", "chief technology", "cio", "chief information",
                                            "chief legal", "general counsel", "cmo", "chief marketing",
                                            "chief risk", "chief compliance", "chief strategy"]):
            return "c-suite"
        if any(k in title_lower for k in ["vp", "vice president", "svp", "evp"]):
            return "vp"
        if any(k in title_lower for k in ["director", "board", "chairman", "chairwoman"]):
            return "director"
        if any(k in title_lower for k in ["secretary", "treasurer"]):
            return "officer"
        return "other"

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        if not rows:
            return

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for r in rows:
                    cur.execute("""
                        INSERT INTO raw_executives
                            (security_id, name, title, age, since, compensation,
                             currency, sex, headshot_url, role_type, batch_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (security_id, name, title)
                        DO UPDATE SET
                            age = EXCLUDED.age,
                            since = EXCLUDED.since,
                            compensation = EXCLUDED.compensation,
                            currency = EXCLUDED.currency,
                            sex = EXCLUDED.sex,
                            headshot_url = COALESCE(EXCLUDED.headshot_url, raw_executives.headshot_url),
                            role_type = EXCLUDED.role_type,
                            last_updated = now(),
                            batch_id = EXCLUDED.batch_id
                    """, (
                        r["security_id"], r["name"], r["title"], r.get("age"),
                        r.get("since"), r.get("compensation"), r.get("currency", "USD"),
                        r.get("sex"), r.get("headshot_url"), r["role_type"],
                        r["batch_time"],
                    ))

        super().store(rows)
        log.info("Stored %d executive records", len(rows))


if __name__ == "__main__":
    run_collector(ExecutiveProfilesCollector)
