"""
Prediction Market Feed — Polymarket + Kalshi market data.

Collector ID: 18 (Prediction Market Feed)
Table:        raw_prediction_markets

Aggregates prediction market odds for events relevant to our securities
universe. When the crowd is betting on Fed rate cuts, S&P crashes,
bankruptcies, or crypto price levels — that's sentiment with skin in the game.

Data sources:
  - Polymarket CLOB API (free, no key)
  - Kalshi Trade API (free tier with key)
"""

import sys
import os
import time
import re
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi series relevant to our universe
KALSHI_FINANCIAL_SERIES = [
    # Indices
    "INXM", "KXNASDAQ100Z", "KXSPRLVL",
    # Commodities
    "GOLD", "KXGOLDD", "KXNATGASD", "KXCRUDE",
    # Rates / macro
    "KXRATEHIKE", "RATECUTCOUNT", "KXMORTGAGERATE", "KX10Y2Y",
    "KXCPI", "KXJOBS", "KXGDP",
    # Credit / corporate
    "KXBANKRUPTS",
    # Crypto
    "KXBITCOINMAXY", "KXBTCMINMON", "KXBTCMAXMON",
    "KXETHMAXMON", "KXETHMINMON", "KXDOGEMINMON",
    "KXSOL",
    # Forex
    "KXGBPUSD", "EURUSDMIN",
]

# Map prediction market topics to our security tickers
TOPIC_TICKER_MAP = {
    # Crypto
    "bitcoin": ["BTC-USD"],
    "btc": ["BTC-USD"],
    "ethereum": ["ETH-USD"],
    "eth": ["ETH-USD"],
    "solana": ["SOL-USD"],
    "sol": ["SOL-USD"],
    "dogecoin": ["DOGE-USD"],
    "doge": ["DOGE-USD"],
    # Indices
    "s&p": ["SPY", "VOO"],
    "sp500": ["SPY", "VOO"],
    "s&p 500": ["SPY", "VOO"],
    "nasdaq": ["QQQ", "TQQQ"],
    # Commodities
    "gold": ["GLD", "GOLD"],
    "crude oil": ["USO", "XLE"],
    "crude": ["USO", "XLE"],
    "natural gas": ["UNG"],
    # Rates / macro
    "fed": ["TLT", "SHY"],
    "interest rate": ["TLT", "SHY"],
    "rate cut": ["TLT", "SHY"],
    "rate hike": ["TLT", "SHY"],
    "treasury": ["TLT", "SHY"],
    "mortgage": ["TLT"],
    "cpi": ["TIP", "SPY"],
    "inflation": ["TIP"],
    "jobs": ["SPY"],
    "unemployment": ["SPY"],
    "gdp": ["SPY"],
    "recession": ["SPY"],
    # Equities
    "tesla": ["TSLA"],
    "apple": ["AAPL"],
    "nvidia": ["NVDA"],
    "google": ["GOOGL"],
    "amazon": ["AMZN"],
    "meta": ["META"],
    "microsoft": ["MSFT"],
    "bankruptcy": [],  # general signal
}


def match_tickers(text: str, sec_lookup: dict) -> list[int]:
    """Match prediction market text to our security IDs."""
    text_lower = text.lower()
    matched = set()
    for keyword, tickers in TOPIC_TICKER_MAP.items():
        if keyword in text_lower:
            for t in tickers:
                if t in sec_lookup:
                    matched.add(sec_lookup[t])
    return list(matched)


class PredictionMarketCollector(BaseCollector):

    COLLECTOR_ID = 18
    COLLECTOR_NAME = "Prediction Market Feed"
    COLLECTOR_TYPE = "social"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_prediction_markets (
                        market_id       SERIAL PRIMARY KEY,
                        security_id     INT REFERENCES securities(security_id),
                        source          VARCHAR(20) NOT NULL,
                        event_title     TEXT NOT NULL,
                        market_question TEXT,
                        market_ticker   TEXT,
                        probability     NUMERIC(6,4),
                        volume          NUMERIC(16,2),
                        event_url       TEXT,
                        fetched_date    DATE NOT NULL,
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(source, market_ticker, fetched_date)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpm_security
                        ON raw_prediction_markets (security_id, fetched_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rpm_date
                        ON raw_prediction_markets (fetched_date DESC);
                """)

    def fetch(self, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        today = datetime.now(timezone.utc).date()
        all_rows = []

        # Source 1: Polymarket
        poly_rows = self._fetch_polymarket(sec_lookup, today)
        all_rows.extend(poly_rows)

        # Source 2: Kalshi
        kalshi_rows = self._fetch_kalshi(sec_lookup, today)
        all_rows.extend(kalshi_rows)

        return all_rows

    def _fetch_polymarket(self, sec_lookup, today):
        rows = []
        self.log.info("Fetching Polymarket events...")
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA}/markets",
                params={"limit": 100, "active": "true", "closed": "false",
                         "order": "volume24hr", "ascending": "false"},
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                self.log.warning("Polymarket returned %d", resp.status_code)
                return rows

            markets = resp.json()
            for m in markets:
                question = m.get("question", "")
                sids = match_tickers(question, sec_lookup)

                # Skip if no match to our universe
                if not sids:
                    continue

                # Get probability from outcomePrices [yes, no] or bestBid
                prob = None
                outcome_prices = m.get("outcomePrices")
                if outcome_prices and len(outcome_prices) >= 1:
                    try:
                        prob = float(outcome_prices[0])
                    except (ValueError, TypeError):
                        pass
                if prob is None and m.get("bestBid") is not None:
                    try:
                        prob = float(m["bestBid"])
                    except (ValueError, TypeError):
                        pass

                for sid in sids:
                    rows.append({
                        "security_id": sid,
                        "source": "polymarket",
                        "event_title": question[:300],
                        "market_question": question[:500],
                        "market_ticker": (m.get("condition_id") or m.get("slug") or question[:80])[:100],
                        "probability": prob,
                        "volume": m.get("volume24hr") or m.get("volumeNum") or m.get("volume"),
                        "event_url": f"https://polymarket.com/event/{m.get('slug', '')}",
                        "fetched_date": today,
                    })

            self.stats["fetched"] += len(rows)
            self.log.info("  Polymarket: %d relevant markets matched", len(rows))
        except requests.RequestException as e:
            self.log.warning("Polymarket error: %s", e)
            self.stats["errors"] += 1

        return rows

    def _kalshi_headers(self):
        """Build Kalshi API auth headers. Falls back to unauthenticated."""
        headers = {"Accept": "application/json"}
        if config.KALSHI_API_KEY:
            headers["Authorization"] = f"Bearer {config.KALSHI_API_KEY}"
        return headers

    def _fetch_kalshi(self, sec_lookup, today):
        rows = []
        kalshi_headers = self._kalshi_headers()
        authed = "Authorization" in kalshi_headers
        self.log.info("Fetching Kalshi markets... (authenticated=%s)", authed)

        for series in KALSHI_FINANCIAL_SERIES:
            try:
                resp = requests.get(
                    f"{KALSHI_API}/events",
                    params={"limit": 20, "status": "open", "series_ticker": series},
                    headers=kalshi_headers,
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 401:
                    self.log.warning("Kalshi 401 — key may be invalid or expired")
                    break
                if resp.status_code != 200:
                    self.log.debug("Kalshi %d for series %s", resp.status_code, series)
                    continue

                events = resp.json().get("events", [])
                for event in events:
                    title = event.get("title", "")
                    # Match against series name too (e.g., "KXBITCOINMAXY" → bitcoin)
                    series_text = f"{title} {series}"
                    sids = match_tickers(series_text, sec_lookup)

                    # Get markets within event (often embedded in response)
                    # Fetch markets via /markets endpoint (sub-URL returns 404)
                    event_ticker = event.get("event_ticker", "")
                    event_markets = event.get("markets", [])
                    if not event_markets and event_ticker:
                        try:
                            mresp = requests.get(
                                f"{KALSHI_API}/markets",
                                params={"event_ticker": event_ticker, "limit": 20},
                                headers=kalshi_headers,
                                timeout=config.HTTP_TIMEOUT,
                            )
                            if mresp.status_code == 200:
                                event_markets = mresp.json().get("markets", [])
                            time.sleep(0.2)
                        except requests.RequestException:
                            pass

                    for mkt in event_markets[:10]:  # cap per event
                        prob = None
                        # Kalshi v2 uses _dollars fields (0.00-1.00)
                        for price_field in ("last_price_dollars", "yes_bid_dollars",
                                            "yes_ask_dollars", "previous_price_dollars"):
                            val = mkt.get(price_field)
                            if val is not None:
                                try:
                                    fval = float(val)
                                    if 0 < fval < 1:
                                        prob = fval
                                        break
                                except (ValueError, TypeError):
                                    continue

                        vol = mkt.get("volume_fp") or mkt.get("volume_24h_fp") or 0

                        # Also try matching the market question itself
                        mkt_text = mkt.get("title") or mkt.get("subtitle") or ""
                        mkt_sids = match_tickers(f"{series_text} {mkt_text}", sec_lookup)
                        final_sids = mkt_sids if mkt_sids else sids

                        target_sids = final_sids if final_sids else [None]
                        for sid in target_sids:
                            rows.append({
                                "security_id": sid,
                                "source": "kalshi",
                                "event_title": title[:300],
                                "market_question": (mkt.get("title") or mkt.get("subtitle") or title)[:500],
                                "market_ticker": mkt.get("ticker", "")[:100],
                                "probability": prob,
                                "volume": vol,
                                "event_url": f"https://kalshi.com/events/{event.get('event_ticker', '')}",
                                "fetched_date": today,
                            })

                time.sleep(0.3)  # rate courtesy
            except requests.RequestException as e:
                self.log.debug("Kalshi error for %s: %s", series, e)
                self.stats["errors"] += 1

        # Filter out rows with no security_id (general market events)
        rows = [r for r in rows if r["security_id"] is not None]
        self.stats["fetched"] += len(rows)
        self.log.info("  Kalshi: %d relevant markets matched (%d series scanned)",
                      len(rows), len(KALSHI_FINANCIAL_SERIES))
        return rows

    def transform(self, raw_data, securities):
        seen = set()
        rows = []
        for r in raw_data:
            key = (r["source"], r["market_ticker"], str(r["fetched_date"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
        return rows

    def store(self, rows):
        self.log.info("Writing %d prediction market records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_prediction_markets
                           (security_id, source, event_title, market_question,
                            market_ticker, probability, volume, event_url, fetched_date)
                       VALUES %s
                       ON CONFLICT (source, market_ticker, fetched_date)
                       DO UPDATE SET probability = EXCLUDED.probability,
                                     volume = EXCLUDED.volume,
                                     last_updated = now()""",
                    [(r["security_id"], r["source"], r["event_title"],
                      r["market_question"], r["market_ticker"], r["probability"],
                      r["volume"], r["event_url"], r["fetched_date"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Prediction markets: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(PredictionMarketCollector)
