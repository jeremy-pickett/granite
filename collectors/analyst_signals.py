"""
Analyst Signals — derive IALD signals from raw_analyst_actions.

Signals produced:
  - analyst_consensus_shift: month-over-month change in buy/sell ratio
"""

import sys
import os
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("analyst_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Get the two most recent periods per security
            cur.execute("""
                WITH ranked AS (
                    SELECT security_id, period, strong_buy, buy, hold, sell, strong_sell, total_analysts,
                           row_number() OVER (PARTITION BY security_id ORDER BY period DESC) AS rn
                    FROM raw_analyst_actions
                    WHERE total_analysts > 0
                )
                SELECT a.security_id, s.ticker,
                       a.strong_buy AS sb1, a.buy AS b1, a.hold AS h1, a.sell AS s1, a.strong_sell AS ss1, a.total_analysts AS t1,
                       b.strong_buy AS sb2, b.buy AS b2, b.hold AS h2, b.sell AS s2, b.strong_sell AS ss2, b.total_analysts AS t2
                FROM ranked a
                JOIN ranked b ON a.security_id = b.security_id AND b.rn = 2
                JOIN securities s ON s.security_id = a.security_id
                WHERE a.rn = 1
            """)
            pairs = cur.fetchall()

    signals = []
    for (sid, ticker, sb1, b1, h1, s1, ss1, t1, sb2, b2, h2, s2, ss2, t2) in pairs:
        if t1 == 0 or t2 == 0:
            continue

        # Bull ratio: (strongBuy + buy) / total
        bull_now = (sb1 + b1) / t1
        bull_prev = (sb2 + b2) / t2
        shift = bull_now - bull_prev

        if abs(shift) < 0.05:
            continue  # no meaningful change

        direction = "bullish" if shift > 0 else "bearish"
        contribution = min(abs(shift) * 3, 1.0)  # 0.33 shift → 1.0

        signals.append({
            "security_id": sid,
            "signal_type": "analyst_consensus_shift",
            "contribution": round(contribution, 4),
            "confidence": min(0.5 + t1 / 50, 0.85),
            "direction": direction,
            "magnitude": "strong" if abs(shift) > 0.15 else "moderate",
            "raw_value": round(shift, 4),
            "description": f"{ticker} analyst consensus {direction} shift {shift:+.0%} ({t1} analysts)",
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

    log.info("Analyst signals: %d consensus shifts detected", len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
