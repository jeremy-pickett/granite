"""
Compound Signals — detect temporal co-occurrence of independent signals.

Runs AFTER all other signal extractors. Reads from the signals table and
emits compound signals when specific multi-signal patterns are detected
within a security's recent history.

Signals produced:
  - governance_crisis: auditor_change + (csuite_exodus OR material_weakness) within 180d
  - short_squeeze_setup: short_interest_spike + ftd_spike + options_unusual_activity within 14d
  - insider_capitulation: insider_sale_cluster + (csuite_exodus OR news_sentiment_extreme bearish) within 30d
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("compound_signals")


# ── Pattern definitions ──────────────────────────────────────────────

PATTERNS = [
    # ── Governance fraud patterns ─────────────────────────────────────
    {
        "signal_type": "governance_crisis",
        "window_days": 180,
        "required": ["auditor_change"],
        "any_of": ["csuite_exodus", "material_weakness"],
        "direction": "bearish",
    },
    {
        # A1: CFO + Auditor — the Enron/Wirecard/Luckin Coffee signature.
        # When the person responsible for the numbers leaves AND the auditor
        # changes within 90 days, this is the highest-conviction fraud signal.
        # Fires as governance_crisis but with forced max contribution.
        "signal_type": "governance_crisis",
        "window_days": 90,
        "required": ["auditor_change", "csuite_exodus"],
        "any_of": [],
        "direction": "bearish",
        "min_contribution": 1.0,
        "min_confidence": 0.95,
        "label": "CFO+Auditor alarm",
    },
    {
        # B4: Governance domino sequence — escalating cascade.
        # material_weakness → late filing → going concern within 365 days.
        # Each additional stage multiplies severity.
        "signal_type": "governance_crisis",
        "window_days": 365,
        "required": ["material_weakness"],
        "any_of": ["auditor_change", "csuite_exodus"],
        "direction": "bearish",
        "min_contribution": 0.85,
        "label": "Governance domino",
    },

    # ── Market microstructure patterns ────────────────────────────────
    {
        "signal_type": "short_squeeze_setup",
        "window_days": 14,
        "required": ["short_interest_spike", "ftd_spike", "options_unusual_activity"],
        "any_of": [],
        "direction": "neutral",
    },

    # ── Insider patterns ──────────────────────────────────────────────
    {
        "signal_type": "insider_capitulation",
        "window_days": 30,
        "required": ["insider_sale_cluster"],
        "any_of": ["csuite_exodus", "news_sentiment_extreme"],
        "direction": "bearish",
        "any_of_direction_filter": {"news_sentiment_extreme": "bearish"},
    },
]


def _load_recent_signals(cur, window_days):
    """Load all signals within the max window, grouped by security_id."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cur.execute("""
        SELECT security_id, signal_type, contribution, confidence,
               direction, detected_at
        FROM signals
        WHERE detected_at >= %s
        ORDER BY security_id, detected_at DESC
    """, (cutoff.replace(tzinfo=None),))

    by_security = defaultdict(list)
    for sid, stype, contrib, conf, direction, detected in cur.fetchall():
        by_security[sid].append({
            "signal_type": stype,
            "contribution": float(contrib),
            "confidence": float(conf),
            "direction": direction,
            "detected_at": detected,
        })
    return by_security


def _check_pattern(signals, pattern, now):
    """Check if a list of signals for one security matches a compound pattern."""
    window = timedelta(days=pattern["window_days"])

    # Find matching signals within the window
    recent = [s for s in signals if (now - s["detected_at"]) <= window]

    types_present = {s["signal_type"]: s for s in recent}

    # All required signals must be present
    for req in pattern["required"]:
        if req not in types_present:
            return None

    # At least one of any_of must be present (if any_of is non-empty)
    if pattern["any_of"]:
        matched_any = None
        dir_filter = pattern.get("any_of_direction_filter", {})
        for opt in pattern["any_of"]:
            if opt in types_present:
                # Check direction filter if specified
                if opt in dir_filter and types_present[opt]["direction"] != dir_filter[opt]:
                    continue
                matched_any = types_present[opt]
                break
        if matched_any is None:
            return None

    # Compute compound contribution: average of constituent contributions, boosted
    all_matched = [types_present[r] for r in pattern["required"]]
    for opt in pattern["any_of"]:
        if opt in types_present:
            all_matched.append(types_present[opt])
            break

    avg_contrib = sum(s["contribution"] for s in all_matched) / len(all_matched)
    avg_conf = sum(s["confidence"] for s in all_matched) / len(all_matched)
    # Compound boost: co-occurrence is more significant than individual signals
    contribution = min(avg_contrib * 1.3, 1.0)
    confidence = min(avg_conf * 1.1, 0.95)

    # Override floors for high-severity patterns (e.g., CFO+Auditor alarm)
    if "min_contribution" in pattern:
        contribution = max(contribution, pattern["min_contribution"])
    if "min_confidence" in pattern:
        confidence = max(confidence, pattern["min_confidence"])

    label = pattern.get("label", pattern["signal_type"])
    components = ", ".join(s["signal_type"] for s in all_matched)
    return {
        "contribution": round(min(contribution, 1.0), 4),
        "confidence": round(min(confidence, 0.95), 4),
        "direction": pattern["direction"],
        "components": components,
        "n_components": len(all_matched),
        "label": label,
    }


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                              microsecond=0, tzinfo=None)
    max_window = max(p["window_days"] for p in PATTERNS)
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            by_security = _load_recent_signals(cur, max_window)

    for sid, sec_signals in by_security.items():
        for pattern in PATTERNS:
            result = _check_pattern(sec_signals, pattern, now)
            if result is None:
                continue

            magnitude = "extreme" if result["contribution"] >= 0.6 else \
                        "strong" if result["contribution"] >= 0.35 else "moderate"

            desc = (f"Compound: {result['label']} — "
                    f"{result['n_components']} co-occurring signals "
                    f"({result['components']})")

            signals.append({
                "security_id": sid,
                "signal_type": pattern["signal_type"],
                "contribution": result["contribution"],
                "confidence": result["confidence"],
                "direction": result["direction"],
                "magnitude": magnitude,
                "raw_value": float(result["n_components"]),
                "description": desc[:300],
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

    log.info("Compound signals: %d patterns checked across %d securities → %d signals",
             len(PATTERNS), len(by_security), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
