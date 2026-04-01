"""
Crypto Governance Signal Extractor — derive signals from governance + death spiral data.

Reads from:
  - raw_crypto_governance (token distribution, dev activity, supply metrics)
  - raw_crypto_death_spiral (phase classification, indicator triggers)

Writes to signals table:
  1. blockchain_anomaly — when death spiral phase is critical/terminal
  2. blockchain_anomaly — when governance profile shows red flags
  3. crypto_rug_pull_risk — when multiple high-severity indicators align
  4. crypto_death_spiral — phase-based collapse progression signal
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import db

log = logging.getLogger("crypto_governance_signals")


def run():
    """
    Extract governance and death spiral signals from raw data tables.
    Called by collectors_run.py run_signals().
    """
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today = datetime.now(timezone.utc).date()
    signals = []

    # ── Signal 1: Death spiral phase → blockchain_anomaly ────────────────
    # When phase is 'critical' or 'terminal', fire a high-contribution signal.
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT security_id, phase, phase_score, indicators_triggered,
                           price_from_peak_pct, volume_trend, social_trend
                    FROM raw_crypto_death_spiral
                    WHERE detection_date = %s
                      AND phase IN ('critical', 'terminal')
                """, (today,))
                rows = cur.fetchall()

        for sid, phase, phase_score, indicators, drawdown, vol_trend, soc_trend in rows:
            phase_score = float(phase_score or 0)
            drawdown = float(drawdown or 0)
            desc = (f"Death spiral {phase}: score={phase_score:.3f}, "
                    f"drawdown={drawdown:.1f}%, vol={vol_trend}, social={soc_trend}")
            if indicators:
                desc += f" [{indicators}]"

            signals.append({
                "security_id": sid,
                "signal_type": "blockchain_anomaly",
                "contribution": round(min(phase_score, 0.95), 4),
                "confidence": 0.85,
                "direction": "bearish",
                "magnitude": "extreme" if phase == "terminal" else "strong",
                "raw_value": round(phase_score, 4),
                "description": desc[:300],
                "detected_at": now,
            })

    except Exception as e:
        log.warning("Error extracting death spiral → blockchain_anomaly signals: %s", e)

    # ── Signal 2: Governance red flags → blockchain_anomaly ──────────────
    # Red flags: low circulating ratio, zero dev activity, dead market
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT security_id, circulating_ratio, dev_activity_score,
                           volume_to_mcap_ratio, liquidity_score
                    FROM raw_crypto_governance
                    WHERE snapshot_date = %s
                """, (today,))
                rows = cur.fetchall()

        for sid, circ_ratio, dev_score, vol_mcap, liq_score in rows:
            red_flags = []
            circ_ratio = float(circ_ratio) if circ_ratio is not None else None
            dev_score = float(dev_score) if dev_score is not None else None
            vol_mcap = float(vol_mcap) if vol_mcap is not None else None
            liq_score = float(liq_score) if liq_score is not None else None

            if circ_ratio is not None and circ_ratio < 0.30:
                red_flags.append(f"low_circ_ratio({circ_ratio:.2f})")
            if dev_score is not None and dev_score == 0:
                red_flags.append("zero_dev_activity")
            if vol_mcap is not None and vol_mcap < 0.001:
                red_flags.append(f"dead_market(vol/mcap={vol_mcap:.6f})")
            if liq_score is not None and liq_score < 5.0:
                red_flags.append(f"low_liquidity({liq_score:.1f})")

            if not red_flags:
                continue

            contribution = min(len(red_flags) / 5.0, 0.80)
            signals.append({
                "security_id": sid,
                "signal_type": "blockchain_anomaly",
                "contribution": round(contribution, 4),
                "confidence": 0.70,
                "direction": "bearish",
                "magnitude": "strong" if len(red_flags) >= 3 else "moderate",
                "raw_value": round(len(red_flags), 2),
                "description": f"Governance red flags ({len(red_flags)}): {', '.join(red_flags)}"[:300],
                "detected_at": now,
            })

    except Exception as e:
        log.warning("Error extracting governance red flag signals: %s", e)

    # ── Signal 3: Rug pull risk (crypto_rug_pull_risk) ───────────────────
    # When multiple high-severity indicators align: concentrated ownership +
    # abandoned development + collapsing volume
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Join governance + death spiral for combined assessment
                cur.execute("""
                    SELECT g.security_id,
                           g.holder_herfindahl,
                           g.circulating_ratio,
                           g.dev_activity_score,
                           g.volume_to_mcap_ratio,
                           d.volume_trend,
                           d.phase_score
                    FROM raw_crypto_governance g
                    LEFT JOIN raw_crypto_death_spiral d
                        ON d.security_id = g.security_id
                       AND d.detection_date = g.snapshot_date
                    WHERE g.snapshot_date = %s
                """, (today,))
                rows = cur.fetchall()

        for sid, herfindahl, circ_ratio, dev_score, vol_mcap, vol_trend, phase_score in rows:
            rug_indicators = []

            herfindahl = float(herfindahl) if herfindahl is not None else None
            circ_ratio = float(circ_ratio) if circ_ratio is not None else None
            dev_score = float(dev_score) if dev_score is not None else None
            vol_mcap = float(vol_mcap) if vol_mcap is not None else None

            if herfindahl is not None and herfindahl > 0.25:
                rug_indicators.append(f"concentrated_ownership(HHI={herfindahl:.4f})")
            if circ_ratio is not None and circ_ratio < 0.20:
                rug_indicators.append(f"extreme_supply_lock(circ={circ_ratio:.2f})")
            if dev_score is not None and dev_score == 0:
                rug_indicators.append("dev_abandoned")
            if vol_trend == "collapsing":
                rug_indicators.append("volume_collapsing")
            elif vol_mcap is not None and vol_mcap < 0.0005:
                rug_indicators.append(f"near_zero_volume(vol/mcap={vol_mcap:.6f})")

            # Need at least 3 indicators to flag rug pull risk
            if len(rug_indicators) < 3:
                continue

            signals.append({
                "security_id": sid,
                "signal_type": "crypto_rug_pull_risk",
                "contribution": 0.95,
                "confidence": 0.90,
                "direction": "bearish",
                "magnitude": "extreme",
                "raw_value": round(len(rug_indicators), 2),
                "description": f"Rug pull risk ({len(rug_indicators)} indicators): {', '.join(rug_indicators)}"[:300],
                "detected_at": now,
            })

    except Exception as e:
        log.warning("Error extracting rug pull risk signals: %s", e)

    # ── Signal 4: Death spiral progression (crypto_death_spiral) ─────────
    # Any non-healthy phase produces a signal proportional to the phase score.
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT security_id, phase, phase_score, indicators_triggered,
                           price_from_peak_pct, days_since_peak
                    FROM raw_crypto_death_spiral
                    WHERE detection_date = %s
                      AND phase != 'healthy'
                """, (today,))
                rows = cur.fetchall()

        for sid, phase, phase_score, indicators, drawdown, days_peak in rows:
            phase_score = float(phase_score or 0)
            drawdown = float(drawdown or 0)
            days_peak = int(days_peak or 0)

            magnitude = "moderate"
            if phase in ("critical", "terminal"):
                magnitude = "extreme"
            elif phase == "deteriorating":
                magnitude = "strong"

            desc = (f"Crypto death spiral phase={phase}: drawdown={drawdown:.1f}% "
                    f"over {days_peak}d")
            if indicators:
                desc += f" [{indicators}]"

            signals.append({
                "security_id": sid,
                "signal_type": "crypto_death_spiral",
                "contribution": round(min(phase_score, 1.0), 4),
                "confidence": 0.80,
                "direction": "bearish",
                "magnitude": magnitude,
                "raw_value": round(phase_score, 4),
                "description": desc[:300],
                "detected_at": now,
            })

    except Exception as e:
        log.warning("Error extracting death spiral progression signals: %s", e)

    # ── Write all signals ────────────────────────────────────────────────
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

    log.info("Crypto governance signals: %d signals fired "
             "(blockchain_anomaly + crypto_rug_pull_risk + crypto_death_spiral)", len(signals))
    return len(signals)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    n = run()
    log.info("Done — %d signals", n)
