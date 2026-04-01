"""
Blockchain Signals — derive IALD signals from all three blockchain collectors.

Reads:
  - raw_crypto_whale_txs (whale movements)
  - raw_exchange_flows (exchange balance snapshots)
  - raw_onchain_activity (chain metrics)

Signals produced:
  - blockchain_anomaly: Composite signal from whale activity, exchange flows,
    and on-chain metrics. Fires on: large whale movements, exchange balance
    shifts, mempool congestion spikes, or hash rate changes.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("blockchain_signals")


def _safe_query(cur, sql, params):
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception:
        try:
            cur.execute("ROLLBACK")
            cur.execute("BEGIN")
        except Exception:
            pass
        return []


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff_1d = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).date()

    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # 1. Whale activity — count and volume of large txs in last 24h
            whale_rows = _safe_query(cur, """
                SELECT security_id, count(*) AS tx_count,
                       sum(amount_btc) AS total_btc,
                       sum(amount_usd) AS total_usd,
                       count(*) FILTER (WHERE to_exchange IS NOT NULL) AS to_exchange_count,
                       count(*) FILTER (WHERE from_exchange IS NOT NULL) AS from_exchange_count
                FROM raw_crypto_whale_txs
                WHERE tx_time >= %s::date
                GROUP BY security_id
            """, (cutoff_1d,))

            for sid, tx_count, total_btc, total_usd, to_ex, from_ex in whale_rows:
                tx_count = int(tx_count)
                total_btc = float(total_btc or 0)
                total_usd = float(total_usd or 0)
                to_ex = int(to_ex or 0)
                from_ex = int(from_ex or 0)

                # Score: more txs + higher volume + exchange-bound = stronger
                vol_score = min(total_btc / 500, 0.4)
                count_score = min(tx_count / 20, 0.3)
                exchange_score = min((to_ex + from_ex) / 10, 0.3)
                contribution = min(vol_score + count_score + exchange_score, 1.0)

                if contribution < 0.15:
                    continue

                direction = "bearish" if to_ex > from_ex else "bullish" if from_ex > to_ex else "neutral"
                magnitude = "extreme" if contribution >= 0.6 else "strong" if contribution >= 0.35 else "moderate"

                desc = f"BTC {tx_count} whale txs ({total_btc:.0f} BTC, ${total_usd/1e6:.1f}M)"
                if to_ex:
                    desc += f", {to_ex} to exchanges"
                if from_ex:
                    desc += f", {from_ex} from exchanges"

                signals.append({
                    "security_id": sid,
                    "signal_type": "blockchain_anomaly",
                    "contribution": round(contribution, 4),
                    "confidence": 0.70,
                    "direction": direction,
                    "magnitude": magnitude,
                    "raw_value": float(tx_count),
                    "description": desc[:300],
                    "detected_at": now,
                })

            # 2. Exchange net flow — day-over-day balance deltas
            flow_rows = _safe_query(cur, """
                WITH ranked AS (
                    SELECT security_id, exchange_name, snapshot_date, balance_btc,
                           ROW_NUMBER() OVER (
                               PARTITION BY exchange_name ORDER BY snapshot_date DESC
                           ) AS rn
                    FROM raw_exchange_flows
                    WHERE snapshot_date >= %s
                )
                SELECT r1.security_id, r1.exchange_name,
                       r1.balance_btc AS latest_btc,
                       r2.balance_btc AS prev_btc,
                       r1.balance_btc - r2.balance_btc AS delta_btc
                FROM ranked r1
                JOIN ranked r2 ON r1.exchange_name = r2.exchange_name
                                  AND r1.rn = 1 AND r2.rn = 2
            """, (cutoff_7d,))

            if flow_rows:
                # Aggregate net flow across all exchanges
                total_net_flow = sum(float(r[4] or 0) for r in flow_rows)
                # Use the security_id from the first row (all should be BTC-USD)
                flow_sid = flow_rows[0][0]
                abs_flow = abs(total_net_flow)

                if abs_flow > 100:  # >100 BTC net movement is noteworthy
                    contribution = min(abs_flow / 2000, 0.4)
                    # Inflow to exchanges = selling pressure (bearish)
                    # Outflow from exchanges = accumulation (bullish)
                    direction = "bearish" if total_net_flow > 0 else "bullish"
                    n_exchanges = len(flow_rows)
                    desc = (f"Exchange net flow: {total_net_flow:+,.0f} BTC "
                            f"across {n_exchanges} exchanges")

                    signals.append({
                        "security_id": flow_sid,
                        "signal_type": "blockchain_anomaly",
                        "contribution": round(contribution, 4),
                        "confidence": 0.70,
                        "direction": direction,
                        "magnitude": "strong" if abs_flow > 1000 else "moderate",
                        "raw_value": round(total_net_flow, 2),
                        "description": desc[:300],
                        "detected_at": now,
                    })

            # 3. On-chain anomalies — high mempool, tx spikes
            chain_rows = _safe_query(cur, """
                SELECT security_id, chain, mempool_txs, tx_count_24h
                FROM raw_onchain_activity
                WHERE snapshot_date = %s
            """, (cutoff_1d,))

            for sid, chain, mempool_txs, tx_count in chain_rows:
                mempool_txs = int(mempool_txs or 0)
                tx_count = int(tx_count or 0)

                # BTC mempool > 50k or ETH mempool > 100k = congestion
                if chain == "BTC" and mempool_txs > 50000:
                    signals.append({
                        "security_id": sid,
                        "signal_type": "blockchain_anomaly",
                        "contribution": min(mempool_txs / 200000, 1.0),
                        "confidence": 0.65,
                        "direction": "neutral",
                        "magnitude": "strong" if mempool_txs > 100000 else "moderate",
                        "raw_value": float(mempool_txs),
                        "description": f"BTC mempool congestion: {mempool_txs:,} pending txs",
                        "detected_at": now,
                    })
                elif chain == "ETH" and mempool_txs > 100000:
                    signals.append({
                        "security_id": sid,
                        "signal_type": "blockchain_anomaly",
                        "contribution": min(mempool_txs / 500000, 1.0),
                        "confidence": 0.65,
                        "direction": "neutral",
                        "magnitude": "strong" if mempool_txs > 200000 else "moderate",
                        "raw_value": float(mempool_txs),
                        "description": f"ETH mempool congestion: {mempool_txs:,} pending txs",
                        "detected_at": now,
                    })

    # 4. Propagate crypto signals to equities via crypto_exposure
    crypto_signals = [s for s in signals if s["contribution"] >= 0.20]
    if crypto_signals:
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT ce.security_id, s.ticker, ce.exposure_score, ce.classification
                        FROM crypto_exposure ce
                        JOIN securities s ON s.security_id = ce.security_id
                        WHERE ce.exposure_score > 0.2
                          AND s.security_type = 'equity'
                    """)
                    exposed = cur.fetchall()
        except Exception:
            exposed = []

        for eq_sid, eq_ticker, exposure, classification in exposed:
            # Pick the strongest crypto signal to propagate
            strongest = max(crypto_signals, key=lambda s: s["contribution"])
            prop_contribution = round(strongest["contribution"] * float(exposure) * 0.5, 4)
            if prop_contribution < 0.10:
                continue
            signals.append({
                "security_id": eq_sid,
                "signal_type": "blockchain_anomaly",
                "contribution": prop_contribution,
                "confidence": 0.50,
                "direction": strongest["direction"],
                "magnitude": "moderate",
                "raw_value": strongest["raw_value"],
                "description": (f"{eq_ticker} ({classification}) crypto exposure propagation "
                                f"from {strongest['description'][:100]}")[:300],
                "detected_at": now,
            })

        if exposed:
            log.info("Propagated blockchain signals to %d exposed equities", len(exposed))

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

    log.info("Blockchain signals: %d signals fired", len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
