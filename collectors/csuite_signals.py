"""
C-Suite Signals — derive IALD signals from raw_csuite_departures.

Signals produced:
  - csuite_exodus: Abnormal rate of executive departures.
                   Normal turnover is ~2-4 filings per year for a large company.
                   When you see 8+ in a year, or a spike of 3+ in 90 days,
                   people are running for the exits. WeWork, Theranos, and
                   Luckin Coffee all had executive stampedes pre-collapse.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("csuite_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff_1y = (datetime.now(timezone.utc) - timedelta(days=365)).date()
    cutoff_90d = (datetime.now(timezone.utc) - timedelta(days=90)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Annual rate: flag companies with 6+ departures in a year
            # (normal large-cap baseline is ~2-4)
            cur.execute("""
                SELECT r.security_id, s.ticker,
                       count(*) AS total_1y,
                       count(*) FILTER (WHERE r.filing_date >= %s) AS recent_90d,
                       max(r.filing_date) AS most_recent
                FROM raw_csuite_departures r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.filing_date >= %s
                GROUP BY r.security_id, s.ticker
                HAVING count(*) >= 6 OR count(*) FILTER (WHERE r.filing_date >= %s) >= 3
            """, (cutoff_90d, cutoff_1y, cutoff_90d))
            rows = cur.fetchall()

    for sid, ticker, total_1y, recent_90d, most_recent in rows:
        # Contribution: annual rate + recency spike
        annual_score = min(total_1y / 12.0, 1.0)
        spike_score = min(recent_90d / 5.0, 1.0) if recent_90d >= 3 else 0
        contribution = min((annual_score + spike_score) / 2 + 0.15, 1.0)

        if total_1y >= 10 or recent_90d >= 5:
            magnitude = "extreme"
        elif total_1y >= 8 or recent_90d >= 4:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        days_ago = (datetime.now(timezone.utc).date() - most_recent).days
        confidence = 0.80 if days_ago < 180 else 0.60

        desc = f"{ticker} {total_1y} executive changes in 1y"
        if recent_90d >= 3:
            desc += f" ({recent_90d} in last 90d)"
        desc += f", most recent {most_recent}"

        signals.append({
            "security_id": sid,
            "signal_type": "csuite_exodus",
            "contribution": round(contribution, 4),
            "confidence": confidence,
            "direction": "bearish",
            "magnitude": magnitude,
            "raw_value": float(total_1y),
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

    log.info("C-Suite signals: %d securities flagged → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
