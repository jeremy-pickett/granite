"""
Concentration Signals — derive IALD signals from raw_concentration_disclosures.

Signals produced:
  - concentration_shift: Unusual 13D/13G filing frequency (3+ in 90 days)
                         or first-ever SC 13D (activist) filing for a security.
                         The pre-collapse pattern: institutional holders filing
                         amendments as they reduce positions while retail stays in.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("concentration_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=730)).date()  # 2y lookback (EDGAR data lags)

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Signal 1: Filing frequency — 3+ 13D/13G filings in 90 days
            # High amendment frequency = large holders actively adjusting positions
            cur.execute("""
                SELECT r.security_id, s.ticker,
                       count(*) AS filing_count,
                       count(*) FILTER (WHERE r.form_type LIKE 'SC 13D%%') AS activist_count
                FROM raw_concentration_disclosures r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.filing_date >= %s
                GROUP BY r.security_id, s.ticker
                HAVING count(*) >= 3
            """, (cutoff,))
            clusters = cur.fetchall()

            # Signal 2: New activist — first SC 13D filing ever for this security
            # (no prior 13D history, but one appeared in the last 90 days)
            cur.execute("""
                SELECT r.security_id, s.ticker, r.filing_date, r.form_type
                FROM raw_concentration_disclosures r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.form_type LIKE 'SC 13D%%'
                  AND r.filing_date >= %s
                  AND r.security_id NOT IN (
                      SELECT security_id
                      FROM raw_concentration_disclosures
                      WHERE form_type LIKE 'SC 13D%%'
                        AND filing_date < %s
                  )
            """, (cutoff, cutoff))
            new_activists = cur.fetchall()

    # Build signals from filing frequency clusters
    for sid, ticker, filing_count, activist_count in clusters:
        # More filings = stronger signal; activist filings weigh heavier
        raw = filing_count + activist_count  # activist counted double
        contribution = min(raw / 8.0, 1.0)
        magnitude = "extreme" if raw >= 6 else "strong" if raw >= 4 else "moderate"

        signals.append({
            "security_id": sid,
            "signal_type": "concentration_shift",
            "contribution": round(contribution, 4),
            "confidence": min(0.5 + filing_count / 10, 0.85),
            "direction": "bearish",
            "magnitude": magnitude,
            "raw_value": float(filing_count),
            "description": f"{ticker} {filing_count} concentration filings in 1y ({activist_count} activist)",
            "detected_at": now,
        })

    # Build signals from new activist appearances
    seen = set()  # avoid dupes if same security hit both queries
    for sid, ticker, fdate, ftype in new_activists:
        if sid in seen or sid in {s["security_id"] for s in signals}:
            continue
        seen.add(sid)
        signals.append({
            "security_id": sid,
            "signal_type": "concentration_shift",
            "contribution": 0.60,
            "confidence": 0.70,
            "direction": "bearish",
            "magnitude": "strong",
            "raw_value": 1.0,
            "description": f"{ticker} first activist (13D) filing: {ftype} on {fdate}",
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

    log.info("Concentration signals: %d clusters, %d new activists → %d total signals",
             len(clusters), len(new_activists), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
