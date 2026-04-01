"""
PE Signals — detect private equity predatory patterns from PE activity + debt data.

Signals produced:
  - going_private_detected: Recent going-private or tender offer filing
  - debt_loading_spike: Rapid debt-to-equity increase or excessive interest burden
  - pe_distress_pattern: PE activity + governance failure co-occurrence (the kill shot)

The pe_distress_pattern is the highest-conviction PE predation signal:
a company that has recently been subject to PE activity AND is showing
governance distress (material weakness, auditor change, C-suite exodus)
is likely in the strip-and-dump death spiral.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("pe_signals")


def _safe_query(cur, query, params):
    """Execute a query, returning empty list if the table doesn't exist yet."""
    try:
        cur.execute(query, params)
        return cur.fetchall()
    except Exception:
        cur.execute("ROLLBACK")
        cur.execute("BEGIN")
        return []


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                              microsecond=0, tzinfo=None)
    cutoff_365 = (datetime.now(timezone.utc) - timedelta(days=365)).date()
    cutoff_90 = (datetime.now(timezone.utc) - timedelta(days=90)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:

            # ── Signal 1: going_private_detected ─────────────────────────
            # Recent going-private, tender offer, or merger events
            pe_events = _safe_query(cur, """
                SELECT r.security_id, s.ticker, r.event_type,
                       count(*) AS cnt, max(r.filing_date) AS most_recent
                FROM raw_pe_activity r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.filing_date >= %s
                  AND r.event_type IN ('going_private', 'tender_offer',
                                       'merger_agreement', 'acquisition_complete')
                GROUP BY r.security_id, s.ticker, r.event_type
            """, (cutoff_365,))

            pe_sids = set()
            for sid, ticker, event_type, cnt, most_recent in pe_events:
                pe_sids.add(sid)

                # Going-private is the strongest signal
                if event_type == "going_private":
                    contribution = 0.80
                elif event_type == "tender_offer":
                    contribution = 0.60
                elif event_type == "merger_agreement":
                    contribution = 0.50
                else:
                    contribution = 0.40

                # Boost for multiple events
                if cnt >= 3:
                    contribution = min(contribution + 0.15, 1.0)
                elif cnt >= 2:
                    contribution = min(contribution + 0.08, 1.0)

                days_ago = (datetime.now(timezone.utc).date() - most_recent).days if most_recent else 999
                confidence = 0.90 if days_ago < 90 else 0.75 if days_ago < 180 else 0.60

                magnitude = "extreme" if contribution >= 0.7 else \
                            "strong" if contribution >= 0.5 else "moderate"

                signals.append({
                    "security_id": sid,
                    "signal_type": "going_private_detected",
                    "contribution": round(contribution, 4),
                    "confidence": round(confidence, 4),
                    "direction": "neutral",
                    "magnitude": magnitude,
                    "raw_value": float(cnt),
                    "description": f"{ticker}: {cnt} {event_type.replace('_', ' ')} event(s), most recent {most_recent}",
                    "detected_at": now,
                })

            # ── Signal 2: debt_loading_spike ─────────────────────────────
            # Look for securities where debt-to-equity increased >2x
            # across available quarters, or interest burden > 30% of revenue
            debt_spikes = _safe_query(cur, """
                WITH quarterly AS (
                    SELECT security_id, period_date,
                           debt_to_equity,
                           interest_to_revenue,
                           ROW_NUMBER() OVER (PARTITION BY security_id ORDER BY period_date DESC) AS rn
                    FROM raw_debt_metrics
                    WHERE period_date >= %s
                      AND debt_to_equity IS NOT NULL
                )
                SELECT q1.security_id, s.ticker,
                       q1.debt_to_equity AS latest_dte,
                       q4.debt_to_equity AS oldest_dte,
                       q1.interest_to_revenue AS latest_itr
                FROM quarterly q1
                JOIN quarterly q4 ON q1.security_id = q4.security_id AND q4.rn = 4
                JOIN securities s ON s.security_id = q1.security_id
                WHERE q1.rn = 1
                  AND (
                      -- Debt-to-equity increased >2x
                      (q4.debt_to_equity > 0 AND q1.debt_to_equity / q4.debt_to_equity > 2.0)
                      -- OR interest eating >30% of revenue
                      OR q1.interest_to_revenue > 0.30
                  )
            """, (cutoff_365,))

            for sid, ticker, latest_dte, oldest_dte, latest_itr in debt_spikes:
                # Compute contribution based on severity
                ratio_change = 0.0
                if oldest_dte and oldest_dte > 0:
                    ratio_change = latest_dte / oldest_dte

                # Primary metric: debt ratio explosion
                contrib_dte = min(ratio_change / 5.0, 1.0) if ratio_change > 2.0 else 0.0

                # Secondary metric: interest burden
                contrib_itr = 0.0
                if latest_itr and latest_itr > 0.30:
                    contrib_itr = min(latest_itr / 0.60, 1.0)

                contribution = max(contrib_dte, contrib_itr)
                if contribution < 0.15:
                    continue

                magnitude = "extreme" if contribution >= 0.7 else \
                            "strong" if contribution >= 0.4 else "moderate"

                desc_parts = [ticker]
                if ratio_change > 2.0:
                    desc_parts.append(f"D/E ratio {ratio_change:.1f}x increase")
                if latest_itr and latest_itr > 0.30:
                    desc_parts.append(f"interest/revenue {latest_itr:.1%}")

                signals.append({
                    "security_id": sid,
                    "signal_type": "debt_loading_spike",
                    "contribution": round(contribution, 4),
                    "confidence": 0.80,
                    "direction": "bearish",
                    "magnitude": magnitude,
                    "raw_value": round(ratio_change, 4),
                    "description": ", ".join(desc_parts)[:300],
                    "detected_at": now,
                })

            # ── Signal 3: pe_distress_pattern ────────────────────────────
            # Cross-reference: security has PE activity AND governance distress
            # within 365 days. This is "loaded with debt, now governance is failing."
            if pe_sids:
                distress_signals = _safe_query(cur, """
                    SELECT DISTINCT security_id, signal_type
                    FROM signals
                    WHERE security_id = ANY(%s)
                      AND signal_type IN ('material_weakness', 'auditor_change',
                                          'csuite_exodus', 'governance_crisis')
                      AND detected_at >= %s
                """, (list(pe_sids), now - timedelta(days=365)))

                # Group distress signals by security
                distress_by_sid: dict[int, list[str]] = {}
                for sid, stype in distress_signals:
                    distress_by_sid.setdefault(sid, []).append(stype)

                for sid, distress_types in distress_by_sid.items():
                    # Look up ticker
                    ticker = "?"
                    for evt_sid, evt_ticker, *_ in pe_events:
                        if evt_sid == sid:
                            ticker = evt_ticker
                            break

                    # More co-occurring distress signals = higher severity
                    n_distress = len(set(distress_types))
                    contribution = 0.95 if n_distress >= 2 else 0.85

                    desc = (f"{ticker}: PE activity + {', '.join(set(distress_types))} "
                            f"({n_distress} governance signals)")

                    signals.append({
                        "security_id": sid,
                        "signal_type": "pe_distress_pattern",
                        "contribution": round(contribution, 4),
                        "confidence": 0.90,
                        "direction": "bearish",
                        "magnitude": "extreme",
                        "raw_value": float(n_distress),
                        "description": desc[:300],
                        "detected_at": now,
                    })

    # Write signals to DB
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

    log.info("PE signals: %d going_private, %d debt_loading, %d distress_pattern → %d total",
             sum(1 for s in signals if s["signal_type"] == "going_private_detected"),
             sum(1 for s in signals if s["signal_type"] == "debt_loading_spike"),
             sum(1 for s in signals if s["signal_type"] == "pe_distress_pattern"),
             len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
