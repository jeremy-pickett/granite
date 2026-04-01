"""
Auditor Signals — derive IALD signals from raw_auditor_changes.

Signals produced:
  - auditor_change: Auditor appointment, resignation, or disagreement.
                    Any auditor change is a yellow flag. Multiple changes
                    or a change that coincides with other governance signals
                    (material weakness, late filing) is a red one. Arthur
                    Andersen walked away from Enron. SMCI's auditor resigned.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("auditor_signals")

# --- A3: Auditor tier classification ---
# Tier 1 = Big 4, Tier 2 = next-tier national firms, Tier 3 = regional/small/unknown
AUDITOR_TIERS = {
    # Tier 1: Big 4
    "deloitte": 1, "ernst & young": 1, "ey ": 1, "kpmg": 1,
    "pricewaterhousecoopers": 1, "pwc": 1,
    # Tier 2: Next tier
    "bdo": 2, "grant thornton": 2, "rsm": 2, "crowe": 2,
    "baker tilly": 2, "marcum": 2,
    # Tier 3: default for everything else
}


def _get_auditor_tier(name: str) -> int:
    """Return auditor tier (1=Big4, 2=national, 3=regional/unknown).

    Used downstream when text parsing extracts auditor firm names from
    8-K Item 4.01 filings. For now, provides the lookup infrastructure.
    """
    if not name:
        return 3
    lower = name.lower()
    for keyword, tier in AUDITOR_TIERS.items():
        if keyword in lower:
            return tier
    return 3


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=730)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.security_id, s.ticker,
                       count(*) AS filing_count,
                       max(r.filing_date) AS most_recent,
                       bool_or(COALESCE(r.has_disagreement, false)) AS any_disagreement
                FROM raw_auditor_changes r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.filing_date >= %s
                GROUP BY r.security_id, s.ticker
            """, (cutoff,))
            rows = cur.fetchall()

            # A4: Silence Before Storm — securities with a change in the
            # 2-year window but NO changes in the 8+ years before that.
            # First change in a decade = amplified signal.
            silence_cutoff = (datetime.now(timezone.utc) - timedelta(days=730 + 8 * 365)).date()
            try:
                cur.execute("""
                    SELECT DISTINCT recent.security_id
                    FROM raw_auditor_changes recent
                    WHERE recent.filing_date >= %s
                      AND NOT EXISTS (
                          SELECT 1 FROM raw_auditor_changes older
                          WHERE older.security_id = recent.security_id
                            AND older.filing_date < %s
                            AND older.filing_date >= %s
                      )
                """, (cutoff, cutoff, silence_cutoff))
                silence_sids = {row[0] for row in cur.fetchall()}
            except Exception:
                silence_sids = set()

    for sid, ticker, filing_count, most_recent, any_disagreement in rows:
        # Even a single auditor change is meaningful
        # Multiple = escalating instability
        contribution = min(filing_count / 4.0, 1.0)

        if filing_count >= 3:
            magnitude = "extreme"
        elif filing_count >= 2:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        days_ago = (datetime.now(timezone.utc).date() - most_recent).days
        confidence = 0.80 if days_ago < 365 else 0.60

        desc = f"{ticker} {filing_count} auditor changes, most recent {most_recent}"

        # B2: Disagreement disclosed — escalate to near-maximum severity
        if any_disagreement:
            contribution = max(contribution, 0.90)
            confidence = 0.90
            magnitude = "extreme"
            desc += " — DISAGREEMENT DISCLOSED"

        # A4: Silence Before Storm — first auditor change in 10+ years
        if sid in silence_sids:
            contribution = min(contribution * 1.5, 1.0)
            desc += " — FIRST CHANGE IN 10+ YEARS"

        signals.append({
            "security_id": sid,
            "signal_type": "auditor_change",
            "contribution": round(contribution, 4),
            "confidence": confidence,
            "direction": "bearish",
            "magnitude": magnitude,
            "raw_value": float(filing_count),
            "description": desc,
            "detected_at": now,
        })

    if signals:
        from psycopg2.extras import execute_values
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO signals
                           (security_id, signal_type, contribution, confidence,
                            direction, magnitude, raw_value, description, detected_at)
                       VALUES %s
                       ON CONFLICT (security_id, signal_type, detected_at)
                       DO UPDATE SET contribution = GREATEST(EXCLUDED.contribution, signals.contribution),
                                     confidence = GREATEST(EXCLUDED.confidence, signals.confidence)""",
                    [(s["security_id"], s["signal_type"], s["contribution"],
                      s["confidence"], s["direction"], s["magnitude"],
                      s["raw_value"], s["description"], s["detected_at"])
                     for s in signals],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                )

    log.info("Auditor signals: %d securities flagged → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
