"""
Backtesting Framework — validate signal accuracy against historical price data.

For each signal that fired historically, computes forward returns at 30d, 90d,
and 180d horizons and compares against SPY benchmark. Tracks per-signal hit rate
(did signal direction match subsequent price movement?) and excess returns.

Reads from: signals, raw_market_data
Writes to:  signal_backtests

Usage:
    python collectors/backtest.py           # backtest all signal types
    python collectors/backtest.py volume_spike  # backtest one signal type
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("backtest")


def _ensure_table():
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_backtests (
                    signal_type         VARCHAR(50) PRIMARY KEY,
                    sample_size         INT NOT NULL DEFAULT 0,
                    hit_rate_30d        NUMERIC(5,4),
                    hit_rate_90d        NUMERIC(5,4),
                    hit_rate_180d       NUMERIC(5,4),
                    avg_return_30d      NUMERIC(8,4),
                    avg_return_90d      NUMERIC(8,4),
                    avg_return_180d     NUMERIC(8,4),
                    avg_excess_30d      NUMERIC(8,4),
                    avg_excess_90d      NUMERIC(8,4),
                    avg_excess_180d     NUMERIC(8,4),
                    last_computed       TIMESTAMP DEFAULT now()
                );
            """)


def _load_price_data(cur):
    """Load all daily closes indexed by (security_id, date)."""
    cur.execute("""
        SELECT security_id, trade_date, close
        FROM raw_market_data
        WHERE close IS NOT NULL
        ORDER BY security_id, trade_date
    """)
    prices = defaultdict(dict)
    for sid, tdate, close in cur.fetchall():
        prices[sid][tdate] = float(close)
    return prices


def _load_spy_prices(cur):
    """Load SPY prices for benchmark comparison."""
    cur.execute("""
        SELECT trade_date, close
        FROM raw_market_data
        WHERE security_id = (SELECT security_id FROM securities WHERE ticker = 'SPY' LIMIT 1)
          AND close IS NOT NULL
        ORDER BY trade_date
    """)
    return {tdate: float(close) for tdate, close in cur.fetchall()}


def _forward_return(prices_by_date, signal_date, horizon_days):
    """Compute forward return from signal_date over horizon_days.

    Returns None if insufficient price data.
    """
    dates = sorted(prices_by_date.keys())
    # Find the closest trading day on or after signal_date
    start_price = None
    start_date = None
    for d in dates:
        if d >= signal_date:
            start_price = prices_by_date[d]
            start_date = d
            break
    if start_price is None:
        return None

    # Find the closest trading day on or after start_date + horizon
    target_date = start_date + timedelta(days=horizon_days)
    end_price = None
    for d in dates:
        if d >= target_date:
            end_price = prices_by_date[d]
            break
    if end_price is None:
        return None

    return (end_price - start_price) / start_price


def _direction_hit(signal_direction, forward_return):
    """Check if signal direction matched actual price movement."""
    if signal_direction == "neutral":
        return None  # can't evaluate neutral signals
    if forward_return is None:
        return None
    if signal_direction == "bearish":
        return forward_return < 0
    if signal_direction == "bullish":
        return forward_return > 0
    return None


def backtest(signal_type=None):
    """Run backtests for all (or one) signal type(s)."""
    _ensure_table()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Load signals
            if signal_type:
                cur.execute("""
                    SELECT security_id, signal_type, direction, detected_at
                    FROM signals
                    WHERE signal_type = %s
                    ORDER BY detected_at
                """, (signal_type,))
            else:
                cur.execute("""
                    SELECT security_id, signal_type, direction, detected_at
                    FROM signals
                    ORDER BY signal_type, detected_at
                """)
            all_signals = cur.fetchall()

            if not all_signals:
                log.info("No signals found to backtest")
                return

            log.info("Loading price data...")
            prices = _load_price_data(cur)
            spy_prices = _load_spy_prices(cur)

    log.info("Loaded %d signals, %d securities with price data, %d SPY dates",
             len(all_signals), len(prices), len(spy_prices))

    # Group signals by type
    by_type = defaultdict(list)
    for sid, stype, direction, detected_at in all_signals:
        by_type[stype].append((sid, direction, detected_at.date() if hasattr(detected_at, 'date') else detected_at))

    results = []
    for stype, sigs in sorted(by_type.items()):
        stats = {h: {"returns": [], "hits": [], "excess": []} for h in [30, 90, 180]}

        for sid, direction, signal_date in sigs:
            if sid not in prices:
                continue

            for horizon in [30, 90, 180]:
                ret = _forward_return(prices[sid], signal_date, horizon)
                spy_ret = _forward_return(spy_prices, signal_date, horizon)

                if ret is not None:
                    stats[horizon]["returns"].append(ret)
                    hit = _direction_hit(direction, ret)
                    if hit is not None:
                        stats[horizon]["hits"].append(hit)
                    if spy_ret is not None:
                        stats[horizon]["excess"].append(ret - spy_ret)

        sample = len(sigs)
        row = {"signal_type": stype, "sample_size": sample}

        for h in [30, 90, 180]:
            s = stats[h]
            row[f"hit_rate_{h}d"] = (
                sum(s["hits"]) / len(s["hits"]) if s["hits"] else None
            )
            row[f"avg_return_{h}d"] = (
                sum(s["returns"]) / len(s["returns"]) if s["returns"] else None
            )
            row[f"avg_excess_{h}d"] = (
                sum(s["excess"]) / len(s["excess"]) if s["excess"] else None
            )

        hit_30 = row.get("hit_rate_30d")
        hit_str = f"{hit_30:.1%}" if hit_30 is not None else "N/A"
        log.info("  %-30s  n=%-5d  hit_30d=%s", stype, sample, hit_str)
        results.append(row)

    # Write results
    if results:
        from psycopg2.extras import execute_values
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO signal_backtests
                           (signal_type, sample_size,
                            hit_rate_30d, hit_rate_90d, hit_rate_180d,
                            avg_return_30d, avg_return_90d, avg_return_180d,
                            avg_excess_30d, avg_excess_90d, avg_excess_180d,
                            last_computed)
                       VALUES %s
                       ON CONFLICT (signal_type)
                       DO UPDATE SET
                           sample_size = EXCLUDED.sample_size,
                           hit_rate_30d = EXCLUDED.hit_rate_30d,
                           hit_rate_90d = EXCLUDED.hit_rate_90d,
                           hit_rate_180d = EXCLUDED.hit_rate_180d,
                           avg_return_30d = EXCLUDED.avg_return_30d,
                           avg_return_90d = EXCLUDED.avg_return_90d,
                           avg_return_180d = EXCLUDED.avg_return_180d,
                           avg_excess_30d = EXCLUDED.avg_excess_30d,
                           avg_excess_90d = EXCLUDED.avg_excess_90d,
                           avg_excess_180d = EXCLUDED.avg_excess_180d,
                           last_computed = now()""",
                    [(r["signal_type"], r["sample_size"],
                      r.get("hit_rate_30d"), r.get("hit_rate_90d"), r.get("hit_rate_180d"),
                      r.get("avg_return_30d"), r.get("avg_return_90d"), r.get("avg_return_180d"),
                      r.get("avg_excess_30d"), r.get("avg_excess_90d"), r.get("avg_excess_180d"),
                      datetime.now(timezone.utc).replace(tzinfo=None))
                     for r in results],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                )

    log.info("Backtest complete: %d signal types evaluated", len(results))
    return results


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    backtest(signal_type=target)
