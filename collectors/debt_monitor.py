"""
Debt Loading Monitor — quarterly balance sheet metrics for post-acquisition debt detection.

Collector ID: 32
Table:        raw_debt_metrics

Tracks debt-to-equity ratios, interest burden, and free cash flow to detect
the classic PE playbook: load the acquisition target with debt, extract
dividends, strip assets, let the carcass collapse.

Signals that a company is being hollowed out:
  - debt_to_equity spikes >2x within 4 quarters
  - interest_to_revenue exceeds 0.30 (30% of revenue servicing debt)
  - free_cash_flow turns deeply negative after acquisition

Data source: Finnhub /stock/metric and /stock/financials-reported endpoints.
"""

import sys
import os
import time
import logging
import requests

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

FINNHUB_METRIC_URL = "https://finnhub.io/api/v1/stock/metric"
FINNHUB_FINANCIALS_URL = "https://finnhub.io/api/v1/stock/financials-reported"


class DebtMonitorCollector(BaseCollector):

    COLLECTOR_ID = 32
    COLLECTOR_NAME = "Debt Loading Monitor"
    COLLECTOR_TYPE = "market_data"
    SECURITY_TYPE_FILTER = "equity"

    def setup(self):
        self._ensure_table()
        if not config.FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY not set — cannot run debt monitor")

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_debt_metrics (
                        metric_id           SERIAL PRIMARY KEY,
                        security_id         INT NOT NULL REFERENCES securities(security_id),
                        period_date         DATE NOT NULL,
                        total_debt          NUMERIC(16,2),
                        total_equity        NUMERIC(16,2),
                        debt_to_equity      NUMERIC(10,4),
                        interest_expense    NUMERIC(16,2),
                        revenue             NUMERIC(16,2),
                        interest_to_revenue NUMERIC(8,4),
                        free_cash_flow      NUMERIC(16,2),
                        collected_at        TIMESTAMP DEFAULT now(),
                        last_updated        TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, period_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rdm_security
                        ON raw_debt_metrics (security_id, period_date DESC);
                """)

    def _fetch_metric(self, ticker):
        """Fetch current key metrics from Finnhub /stock/metric."""
        try:
            resp = requests.get(
                FINNHUB_METRIC_URL,
                params={
                    "symbol": ticker,
                    "metric": "all",
                    "token": config.FINNHUB_API_KEY,
                },
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("metric", {})
        except requests.RequestException as e:
            self.log.debug("Metric fetch failed for %s: %s", ticker, e)
        return {}

    def _fetch_financials(self, ticker):
        """Fetch quarterly reported financials from Finnhub."""
        try:
            resp = requests.get(
                FINNHUB_FINANCIALS_URL,
                params={
                    "symbol": ticker,
                    "freq": "quarterly",
                    "token": config.FINNHUB_API_KEY,
                },
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("data", [])
        except requests.RequestException as e:
            self.log.debug("Financials fetch failed for %s: %s", ticker, e)
        return []

    def _extract_line_item(self, report, *concept_names):
        """Search report line items for any matching concept name, return value."""
        items = report.get("report", {}).get("bs", [])
        items += report.get("report", {}).get("ic", [])
        items += report.get("report", {}).get("cf", [])
        for item in items:
            label = (item.get("concept") or "").lower()
            for name in concept_names:
                if name.lower() in label:
                    val = item.get("value")
                    if val is not None:
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
        return None

    def fetch(self, securities):
        """Fetch debt metrics for each equity security."""
        raw_data = []

        for s in securities:
            if s["security_type"] != "equity":
                continue

            ticker = s["ticker"]
            sid = s["security_id"]

            # Step 1: Get current metrics snapshot
            metrics = self._fetch_metric(ticker)
            time.sleep(1.1)  # Finnhub rate limit: 60/min

            # Step 2: Get quarterly financials (last 4 quarters)
            financials = self._fetch_financials(ticker)
            time.sleep(1.1)

            # Process quarterly reports (limit to 4 most recent)
            quarters_processed = 0
            for report in financials[:4]:
                period = report.get("endDate") or report.get("period")
                if not period:
                    continue

                total_debt = self._extract_line_item(
                    report, "totaldebt", "longtermdebt", "totalliabilities",
                    "longTermDebt", "totalDebt",
                )
                total_equity = self._extract_line_item(
                    report, "totalequity", "totalstockholdersequity",
                    "stockholdersequity", "totalStockholdersEquity",
                )
                interest_expense = self._extract_line_item(
                    report, "interestexpense", "interestExpense",
                    "interestincomeexpensenet",
                )
                revenue = self._extract_line_item(
                    report, "revenue", "totalrevenue", "revenues",
                    "totalRevenue", "netRevenue",
                )
                fcf = self._extract_line_item(
                    report, "freecashflow", "operatingcashflow",
                    "netcashfromoperatingactivities",
                )

                # If no quarterly data, try to use the current metrics for the latest period
                if quarters_processed == 0 and metrics:
                    if total_debt is None:
                        total_debt_metric = metrics.get("totalDebt/totalEquityQuarterly")
                        if total_debt_metric and total_equity:
                            total_debt = total_debt_metric * total_equity

                raw_data.append({
                    "security_id": sid,
                    "period_date": period,
                    "total_debt": total_debt,
                    "total_equity": total_equity,
                    "interest_expense": interest_expense,
                    "revenue": revenue,
                    "free_cash_flow": fcf,
                })
                quarters_processed += 1

            if quarters_processed > 0:
                self.stats["fetched"] += 1
            else:
                self.stats["skipped"] += 1

            if self.stats["fetched"] % 25 == 0 and self.stats["fetched"] > 0:
                self.log.info("  Progress: %d tickers fetched, %d skipped",
                              self.stats["fetched"], self.stats["skipped"])

        return raw_data

    def transform(self, raw_data, securities):
        """Compute derived debt ratios."""
        rows = []
        for r in raw_data:
            total_debt = r.get("total_debt")
            total_equity = r.get("total_equity")
            interest_expense = r.get("interest_expense")
            revenue = r.get("revenue")

            # Compute debt_to_equity — handle zero/negative equity
            dte = None
            if total_debt is not None and total_equity is not None:
                if total_equity > 0:
                    dte = total_debt / total_equity
                elif total_equity < 0:
                    # Negative equity = worse than any positive ratio
                    dte = 9999.0
                # total_equity == 0 → leave as None (undefined)

            # Compute interest_to_revenue (debt service burden)
            itr = None
            if interest_expense is not None and revenue is not None and revenue > 0:
                itr = abs(interest_expense) / revenue

            r["debt_to_equity"] = round(dte, 4) if dte is not None else None
            r["interest_to_revenue"] = round(itr, 4) if itr is not None else None
            rows.append(r)

        return rows

    def store(self, rows):
        if not rows:
            self.log.info("No debt metrics to store")
            super().store(rows)
            return

        # Deduplicate by (security_id, period_date) — keep last occurrence
        seen = {}
        for r in rows:
            seen[(r["security_id"], r["period_date"])] = r
        rows = list(seen.values())

        self.log.info("Writing %d debt metric records (%d deduped)...", len(rows), len(seen))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_debt_metrics
                           (security_id, period_date, total_debt, total_equity,
                            debt_to_equity, interest_expense, revenue,
                            interest_to_revenue, free_cash_flow)
                       VALUES %s
                       ON CONFLICT (security_id, period_date)
                       DO UPDATE SET
                           total_debt = EXCLUDED.total_debt,
                           total_equity = EXCLUDED.total_equity,
                           debt_to_equity = EXCLUDED.debt_to_equity,
                           interest_expense = EXCLUDED.interest_expense,
                           revenue = EXCLUDED.revenue,
                           interest_to_revenue = EXCLUDED.interest_to_revenue,
                           free_cash_flow = EXCLUDED.free_cash_flow,
                           last_updated = now()""",
                    [(r["security_id"], r["period_date"], r.get("total_debt"),
                      r.get("total_equity"), r.get("debt_to_equity"),
                      r.get("interest_expense"), r.get("revenue"),
                      r.get("interest_to_revenue"), r.get("free_cash_flow"))
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info(
            "Debt monitor: %d tickers fetched, %d skipped, %d errors",
            self.stats["fetched"], self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(DebtMonitorCollector)
