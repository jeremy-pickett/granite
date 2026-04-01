"""
Prediction Market Signals — derive IALD signals from raw_prediction_markets.

Signals produced:
  - prediction_market_heat: High volume or extreme probability on prediction
    markets relevant to a security. When the crowd puts real money on an
    outcome, that's conviction with skin in the game.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("prediction_market_signals")


_BEARISH_KW = {"bankrupt", "delist", "default", "investigation", "fraud",
               "lawsuit", "indict", "collapse", "crash", "below", "under",
               "fail", "miss", "decline", "drop", "fall"}
_BULLISH_KW = {"beat", "approval", "approve", "merger", "acquisition",
               "acquire", "rally", "above", "over", "exceed", "rise",
               "gain", "profit", "record high", "ipo"}


def _infer_direction(max_prob, min_prob, titles):
    """Derive signal direction from probability extremity and event title keywords."""
    if max_prob < 0.65 and min_prob > 0.35:
        return "neutral"

    title_text = " ".join(t.lower() for t in (titles or []))
    bear_hits = sum(1 for kw in _BEARISH_KW if kw in title_text)
    bull_hits = sum(1 for kw in _BULLISH_KW if kw in title_text)

    if bear_hits > bull_hits and max_prob > 0.65:
        return "bearish"
    if bull_hits > bear_hits and max_prob > 0.65:
        return "bullish"
    if bear_hits > bull_hits and min_prob < 0.35:
        return "bullish"  # low prob of bad event = bullish
    if bull_hits > bear_hits and min_prob < 0.35:
        return "bearish"  # low prob of good event = bearish
    return "neutral"


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT r.security_id, s.ticker,
                           count(*) AS market_count,
                           count(DISTINCT r.source) AS source_count,
                           max(r.probability) AS max_prob,
                           min(r.probability) AS min_prob,
                           sum(COALESCE(r.volume, 0)) AS total_volume,
                           array_agg(DISTINCT LEFT(r.event_title, 60)) AS titles
                    FROM raw_prediction_markets r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.fetched_date >= %s
                    GROUP BY r.security_id, s.ticker
                    HAVING count(*) >= 2 OR sum(COALESCE(r.volume, 0)) > 100000
                """, (cutoff,))
                rows = cur.fetchall()
            except Exception as e:
                log.warning("Query error: %s", e)
                rows = []

    for sid, ticker, market_count, source_count, max_prob, min_prob, total_vol, titles in rows:
        market_count = int(market_count)
        total_vol = float(total_vol or 0)
        max_prob = float(max_prob) if max_prob else 0.5
        min_prob = float(min_prob) if min_prob else 0.5

        # Score based on: market count, volume, probability extremity
        count_score = min(market_count / 10.0, 0.4)
        vol_score = min(total_vol / 1_000_000, 0.3)
        # Extreme probabilities (>0.85 or <0.15) are more interesting
        extremity = max(max_prob - 0.5, 0.5 - min_prob, 0) * 2
        prob_score = min(extremity * 0.3, 0.3)

        contribution = min(count_score + vol_score + prob_score, 1.0)
        if contribution < 0.15:
            continue

        if contribution >= 0.6:
            magnitude = "extreme"
        elif contribution >= 0.35:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        # Multi-source bonus
        confidence = 0.55 + min(source_count * 0.1, 0.2) + min(market_count * 0.02, 0.15)

        # Derive direction from probability + event title keywords
        direction = _infer_direction(max_prob, min_prob, titles)

        title_str = "; ".join(titles[:3]) if titles else ""
        desc = f"{ticker} {market_count} prediction markets"
        if total_vol > 0:
            desc += f" (${total_vol/1e6:.1f}M volume)"
        if title_str:
            desc += f": {title_str[:100]}"

        signals.append({
            "security_id": sid,
            "signal_type": "prediction_market_heat",
            "contribution": round(contribution, 4),
            "confidence": round(min(confidence, 0.90), 4),
            "direction": direction,
            "magnitude": magnitude,
            "raw_value": float(market_count),
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

    log.info("Prediction market signals: %d securities → %d signals", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
