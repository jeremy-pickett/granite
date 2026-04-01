"""
Crypto Whale Tracker — Large wallet movements and exchange inflow/outflow.

Collector ID: 20 (Crypto Whale Tracker)
Table:        raw_crypto_whale_txs

Tracks large BTC transactions from the mempool and recent blocks.
When whales move coins — especially to/from exchanges — it's a
leading indicator of buying/selling pressure.

Data sources:
  - Blockchain.com API (free, no key) — BTC large txs
  - Blockchain.com balance API — known exchange wallet monitoring
"""

import sys
import os
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

# Known exchange cold wallet addresses (BTC)
EXCHANGE_WALLETS = {
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance",
    "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h": "Binance",
    "1FzWLkAahHooV3kzTgyx6qsXoRDrBv5CeG": "Bitfinex",
    "3JZq4atUahhuA9rLhXLMhhTo133J9rF97j": "Bitfinex",
    "1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g": "Bittrex",
    "bc1qazcm763858nkj2dz7g3vafgk2ys9xceawk2qhj": "Coinbase",
    "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64": "Coinbase",
    "3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb": "OKX",
    "bc1q2s3rjwvam9dt2ftt4sqxqjf3twav0gdx0k0q2etjz8pd4": "Kraken",
}

WHALE_THRESHOLD_BTC = 10.0  # minimum BTC to track


class CryptoWhaleCollector(BaseCollector):

    COLLECTOR_ID = 20
    COLLECTOR_NAME = "Crypto Whale Tracker"
    COLLECTOR_TYPE = "blockchain"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_crypto_whale_txs (
                        whale_id        SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        tx_hash         TEXT NOT NULL,
                        amount_btc      NUMERIC(16,8),
                        amount_usd      NUMERIC(16,2),
                        from_exchange   TEXT,
                        to_exchange     TEXT,
                        tx_time         TIMESTAMP,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(tx_hash)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rcwt_security
                        ON raw_crypto_whale_txs (security_id, tx_time DESC);
                """)

    def fetch(self, securities):
        btc_sec = next((s for s in securities if s["ticker"] == "BTC-USD"
                        or s["ticker"] == "BTC"), None)
        if not btc_sec:
            # Try without -USD
            for s in securities:
                if "BTC" in s["ticker"] or "bitcoin" in s.get("name", "").lower():
                    btc_sec = s
                    break

        if not btc_sec:
            self.log.warning("No BTC security found in universe")
            self.stats["skipped"] += 1
            return []

        rows = []

        # Source 1: Recent unconfirmed large transactions
        self.log.info("Fetching BTC mempool large transactions...")
        try:
            resp = requests.get(
                "https://blockchain.info/unconfirmed-transactions?format=json",
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                txs = resp.json().get("txs", [])
                btc_price = self._get_btc_price()

                for tx in txs:
                    total_out = sum(o.get("value", 0) for o in tx.get("out", [])) / 1e8
                    if total_out < WHALE_THRESHOLD_BTC:
                        continue

                    tx_hash = tx.get("hash", "")
                    # Check if to/from known exchange
                    from_exchange = None
                    to_exchange = None
                    for inp in tx.get("inputs", []):
                        addr = inp.get("prev_out", {}).get("addr", "")
                        if addr in EXCHANGE_WALLETS:
                            from_exchange = EXCHANGE_WALLETS[addr]
                    for out in tx.get("out", []):
                        addr = out.get("addr", "")
                        if addr in EXCHANGE_WALLETS:
                            to_exchange = EXCHANGE_WALLETS[addr]

                    rows.append({
                        "security_id": btc_sec["security_id"],
                        "tx_hash": tx_hash,
                        "amount_btc": total_out,
                        "amount_usd": total_out * btc_price if btc_price else None,
                        "from_exchange": from_exchange,
                        "to_exchange": to_exchange,
                        "tx_time": datetime.fromtimestamp(
                            tx.get("time", 0), tz=timezone.utc
                        ).replace(tzinfo=None) if tx.get("time") else None,
                    })

                self.stats["fetched"] += len(rows)
                self.log.info("  Found %d whale transactions (>%.0f BTC)", len(rows), WHALE_THRESHOLD_BTC)
        except requests.RequestException as e:
            self.log.warning("Blockchain.com error: %s", e)
            self.stats["errors"] += 1

        # Source 2: Exchange wallet balance snapshots
        self.log.info("Checking exchange wallet balances...")
        try:
            addrs = "|".join(EXCHANGE_WALLETS.keys())
            resp = requests.get(
                f"https://blockchain.info/balance?active={addrs}",
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                balances = resp.json()
                for addr, info in balances.items():
                    exchange = EXCHANGE_WALLETS.get(addr, "Unknown")
                    bal_btc = info.get("final_balance", 0) / 1e8
                    self.log.info("  %s: %.2f BTC", exchange, bal_btc)
        except requests.RequestException as e:
            self.log.debug("Balance check error: %s", e)

        return rows

    def _get_btc_price(self):
        try:
            resp = requests.get(
                "https://api.blockchain.info/stats",
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("market_price_usd", 0)
        except requests.RequestException:
            pass
        return None

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d whale transaction records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_crypto_whale_txs
                           (security_id, tx_hash, amount_btc, amount_usd,
                            from_exchange, to_exchange, tx_time)
                       VALUES %s
                       ON CONFLICT (tx_hash)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["tx_hash"], r["amount_btc"],
                      r["amount_usd"], r["from_exchange"], r["to_exchange"],
                      r["tx_time"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Whale tracker: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(CryptoWhaleCollector)
