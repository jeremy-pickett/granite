"""
DefiLlama TVL Monitor — Total Value Locked across DeFi chains.

Collector ID: 40 (DefiLlama TVL Monitor)
Table:        raw_defi_tvl

Source: https://api.llama.fi/ (free, no auth)

Tracks TVL by chain for major L1/L2 networks. Fires blockchain_anomaly
signals when TVL drops >10% in 24h (liquidity flight) or rises >20%
(capital inflow).
"""

import sys
import os
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

# Chains to track and their security ticker mappings
TRACKED_CHAINS = [
    "Ethereum", "BSC", "Solana", "Arbitrum",
    "Polygon", "Avalanche", "Base", "Optimism",
]

# Chains with historical TVL fetch (for trend computation)
HISTORICAL_CHAINS = ["Ethereum", "Solana"]

# Map chain name → security ticker
CHAIN_TO_TICKER = {
    "Ethereum": "ETH-USD",
    "Solana": "SOL-USD",
    "BSC": "BNB-USD",
    "Avalanche": "AVAX-USD",
}


class DefiLlamaTVLCollector(BaseCollector):

    COLLECTOR_ID = 40
    COLLECTOR_NAME = "DefiLlama TVL Monitor"
    COLLECTOR_TYPE = "blockchain"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_defi_tvl (
                        tvl_id              SERIAL PRIMARY KEY,
                        chain               VARCHAR(30) NOT NULL,
                        observation_date    DATE NOT NULL,
                        tvl_usd             NUMERIC(20,2),
                        tvl_change_24h_pct  NUMERIC(8,4),
                        collected_at        TIMESTAMP DEFAULT now(),
                        UNIQUE(chain, observation_date)
                    );
                """)

    def fetch(self, securities):
        rows = []
        today = datetime.now(timezone.utc).date()

        # 1. Current TVL by chain
        self.log.info("Fetching current chain TVL from DefiLlama...")
        try:
            resp = requests.get(
                "https://api.llama.fi/v2/chains",
                timeout=config.HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            chains = resp.json()

            chain_tvl = {}
            for c in chains:
                name = c.get("name", "")
                if name in TRACKED_CHAINS:
                    tvl = float(c.get("tvl", 0))
                    chain_tvl[name] = tvl
                    self.log.info("  %s: $%.2fB TVL", name, tvl / 1e9)

            self.stats["fetched"] += len(chain_tvl)
        except requests.RequestException as e:
            self.log.error("DefiLlama chains API error: %s", e)
            self.stats["errors"] += 1
            chain_tvl = {}

        # 2. Historical TVL for trend chains (7 days)
        historical = {}
        for chain_name in HISTORICAL_CHAINS:
            self.log.info("Fetching 7d historical TVL for %s...", chain_name)
            try:
                resp = requests.get(
                    f"https://api.llama.fi/v2/historicalChainTvl/{chain_name}",
                    timeout=config.HTTP_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()

                # Get last 7 days of data points
                cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=8)).timestamp())
                recent = [d for d in data if d.get("date", 0) >= cutoff_ts]
                recent.sort(key=lambda d: d["date"])

                if len(recent) >= 2:
                    historical[chain_name] = recent
                    self.log.info("  %s: %d historical data points", chain_name, len(recent))
            except requests.RequestException as e:
                self.log.warning("DefiLlama historical error for %s: %s", chain_name, e)
                self.stats["errors"] += 1

        # 3. Build rows: current TVL + computed 24h change
        for chain_name, tvl in chain_tvl.items():
            change_pct = None

            if chain_name in historical and len(historical[chain_name]) >= 2:
                hist = historical[chain_name]
                # Latest and previous day
                latest_tvl = hist[-1].get("tvl", 0)
                prev_tvl = hist[-2].get("tvl", 0)
                if prev_tvl > 0:
                    change_pct = round(((latest_tvl - prev_tvl) / prev_tvl) * 100, 4)

            # Map to security_id
            ticker = CHAIN_TO_TICKER.get(chain_name)
            sid = None
            if ticker:
                sid = next(
                    (s["security_id"] for s in securities if s["ticker"] == ticker),
                    None,
                )

            rows.append({
                "security_id": sid,
                "chain": chain_name,
                "observation_date": today,
                "tvl_usd": tvl,
                "tvl_change_24h_pct": change_pct,
            })

        # Also insert historical daily rows for trend chains
        for chain_name, hist_data in historical.items():
            ticker = CHAIN_TO_TICKER.get(chain_name)
            sid = None
            if ticker:
                sid = next(
                    (s["security_id"] for s in securities if s["ticker"] == ticker),
                    None,
                )

            for i, point in enumerate(hist_data):
                obs_date = datetime.fromtimestamp(
                    point["date"], tz=timezone.utc
                ).date()
                tvl_val = point.get("tvl", 0)
                prev_tvl = hist_data[i - 1].get("tvl", 0) if i > 0 else 0
                pct = round(((tvl_val - prev_tvl) / prev_tvl) * 100, 4) if prev_tvl > 0 else None

                # Skip if we already have today's row from the current TVL fetch
                if obs_date == today and chain_name in chain_tvl:
                    continue

                rows.append({
                    "security_id": sid,
                    "chain": chain_name,
                    "observation_date": obs_date,
                    "tvl_usd": tvl_val,
                    "tvl_change_24h_pct": pct,
                })

        return rows

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d TVL records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_defi_tvl
                           (chain, observation_date, tvl_usd, tvl_change_24h_pct)
                       VALUES %s
                       ON CONFLICT (chain, observation_date)
                       DO UPDATE SET tvl_usd = EXCLUDED.tvl_usd,
                                     tvl_change_24h_pct = EXCLUDED.tvl_change_24h_pct""",
                    [(r["chain"], r["observation_date"], r["tvl_usd"],
                      r["tvl_change_24h_pct"])
                     for r in rows],
                    template="(%s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("DefiLlama TVL: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


# ── Signal extraction ─────────────────────────────────────────────────

def run_signals():
    """Fire blockchain_anomaly signals on extreme TVL movements."""
    import logging
    logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
    log = logging.getLogger("defillama_signals")

    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today = datetime.now(timezone.utc).date()
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Get the most recent TVL readings with 24h change
            try:
                cur.execute("""
                    SELECT dt.chain, dt.observation_date, dt.tvl_usd, dt.tvl_change_24h_pct
                    FROM raw_defi_tvl dt
                    WHERE dt.observation_date >= %s - INTERVAL '2 days'
                      AND dt.tvl_change_24h_pct IS NOT NULL
                    ORDER BY dt.observation_date DESC
                """, (today,))
                rows = cur.fetchall()
            except Exception as e:
                log.warning("Query error: %s", e)
                rows = []

            # Deduplicate: keep most recent per chain
            seen_chains = set()
            deduped = []
            for chain, obs_date, tvl_usd, change_pct in rows:
                if chain not in seen_chains:
                    seen_chains.add(chain)
                    deduped.append((chain, obs_date, tvl_usd, change_pct))

            for chain, obs_date, tvl_usd, change_pct in deduped:
                change_pct = float(change_pct)

                # Map chain to security_id
                ticker = CHAIN_TO_TICKER.get(chain)
                if not ticker:
                    continue

                try:
                    cur.execute(
                        "SELECT security_id FROM securities WHERE ticker = %s LIMIT 1",
                        (ticker,),
                    )
                    sec_row = cur.fetchone()
                except Exception:
                    sec_row = None

                if not sec_row:
                    continue

                sid = sec_row[0]

                # TVL drop >10% → liquidity flight (bearish)
                if change_pct < -10:
                    contribution = min(abs(change_pct) / 30.0, 1.0)
                    signals.append({
                        "security_id": sid,
                        "signal_type": "blockchain_anomaly",
                        "contribution": round(contribution, 4),
                        "confidence": 0.70,
                        "direction": "bearish",
                        "magnitude": "extreme" if change_pct < -20 else "strong",
                        "raw_value": change_pct,
                        "description": (
                            f"{chain} TVL dropped {change_pct:.1f}% "
                            f"(${float(tvl_usd)/1e9:.2f}B) — liquidity flight"
                        ),
                        "detected_at": now,
                    })

                # TVL rise >20% → capital inflow (bullish)
                elif change_pct > 20:
                    contribution = min(change_pct / 50.0, 1.0)
                    signals.append({
                        "security_id": sid,
                        "signal_type": "blockchain_anomaly",
                        "contribution": round(contribution, 4),
                        "confidence": 0.65,
                        "direction": "bullish",
                        "magnitude": "extreme" if change_pct > 40 else "strong",
                        "raw_value": change_pct,
                        "description": (
                            f"{chain} TVL surged +{change_pct:.1f}% "
                            f"(${float(tvl_usd)/1e9:.2f}B) — capital inflow"
                        ),
                        "detected_at": now,
                    })

    if signals:
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

    log.info("DefiLlama signals: %d fired", len(signals))
    return len(signals)


if __name__ == "__main__":
    run_collector(DefiLlamaTVLCollector)
