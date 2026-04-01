"""
Congressional Signals — derive IALD signals from raw_congressional_trades.

Signals produced:
  - congressional_trade: any congress member traded a security we track
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("congressional_signals")

# B5: Committee-to-sector mapping infrastructure.
# Maps congressional committee keywords to GICS sector keywords.
# TODO: Actual committee assignments per representative require congress.gov API
# integration (or a static lookup table maintained per Congress session).
# The `representative` column in raw_congressional_trades does not currently
# include committee membership. When that data is available, use this dict
# to detect committee-correlated trades (e.g., Banking Committee member
# trading financials).
COMMITTEE_SECTORS = {
    "banking": ["financials", "bank", "insurance"],
    "finance": ["financials", "bank", "insurance"],
    "energy": ["energy", "oil", "gas", "utilities"],
    "commerce": ["technology", "communication", "consumer"],
    "health": ["health", "pharma", "biotech"],
    "armed services": ["defense", "aerospace"],
    "agriculture": ["agriculture", "food", "consumer staples"],
}


def run():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.security_id, r.ticker, r.representative, r.party,
                       r.transaction_type, r.amount_low, r.amount_high,
                       r.trade_date, r.chamber
                FROM raw_congressional_trades r
                WHERE r.security_id IS NOT NULL
                  AND r.trade_date >= %s
                ORDER BY r.trade_date DESC
            """, (cutoff,))
            trades = cur.fetchall()

    # Group by security to detect clusters
    by_security: dict = {}
    for sid, ticker, rep, party, tx, amt_low, amt_high, trade_date, chamber in trades:
        by_security.setdefault(sid, []).append({
            "ticker": ticker, "rep": rep, "party": party, "tx": tx,
            "amt_low": amt_low or 0, "amt_high": amt_high or 0,
            "trade_date": trade_date, "chamber": chamber,
        })

    signals = []
    for sid, group in by_security.items():
        ticker = group[0]["ticker"]
        n_trades = len(group)
        n_reps = len({t["rep"] for t in group})
        max_amount = max(t["amt_high"] for t in group)

        # Scale contribution by number of reps and amounts
        contribution = min(0.3 + n_reps * 0.2 + (max_amount / 1000000) * 0.3, 1.0)

        if n_reps >= 3:
            magnitude = "extreme"
        elif n_reps >= 2 or max_amount >= 100000:
            magnitude = "strong"
        else:
            magnitude = "moderate"

        # Direction from transaction types
        sales = sum(1 for t in group if "sale" in (t["tx"] or "").lower())
        buys = sum(1 for t in group if "purchase" in (t["tx"] or "").lower())
        direction = "bearish" if sales > buys else "bullish" if buys > sales else "neutral"

        reps_str = ", ".join(sorted({t["rep"][:20] for t in group})[:3])
        signals.append({
            "security_id": sid,
            "signal_type": "congressional_trade",
            "contribution": round(contribution, 4),
            "confidence": min(0.6 + n_reps * 0.1, 0.95),
            "direction": direction,
            "magnitude": magnitude,
            "raw_value": float(n_trades),
            "description": f"{ticker} {n_trades} congressional trade(s) by {reps_str}",
            "detected_at": now,
        })

    # C1: Bipartisan Consensus Detector — boost signals where both parties
    # traded the same security in the same direction within the 30-day window.
    for sig in signals:
        sid = sig["security_id"]
        group = by_security.get(sid, [])
        parties_buying = set()
        parties_selling = set()
        for t in group:
            party = (t.get("party") or "").upper()
            if not party:
                continue
            tx = (t.get("tx") or "").lower()
            if "purchase" in tx:
                parties_buying.add(party)
            elif "sale" in tx:
                parties_selling.add(party)
        bipartisan_buy = "R" in parties_buying and "D" in parties_buying
        bipartisan_sell = "R" in parties_selling and "D" in parties_selling
        if bipartisan_buy or bipartisan_sell:
            sig["contribution"] = round(min(sig["contribution"] * 1.5, 1.0), 4)
            direction_word = "buying" if bipartisan_buy else "selling"
            sig["description"] += f" [bipartisan consensus: both parties {direction_word}]"

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

    log.info("Congressional signals: %d securities with trades → %d signals", len(by_security), len(signals))
    return len(signals)


if __name__ == "__main__":
    run()
