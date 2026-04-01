"""
Nasdaq Data Link Collector — macro economic indicators via Nasdaq Data Link API.

Collector ID: 28
Table:        raw_economic_indicators (created on first run)
API:          https://data.nasdaq.com/api/v3/datasets/{code}.json
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
import requests
from datetime import datetime
from psycopg2.extras import execute_values

from base import BaseCollector, run_collector
import config
import db


# Datasets to fetch: (dataset_code, human_name)
INDICATOR_DATASETS = [
    ("FRED/DFF",                    "Fed Funds Rate"),
    ("FRED/T10Y2Y",                 "10Y-2Y Treasury Spread"),
    ("FRED/VIXCLS",                 "VIX"),
    ("FRED/BAMLH0A0HYM2",          "High Yield Spread"),
    ("FRED/UNRATE",                 "Unemployment Rate"),
    ("MULTPL/SP500_PE_RATIO_MONTH", "S&P 500 PE Ratio"),
]


class NasdaqDataLinkCollector(BaseCollector):

    # ── identity (must match `collectors` table) ──────────────────────
    COLLECTOR_ID = 28
    COLLECTOR_NAME = "Nasdaq Data Link"
    COLLECTOR_TYPE = "market_data"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        if not config.NASDAQ_DATA_LINK_API_KEY:
            raise RuntimeError("NASDAQ_DATA_LINK_API_KEY is not set — cannot proceed")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_economic_indicators (
                        indicator_id    SERIAL PRIMARY KEY,
                        indicator_code  VARCHAR(50) NOT NULL,
                        indicator_name  VARCHAR(200),
                        observation_date DATE NOT NULL,
                        value           NUMERIC(16,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(indicator_code, observation_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rei_code
                        ON raw_economic_indicators (indicator_code);
                    CREATE INDEX IF NOT EXISTS idx_rei_date
                        ON raw_economic_indicators (observation_date);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Fetch recent observations for each macro indicator dataset."""
        raw_results = {}

        self.log.info("Fetching %d indicator datasets from Nasdaq Data Link...", len(INDICATOR_DATASETS))

        for dataset_code, indicator_name in INDICATOR_DATASETS:
            url = (
                f"https://data.nasdaq.com/api/v3/datasets/{dataset_code}.json"
                f"?api_key={config.NASDAQ_DATA_LINK_API_KEY}&limit=5"
            )

            for attempt in range(1, config.HTTP_RETRIES + 1):
                try:
                    resp = self.session.get(url, timeout=config.HTTP_TIMEOUT)
                    if resp.status_code == 200:
                        data = resp.json()
                        dataset = data.get("dataset", {})
                        if dataset.get("data"):
                            raw_results[dataset_code] = {
                                "name": indicator_name,
                                "column_names": dataset.get("column_names", []),
                                "data": dataset["data"],
                            }
                            self.stats["fetched"] += 1
                            self.log.info("  %s: %d observations", dataset_code, len(dataset["data"]))
                        else:
                            self.log.warning("  %s: no data returned", dataset_code)
                            self.stats["skipped"] += 1
                        break
                    elif resp.status_code == 429:
                        wait = config.HTTP_BACKOFF ** attempt
                        self.log.warning("Rate limited, sleeping %.1fs...", wait)
                        time.sleep(wait)
                    elif resp.status_code == 404:
                        self.log.warning("  Dataset %s not found", dataset_code)
                        self.stats["skipped"] += 1
                        break
                    else:
                        self.log.debug(
                            "Nasdaq %s returned %d on attempt %d",
                            dataset_code, resp.status_code, attempt,
                        )
                        if attempt == config.HTTP_RETRIES:
                            self.stats["errors"] += 1
                        else:
                            time.sleep(config.HTTP_BACKOFF ** attempt)
                except requests.RequestException as e:
                    self.log.debug("Request error for %s (attempt %d): %s", dataset_code, attempt, e)
                    if attempt == config.HTTP_RETRIES:
                        self.stats["errors"] += 1
                    else:
                        time.sleep(config.HTTP_BACKOFF ** attempt)

            # Be polite between requests
            time.sleep(0.5)

        return raw_results

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        """Normalize each dataset's observations into flat rows."""
        rows = []
        for dataset_code, payload in raw_data.items():
            indicator_name = payload["name"]
            column_names = [c.lower() for c in payload.get("column_names", [])]

            # Find the value column index (first column after date)
            # Typical column layout: ["Date", "Value"] or ["Date", "Rate"]
            value_idx = 1  # default: second column

            for obs in payload["data"]:
                try:
                    # First column is always the date
                    obs_date = datetime.strptime(obs[0], "%Y-%m-%d").date()
                    value = float(obs[value_idx]) if obs[value_idx] is not None else None

                    if value is None:
                        continue

                    rows.append({
                        "indicator_code": dataset_code.replace("/", "_"),
                        "indicator_name": indicator_name,
                        "observation_date": obs_date,
                        "value": round(value, 4),
                    })
                except (IndexError, ValueError, TypeError) as e:
                    self.log.debug("Transform error for %s obs %s: %s", dataset_code, obs, e)
                    self.stats["errors"] += 1

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        """Write to raw_economic_indicators with upsert."""
        self.log.info("Writing %d rows to raw_economic_indicators...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_economic_indicators
                           (indicator_code, indicator_name, observation_date, value)
                       VALUES %s
                       ON CONFLICT (indicator_code, observation_date)
                       DO UPDATE SET value = EXCLUDED.value,
                                     indicator_name = EXCLUDED.indicator_name,
                                     last_updated = now()""",
                    [(r["indicator_code"], r["indicator_name"],
                      r["observation_date"], r["value"])
                     for r in rows],
                    template="(%s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        # No per-security coverage update for macro data — these are market-level indicators
        self.stats["stored"] = len(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "Nasdaq Data Link: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )
        if hasattr(self, "session"):
            self.session.close()


if __name__ == "__main__":
    run_collector(NasdaqDataLinkCollector)
