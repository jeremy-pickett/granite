"""
On-Chain Activity — Active addresses, tx count, gas usage anomalies.

Collector ID: 22 (On-Chain Activity)
Table:        raw_onchain_activity

Daily chain-level metrics: transaction counts, mempool size, hash rate,
block stats. Anomalies in these metrics precede price moves — congestion
spikes mean people are rushing to transact.

Data sources:
  - Blockchain.com stats API (BTC, free)
  - Blockchair stats API (BTC/ETH, free)
  - Etherscan V2 (ETH gas, with key)
"""

import sys
import os
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"


class OnChainActivityCollector(BaseCollector):

    COLLECTOR_ID = 22
    COLLECTOR_NAME = "On-Chain Activity"
    COLLECTOR_TYPE = "blockchain"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_onchain_activity (
                        activity_id     SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        chain           VARCHAR(10) NOT NULL,
                        snapshot_date   DATE NOT NULL,
                        tx_count_24h    BIGINT,
                        mempool_size    BIGINT,
                        mempool_txs     INT,
                        hash_rate       NUMERIC(30,0),
                        avg_block_size  INT,
                        gas_price_gwei  NUMERIC(10,2),
                        difficulty      NUMERIC(30,0),
                        block_height    INT,
                        market_price    NUMERIC(16,2),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(chain, snapshot_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_roa_chain
                        ON raw_onchain_activity (chain, snapshot_date DESC);
                """)

    def fetch(self, securities):
        today = datetime.now(timezone.utc).date()
        rows = []

        # Find our crypto securities
        sec_map = {}
        for s in securities:
            t = s["ticker"].upper()
            if "BTC" in t or "bitcoin" in s.get("name", "").lower():
                sec_map["BTC"] = s["security_id"]
            elif "ETH" in t or "ethereum" in s.get("name", "").lower():
                sec_map["ETH"] = s["security_id"]
            elif "ADA" in t or "cardano" in s.get("name", "").lower():
                sec_map["ADA"] = s["security_id"]

        # BTC on-chain via blockchain.com + blockchair
        if "BTC" in sec_map:
            btc_row = self._fetch_btc(sec_map["BTC"], today)
            if btc_row:
                rows.append(btc_row)

        # ETH on-chain via blockchair + etherscan
        if "ETH" in sec_map:
            eth_row = self._fetch_eth(sec_map["ETH"], today)
            if eth_row:
                rows.append(eth_row)

        return rows

    def _fetch_btc(self, security_id, today):
        self.log.info("Fetching BTC on-chain metrics...")
        row = {
            "security_id": security_id,
            "chain": "BTC",
            "snapshot_date": today,
        }

        # Blockchain.com stats
        try:
            resp = requests.get("https://api.blockchain.info/stats", timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                d = resp.json()
                row["tx_count_24h"] = d.get("n_tx")
                row["hash_rate"] = d.get("hash_rate")
                row["market_price"] = d.get("market_price_usd")
                row["difficulty"] = d.get("difficulty")
                self.log.info("  BTC: %s tx/24h, price=$%s",
                              f'{d.get("n_tx",0):,}', f'{d.get("market_price_usd",0):,.0f}')
        except requests.RequestException as e:
            self.log.debug("Blockchain.com error: %s", e)

        # Blockchair for mempool + block stats
        try:
            resp = requests.get("https://api.blockchair.com/bitcoin/stats", timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                d = resp.json().get("data", {})
                row["mempool_txs"] = d.get("mempool_transactions")
                row["mempool_size"] = d.get("mempool_size")
                row["avg_block_size"] = d.get("average_block_size_24h")
                row["block_height"] = d.get("blocks")
                self.log.info("  BTC mempool: %s txs, block %s",
                              f'{d.get("mempool_transactions",0):,}', f'{d.get("blocks",0):,}')
        except requests.RequestException as e:
            self.log.debug("Blockchair error: %s", e)

        self.stats["fetched"] += 1
        return row

    def _fetch_eth(self, security_id, today):
        self.log.info("Fetching ETH on-chain metrics...")
        row = {
            "security_id": security_id,
            "chain": "ETH",
            "snapshot_date": today,
        }

        # Blockchair for ETH stats
        try:
            resp = requests.get("https://api.blockchair.com/ethereum/stats", timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                d = resp.json().get("data", {})
                row["tx_count_24h"] = d.get("transactions_24h")
                row["mempool_txs"] = d.get("mempool_transactions")
                row["mempool_size"] = d.get("mempool_size")
                row["block_height"] = d.get("blocks")
                row["market_price"] = d.get("market_price_usd")
                self.log.info("  ETH: %s tx/24h, block %s",
                              f'{d.get("transactions_24h",0):,}', f'{d.get("blocks",0):,}')
        except requests.RequestException as e:
            self.log.debug("Blockchair ETH error: %s", e)

        # Etherscan V2 for gas price
        if config.ETHERSCAN_API_KEY:
            try:
                resp = requests.get(
                    ETHERSCAN_V2,
                    params={
                        "chainid": 1,
                        "module": "proxy",
                        "action": "eth_gasPrice",
                        "apikey": config.ETHERSCAN_API_KEY,
                    },
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    result = resp.json().get("result", "0x0")
                    gas_wei = int(result, 16)
                    gas_gwei = gas_wei / 1e9
                    row["gas_price_gwei"] = round(gas_gwei, 2)
                    self.log.info("  ETH gas: %.1f gwei", gas_gwei)
            except (requests.RequestException, ValueError) as e:
                self.log.debug("Etherscan gas error: %s", e)

        self.stats["fetched"] += 1
        return row

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d on-chain activity snapshots...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_onchain_activity
                           (security_id, chain, snapshot_date, tx_count_24h,
                            mempool_size, mempool_txs, hash_rate, avg_block_size,
                            gas_price_gwei, difficulty, block_height, market_price)
                       VALUES %s
                       ON CONFLICT (chain, snapshot_date)
                       DO UPDATE SET tx_count_24h = EXCLUDED.tx_count_24h,
                                     mempool_size = EXCLUDED.mempool_size,
                                     mempool_txs = EXCLUDED.mempool_txs,
                                     hash_rate = EXCLUDED.hash_rate,
                                     gas_price_gwei = EXCLUDED.gas_price_gwei,
                                     market_price = EXCLUDED.market_price,
                                     last_updated = now()""",
                    [(r["security_id"], r["chain"], r["snapshot_date"],
                      r.get("tx_count_24h"), r.get("mempool_size"),
                      r.get("mempool_txs"), r.get("hash_rate"),
                      r.get("avg_block_size"), r.get("gas_price_gwei"),
                      r.get("difficulty"), r.get("block_height"),
                      r.get("market_price"))
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("On-chain activity: %d chains snapshotted, %d errors",
                      self.stats["fetched"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(OnChainActivityCollector)
