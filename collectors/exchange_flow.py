"""
Exchange Flow Monitor — Net exchange deposits/withdrawals across major CEXs.

Collector ID: 21 (Exchange Flow Monitor)
Table:        raw_exchange_flows

Daily snapshots of known exchange wallet balances. When BTC flows
into exchanges → selling pressure. When it flows out → accumulation.
The delta between daily snapshots IS the signal.

Data source: Blockchain.com balance API (free, no key).
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

# Known exchange wallets — same list, tracked daily for flow deltas
EXCHANGE_WALLETS = {
    "Binance": [
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
        "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h",
    ],
    "Bitfinex": [
        "1FzWLkAahHooV3kzTgyx6qsXoRDrBv5CeG",
        "3JZq4atUahhuA9rLhXLMhhTo133J9rF97j",
    ],
    "Coinbase": [
        "bc1qazcm763858nkj2dz7g3vafgk2ys9xceawk2qhj",
        "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64",
    ],
    "OKX": [
        "3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb",
    ],
}


class ExchangeFlowCollector(BaseCollector):

    COLLECTOR_ID = 21
    COLLECTOR_NAME = "Exchange Flow Monitor"
    COLLECTOR_TYPE = "blockchain"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_exchange_flows (
                        flow_id         SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        exchange_name   TEXT NOT NULL,
                        snapshot_date   DATE NOT NULL,
                        balance_btc     NUMERIC(16,8),
                        balance_usd     NUMERIC(16,2),
                        tx_count        INT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(exchange_name, snapshot_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ref_exchange
                        ON raw_exchange_flows (exchange_name, snapshot_date DESC);
                """)

    def fetch(self, securities):
        btc_sec = None
        for s in securities:
            if "BTC" in s["ticker"] or "bitcoin" in s.get("name", "").lower():
                btc_sec = s
                break

        if not btc_sec:
            self.log.warning("No BTC security found")
            return []

        today = datetime.now(timezone.utc).date()
        btc_price = self._get_btc_price()
        rows = []

        for exchange, addresses in EXCHANGE_WALLETS.items():
            total_balance = 0
            total_tx = 0

            try:
                addr_str = "|".join(addresses)
                resp = requests.get(
                    f"https://blockchain.info/balance?active={addr_str}",
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for addr in addresses:
                        info = data.get(addr, {})
                        total_balance += info.get("final_balance", 0) / 1e8
                        total_tx += info.get("n_tx", 0)
            except requests.RequestException as e:
                self.log.debug("Balance error for %s: %s", exchange, e)
                self.stats["errors"] += 1
                continue

            rows.append({
                "security_id": btc_sec["security_id"],
                "exchange_name": exchange,
                "snapshot_date": today,
                "balance_btc": total_balance,
                "balance_usd": total_balance * btc_price if btc_price else None,
                "tx_count": total_tx,
            })

            self.log.info("  %s: %.2f BTC ($%.0fM) %d txs",
                          exchange, total_balance,
                          (total_balance * btc_price / 1e6) if btc_price else 0,
                          total_tx)
            self.stats["fetched"] += 1

        return rows

    def _get_btc_price(self):
        try:
            resp = requests.get("https://api.blockchain.info/stats", timeout=10)
            if resp.status_code == 200:
                return resp.json().get("market_price_usd", 0)
        except requests.RequestException:
            pass
        return None

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d exchange flow snapshots...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_exchange_flows
                           (security_id, exchange_name, snapshot_date,
                            balance_btc, balance_usd, tx_count)
                       VALUES %s
                       ON CONFLICT (exchange_name, snapshot_date)
                       DO UPDATE SET balance_btc = EXCLUDED.balance_btc,
                                     balance_usd = EXCLUDED.balance_usd,
                                     tx_count = EXCLUDED.tx_count,
                                     last_updated = now()""",
                    [(r["security_id"], r["exchange_name"], r["snapshot_date"],
                      r["balance_btc"], r["balance_usd"], r["tx_count"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Exchange flows: %d exchanges snapshotted, %d errors",
                      self.stats["fetched"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(ExchangeFlowCollector)
