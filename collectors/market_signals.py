"""
Market Signals — derive IALD signals from raw_market_data.

Reads OHLCV, detects anomalies, writes to the `signals` table.
This is a derived-signal job, not a collector (it reads internal data, not external APIs).

Signals produced:
  - volume_spike:   volume > 2x 20-day average
  - price_gap:      open > 2% away from prior close
  - unusual_range:  daily range > 2x 20-day average range

Collector ID: None (derived, not a collector)
"""

import sys
import os
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import config
import db
from signal_config import SIGNAL_CONFIG

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("market_signals")


def load_market_history(security_id: int, days: int = 25):
    """Load recent OHLCV for one security, oldest first."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT trade_date, open, high, low, close, volume
                   FROM raw_market_data
                   WHERE security_id = %s
                   ORDER BY trade_date DESC
                   LIMIT %s""",
                (security_id, days),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            rows.reverse()  # oldest first
            return rows


def detect_signals(security_id: int, ticker: str, rows: list[dict]) -> list[dict]:
    """Analyze OHLCV history and return signal dicts for today."""
    if len(rows) < 5:
        return []

    latest = rows[-1]
    prior = rows[-2] if len(rows) >= 2 else None
    today = latest["trade_date"]
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    # 20-day lookback (or whatever we have, minus today)
    history = rows[:-1]
    if len(history) < 3:
        return []

    signals = []
    avg_volume = sum(float(r["volume"]) for r in history) / len(history)
    ranges = [float(r["high"]) - float(r["low"]) for r in history if float(r["high"]) > 0]
    avg_range = sum(ranges) / len(ranges) if ranges else 0
    today_range = float(latest["high"]) - float(latest["low"])

    # ── volume_spike ──────────────────────────────────────────────
    if avg_volume > 0:
        vol_ratio = float(latest["volume"]) / avg_volume
        if vol_ratio >= 2.0:
            magnitude = "extreme" if vol_ratio >= 5.0 else "strong" if vol_ratio >= 3.0 else "moderate"
            contribution = min(vol_ratio / 5.0, 1.0)
            signals.append({
                "security_id": security_id,
                "signal_type": "volume_spike",
                "contribution": round(contribution, 4),
                "confidence": min(0.5 + len(history) / 40, 0.95),
                "direction": "neutral",
                "magnitude": magnitude,
                "raw_value": round(vol_ratio, 4),
                "description": f"{ticker} volume {vol_ratio:.1f}x 20d avg",
                "detected_at": now,
            })

    # ── price_gap ─────────────────────────────────────────────────
    if prior:
        prior_close = float(prior["close"])
        today_open = float(latest["open"])
        if prior_close > 0:
            gap_pct = (today_open - prior_close) / prior_close * 100
            if abs(gap_pct) >= 2.0:
                direction = "bullish" if gap_pct > 0 else "bearish"
                magnitude = "extreme" if abs(gap_pct) >= 5.0 else "strong" if abs(gap_pct) >= 3.0 else "moderate"
                contribution = min(abs(gap_pct) / 10.0, 1.0)
                signals.append({
                    "security_id": security_id,
                    "signal_type": "price_gap",
                    "contribution": round(contribution, 4),
                    "confidence": 0.80,
                    "direction": direction,
                    "magnitude": magnitude,
                    "raw_value": round(gap_pct, 4),
                    "description": f"{ticker} gap {gap_pct:+.1f}% from prior close",
                    "detected_at": now,
                })

    # ── unusual_range ─────────────────────────────────────────────
    if avg_range > 0:
        range_ratio = today_range / avg_range
        if range_ratio >= 2.0:
                magnitude = "extreme" if range_ratio >= 4.0 else "strong" if range_ratio >= 3.0 else "moderate"
                contribution = min(range_ratio / 5.0, 1.0)
                signals.append({
                    "security_id": security_id,
                    "signal_type": "unusual_range",
                    "contribution": round(contribution, 4),
                    "confidence": min(0.4 + len(history) / 40, 0.85),
                    "direction": "neutral",
                    "magnitude": magnitude,
                    "raw_value": round(range_ratio, 4),
                    "description": f"{ticker} range {range_ratio:.1f}x 20d avg",
                    "detected_at": now,
                })

    # =====================================================================
    # BASELINE SIGNALS — fire for every security with sufficient data
    # =====================================================================

    # ── relative_volume ───────────────────────────────────────────
    # Continuous: how today's volume compares to average. Always fires.
    if avg_volume > 0:
        vol_ratio = float(latest["volume"]) / avg_volume
        # Contribution scales with deviation from 1.0 (normal)
        # 0.5x = -0.5 contribution, 2x = +0.5, 5x = +1.0
        deviation = vol_ratio - 1.0
        contribution = max(min(deviation / 4.0, 1.0), -1.0)
        signals.append({
            "security_id": security_id,
            "signal_type": "relative_volume",
            "contribution": round(abs(contribution), 4),
            "confidence": min(0.4 + len(history) / 40, 0.80),
            "direction": "neutral",
            "magnitude": None,
            "raw_value": round(vol_ratio, 4),
            "description": f"{ticker} volume {vol_ratio:.2f}x avg",
            "detected_at": now,
        })

    # ── price_momentum ────────────────────────────────────────────
    # 5-day return (or however many days we have)
    if len(rows) >= 2:
        oldest_close = float(rows[0]["close"])
        latest_close = float(latest["close"])
        if oldest_close > 0:
            pct_return = (latest_close - oldest_close) / oldest_close * 100
            n_days = len(rows) - 1
            contribution = max(min(abs(pct_return) / 10.0, 1.0), 0.0)
            direction = "bullish" if pct_return > 0.5 else "bearish" if pct_return < -0.5 else "neutral"
            signals.append({
                "security_id": security_id,
                "signal_type": "price_momentum",
                "contribution": round(contribution, 4),
                "confidence": min(0.3 + n_days / 10, 0.80),
                "direction": direction,
                "magnitude": None,
                "raw_value": round(pct_return, 4),
                "description": f"{ticker} {pct_return:+.1f}% over {n_days}d",
                "detected_at": now,
            })

    # ── volatility_compression ────────────────────────────────────
    # Today's range vs average range. Low ratio = squeeze building.
    if ranges and avg_range > 0:
        range_ratio = today_range / avg_range
        # Compression (ratio < 0.5) and expansion (ratio > 2.0) both interesting
        if range_ratio < 0.5:
            contribution = (0.5 - range_ratio) / 0.5  # tighter = stronger
            description = f"{ticker} range compressed {range_ratio:.2f}x avg (squeeze)"
        else:
            contribution = min((range_ratio - 1.0) / 3.0, 1.0)
            description = f"{ticker} range {range_ratio:.2f}x avg"
        signals.append({
            "security_id": security_id,
            "signal_type": "volatility_compression",
            "contribution": round(max(contribution, 0.01), 4),
            "confidence": min(0.3 + len(history) / 40, 0.75),
            "direction": "neutral",
            "magnitude": None,
            "raw_value": round(range_ratio, 4),
            "description": description,
            "detected_at": now,
        })

    # ── closing_strength ──────────────────────────────────────────
    # Where did price close within the day's range? 1.0 = at high, 0.0 = at low
    if today_range > 0:
        close_pos = (float(latest["close"]) - float(latest["low"])) / today_range
        # Extremes (near 0 or near 1) are more interesting
        contribution = abs(close_pos - 0.5) * 2  # 0 at midrange, 1 at extremes
        direction = "bullish" if close_pos > 0.7 else "bearish" if close_pos < 0.3 else "neutral"
        signals.append({
            "security_id": security_id,
            "signal_type": "closing_strength",
            "contribution": round(contribution, 4),
            "confidence": 0.60,
            "direction": direction,
            "magnitude": None,
            "raw_value": round(close_pos, 4),
            "description": f"{ticker} closed at {close_pos:.0%} of range",
            "detected_at": now,
        })

    return signals


def write_signals(signals: list[dict]):
    """Batch insert signals, skipping duplicates."""
    if not signals:
        return 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            values = [
                (s["security_id"], s["signal_type"], s["contribution"],
                 s["confidence"], s["direction"], s["magnitude"],
                 s["raw_value"], s["description"], s["detected_at"])
                for s in signals
            ]
            execute_values(
                cur,
                """INSERT INTO signals
                       (security_id, signal_type, contribution, confidence,
                        direction, magnitude, raw_value, description, detected_at)
                   VALUES %s
                   ON CONFLICT (security_id, signal_type, detected_at)
                   DO UPDATE SET contribution = GREATEST(EXCLUDED.contribution, signals.contribution),
                                 confidence = GREATEST(EXCLUDED.confidence, signals.confidence)""",
                values,
                template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            )
    return len(signals)


def run(tickers: list[str] | None = None):
    """Extract market signals for all securities with market data."""
    securities = db.get_securities()
    if tickers:
        tickers_upper = {t.upper() for t in tickers}
        securities = [s for s in securities if s["ticker"] in tickers_upper]

    log.info("Scanning %d securities for market signals...", len(securities))
    all_signals = []
    detected_count = 0

    for s in securities:
        rows = load_market_history(s["security_id"])
        signals = detect_signals(s["security_id"], s["ticker"], rows)
        if signals:
            all_signals.extend(signals)
            detected_count += 1

    written = write_signals(all_signals)
    log.info("Detected %d signals across %d securities, wrote %d",
             len(all_signals), detected_count, written)
    return len(all_signals)


def main():
    args = sys.argv[1:]
    tickers = [a.upper() for a in args if not a.startswith("--")] or None
    run(tickers)


if __name__ == "__main__":
    main()
