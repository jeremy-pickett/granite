"""
Short Interest Signals — derive IALD signals from raw_short_interest.

Signals produced:
  - short_interest_spike: High short interest as % of float, or significant
    month-over-month increase in shares sold short.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("short_interest_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                # Get most recent short interest per security
                cur.execute("""
                    SELECT DISTINCT ON (r.security_id)
                        r.security_id, s.ticker,
                        r.shares_short, r.shares_short_prior,
                        r.short_pct_float, r.short_ratio,
                        r.report_date
                    FROM raw_short_interest r
                    JOIN securities s ON s.security_id = r.security_id
                    ORDER BY r.security_id, r.report_date DESC
                """)
                rows = cur.fetchall()
            except Exception as e:
                log.warning("Query error: %s", e)
                rows = []

    for sid, ticker, shares_short, shares_prior, pct_float, short_ratio, report_date in rows:
        shares_short = int(shares_short or 0)
        shares_prior = int(shares_prior or 0)
        pct_float = float(pct_float) if pct_float else 0
        short_ratio = float(short_ratio) if short_ratio else 0

        # Threshold: >10% of float is notable, >20% strong, >30% extreme
        if pct_float < 0.05:
            continue  # under 5% — not interesting

        # Contribution from % of float
        float_score = min(pct_float / 0.30, 1.0) * 0.5

        # Contribution from month-over-month change
        mom_change = 0
        if shares_prior and shares_prior > 0:
            mom_change = (shares_short - shares_prior) / shares_prior
        mom_score = min(max(mom_change, 0) / 0.50, 1.0) * 0.3

        # Contribution from days-to-cover (short ratio)
        dtc_score = min(short_ratio / 10.0, 1.0) * 0.2

        contribution = min(float_score + mom_score + dtc_score, 1.0)

        if pct_float >= 0.30 or (mom_change >= 0.50 and pct_float >= 0.15):
            magnitude = "extreme"
        elif pct_float >= 0.20 or mom_change >= 0.25:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        days_ago = (datetime.now(timezone.utc).date() - report_date).days
        confidence = 0.80 if days_ago < 20 else 0.60

        desc = f"{ticker} {pct_float:.1%} short interest"
        if short_ratio:
            desc += f", {short_ratio:.1f} days to cover"
        if mom_change > 0.05:
            desc += f", +{mom_change:.0%} MoM"

        signals.append({
            "security_id": sid,
            "signal_type": "short_interest_spike",
            "contribution": round(contribution, 4),
            "confidence": confidence,
            "direction": "bearish",
            "magnitude": magnitude,
            "raw_value": pct_float,
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

    log.info("Short interest signals: %d securities analyzed → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
