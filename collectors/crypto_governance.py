"""
Crypto Project Governance — token distribution, developer activity, and market health.

Collector ID: 33 (Crypto Project Governance)
Table:        raw_crypto_governance

Builds a governance profile for each crypto project using multiple data sources.
Tracks token concentration, supply dynamics, developer activity, and liquidity.
Projects with concentrated ownership, locked supply, and zero development
are the precursors to rug pulls.

Data sources:
  - CoinGecko API (free, no key, 30 req/min)
  - Santiment raw_santiment_metrics (dev_activity, daily_active_addresses)
"""

import sys
import os
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

log = logging.getLogger("crypto_governance")

# Map our ticker symbols to CoinGecko IDs
TICKER_TO_COINGECKO = {
    "BTC-USD": "bitcoin",
    "BTC":     "bitcoin",
    "ETH-USD": "ethereum",
    "ETH":     "ethereum",
}

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class CryptoGovernanceCollector(BaseCollector):

    COLLECTOR_ID = 33
    COLLECTOR_NAME = "Crypto Project Governance"
    COLLECTOR_TYPE = "blockchain"
    SECURITY_TYPE_FILTER = "crypto"

    def setup(self):
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_crypto_governance (
                        gov_id              SERIAL PRIMARY KEY,
                        security_id         INT NOT NULL REFERENCES securities(security_id),
                        snapshot_date       DATE NOT NULL,
                        top10_holder_pct    NUMERIC(8,4),
                        top1_holder_pct     NUMERIC(8,4),
                        holder_herfindahl   NUMERIC(8,6),
                        total_holders       INT,
                        circulating_supply  NUMERIC(20,2),
                        total_supply        NUMERIC(20,2),
                        circulating_ratio   NUMERIC(8,4),
                        github_commits_30d  INT,
                        github_contributors INT,
                        dev_activity_score  NUMERIC(8,2),
                        contract_verified   BOOLEAN,
                        contract_age_days   INT,
                        liquidity_score     NUMERIC(8,4),
                        volume_to_mcap_ratio NUMERIC(8,6),
                        collected_at        TIMESTAMP DEFAULT now(),
                        last_updated        TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, snapshot_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rcg_security_date
                        ON raw_crypto_governance (security_id, snapshot_date DESC);
                """)

    def _coingecko_get(self, path, params=None):
        """Rate-limited GET against CoinGecko free API."""
        url = f"{COINGECKO_BASE}/{path}"
        for attempt in range(config.HTTP_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
                if resp.status_code == 429:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("CoinGecko rate limited, waiting %.1fs...", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt < config.HTTP_RETRIES - 1:
                    wait = config.HTTP_BACKOFF ** (attempt + 1)
                    self.log.warning("CoinGecko request error (attempt %d): %s — retrying in %.1fs",
                                     attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    self.log.error("CoinGecko request failed after %d attempts: %s",
                                   config.HTTP_RETRIES, e)
                    raise
        return None

    def _get_santiment_dev_activity(self, security_id):
        """Pull latest dev_activity from raw_santiment_metrics if available."""
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT value FROM raw_santiment_metrics
                        WHERE security_id = %s
                          AND metric_name = 'dev_activity'
                        ORDER BY observation_date DESC
                        LIMIT 1
                    """, (security_id,))
                    row = cur.fetchone()
                    return float(row[0]) if row else None
        except Exception:
            return None

    def _get_santiment_active_addresses(self, security_id):
        """Pull latest daily_active_addresses from raw_santiment_metrics."""
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT value FROM raw_santiment_metrics
                        WHERE security_id = %s
                          AND metric_name = 'daily_active_addresses'
                        ORDER BY observation_date DESC
                        LIMIT 1
                    """, (security_id,))
                    row = cur.fetchone()
                    return float(row[0]) if row else None
        except Exception:
            return None

    def fetch(self, securities):
        rows = []
        today = datetime.now(timezone.utc).date()

        for sec in securities:
            ticker = sec["ticker"]
            coin_id = TICKER_TO_COINGECKO.get(ticker)
            if not coin_id:
                self.log.debug("No CoinGecko mapping for %s, skipping", ticker)
                self.stats["skipped"] += 1
                continue

            self.log.info("Fetching governance data for %s (%s)...", ticker, coin_id)

            try:
                # Step 1: CoinGecko coin detail
                data = self._coingecko_get(
                    f"coins/{coin_id}",
                    params={
                        "localization": "false",
                        "tickers": "false",
                        "community_data": "true",
                        "developer_data": "true",
                    },
                )
                if not data:
                    self.log.warning("No CoinGecko data for %s", coin_id)
                    self.stats["skipped"] += 1
                    continue

                # Extract supply metrics
                market_data = data.get("market_data", {})
                circulating = market_data.get("circulating_supply")
                total = market_data.get("total_supply")
                total_volume = (market_data.get("total_volume") or {}).get("usd")
                market_cap = (market_data.get("market_cap") or {}).get("usd")

                # Compute derived metrics
                circ_ratio = None
                if circulating and total and total > 0:
                    circ_ratio = circulating / total

                vol_mcap_ratio = None
                if total_volume and market_cap and market_cap > 0:
                    vol_mcap_ratio = total_volume / market_cap

                # Extract developer data
                dev_data = data.get("developer_data", {})
                commits_4w = dev_data.get("commit_count_4_weeks")
                contributors = None
                # CoinGecko provides code_additions_deletions_4_weeks
                # but not direct contributor count; use stars as proxy
                # for project health alongside commit count

                # Liquidity score from CoinGecko
                liquidity_score = data.get("liquidity_score")

                # Step 2: Pull Santiment dev_activity if available
                santiment_dev = self._get_santiment_dev_activity(sec["security_id"])

                # Compute a combined dev_activity_score
                dev_score = None
                if santiment_dev is not None:
                    dev_score = santiment_dev
                elif commits_4w is not None:
                    dev_score = float(commits_4w)

                row = {
                    "security_id":       sec["security_id"],
                    "snapshot_date":     today,
                    "top10_holder_pct":  None,  # Requires on-chain analysis for each chain
                    "top1_holder_pct":   None,
                    "holder_herfindahl": None,
                    "total_holders":     None,
                    "circulating_supply": circulating,
                    "total_supply":      total,
                    "circulating_ratio": circ_ratio,
                    "github_commits_30d": commits_4w,
                    "github_contributors": contributors,
                    "dev_activity_score": dev_score,
                    "contract_verified": None,  # ERC-20 only, future expansion
                    "contract_age_days": None,
                    "liquidity_score":   liquidity_score,
                    "volume_to_mcap_ratio": vol_mcap_ratio,
                }
                rows.append(row)
                self.stats["fetched"] += 1

                self.log.info("  %s: circ_ratio=%.4f  vol/mcap=%.6f  commits_4w=%s  dev_score=%s  liq=%.2f",
                              coin_id,
                              circ_ratio or 0,
                              vol_mcap_ratio or 0,
                              commits_4w,
                              dev_score,
                              float(liquidity_score or 0))

                # CoinGecko free tier: ~30 req/min — be conservative
                time.sleep(2.5)

            except Exception as e:
                self.log.warning("Error fetching governance data for %s: %s", ticker, e)
                self.stats["errors"] += 1

        return rows

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d governance records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_crypto_governance
                           (security_id, snapshot_date, top10_holder_pct,
                            top1_holder_pct, holder_herfindahl, total_holders,
                            circulating_supply, total_supply, circulating_ratio,
                            github_commits_30d, github_contributors, dev_activity_score,
                            contract_verified, contract_age_days,
                            liquidity_score, volume_to_mcap_ratio)
                       VALUES %s
                       ON CONFLICT (security_id, snapshot_date)
                       DO UPDATE SET top10_holder_pct     = EXCLUDED.top10_holder_pct,
                                     top1_holder_pct      = EXCLUDED.top1_holder_pct,
                                     holder_herfindahl    = EXCLUDED.holder_herfindahl,
                                     total_holders        = EXCLUDED.total_holders,
                                     circulating_supply   = EXCLUDED.circulating_supply,
                                     total_supply         = EXCLUDED.total_supply,
                                     circulating_ratio    = EXCLUDED.circulating_ratio,
                                     github_commits_30d   = EXCLUDED.github_commits_30d,
                                     github_contributors  = EXCLUDED.github_contributors,
                                     dev_activity_score   = EXCLUDED.dev_activity_score,
                                     contract_verified    = EXCLUDED.contract_verified,
                                     contract_age_days    = EXCLUDED.contract_age_days,
                                     liquidity_score      = EXCLUDED.liquidity_score,
                                     volume_to_mcap_ratio = EXCLUDED.volume_to_mcap_ratio,
                                     last_updated         = now()""",
                    [(r["security_id"], r["snapshot_date"], r["top10_holder_pct"],
                      r["top1_holder_pct"], r["holder_herfindahl"], r["total_holders"],
                      r["circulating_supply"], r["total_supply"], r["circulating_ratio"],
                      r["github_commits_30d"], r["github_contributors"], r["dev_activity_score"],
                      r["contract_verified"], r["contract_age_days"],
                      r["liquidity_score"], r["volume_to_mcap_ratio"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        if hasattr(self, "_session"):
            self._session.close()
        self.log.info("Governance: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(CryptoGovernanceCollector)
