"""
COLLECTOR TEMPLATE — copy this file to start a new collector.

Steps:
  1. cp _template.py my_collector.py
  2. Set COLLECTOR_ID to match your row in the `collectors` table
  3. Set COLLECTOR_NAME, COLLECTOR_TYPE
  4. Implement fetch() and transform()
  5. Optionally override setup(), store(), teardown()
  6. Run:  python collectors/my_collector.py

Lifecycle (handled by BaseCollector.run()):
  setup()  →  fetch()  →  transform()  →  store()  →  teardown()
              ^^^^^^^^     ^^^^^^^^^^^
              you write    you write      (store has a sensible default)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
import config
import db


class MyCollector(BaseCollector):

    # ── identity (must match `collectors` table) ──────────────────────
    COLLECTOR_ID = 0          # TODO: set to your collector_id
    COLLECTOR_NAME = "My Collector"
    COLLECTOR_TYPE = "market_data"  # market_data | sec_filing | analytics | political | social | blockchain

    # Optional: only run against a subset of securities
    # SECURITY_TYPE_FILTER = "equity"   # or "crypto", or None for all

    # ── setup (optional) ──────────────────────────────────────────────

    def setup(self):
        """Check API keys, open HTTP sessions, create custom tables."""
        # If your collector writes to a custom table, create it here:
        # self._ensure_table()
        pass

    # def _ensure_table(self):
    #     with db.get_conn() as conn:
    #         with conn.cursor() as cur:
    #             cur.execute("""
    #                 CREATE TABLE IF NOT EXISTS raw_my_data (
    #                     security_id INT NOT NULL REFERENCES securities(security_id),
    #                     ...
    #                 )
    #             """)

    # ── fetch (required) ──────────────────────────────────────────────

    def fetch(self, securities):
        """
        Pull raw data from external source.

        Args:
            securities: list of {security_id, ticker, name, security_type}

        Returns:
            Raw data in whatever shape you want — it goes straight to transform().

        Tips:
            - Use config.HTTP_TIMEOUT, config.HTTP_RETRIES for requests
            - Batch tickers when the API supports it (config.BATCH_SIZE)
            - Update self.stats["fetched"] as you go
            - Update self.stats["skipped"] for tickers with no data
        """
        raise NotImplementedError

    # ── transform (required) ──────────────────────────────────────────

    def transform(self, raw_data, securities):
        """
        Normalize raw_data into a flat list of dicts.

        Each dict MUST contain:
            { "security_id": int, ...your fields... }

        Args:
            raw_data: whatever fetch() returned
            securities: same list from fetch()

        Returns:
            list[dict] — rows to be persisted
        """
        raise NotImplementedError

    # ── store (optional override) ─────────────────────────────────────

    # def store(self, rows):
    #     """Override to write to custom tables. Call super().store(rows) to update coverage."""
    #     with db.get_conn() as conn:
    #         with conn.cursor() as cur:
    #             from psycopg2.extras import execute_values
    #             execute_values(cur, "INSERT INTO raw_my_data ...", [...])
    #     super().store(rows)

    # ── teardown (optional) ───────────────────────────────────────────

    # def teardown(self):
    #     """Close sessions, log summary, etc."""
    #     pass


if __name__ == "__main__":
    run_collector(MyCollector)
