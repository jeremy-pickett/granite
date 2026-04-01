"""
Sector Correlation Signals — derive IALD signals from raw_sector_correlations.

Signals produced:
  - sector_divergence: Stock decorrelating from its sector ETF (correlation < 0.3)
    or large residual returns (>2 sigma). Something specific to this company is
    driving the move independently of sector dynamics.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("sector_correlation_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT DISTINCT ON (r.security_id)
                        r.security_id, s.ticker, s.sector,
                        r.sector_etf, r.rolling_correlation, r.residual_return,
                        r.correlation_date
                    FROM raw_sector_correlations r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.correlation_date >= %s
                    ORDER BY r.security_id, r.correlation_date DESC
                """, (cutoff,))
                rows = cur.fetchall()
            except Exception as e:
                log.warning("Query error: %s", e)
                rows = []

    for sid, ticker, sector, etf, corr, residual, corr_date in rows:
        corr = float(corr) if corr is not None else 1.0
        residual = float(residual) if residual is not None else 0.0

        # Decorrelation: correlation < 0.3 is unusual
        is_decorrelated = corr < 0.3
        # Large residual: abs > 0.03 (3% idiosyncratic move in a day)
        is_large_residual = abs(residual) > 0.03

        if not (is_decorrelated or is_large_residual):
            continue

        # Score
        decorr_score = max(0, (0.5 - corr)) * 1.5 if is_decorrelated else 0
        residual_score = min(abs(residual) / 0.10, 0.5) if is_large_residual else 0
        contribution = min(decorr_score + residual_score, 1.0)

        if contribution >= 0.6:
            magnitude = "extreme"
        elif contribution >= 0.35:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        direction = "bearish" if residual < -0.02 else "bullish" if residual > 0.02 else "neutral"

        desc = f"{ticker} decorrelating from {sector} ({etf}): corr={corr:.2f}"
        if abs(residual) > 0.01:
            desc += f", residual={residual:+.1%}"

        signals.append({
            "security_id": sid,
            "signal_type": "sector_divergence",
            "contribution": round(contribution, 4),
            "confidence": 0.65,
            "direction": direction,
            "magnitude": magnitude,
            "raw_value": round(corr, 6),
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

    log.info("Sector divergence signals: %d analyzed → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
