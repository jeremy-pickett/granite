"""
13F Signals — derive IALD signals from raw_13f_holdings.

Signals produced:
  - institutional_filing_spike: Unusual 13F filing frequency for a company
                                that IS an institutional filer. When a fund
                                manager files amendments or unusually frequent
                                13F updates, they're reshuffling. Combined with
                                being in our universe, this means a major player
                                is actively changing positions.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("sec_13f_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                # Flag companies with high 13F filing frequency (>4/year is unusual)
                # Normal is quarterly = 4. Amendments and corrections push it higher.
                cur.execute("""
                    SELECT r.security_id, s.ticker,
                           count(*) AS filing_count,
                           count(*) FILTER (WHERE r.form_type LIKE '%%/A') AS amendment_count,
                           max(r.filing_date) AS most_recent
                    FROM raw_13f_holdings r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.filing_date >= %s
                    GROUP BY r.security_id, s.ticker
                    HAVING count(*) >= 5 OR count(*) FILTER (WHERE r.form_type LIKE '%%/A') >= 2
                """, (cutoff,))
                rows = cur.fetchall()
            except Exception:
                rows = []

    for sid, ticker, filing_count, amendment_count, most_recent in rows:
        # Amendments to 13F = correcting previously reported positions
        raw = filing_count + amendment_count
        contribution = min(raw / 10.0, 1.0)

        if amendment_count >= 3 or filing_count >= 8:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        days_ago = (datetime.now(timezone.utc).date() - most_recent).days
        confidence = 0.70 if days_ago < 180 else 0.55

        desc = f"{ticker} {filing_count} 13F filings in 1y"
        if amendment_count:
            desc += f" ({amendment_count} amendments)"
        desc += f", most recent {most_recent}"

        signals.append({
            "security_id": sid,
            "signal_type": "institutional_filing_spike",
            "contribution": round(contribution, 4),
            "confidence": confidence,
            "direction": "neutral",
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

    log.info("13F signals: %d securities flagged → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
