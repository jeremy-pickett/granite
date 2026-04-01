"""
Options Signals — derive IALD signals from raw_options_flow.

Signals produced:
  - options_unusual_activity: High options volume concentrated in specific
    strikes/expirations. Adapted from volume/OI spike detection.
    Without OI data (free Polygon tier), we detect:
      1. Volume concentration: single contract with volume > 5x the
         median volume across that ticker's options
      2. OTM loading: heavy volume in strikes >10% OTM (the Enron put pattern)
      3. Put/call skew: extreme imbalance in put vs call volume
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("options_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            try:
                # Per-security aggregates from recent options flow
                cur.execute("""
                    SELECT
                        r.security_id, s.ticker,
                        count(*) AS contract_count,
                        sum(r.volume) AS total_volume,
                        max(r.volume) AS max_single_volume,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY r.volume) AS median_volume,
                        sum(r.volume) FILTER (WHERE r.contract_type = 'put') AS put_volume,
                        sum(r.volume) FILTER (WHERE r.contract_type = 'call') AS call_volume,
                        max(r.underlying_close) AS underlying_price,
                        -- OTM puts: strike < underlying * 0.9
                        sum(r.volume) FILTER (
                            WHERE r.contract_type = 'put'
                              AND r.strike_price < r.underlying_close * 0.9
                        ) AS deep_otm_put_volume,
                        -- OTM calls: strike > underlying * 1.1
                        sum(r.volume) FILTER (
                            WHERE r.contract_type = 'call'
                              AND r.strike_price > r.underlying_close * 1.1
                        ) AS deep_otm_call_volume
                    FROM raw_options_flow r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE r.trade_date >= %s
                      AND r.volume > 0
                    GROUP BY r.security_id, s.ticker
                    HAVING count(*) >= 3
                """, (cutoff,))
                rows = cur.fetchall()
            except Exception as e:
                log.warning("Query error (table may not exist yet): %s", e)
                rows = []

    for row in rows:
        (sid, ticker, contract_count, total_volume, max_single,
         median_vol, put_vol, call_vol, underlying,
         deep_otm_put_vol, deep_otm_call_vol) = row

        total_volume = int(total_volume or 0)
        max_single = int(max_single or 0)
        median_vol = float(median_vol or 1)
        put_vol = int(put_vol or 0)
        call_vol = int(call_vol or 0)
        deep_otm_put_vol = int(deep_otm_put_vol or 0)
        deep_otm_call_vol = int(deep_otm_call_vol or 0)

        # Signal 1: Volume concentration spike
        # Single contract has >5x median volume = someone knows something
        concentration_ratio = max_single / max(median_vol, 1)

        # Signal 2: Deep OTM loading
        # Heavy put volume far from money = crash bet
        otm_ratio = (deep_otm_put_vol + deep_otm_call_vol) / max(total_volume, 1)

        # Signal 3: Put/call skew
        total_pc = put_vol + call_vol
        if total_pc > 0:
            put_pct = put_vol / total_pc
        else:
            put_pct = 0.5

        # Determine if this is unusual enough to signal
        is_concentrated = concentration_ratio >= 5.0
        is_otm_loaded = otm_ratio >= 0.3 and (deep_otm_put_vol + deep_otm_call_vol) >= 500
        is_skewed = put_pct >= 0.75 or put_pct <= 0.25

        if not (is_concentrated or is_otm_loaded or is_skewed):
            continue

        # Build composite score
        score = 0.0
        desc_parts = [ticker]

        if is_concentrated:
            score += min(concentration_ratio / 15.0, 0.5)
            desc_parts.append(f"vol concentration {concentration_ratio:.0f}x median")

        if is_otm_loaded:
            score += min(otm_ratio, 0.3)
            if deep_otm_put_vol > deep_otm_call_vol:
                desc_parts.append(f"deep OTM puts {deep_otm_put_vol:,} vol")
            else:
                desc_parts.append(f"deep OTM calls {deep_otm_call_vol:,} vol")

        if is_skewed:
            skew_strength = abs(put_pct - 0.5) * 2
            score += skew_strength * 0.2
            if put_pct >= 0.75:
                desc_parts.append(f"put-heavy {put_pct:.0%}")
            else:
                desc_parts.append(f"call-heavy {1-put_pct:.0%}")

        # A5: Put Skew Persistence — check last 5 days for sustained put bias
        if put_pct >= 0.65:
            try:
                with db.get_conn() as conn2:
                    with conn2.cursor() as cur2:
                        cur2.execute("""
                            SELECT trade_date,
                                   sum(volume) FILTER (WHERE contract_type = 'put') AS pv,
                                   sum(volume) FILTER (WHERE contract_type = 'call') AS cv
                            FROM raw_options_flow
                            WHERE security_id = %s
                              AND trade_date >= %s - interval '5 days'
                              AND volume > 0
                            GROUP BY trade_date
                            ORDER BY trade_date DESC
                            LIMIT 5
                        """, (sid, cutoff))
                        daily_rows = cur2.fetchall()
                put_days = 0
                for _, pv, cv in daily_rows:
                    pv = int(pv or 0)
                    cv = int(cv or 0)
                    if (pv + cv) > 0 and pv / (pv + cv) >= 0.65:
                        put_days += 1
                if put_days >= 4 and len(daily_rows) >= 4:
                    score *= 1.5
                    desc_parts.append(f"persistent put skew ({put_days}/5 days)")
            except Exception:
                pass  # table may not exist or insufficient data

        contribution = min(score, 1.0)

        if contribution >= 0.6:
            magnitude = "extreme"
        elif contribution >= 0.35:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        # Direction from put/call skew
        if put_pct >= 0.65:
            direction = "bearish"
        elif put_pct <= 0.35:
            direction = "bullish"
        else:
            direction = "neutral"

        signals.append({
            "security_id": sid,
            "signal_type": "options_unusual_activity",
            "contribution": round(contribution, 4),
            "confidence": min(0.5 + contract_count / 50, 0.85),
            "direction": direction,
            "magnitude": magnitude,
            "raw_value": float(total_volume),
            "description": ", ".join(desc_parts),
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

    log.info("Options signals: %d securities analyzed, %d signals fired", len(rows), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
