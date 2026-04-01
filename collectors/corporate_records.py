"""
Corporate Records Collector — Loans, Liens, Judgments, Bankruptcies, Related LLCs

Scrapes SEC EDGAR EFTS for UCC filings, bankruptcy mentions, lien disclosures,
and related-entity references in 10-K/10-Q exhibits and footnotes.
Also queries PACER-adjacent public bankruptcy court RSS feeds.

Writes to raw_corporate_records for entity linkage and "resembles" detection.

Collector ID: 43
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

# SEC EDGAR full-text search
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FTS_URL = "https://efts.sec.gov/LATEST/search-index"

# Keywords we scan for in filings
LIEN_KEYWORDS = ["lien", "UCC filing", "UCC-1", "security interest", "pledge agreement"]
JUDGMENT_KEYWORDS = ["judgment", "judgement", "consent decree", "settlement agreement"]
BANKRUPTCY_KEYWORDS = ["bankruptcy", "chapter 11", "chapter 7", "chapter 15",
                       "reorganization", "debtor-in-possession", "DIP financing"]
LOAN_KEYWORDS = ["credit facility", "revolving credit", "term loan", "promissory note",
                 "loan agreement", "credit agreement", "indebtedness"]
LLC_KEYWORDS = ["LLC", "limited liability company", "subsidiary", "wholly-owned",
                "variable interest entity", "VIE", "consolidated entity"]


class CorporateRecordsCollector(BaseCollector):

    COLLECTOR_ID = 43
    COLLECTOR_NAME = "Corporate Records"
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
                    CREATE TABLE IF NOT EXISTS raw_corporate_records (
                        id              SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        record_type     TEXT NOT NULL,
                        description     TEXT NOT NULL,
                        source_filing   TEXT,
                        filing_date     DATE,
                        related_entity  TEXT,
                        amount          NUMERIC,
                        currency        TEXT DEFAULT 'USD',
                        collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                        last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(security_id, record_type, description, filing_date)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_related_entities (
                        id              SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        entity_name     TEXT NOT NULL,
                        entity_type     TEXT NOT NULL,
                        relationship    TEXT,
                        state           TEXT,
                        first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
                        last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(security_id, entity_name, entity_type)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_corp_records_security
                    ON raw_corporate_records(security_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_related_entities_security
                    ON raw_related_entities(security_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_related_entities_name
                    ON raw_related_entities(entity_name)
                """)

    def fetch(self, securities):
        results = []

        for sec in securities:
            ticker = sec["ticker"]
            name = sec["name"]
            cik = self._lookup_cik(ticker)
            if not cik:
                self.stats["skipped"] += 1
                continue

            try:
                filings = self._get_recent_filings(cik)
                for filing in filings:
                    records = self._scan_filing(sec, filing)
                    results.extend(records)
                    self.stats["fetched"] += len(records)

                log.info("%s: %d records from %d filings", ticker, len(results), len(filings))
            except Exception as e:
                log.warning("%s: %s", ticker, e)
                self.stats["skipped"] += 1

            time.sleep(0.3)

        return results

    def _lookup_cik(self, ticker: str) -> str | None:
        """Look up CIK from SEC EDGAR."""
        try:
            resp = self._session.get(
                f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2025-01-01&forms=10-K,10-Q",
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                if hits:
                    return hits[0].get("_source", {}).get("entity_id")
        except Exception:
            pass

        # Fallback: ticker->CIK mapping
        try:
            resp = self._session.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={"action": "getcompany", "company": ticker, "type": "10-K",
                        "dateb": "", "owner": "include", "count": "1", "search_text": "",
                        "action": "getcompany", "output": "atom"},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                match = re.search(r"CIK=(\d+)", resp.text)
                if match:
                    return match.group(1)
        except Exception:
            pass

        return None

    def _get_recent_filings(self, cik: str) -> list:
        """Get recent 10-K, 10-Q, 8-K filings from EDGAR."""
        filings = []
        try:
            resp = self._session.get(
                f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json",
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                return filings

            data = resp.json()
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            dates = recent.get("filingDate", [])
            primary_docs = recent.get("primaryDocument", [])

            for i, form in enumerate(forms[:20]):  # last 20 filings
                if form in ("10-K", "10-Q", "8-K", "10-K/A", "10-Q/A"):
                    filings.append({
                        "form": form,
                        "accession": accessions[i].replace("-", ""),
                        "date": dates[i],
                        "doc": primary_docs[i] if i < len(primary_docs) else None,
                        "cik": cik,
                    })
        except Exception as e:
            log.debug("Failed to get filings for CIK %s: %s", cik, e)

        return filings

    def _scan_filing(self, security: dict, filing: dict) -> list:
        """Download filing text and scan for relevant keywords."""
        records = []
        cik = filing["cik"].zfill(10)
        accession = filing["accession"]
        doc = filing.get("doc")

        if not doc:
            return records

        try:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
            resp = self._session.get(url, timeout=config.HTTP_TIMEOUT)
            if resp.status_code != 200:
                return records

            text = resp.text[:500000]  # cap at 500KB to avoid memory issues
            text_lower = text.lower()
            sid = security["security_id"]

            # Scan for each category
            for category, keywords in [
                ("loan", LOAN_KEYWORDS),
                ("lien", LIEN_KEYWORDS),
                ("judgment", JUDGMENT_KEYWORDS),
                ("bankruptcy", BANKRUPTCY_KEYWORDS),
            ]:
                for kw in keywords:
                    if kw.lower() in text_lower:
                        # Extract surrounding context
                        idx = text_lower.index(kw.lower())
                        start = max(0, idx - 100)
                        end = min(len(text), idx + 200)
                        context = re.sub(r'<[^>]+>', ' ', text[start:end])
                        context = re.sub(r'\s+', ' ', context).strip()

                        # Try to extract dollar amount
                        amount = self._extract_amount(text[max(0, idx - 200):idx + 300])

                        records.append({
                            "security_id": sid,
                            "record_type": category,
                            "description": context[:500],
                            "source_filing": f"{filing['form']} {filing['date']}",
                            "filing_date": filing["date"],
                            "related_entity": None,
                            "amount": amount,
                        })
                        break  # one hit per category per filing

            # Extract LLC/subsidiary names
            llc_pattern = r'([A-Z][A-Za-z0-9\s&,.\'-]+(?:LLC|L\.L\.C\.|Inc\.|Corp\.|LP|L\.P\.))'
            matches = re.findall(llc_pattern, text[:200000])
            seen = set()
            for match in matches:
                entity = match.strip()
                if len(entity) > 10 and entity not in seen and security["name"].lower() not in entity.lower():
                    seen.add(entity)
                    records.append({
                        "security_id": sid,
                        "record_type": "related_entity",
                        "description": entity,
                        "source_filing": f"{filing['form']} {filing['date']}",
                        "filing_date": filing["date"],
                        "related_entity": entity,
                        "amount": None,
                    })

        except Exception as e:
            log.debug("Failed to scan %s: %s", accession, e)

        return records

    def _extract_amount(self, text: str) -> float | None:
        """Try to extract a dollar amount from surrounding text."""
        matches = re.findall(r'\$\s?([\d,]+(?:\.\d+)?)\s*(?:million|billion)?', text, re.IGNORECASE)
        if matches:
            try:
                val = float(matches[0].replace(',', ''))
                if 'billion' in text.lower():
                    val *= 1_000_000_000
                elif 'million' in text.lower():
                    val *= 1_000_000
                return val
            except ValueError:
                pass
        return None

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        if not rows:
            return

        record_rows = [r for r in rows if r["record_type"] != "related_entity"]
        entity_rows = [r for r in rows if r["record_type"] == "related_entity"]

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for r in record_rows:
                    cur.execute("""
                        INSERT INTO raw_corporate_records
                            (security_id, record_type, description, source_filing,
                             filing_date, related_entity, amount)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (security_id, record_type, description, filing_date)
                        DO UPDATE SET last_updated = now()
                    """, (
                        r["security_id"], r["record_type"], r["description"],
                        r["source_filing"], r["filing_date"], r["related_entity"],
                        r.get("amount"),
                    ))

                for r in entity_rows:
                    entity_type = "llc" if "LLC" in r["description"] else "subsidiary"
                    cur.execute("""
                        INSERT INTO raw_related_entities
                            (security_id, entity_name, entity_type, relationship)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (security_id, entity_name, entity_type)
                        DO UPDATE SET last_seen = now()
                    """, (
                        r["security_id"], r["description"], entity_type,
                        r.get("source_filing"),
                    ))

        super().store(rows)
        log.info("Stored %d records, %d entities", len(record_rows), len(entity_rows))


if __name__ == "__main__":
    run_collector(CorporateRecordsCollector)
