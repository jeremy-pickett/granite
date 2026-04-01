"""
BaseCollector — the template every collector inherits from.

Lifecycle:
    1. __init__     → set COLLECTOR_ID, NAME, TYPE
    2. setup()      → optional: auth, warm caches, check API keys
    3. fetch()      → REQUIRED: pull raw data from source, return it
    4. transform()  → REQUIRED: normalize raw data into standard rows
    5. store()      → persist rows to database + update coverage
    6. teardown()   → optional: close sessions, log summary
    7. run()        → orchestrates the full lifecycle (don't override)

Every subclass must define:
    COLLECTOR_ID   int    — matches the collectors table PK
    COLLECTOR_NAME str    — human label (for logs)
    COLLECTOR_TYPE str    — one of: market_data, sec_filing, analytics,
                            political, social, blockchain

Every subclass must implement:
    fetch(securities)     → raw data (any shape)
    transform(raw, securities) → list of dicts ready for store()
"""

import logging
import time
import sys
from abc import ABC, abstractmethod

import config
import db

logging.basicConfig(
    format=config.LOG_FORMAT,
    datefmt=config.LOG_DATE_FORMAT,
    level=logging.INFO,
)


class BaseCollector(ABC):

    COLLECTOR_ID: int = 0
    COLLECTOR_NAME: str = "unnamed"
    COLLECTOR_TYPE: str = "unknown"

    # Override to filter securities (e.g. "equity" or "crypto")
    SECURITY_TYPE_FILTER: str | None = None

    def __init__(self):
        self.log = logging.getLogger(self.COLLECTOR_NAME)
        self.securities: list[dict] = []
        self.stats = {
            "fetched": 0,
            "transformed": 0,
            "stored": 0,
            "errors": 0,
            "skipped": 0,
            "elapsed": 0.0,
        }

    # ── lifecycle hooks (override as needed) ──────────────────────────

    def setup(self):
        """Called before fetch(). Check API keys, open sessions, etc."""
        pass

    @abstractmethod
    def fetch(self, securities: list[dict]):
        """
        Pull raw data from the external source.
        `securities` is the full list of {security_id, ticker, name, security_type}.
        Return whatever shape makes sense — the same object goes to transform().
        """
        ...

    @abstractmethod
    def transform(self, raw_data, securities: list[dict]) -> list[dict]:
        """
        Normalize raw_data into a list of dicts.
        Each dict must have at minimum:
            { "security_id": int, ...your fields... }
        Return only rows you want persisted.
        """
        ...

    def store(self, rows: list[dict]):
        """
        Persist transformed rows. Default: upsert collector_coverage.
        Override to write to additional tables (e.g. a raw_market_data table).
        Always call super().store(rows) to keep coverage stats updated.
        """
        coverage = {}
        for row in rows:
            sid = row.get("security_id")
            if sid is not None:
                coverage[sid] = coverage.get(sid, 0) + 1

        if coverage:
            db.upsert_coverage_batch(
                self.COLLECTOR_ID,
                list(coverage.items()),
            )
        self.stats["stored"] = len(rows)

    def teardown(self):
        """Called after store(). Close sessions, log summary, etc."""
        pass

    # ── orchestrator (don't override) ─────────────────────────────────

    def run(self):
        """Execute the full collect cycle."""
        t0 = time.time()
        self.log.info("=== %s (ID %d) starting ===", self.COLLECTOR_NAME, self.COLLECTOR_ID)

        try:
            # Load target securities
            self.securities = db.get_securities(self.SECURITY_TYPE_FILTER)
            self.log.info("Loaded %d securities", len(self.securities))

            # Setup
            self.setup()

            # Mark run started
            db.collector_start(self.COLLECTOR_ID)

            # Fetch
            self.log.info("Fetching...")
            raw = self.fetch(self.securities)
            self.log.info("Fetch complete — stats so far: %s", self.stats)

            # Transform
            self.log.info("Transforming...")
            rows = self.transform(raw, self.securities)
            self.stats["transformed"] = len(rows)
            self.log.info("Transformed %d rows", len(rows))

            # Store
            if rows:
                self.log.info("Storing...")
                self.store(rows)
                self.log.info("Stored %d rows", self.stats["stored"])
            else:
                self.log.info("No new rows — nothing to store")

            # Always update collector record (even zero rows = successful run)
            covered = len({r["security_id"] for r in rows}) if rows else 0
            db.collector_success(
                self.COLLECTOR_ID,
                records_total=self.stats["stored"],
                securities_covered=covered,
                total_securities=len(self.securities),
            )

        except Exception as e:
            self.log.exception("Collector failed: %s", e)
            self.stats["errors"] += 1
            db.collector_error(self.COLLECTOR_ID, e)
            raise

        finally:
            self.teardown()
            self.stats["elapsed"] = round(time.time() - t0, 2)
            self.log.info("=== Done in %.2fs | %s ===", self.stats["elapsed"], self.stats)


def run_collector(collector_class):
    """Entry point helper — instantiate and run, exit 1 on failure."""
    try:
        c = collector_class()
        c.run()
    except Exception:
        sys.exit(1)
