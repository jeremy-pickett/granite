"""
Insider Signals — derive IALD signals from raw_insider_trades.

Signals produced:
  - insider_sale_cluster:    3+ insiders selling within 30 days
  - insider_large_sale:      single sale >$500K or >50K shares
  - insider_purchase_cluster: 3+ insiders buying within 30 days (bullish)

Enhancements:
  - Sell-despite-good-news: boosts sale cluster contribution 1.5x when
    insiders sell into bullish analyst consensus or near 52-week highs.
  - CFO exit strategy: detects C-suite sustained liquidation (4+ months
    of selling in last 6 months with declining holdings).
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("insider_signals")


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).date()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Cluster detection: 3+ distinct sellers in 30 days
            cur.execute("""
                SELECT r.security_id, s.ticker,
                       count(DISTINCT r.reporter_name) AS seller_count,
                       sum(abs(r.shares_changed)) AS total_shares
                FROM raw_insider_trades r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.transaction_type = 'sale'
                  AND r.filing_date >= %s
                GROUP BY r.security_id, s.ticker
                HAVING count(DISTINCT r.reporter_name) >= 3
            """, (cutoff_30d,))
            clusters = cur.fetchall()

            # Large individual sales (by dollar value if available, else share count)
            cur.execute("""
                SELECT r.security_id, s.ticker, r.reporter_name,
                       abs(r.shares_changed) AS shares, r.filing_date,
                       r.total_value, r.insider_title
                FROM raw_insider_trades r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.transaction_type = 'sale'
                  AND (r.total_value > 500000 OR abs(r.shares_changed) > 50000)
                  AND r.filing_date >= %s
            """, (cutoff_30d,))
            large_sales = cur.fetchall()

            # Purchase cluster detection: 3+ distinct buyers in 30 days
            cur.execute("""
                SELECT r.security_id, s.ticker,
                       count(DISTINCT r.reporter_name) AS buyer_count,
                       sum(abs(r.shares_changed)) AS total_shares,
                       sum(COALESCE(r.total_value, 0)) AS total_value
                FROM raw_insider_trades r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.transaction_type = 'purchase'
                  AND r.filing_date >= %s
                GROUP BY r.security_id, s.ticker
                HAVING count(DISTINCT r.reporter_name) >= 3
            """, (cutoff_30d,))
            purchase_clusters = cur.fetchall()

    signals = []

    for sid, ticker, seller_count, total_shares in clusters:
        contribution = min(seller_count / 6.0, 1.0)
        signals.append({
            "security_id": sid,
            "signal_type": "insider_sale_cluster",
            "contribution": round(contribution, 4),
            "confidence": min(0.5 + seller_count / 10, 0.90),
            "direction": "bearish",
            "magnitude": "extreme" if seller_count >= 5 else "strong" if seller_count >= 4 else "moderate",
            "raw_value": float(seller_count),
            "description": f"{ticker} {seller_count} insiders sold in 30d ({total_shares:,} shares)",
            "detected_at": now,
        })

    # ── B1: Sell Despite Good News — boost sale clusters near 52w high or bullish consensus ──
    sale_cluster_sids = {sid for sid, _, _, _ in clusters}
    if sale_cluster_sids:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # Check for bullish analyst consensus signals in last 30 days
                cur.execute("""
                    SELECT DISTINCT security_id
                    FROM signals
                    WHERE signal_type = 'analyst_consensus_shift'
                      AND direction = 'bullish'
                      AND detected_at >= %s
                      AND security_id = ANY(%s)
                """, (cutoff_30d, list(sale_cluster_sids)))
                bullish_consensus_sids = {row[0] for row in cur.fetchall()}

                # Check for securities near 52-week high
                cur.execute("""
                    SELECT security_id,
                           max(close_price) AS high_52w,
                           (SELECT close_price FROM raw_market_data m2
                            WHERE m2.security_id = m.security_id
                            ORDER BY trade_date DESC LIMIT 1) AS latest_close
                    FROM raw_market_data m
                    WHERE trade_date >= current_date - 252
                      AND security_id = ANY(%s)
                    GROUP BY security_id
                    HAVING max(close_price) > 0
                """, (list(sale_cluster_sids),))
                near_high_sids = set()
                for row_sid, high_52w, latest_close in cur.fetchall():
                    if high_52w and latest_close and latest_close >= high_52w * 0.95:
                        near_high_sids.add(row_sid)

        good_news_sids = bullish_consensus_sids | near_high_sids
    else:
        good_news_sids = set()

    # Apply contrarian boost to sale cluster signals
    for sig in signals:
        if sig["signal_type"] == "insider_sale_cluster" and sig["security_id"] in good_news_sids:
            sig["contribution"] = min(round(sig["contribution"] * 1.5, 4), 1.0)
            sig["description"] += " [contrarian: selling into good news]"

    for sid, ticker, name, shares, filing_date, total_value, title in large_sales:
        total_value = float(total_value or 0)
        # Score by dollar value when available, else fall back to share count
        if total_value > 0:
            contribution = min(total_value / 5_000_000, 1.0)
            val_str = f"${total_value/1e6:.1f}M"
        else:
            contribution = min(shares / 500000, 1.0)
            val_str = f"{shares:,} shares"

        # C-suite sales get a confidence boost
        title_str = (title or "").lower()
        is_csuite = any(r in title_str for r in ["ceo", "cfo", "coo", "cto", "president", "chief"])
        confidence = 0.85 if is_csuite else 0.75

        desc = f"{ticker} insider {name[:30]} sold {val_str}"
        if title:
            desc += f" ({title[:30]})"

        signals.append({
            "security_id": sid,
            "signal_type": "insider_large_sale",
            "contribution": round(contribution, 4),
            "confidence": confidence,
            "direction": "bearish",
            "magnitude": "extreme" if contribution >= 0.6 else "strong" if contribution >= 0.35 else "moderate",
            "raw_value": total_value if total_value > 0 else float(shares),
            "description": desc[:300],
            "detected_at": now,
        })

    for sid, ticker, buyer_count, total_shares, total_value in purchase_clusters:
        contribution = min(buyer_count / 6.0, 1.0)
        total_value = float(total_value or 0)
        val_str = f"${total_value/1e6:.1f}M" if total_value > 0 else f"{total_shares:,} shares"
        signals.append({
            "security_id": sid,
            "signal_type": "insider_purchase_cluster",
            "contribution": round(contribution, 4),
            "confidence": min(0.5 + buyer_count / 10, 0.90),
            "direction": "bullish",
            "magnitude": "extreme" if buyer_count >= 5 else "strong" if buyer_count >= 4 else "moderate",
            "raw_value": float(buyer_count),
            "description": f"{ticker} {buyer_count} insiders bought in 30d ({val_str})",
            "detected_at": now,
        })

    # ── B3: CFO Exit Strategy — C-suite sustained liquidation over 6 months ──
    cutoff_180d = (datetime.now(timezone.utc) - timedelta(days=180)).date()
    csuite_patterns = ['%CEO%', '%CFO%', '%COO%', '%CTO%', '%Chief%', '%President%']
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Find C-suite insiders who sold in 4+ distinct months out of last 6
            cur.execute("""
                SELECT r.security_id, s.ticker, r.reporter_name, r.insider_title,
                       count(DISTINCT date_trunc('month', r.filing_date)) AS sell_months,
                       array_agg(DISTINCT r.shares_after ORDER BY r.shares_after) AS holdings_trend,
                       sum(abs(r.shares_changed)) AS total_sold
                FROM raw_insider_trades r
                JOIN securities s ON s.security_id = r.security_id
                WHERE r.transaction_type = 'sale'
                  AND r.filing_date >= %s
                  AND (r.insider_title ILIKE %s OR r.insider_title ILIKE %s
                       OR r.insider_title ILIKE %s OR r.insider_title ILIKE %s
                       OR r.insider_title ILIKE %s OR r.insider_title ILIKE %s)
                GROUP BY r.security_id, s.ticker, r.reporter_name, r.insider_title
                HAVING count(DISTINCT date_trunc('month', r.filing_date)) >= 4
            """, (cutoff_180d, *csuite_patterns))
            csuite_liquidations = cur.fetchall()

    for sid, ticker, name, title, sell_months, holdings_trend, total_sold in csuite_liquidations:
        # Check if holdings are trending down (last element <= first element)
        if holdings_trend and len(holdings_trend) >= 2:
            trending_down = holdings_trend[-1] is not None and holdings_trend[0] is not None and holdings_trend[-1] <= holdings_trend[0]
        else:
            trending_down = True  # Conservative: if we can't tell, flag it anyway

        if not trending_down:
            continue

        title_short = (title or "C-suite")[:30]
        signals.append({
            "security_id": sid,
            "signal_type": "insider_sale_cluster",
            "contribution": 0.90,
            "confidence": 0.90,
            "direction": "bearish",
            "magnitude": "extreme",
            "raw_value": float(sell_months),
            "description": f"{ticker} {title_short} {name[:20]} sustained liquidation strategy ({sell_months} months of selling)"[:300],
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

    log.info("Insider signals: %d sale clusters, %d large sales, %d purchase clusters, %d C-suite liquidations → %d signals",
             len(clusters), len(large_sales), len(purchase_clusters), len(csuite_liquidations), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
