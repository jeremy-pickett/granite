"""
News Signals — derive IALD signals from raw_news_sentiment.

Signals produced:
  - news_sentiment_extreme: strong negative or positive sentiment cluster
  - news_volume_spike:      unusually high article count for a security
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("news_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = now - timedelta(days=3)

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.security_id, s.ticker,
                       count(*) AS article_count,
                       avg(r.sentiment) AS avg_sentiment,
                       min(r.sentiment) AS min_sentiment,
                       max(r.sentiment) AS max_sentiment
                FROM raw_news_sentiment r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.published_at >= %s
                GROUP BY r.security_id, s.ticker
            """, (cutoff,))
            rows = cur.fetchall()

    if not rows:
        log.info("No recent news data found")
        return 0

    # Compute median article count for volume spike detection
    counts = sorted(r[2] for r in rows)
    median_count = counts[len(counts) // 2] if counts else 1

    signals = []
    for sid, ticker, count, avg_sent, min_sent, max_sent in rows:
        avg_sent = float(avg_sent or 0)
        count = int(count)

        # news_sentiment_extreme: avg sentiment outside ±0.3
        if abs(avg_sent) >= 0.3:
            direction = "bearish" if avg_sent < 0 else "bullish"
            contribution = min(abs(avg_sent), 1.0)
            signals.append({
                "security_id": sid,
                "signal_type": "news_sentiment_extreme",
                "contribution": round(contribution, 4),
                "confidence": min(0.4 + count / 20, 0.85),
                "direction": direction,
                "magnitude": "strong" if abs(avg_sent) >= 0.6 else "moderate",
                "raw_value": round(avg_sent, 4),
                "description": f"{ticker} news sentiment {avg_sent:+.2f} across {count} articles",
                "detected_at": now,
            })

        # news_volume_spike: 3x+ median article count
        if median_count > 0 and count >= median_count * 3 and count >= 5:
            ratio = count / median_count
            contribution = min(ratio / 10, 1.0)
            signals.append({
                "security_id": sid,
                "signal_type": "news_volume_spike",
                "contribution": round(contribution, 4),
                "confidence": 0.65,
                "direction": "neutral",
                "magnitude": "extreme" if ratio >= 8 else "strong" if ratio >= 5 else "moderate",
                "raw_value": round(ratio, 4),
                "description": f"{ticker} {count} articles in 3d ({ratio:.1f}x median)",
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

    log.info("News signals: %d sentiment extremes, %d volume spikes → %d total",
             sum(1 for s in signals if s["signal_type"] == "news_sentiment_extreme"),
             sum(1 for s in signals if s["signal_type"] == "news_volume_spike"),
             len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
