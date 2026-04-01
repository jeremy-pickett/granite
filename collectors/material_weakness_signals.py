"""
Material Weakness Signals — derive IALD signals from FOUR raw tables:

  1. raw_material_weaknesses  — "material weakness" in 10-K/10-Q (EFTS)
  2. raw_late_filings         — NT 10-K/10-Q (can't file on time)
  3. raw_financial_restatements — 8-K Item 4.02 + "restatement" in amendments
  4. raw_going_concern        — "going concern" + "substantial doubt"

Signals produced:
  - material_weakness: Composite score from all four sources.
    Each source has a severity multiplier:
      going_concern   → 4x auditor_report / 2x mda / 1x risk_factors / 3x legacy
      restatement     → 2x (3x if serial: 2+ within 365 days)
      late_filing     → 2x (3x if consecutive NT filings)
      material_weakness → 1x (disclosed internal control failure)
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("material_weakness_signals")

# Severity multipliers per source
SOURCE_WEIGHT = {
    "going_concern": 3.0,
    "restatement": 2.0,
    "item_4.02": 2.5,
    "late_filing": 2.0,
    "material_weakness": 1.0,
}


def _safe_table_query(cur, table, cutoff):
    """Query a table, returning empty list if it doesn't exist yet."""
    try:
        cur.execute(f"""
            SELECT r.security_id, s.ticker,
                   count(*) AS cnt,
                   max(r.filing_date) AS most_recent
            FROM {table} r
            JOIN securities s ON s.security_id = r.security_id
            WHERE r.filing_date >= %s
            GROUP BY r.security_id, s.ticker
        """, (cutoff,))
        return cur.fetchall()
    except Exception:
        cur.execute("ROLLBACK")
        cur.execute("BEGIN")
        return []


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=730)).date()

    # Accumulate per-security: { sid: { ticker, sources: { source: (count, most_recent) } } }
    scores: dict[int, dict] = {}

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # 1. Material weakness filings
            for row in _safe_table_query(cur, "raw_material_weaknesses", cutoff):
                sid, ticker, cnt, recent = row
                scores.setdefault(sid, {"ticker": ticker, "sources": {}})
                scores[sid]["sources"]["material_weakness"] = (cnt, recent)

            # 2. Late filings
            for row in _safe_table_query(cur, "raw_late_filings", cutoff):
                sid, ticker, cnt, recent = row
                scores.setdefault(sid, {"ticker": ticker, "sources": {}})
                scores[sid]["sources"]["late_filing"] = (cnt, recent)

            # 2b. Check for consecutive NT filings (2+ in 365 days) → escalate weight
            consecutive_sids = set()
            try:
                cur.execute("""
                    SELECT security_id
                    FROM raw_late_filings
                    WHERE filing_date >= %s AND is_consecutive = true
                    GROUP BY security_id
                    HAVING count(*) >= 2
                """, (cutoff,))
                consecutive_sids = {row[0] for row in cur.fetchall()}
            except Exception:
                cur.execute("ROLLBACK")
                cur.execute("BEGIN")

            # 3. Financial restatements (split by source_type)
            # C2: Detect serial restatements — 2+ restatements for the same
            # security with filing dates within 365 days of each other.
            # These get escalated from 2x to 3x weight.
            serial_restatement_sids: set = set()
            try:
                cur.execute("""
                    SELECT DISTINCT a.security_id
                    FROM raw_financial_restatements a
                    JOIN raw_financial_restatements b
                      ON a.security_id = b.security_id
                     AND a.ctid <> b.ctid
                     AND abs(a.filing_date - b.filing_date) <= 365
                    WHERE a.filing_date >= %s
                """, (cutoff,))
                serial_restatement_sids = {row[0] for row in cur.fetchall()}
            except Exception:
                cur.execute("ROLLBACK")
                cur.execute("BEGIN")

            try:
                cur.execute("""
                    SELECT r.security_id, s.ticker, r.source_type,
                           count(*) AS cnt,
                           max(r.filing_date) AS most_recent
                    FROM raw_financial_restatements r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.filing_date >= %s
                    GROUP BY r.security_id, s.ticker, r.source_type
                """, (cutoff,))
                for sid, ticker, src_type, cnt, recent in cur.fetchall():
                    scores.setdefault(sid, {"ticker": ticker, "sources": {}})
                    scores[sid]["sources"][src_type] = (cnt, recent)
            except Exception:
                cur.execute("ROLLBACK")
                cur.execute("BEGIN")

            # 4. Going concern — C3: weight by section_type if available
            #   auditor_report → 4x (most severe), mda → 2x,
            #   risk_factors → 1x (boilerplate), NULL (legacy) → 3x
            gc_section_weights = {
                "auditor_report": 4.0,
                "mda": 2.0,
                "risk_factors": 1.0,
            }
            try:
                cur.execute("""
                    SELECT r.security_id, s.ticker,
                           r.section_type,
                           count(*) AS cnt,
                           max(r.filing_date) AS most_recent
                    FROM raw_going_concern r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.filing_date >= %s
                    GROUP BY r.security_id, s.ticker, r.section_type
                """, (cutoff,))
                for sid, ticker, section_type, cnt, recent in cur.fetchall():
                    scores.setdefault(sid, {"ticker": ticker, "sources": {}})
                    # Use section-specific weight, NULL defaults to 3x (legacy)
                    gc_weight = gc_section_weights.get(section_type, 3.0)
                    # Store as going_concern with the highest-severity weight winning
                    existing = scores[sid]["sources"].get("going_concern")
                    if existing is None:
                        scores[sid]["sources"]["going_concern"] = (cnt, recent)
                        scores[sid].setdefault("gc_weight", gc_weight)
                    else:
                        old_cnt, old_recent = existing
                        scores[sid]["sources"]["going_concern"] = (
                            old_cnt + cnt,
                            max(old_recent, recent) if old_recent and recent else (old_recent or recent),
                        )
                        scores[sid]["gc_weight"] = max(scores[sid].get("gc_weight", 3.0), gc_weight)
            except Exception:
                # Fallback if section_type column doesn't exist yet
                cur.execute("ROLLBACK")
                cur.execute("BEGIN")
                for row in _safe_table_query(cur, "raw_going_concern", cutoff):
                    sid, ticker, cnt, recent = row
                    scores.setdefault(sid, {"ticker": ticker, "sources": {}})
                    scores[sid]["sources"]["going_concern"] = (cnt, recent)

    signals = []
    for sid, info in scores.items():
        ticker = info["ticker"]
        sources = info["sources"]

        # Compute weighted severity
        weighted_total = 0.0
        total_filings = 0
        most_recent = None
        desc_parts = [ticker]

        for src, (cnt, recent) in sources.items():
            weight = SOURCE_WEIGHT.get(src, 1.0)
            # C3: Going concern weight from section_type (auditor=4x, mda=2x, risk=1x)
            if src == "going_concern" and "gc_weight" in info:
                weight = info["gc_weight"]
            # Consecutive NT filings (2+ in 365 days) → escalate from 2x to 3x
            if src == "late_filing" and sid in consecutive_sids:
                weight = 3.0
            # C2: Serial restatements (2+ within 365 days) → escalate from 2x to 3x
            if src == "restatement" and sid in serial_restatement_sids:
                weight = 3.0
            weighted_total += cnt * weight
            total_filings += cnt
            if most_recent is None or recent > most_recent:
                most_recent = recent
            desc_parts.append(f"{cnt} {src.replace('_', ' ')}")

        contribution = min(weighted_total / 8.0, 1.0)

        if weighted_total >= 8:
            magnitude = "extreme"
        elif weighted_total >= 4:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        # Confidence: higher if recent, higher if multiple sources
        days_ago = (datetime.now(timezone.utc).date() - most_recent).days if most_recent else 999
        base_confidence = 0.85 if days_ago < 365 else 0.65
        # Bonus for multiple independent sources (max +0.10)
        source_bonus = min(len(sources) * 0.05, 0.10)
        confidence = min(base_confidence + source_bonus, 0.95)

        desc_parts.append(f"most recent {most_recent}")

        signals.append({
            "security_id": sid,
            "signal_type": "material_weakness",
            "contribution": round(contribution, 4),
            "confidence": round(confidence, 4),
            "direction": "bearish",
            "magnitude": magnitude,
            "raw_value": float(total_filings),
            "description": ", ".join(desc_parts),
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

    log.info("Material weakness signals: %d securities flagged → %d signals "
             "(from %d source tables)", len(scores), len(signals),
             sum(1 for s in scores.values() if s["sources"]))
    return len(signals)


if __name__ == "__main__":
    run()
