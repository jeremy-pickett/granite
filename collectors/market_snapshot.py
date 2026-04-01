"""
Market Snapshot Collector — intraday price snapshots + fundamentals context.

Collector ID: 35 (Market Snapshot)
Table:        raw_market_snapshots

Captures point-in-time price data at market open and close for equities,
and every 12 hours for crypto. Also stores P/E ratio, volume velocity,
institutional share movement, and recent press releases when available.

This is a historical context collector — it records what the market looked
like at specific moments, not just end-of-day summaries.

Data sources:
  - Yahoo Finance (yfinance) — real-time quotes, P/E, volume
  - Finnhub — institutional ownership changes, press releases
  - Tiingo — backup quote source

Schedule:
  - Equity open:  09:35 ET (13:35 UTC) — 5 min after NYSE open
  - Equity close: 16:05 ET (20:05 UTC) — 5 min after NYSE close
  - Crypto 12h:   00:00 UTC and 12:00 UTC
"""

import sys
import os
import time
import requests
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

try:
    import yfinance as yf
except ImportError:
    yf = None

# Finnhub endpoints
FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"
FINNHUB_PEERS = "https://finnhub.io/api/v1/stock/metric"
FINNHUB_OWNERSHIP = "https://finnhub.io/api/v1/stock/institutional-ownership"
FINNHUB_PRESS = "https://finnhub.io/api/v1/press-releases"

# Tiingo quote endpoint (backup)
TIINGO_IEX = "https://api.tiingo.com/iex/{ticker}"

# Crypto tickers that get 12h snapshots
CRYPTO_TICKERS = {"BTC-USD", "ETH-USD"}


class MarketSnapshotCollector(BaseCollector):

    COLLECTOR_ID = 35
    COLLECTOR_NAME = "Market Snapshot"
    COLLECTOR_TYPE = "market_data"

    def setup(self):
        self._ensure_tables()

    def _ensure_tables(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_market_snapshots (
                        snapshot_id     SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        snapshot_time   TIMESTAMP NOT NULL,
                        snapshot_type   VARCHAR(20) NOT NULL,
                        price           NUMERIC(14,4),
                        bid             NUMERIC(14,4),
                        ask             NUMERIC(14,4),
                        volume_at_snap  BIGINT,
                        day_open        NUMERIC(14,4),
                        day_high        NUMERIC(14,4),
                        day_low         NUMERIC(14,4),
                        prev_close      NUMERIC(14,4),
                        change_pct      NUMERIC(8,4),
                        pe_ratio        NUMERIC(10,4),
                        forward_pe      NUMERIC(10,4),
                        market_cap      NUMERIC(20,2),
                        avg_volume_10d  BIGINT,
                        volume_velocity NUMERIC(8,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, snapshot_time, snapshot_type)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rms_security
                        ON raw_market_snapshots (security_id, snapshot_time DESC);
                    CREATE INDEX IF NOT EXISTS idx_rms_type
                        ON raw_market_snapshots (snapshot_type, snapshot_time DESC);

                    CREATE TABLE IF NOT EXISTS raw_institutional_moves (
                        move_id         SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        report_date     DATE,
                        holder_name     TEXT,
                        shares_held     BIGINT,
                        shares_changed  BIGINT,
                        change_pct      NUMERIC(8,4),
                        portfolio_pct   NUMERIC(8,4),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, report_date, holder_name)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rim_security
                        ON raw_institutional_moves (security_id, report_date DESC);

                    CREATE TABLE IF NOT EXISTS raw_press_releases (
                        release_id      SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        published_at    TIMESTAMP,
                        headline        TEXT NOT NULL,
                        source          VARCHAR(200),
                        url             TEXT,
                        symbol          VARCHAR(20),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, headline)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rpr_security
                        ON raw_press_releases (security_id, published_at DESC);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour

        # Determine snapshot type based on when we're running
        # 13:00-14:00 UTC = market open snapshot (9:30 ET)
        # 20:00-21:00 UTC = market close snapshot (16:00 ET)
        # 00:00 or 12:00 UTC = crypto 12h snapshot
        if 13 <= hour <= 14:
            snap_type = "market_open"
        elif 20 <= hour <= 21:
            snap_type = "market_close"
        elif hour in (0, 12):
            snap_type = "crypto_12h"
        else:
            snap_type = "manual"

        self.log.info("Snapshot type: %s (UTC hour: %d)", snap_type, hour)

        sec_lookup = {s["ticker"]: s for s in securities}
        quotes = {}
        fundamentals = {}
        institutional = {}
        press = {}

        # Decide which securities to snapshot
        if snap_type == "crypto_12h":
            targets = [s for s in securities if s["security_type"] == "crypto"]
        elif snap_type in ("market_open", "market_close"):
            targets = [s for s in securities if s["security_type"] == "equity"]
        else:
            targets = securities  # manual = everything

        self.log.info("Fetching snapshots for %d securities...", len(targets))

        # ── Price quotes via yfinance (batch) ────────────────────────
        if yf:
            tickers_str = " ".join(s["ticker"] for s in targets)
            try:
                data = yf.download(
                    tickers_str, period="1d", interval="1d",
                    group_by="ticker", auto_adjust=True,
                    threads=True, progress=False, prepost=True,
                )
                if data is not None and not data.empty:
                    quotes["yf_batch"] = data
            except Exception as e:
                self.log.warning("yfinance batch failed: %s", e)

        # ── Per-ticker: yfinance info (P/E, market cap) + Finnhub ────
        for i, s in enumerate(targets):
            ticker = s["ticker"]

            # yfinance Ticker info for fundamentals
            if yf and s["security_type"] == "equity":
                try:
                    info = yf.Ticker(ticker).info
                    fundamentals[ticker] = {
                        "pe_ratio": info.get("trailingPE"),
                        "forward_pe": info.get("forwardPE"),
                        "market_cap": info.get("marketCap"),
                        "avg_volume_10d": info.get("averageDailyVolume10Day"),
                        "bid": info.get("bid"),
                        "ask": info.get("ask"),
                        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                        "prev_close": info.get("previousClose"),
                        "day_open": info.get("regularMarketOpen"),
                        "day_high": info.get("regularMarketDayHigh"),
                        "day_low": info.get("regularMarketDayLow"),
                        "volume": info.get("regularMarketVolume"),
                    }
                    self.stats["fetched"] += 1
                except Exception as e:
                    self.log.debug("yfinance info failed for %s: %s", ticker, e)

            # Finnhub institutional ownership (equities only, once per day)
            if s["security_type"] == "equity" and snap_type == "market_close":
                try:
                    resp = requests.get(
                        FINNHUB_OWNERSHIP,
                        params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
                        timeout=config.HTTP_TIMEOUT,
                    )
                    if resp.status_code == 200:
                        ownership_data = resp.json().get("data", [])
                        if ownership_data:
                            institutional[ticker] = ownership_data[:20]
                except requests.RequestException:
                    pass

            # Finnhub press releases (equities only, once per day)
            if s["security_type"] == "equity" and snap_type == "market_close":
                try:
                    resp = requests.get(
                        FINNHUB_PRESS,
                        params={
                            "symbol": ticker,
                            "from": (date.today() - timedelta(days=3)).isoformat(),
                            "to": date.today().isoformat(),
                            "token": config.FINNHUB_API_KEY,
                        },
                        timeout=config.HTTP_TIMEOUT,
                    )
                    if resp.status_code == 200:
                        pr_data = resp.json().get("majorDevelopment", [])
                        if pr_data:
                            press[ticker] = pr_data[:10]
                except requests.RequestException:
                    pass

            # Rate limit: Finnhub 60/min
            if (i + 1) % 55 == 0:
                self.log.info("  Progress: %d/%d, rate limit pause...", i + 1, len(targets))
                time.sleep(62)
            elif s["security_type"] == "equity":
                time.sleep(0.5)

        return {
            "snap_type": snap_type,
            "quotes": quotes,
            "fundamentals": fundamentals,
            "institutional": institutional,
            "press": press,
            "targets": targets,
            "snap_time": now_utc.replace(tzinfo=None),
        }

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        snap_type = raw_data["snap_type"]
        snap_time = raw_data["snap_time"]
        fundamentals = raw_data["fundamentals"]

        snapshots = []
        inst_rows = []
        press_rows = []

        for s in raw_data["targets"]:
            ticker = s["ticker"]
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            info = fundamentals.get(ticker, {})
            price = info.get("current_price")
            volume = info.get("volume")
            avg_vol = info.get("avg_volume_10d")

            # Volume velocity: current volume / 10-day average
            velocity = None
            if volume and avg_vol and avg_vol > 0:
                velocity = round(volume / avg_vol, 4)

            # Change percent
            prev = info.get("prev_close")
            change_pct = None
            if price and prev and prev > 0:
                change_pct = round(((price - prev) / prev) * 100, 4)

            snapshots.append({
                "security_id": sid,
                "snapshot_time": snap_time,
                "snapshot_type": snap_type,
                "price": price,
                "bid": info.get("bid"),
                "ask": info.get("ask"),
                "volume_at_snap": volume,
                "day_open": info.get("day_open"),
                "day_high": info.get("day_high"),
                "day_low": info.get("day_low"),
                "prev_close": prev,
                "change_pct": change_pct,
                "pe_ratio": info.get("pe_ratio"),
                "forward_pe": info.get("forward_pe"),
                "market_cap": info.get("market_cap"),
                "avg_volume_10d": avg_vol,
                "volume_velocity": velocity,
            })

        # Institutional moves
        for ticker, holders in raw_data["institutional"].items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue
            for h in holders:
                # Finnhub institutional-ownership returns nested structure
                name = h.get("name", "")
                for holding in h.get("holding", [])[:5]:
                    shares = holding.get("share", 0)
                    change = holding.get("change", 0)
                    pct = holding.get("percentage", 0)
                    filing_date = holding.get("filingDate", "")
                    if abs(change) > 0:
                        inst_rows.append({
                            "security_id": sid,
                            "report_date": filing_date or date.today().isoformat(),
                            "holder_name": name[:200],
                            "shares_held": shares,
                            "shares_changed": change,
                            "change_pct": round(change / shares * 100, 4) if shares else None,
                            "portfolio_pct": pct,
                        })

        # Press releases
        for ticker, releases in raw_data["press"].items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue
            for pr in releases:
                headline = (pr.get("headline") or "")[:500]
                if not headline:
                    continue
                pub_date = pr.get("datetime", "")
                press_rows.append({
                    "security_id": sid,
                    "published_at": pub_date or snap_time,
                    "headline": headline,
                    "source": (pr.get("source") or "")[:200],
                    "url": (pr.get("url") or "")[:500],
                    "symbol": ticker[:20],
                })

        return {
            "snapshots": snapshots,
            "institutional": inst_rows,
            "press": press_rows,
        }

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        snapshots = rows["snapshots"]
        inst_rows = rows["institutional"]
        press_rows = rows["press"]

        self.log.info("Writing %d snapshots, %d institutional moves, %d press releases...",
                      len(snapshots), len(inst_rows), len(press_rows))

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                if snapshots:
                    execute_values(
                        cur,
                        """INSERT INTO raw_market_snapshots
                               (security_id, snapshot_time, snapshot_type, price, bid, ask,
                                volume_at_snap, day_open, day_high, day_low, prev_close,
                                change_pct, pe_ratio, forward_pe, market_cap,
                                avg_volume_10d, volume_velocity)
                           VALUES %s
                           ON CONFLICT (security_id, snapshot_time, snapshot_type)
                           DO UPDATE SET price = EXCLUDED.price,
                                         volume_at_snap = EXCLUDED.volume_at_snap,
                                         volume_velocity = EXCLUDED.volume_velocity,
                                         collected_at = now()""",
                        [(s["security_id"], s["snapshot_time"], s["snapshot_type"],
                          s["price"], s["bid"], s["ask"], s["volume_at_snap"],
                          s["day_open"], s["day_high"], s["day_low"], s["prev_close"],
                          s["change_pct"], s["pe_ratio"], s["forward_pe"],
                          s["market_cap"], s["avg_volume_10d"], s["volume_velocity"])
                         for s in snapshots],
                        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        page_size=config.DB_BATCH_SIZE,
                    )
                    self.stats["stored"] += len(snapshots)

                if inst_rows:
                    execute_values(
                        cur,
                        """INSERT INTO raw_institutional_moves
                               (security_id, report_date, holder_name, shares_held,
                                shares_changed, change_pct, portfolio_pct)
                           VALUES %s
                           ON CONFLICT (security_id, report_date, holder_name)
                           DO UPDATE SET shares_held = EXCLUDED.shares_held,
                                         shares_changed = EXCLUDED.shares_changed,
                                         change_pct = EXCLUDED.change_pct,
                                         portfolio_pct = EXCLUDED.portfolio_pct,
                                         last_updated = now()""",
                        [(r["security_id"], r["report_date"], r["holder_name"],
                          r["shares_held"], r["shares_changed"], r["change_pct"],
                          r["portfolio_pct"])
                         for r in inst_rows],
                        template="(%s,%s,%s,%s,%s,%s,%s)",
                        page_size=config.DB_BATCH_SIZE,
                    )
                    self.stats["stored"] += len(inst_rows)

                if press_rows:
                    execute_values(
                        cur,
                        """INSERT INTO raw_press_releases
                               (security_id, published_at, headline, source, url, symbol)
                           VALUES %s
                           ON CONFLICT (security_id, headline)
                           DO UPDATE SET last_updated = now()""",
                        [(r["security_id"], r["published_at"], r["headline"],
                          r["source"], r["url"], r["symbol"])
                         for r in press_rows],
                        template="(%s,%s,%s,%s,%s,%s)",
                        page_size=config.DB_BATCH_SIZE,
                    )
                    self.stats["stored"] += len(press_rows)

        # Coverage tracking uses snapshot count
        coverage = {}
        for s in snapshots:
            sid = s["security_id"]
            coverage[sid] = coverage.get(sid, 0) + 1
        if coverage:
            from base import BaseCollector
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    db.upsert_coverage_batch(cur, self.COLLECTOR_ID,
                                             [(sid, cnt) for sid, cnt in coverage.items()])

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "Market snapshots: %d fetched, %d stored, %d errors",
            self.stats["fetched"], self.stats["stored"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(MarketSnapshotCollector)
