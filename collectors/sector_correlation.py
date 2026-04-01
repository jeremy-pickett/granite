"""
Sector Correlation Engine — cross-sector correlation analysis.

Collector ID: 15 (Sector Correlation Engine)
Table:        raw_sector_correlations

Computes rolling correlations between each security and its sector ETF.
When a stock decorrelates from its sector, something specific to that
company is driving the move — and that's worth investigating.

Data source: raw_market_data (internal) + sector ETF OHLCV via yfinance.
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Basic Materials": "XLB",
}

MIN_DAYS = 15  # minimum trading days for meaningful correlation


class SectorCorrelationCollector(BaseCollector):

    COLLECTOR_ID = 15
    COLLECTOR_NAME = "Sector Correlation Engine"
    COLLECTOR_TYPE = "analytics"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        self._etf_returns: dict[str, dict] = {}  # etf_ticker → {date: return}

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_sector_correlations (
                        corr_id             SERIAL PRIMARY KEY,
                        security_id         INT NOT NULL REFERENCES securities(security_id),
                        sector_etf          VARCHAR(10),
                        correlation_date    DATE NOT NULL,
                        rolling_correlation NUMERIC(8,6),
                        residual_return     NUMERIC(10,6),
                        collected_at        TIMESTAMP DEFAULT now(),
                        last_updated        TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, correlation_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rsc_security
                        ON raw_sector_correlations (security_id, correlation_date DESC);
                """)

    def fetch(self, securities):
        # Check preconditions
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM securities WHERE sector IS NOT NULL AND security_type = 'equity'")
                sector_count = cur.fetchone()[0]
                cur.execute("SELECT count(DISTINCT trade_date) FROM raw_market_data")
                days_count = cur.fetchone()[0]

        if sector_count < 50:
            self.log.warning("Only %d securities have sector data — need backfill first", sector_count)
            return []
        if days_count < MIN_DAYS:
            self.log.warning("Only %d trading days in raw_market_data — need %d minimum", days_count, MIN_DAYS)
            return []

        self.log.info("Preconditions met: %d sectors, %d trading days", sector_count, days_count)

        # Load security OHLCV from raw_market_data
        security_returns = {}
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.security_id, s.sector, r.trade_date, r.close
                    FROM raw_market_data r
                    JOIN securities s ON s.security_id = r.security_id
                    WHERE s.sector IS NOT NULL AND s.security_type = 'equity'
                    ORDER BY s.security_id, r.trade_date
                """)
                current_sid = None
                prices = []
                for sid, sector, trade_date, close_price in cur:
                    if sid != current_sid:
                        if current_sid and len(prices) >= MIN_DAYS:
                            security_returns[current_sid] = {
                                "sector": prev_sector,
                                "dates": [p[0] for p in prices],
                                "returns": self._compute_returns([float(p[1]) for p in prices]),
                            }
                        current_sid = sid
                        prev_sector = sector
                        prices = []
                    prices.append((trade_date, close_price))
                # Last security
                if current_sid and len(prices) >= MIN_DAYS:
                    security_returns[current_sid] = {
                        "sector": prev_sector,
                        "dates": [p[0] for p in prices],
                        "returns": self._compute_returns([float(p[1]) for p in prices]),
                    }

        self.log.info("Loaded returns for %d securities with %d+ days", len(security_returns), MIN_DAYS)

        # Fetch sector ETF data
        needed_etfs = set()
        for data in security_returns.values():
            etf = SECTOR_ETFS.get(data["sector"])
            if etf:
                needed_etfs.add(etf)

        self.log.info("Fetching %d sector ETF histories...", len(needed_etfs))
        if needed_etfs:
            try:
                df = yf.download(
                    list(needed_etfs),
                    period="1mo",
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )
                for etf in needed_etfs:
                    try:
                        if len(needed_etfs) == 1:
                            edf = df
                        else:
                            edf = df[etf]
                        prices = []
                        for dt, row in edf.iterrows():
                            c = row.get("Close")
                            if c is not None and c == c:
                                prices.append((dt.date(), float(c)))
                        if len(prices) >= MIN_DAYS:
                            returns = self._compute_returns([p[1] for p in prices])
                            self._etf_returns[etf] = {d: r for d, r in zip([p[0] for p in prices[1:]], returns)}
                    except Exception:
                        pass
            except Exception as e:
                self.log.warning("ETF download error: %s", e)

        self.log.info("Loaded ETF returns for %d sector ETFs", len(self._etf_returns))

        return security_returns

    def _compute_returns(self, prices):
        """Compute daily returns from price series."""
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
            else:
                returns.append(0.0)
        return returns

    def transform(self, raw_data, securities):
        rows = []
        sec_lookup = {s["security_id"]: s for s in securities}

        for sid, data in raw_data.items():
            etf_ticker = SECTOR_ETFS.get(data["sector"])
            if not etf_ticker or etf_ticker not in self._etf_returns:
                continue

            etf_ret_map = self._etf_returns[etf_ticker]
            dates = data["dates"][1:]  # returns are 1 shorter than prices
            sec_returns = data["returns"]

            # Align dates
            aligned_sec = []
            aligned_etf = []
            for d, r in zip(dates, sec_returns):
                if d in etf_ret_map:
                    aligned_sec.append(r)
                    aligned_etf.append(etf_ret_map[d])

            if len(aligned_sec) < MIN_DAYS:
                continue

            # Rolling correlation (last MIN_DAYS window)
            sec_arr = np.array(aligned_sec[-MIN_DAYS:])
            etf_arr = np.array(aligned_etf[-MIN_DAYS:])

            corr = np.corrcoef(sec_arr, etf_arr)[0, 1]
            if np.isnan(corr):
                continue

            # Residual return: security return - beta * etf return
            beta = np.cov(sec_arr, etf_arr)[0, 1] / (np.var(etf_arr) + 1e-10)
            residuals = sec_arr - beta * etf_arr
            latest_residual = float(residuals[-1])

            latest_date = dates[-1] if dates else None

            rows.append({
                "security_id": sid,
                "sector_etf": etf_ticker,
                "correlation_date": latest_date,
                "rolling_correlation": round(float(corr), 6),
                "residual_return": round(latest_residual, 6),
            })
            self.stats["fetched"] += 1

        return rows

    def store(self, rows):
        self.log.info("Writing %d sector correlation records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_sector_correlations
                           (security_id, sector_etf, correlation_date,
                            rolling_correlation, residual_return)
                       VALUES %s
                       ON CONFLICT (security_id, correlation_date)
                       DO UPDATE SET rolling_correlation = EXCLUDED.rolling_correlation,
                                     residual_return = EXCLUDED.residual_return,
                                     last_updated = now()""",
                    [(r["security_id"], r["sector_etf"], r["correlation_date"],
                      r["rolling_correlation"], r["residual_return"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Sector correlations: %d computed, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(SectorCorrelationCollector)
