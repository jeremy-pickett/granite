"""
Executive Background Check Collector
Searches for criminal records, pending litigation, financial problems,
and warrants for executives/directors associated with each security.

Uses PACER/CourtListener for federal litigation, SEC EDGAR for enforcement
actions, and public records searches for criminal/financial red flags.

Collector ID: 44
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

# CourtListener free API (RECAP archive)
COURTLISTENER_URL = "https://www.courtlistener.com/api/rest/v3"

# SEC enforcement actions
SEC_ENFORCEMENT_URL = "https://efts.sec.gov/LATEST/search-index"


class ExecutiveBackgroundCollector(BaseCollector):

    COLLECTOR_ID = 44
    COLLECTOR_NAME = "Executive Background"
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
                    CREATE TABLE IF NOT EXISTS raw_executive_background (
                        id              SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        executive_name  TEXT NOT NULL,
                        check_type      TEXT NOT NULL,
                        finding         TEXT NOT NULL,
                        severity        TEXT,
                        source          TEXT,
                        source_url      TEXT,
                        case_date       DATE,
                        collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                        last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE(security_id, executive_name, check_type, finding)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_exec_bg_security
                    ON raw_executive_background(security_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_exec_bg_name
                    ON raw_executive_background(executive_name)
                """)

    def fetch(self, securities):
        results = []

        for sec in securities:
            sid = sec["security_id"]
            ticker = sec["ticker"]

            # Get executives for this security from raw_executives
            executives = self._get_executives(sid)
            if not executives:
                self.stats["skipped"] += 1
                continue

            for exec_name, exec_title in executives:
                # 1. Check SEC enforcement actions
                sec_findings = self._check_sec_enforcement(exec_name, sid)
                results.extend(sec_findings)

                # 2. Check CourtListener for federal litigation
                court_findings = self._check_courtlistener(exec_name, sid)
                results.extend(court_findings)

                # 3. Check SEC EDGAR for personal filings/mentions
                edgar_findings = self._check_edgar_personal(exec_name, sid)
                results.extend(edgar_findings)

                self.stats["fetched"] += 1
                time.sleep(0.5)

            log.info("%s: checked %d executives", ticker, len(executives))

        return results

    def _get_executives(self, security_id: int) -> list:
        """Pull executive names from raw_executives table."""
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT name, title FROM (
                          SELECT DISTINCT ON (name) name, title, role_type
                          FROM raw_executives
                          WHERE security_id = %s
                          ORDER BY name,
                            CASE role_type
                              WHEN 'c-suite' THEN 1
                              WHEN 'director' THEN 2
                              WHEN 'vp' THEN 3
                              ELSE 4
                            END
                        ) sub
                        ORDER BY
                          CASE role_type
                            WHEN 'c-suite' THEN 1
                            WHEN 'director' THEN 2
                            WHEN 'vp' THEN 3
                            ELSE 4
                          END
                        LIMIT 20
                    """, (security_id,))
                    return cur.fetchall()
        except Exception:
            return []

    def _check_sec_enforcement(self, name: str, security_id: int) -> list:
        """Search SEC enforcement actions for the person's name."""
        findings = []
        try:
            resp = self._session.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={
                    "q": f'"{name}"',
                    "forms": "LIT-REL,AAER",
                    "dateRange": "custom",
                    "startdt": "2015-01-01",
                },
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                for hit in hits[:5]:
                    source = hit.get("_source", {})
                    title = source.get("display_names", ["SEC Action"])[0] if source.get("display_names") else "SEC Action"
                    date = source.get("file_date")

                    findings.append({
                        "security_id": security_id,
                        "executive_name": name,
                        "check_type": "sec_enforcement",
                        "finding": title[:500],
                        "severity": "high",
                        "source": "SEC EDGAR",
                        "source_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={name}&type=&dateb=&owner=include&count=10",
                        "case_date": date,
                    })
        except Exception as e:
            log.debug("SEC enforcement check failed for %s: %s", name, e)

        return findings

    def _check_courtlistener(self, name: str, security_id: int) -> list:
        """Search CourtListener RECAP for federal civil/criminal cases."""
        findings = []
        try:
            resp = self._session.get(
                f"{COURTLISTENER_URL}/search/",
                params={
                    "q": f'"{name}"',
                    "type": "r",  # RECAP
                    "order_by": "score desc",
                },
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                for result in data.get("results", [])[:5]:
                    case_name = result.get("caseName", "")
                    court = result.get("court", "")
                    date = result.get("dateFiled")

                    # Determine severity by case type
                    severity = "medium"
                    case_lower = case_name.lower()
                    if any(k in case_lower for k in ["criminal", "indictment", "fraud", "embezzlement"]):
                        severity = "critical"
                    elif any(k in case_lower for k in ["bankruptcy", "foreclosure", "default"]):
                        severity = "high"
                    elif any(k in case_lower for k in ["securities", "sec v.", "ftc v."]):
                        severity = "high"

                    findings.append({
                        "security_id": security_id,
                        "executive_name": name,
                        "check_type": "litigation",
                        "finding": f"{case_name} ({court})"[:500],
                        "severity": severity,
                        "source": "CourtListener",
                        "source_url": result.get("absolute_url", ""),
                        "case_date": date,
                    })
        except Exception as e:
            log.debug("CourtListener check failed for %s: %s", name, e)

        return findings

    def _check_edgar_personal(self, name: str, security_id: int) -> list:
        """Search EDGAR full-text for personal bankruptcy, judgments, etc."""
        findings = []
        try:
            # Search for person in context of negative financial events
            for check_type, keywords in [
                ("personal_bankruptcy", f'"{name}" AND (bankruptcy OR "chapter 7" OR "chapter 11")'),
                ("financial_judgment", f'"{name}" AND (judgment OR lien OR garnishment)'),
                ("regulatory_bar", f'"{name}" AND ("barred" OR "suspended" OR "cease and desist")'),
            ]:
                resp = self._session.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={
                        "q": keywords,
                        "dateRange": "custom",
                        "startdt": "2015-01-01",
                    },
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    total = data.get("hits", {}).get("total", {}).get("value", 0)
                    if total > 0:
                        hits = data.get("hits", {}).get("hits", [])
                        for hit in hits[:3]:
                            source = hit.get("_source", {})
                            desc = source.get("display_names", [check_type])[0] if source.get("display_names") else check_type
                            date = source.get("file_date")

                            findings.append({
                                "security_id": security_id,
                                "executive_name": name,
                                "check_type": check_type,
                                "finding": desc[:500],
                                "severity": "high" if "bankruptcy" in check_type else "medium",
                                "source": "SEC EDGAR",
                                "source_url": None,
                                "case_date": date,
                            })

                time.sleep(0.3)

        except Exception as e:
            log.debug("EDGAR personal check failed for %s: %s", name, e)

        return findings

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        if not rows:
            return

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for r in rows:
                    cur.execute("""
                        INSERT INTO raw_executive_background
                            (security_id, executive_name, check_type, finding,
                             severity, source, source_url, case_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (security_id, executive_name, check_type, finding)
                        DO UPDATE SET last_updated = now()
                    """, (
                        r["security_id"], r["executive_name"], r["check_type"],
                        r["finding"], r.get("severity"), r.get("source"),
                        r.get("source_url"), r.get("case_date"),
                    ))

        super().store(rows)
        log.info("Stored %d background findings", len(rows))


if __name__ == "__main__":
    run_collector(ExecutiveBackgroundCollector)
