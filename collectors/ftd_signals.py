"""
FTD Signals — derive IALD signals from raw_ftd_data.

Signals produced:
  - ftd_spike: Persistent or extreme fail-to-deliver volume.
               Fires when total FTD quantity in 30 days exceeds 500k shares
               or when FTDs appear on 5+ distinct settlement dates (persistence).
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("ftd_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT r.security_id, s.ticker,
                           sum(r.quantity) AS total_qty,
                           count(DISTINCT r.settlement_date) AS ftd_days,
                           max(r.settlement_date) AS most_recent,
                           avg(r.price) AS avg_price
                    FROM raw_ftd_data r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.settlement_date >= %s
                    GROUP BY r.security_id, s.ticker
                    HAVING sum(r.quantity) >= 500000 OR count(DISTINCT r.settlement_date) >= 5
                """, (cutoff,))
                rows = cur.fetchall()
            except Exception:
                rows = []

    for sid, ticker, total_qty, ftd_days, most_recent, avg_price in rows:
        total_qty = int(total_qty)
        ftd_days = int(ftd_days)
        # Dollar value of FTDs if price available
        dollar_val = total_qty * float(avg_price) if avg_price else 0

        # Contribution based on volume + persistence
        vol_score = min(total_qty / 5_000_000, 1.0)
        persist_score = min(ftd_days / 15, 1.0)
        contribution = min((vol_score + persist_score) / 2 + 0.1, 1.0)

        if total_qty >= 5_000_000 or ftd_days >= 15:
            magnitude = "extreme"
        elif total_qty >= 1_000_000 or ftd_days >= 10:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        days_ago = (datetime.now(timezone.utc).date() - most_recent).days
        confidence = 0.85 if days_ago < 30 else 0.65

        dollar_str = f" (${dollar_val/1e6:.1f}M)" if dollar_val > 0 else ""
        signals.append({
            "security_id": sid,
            "signal_type": "ftd_spike",
            "contribution": round(contribution, 4),
            "confidence": confidence,
            "direction": "bearish",
            "magnitude": magnitude,
            "raw_value": float(total_qty),
            "description": f"{ticker} {total_qty:,} FTDs over {ftd_days} days{dollar_str}, most recent {most_recent}",
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

    log.info("FTD signals: %d securities flagged → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
