"""
Short Interest Tracker — biweekly short interest data via yfinance.

Collector ID: 5 (Short Interest Tracker)
Table:        raw_short_interest

Fetches exchange-reported short interest from yfinance .info for each
equity. This is the "official" short interest number — how many shares
are currently sold short. GameStop, AMC, Luckin Coffee, and Enron all
had screaming short interest before their respective crises.

Data source: yfinance (free, no key).
"""

import sys
import os
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db


class ShortInterestCollector(BaseCollector):

    COLLECTOR_ID = 5
    COLLECTOR_NAME = "Short Interest Tracker"
    COLLECTOR_TYPE = "market_data"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_short_interest (
                        si_id               SERIAL PRIMARY KEY,
                        security_id         INT NOT NULL REFERENCES securities(security_id),
                        report_date         DATE NOT NULL,
                        shares_short        BIGINT,
                        shares_short_prior  BIGINT,
                        short_pct_float     NUMERIC(10,6),
                        short_ratio         NUMERIC(10,2),
                        float_shares        BIGINT,
                        collected_at        TIMESTAMP DEFAULT now(),
                        last_updated        TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, report_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rsi_security
                        ON raw_short_interest (security_id, report_date DESC);
                """)

    def fetch(self, securities):
        equities = [s for s in securities if s["security_type"] == "equity"]
        total = len(equities)
        self.log.info("Fetching short interest for %d equities...", total)
        rows = []

        for i, s in enumerate(equities):
            ticker = s["ticker"]
            try:
                info = yf.Ticker(ticker).info
                shares_short = info.get("sharesShort")
                if not shares_short:
                    self.stats["skipped"] += 1
                    continue

                # dateShortInterest is epoch seconds
                date_epoch = info.get("dateShortInterest")
                report_date = (
                    datetime.fromtimestamp(date_epoch, tz=timezone.utc).date()
                    if date_epoch else datetime.now(timezone.utc).date()
                )

                rows.append({
                    "security_id": s["security_id"],
                    "report_date": report_date,
                    "shares_short": shares_short,
                    "shares_short_prior": info.get("sharesShortPriorMonth"),
                    "short_pct_float": info.get("shortPercentOfFloat"),
                    "short_ratio": info.get("shortRatio"),
                    "float_shares": info.get("floatShares"),
                })
                self.stats["fetched"] += 1

            except Exception as e:
                self.log.debug("Error %s: %s", ticker, e)
                self.stats["errors"] += 1

            if (i + 1) % 50 == 0:
                self.log.info("  Progress: %d/%d (%d fetched)", i + 1, total, self.stats["fetched"])
            time.sleep(0.2)

        return rows

    def transform(self, raw_data, securities):
        return raw_data

    def store(self, rows):
        self.log.info("Writing %d short interest records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_short_interest
                           (security_id, report_date, shares_short, shares_short_prior,
                            short_pct_float, short_ratio, float_shares)
                       VALUES %s
                       ON CONFLICT (security_id, report_date)
                       DO UPDATE SET shares_short = EXCLUDED.shares_short,
                                     short_pct_float = EXCLUDED.short_pct_float,
                                     short_ratio = EXCLUDED.short_ratio,
                                     last_updated = now()""",
                    [(r["security_id"], r["report_date"], r["shares_short"],
                      r["shares_short_prior"], r["short_pct_float"],
                      r["short_ratio"], r["float_shares"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Short interest: %d fetched, %d stored, %d skipped, %d errors",
                      self.stats["fetched"], self.stats["stored"],
                      self.stats["skipped"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(ShortInterestCollector)
