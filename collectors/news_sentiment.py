"""
News Sentiment Collector — headline sentiment via Finnhub.

Collector ID: 19 (Social Velocity Scanner — repurposed for news)
Table:        raw_news_sentiment

Finnhub endpoint: /api/v1/company-news?symbol=TICKER&from=DATE&to=DATE
  (free tier: 60 calls/min, returns headlines with sentiment)

We use Finnhub instead of NewsAPI because Finnhub returns financial news
with built-in sentiment and is more reliable for ticker-specific queries.
"""

import sys
import os
import time
import requests
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db


class NewsSentimentCollector(BaseCollector):

    # ── identity ──────────────────────────────────────────────────────
    COLLECTOR_ID = 19
    COLLECTOR_NAME = "News Sentiment Scanner"
    COLLECTOR_TYPE = "social"

    # ── setup ─────────────────────────────────────────────────────────

    def setup(self):
        if not config.FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY not set")
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_news_sentiment (
                        news_id         SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        published_at    TIMESTAMP,
                        headline        TEXT,
                        source          VARCHAR(200),
                        url             TEXT,
                        category        VARCHAR(50),
                        sentiment       NUMERIC(5,3),
                        collected_at    TIMESTAMP DEFAULT now(),
                        last_updated    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, headline)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rns_security ON raw_news_sentiment (security_id, published_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_rns_date ON raw_news_sentiment (published_at DESC);
                """)

    # ── fetch ─────────────────────────────────────────────────────────

    def fetch(self, securities):
        """Fetch recent company news from Finnhub."""
        raw = {}
        today = date.today()
        from_date = (today - timedelta(days=3)).isoformat()
        to_date = today.isoformat()
        total = len(securities)

        for i, s in enumerate(securities):
            ticker = s["ticker"]
            if s["security_type"] == "crypto":
                self.stats["skipped"] += 1
                continue

            try:
                resp = requests.get(
                    "https://finnhub.io/api/v1/company-news",
                    params={
                        "symbol": ticker,
                        "from": from_date,
                        "to": to_date,
                        "token": config.FINNHUB_API_KEY,
                    },
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        raw[ticker] = data
                        self.stats["fetched"] += 1
                    elif isinstance(data, dict) and "error" in data:
                        # API limit or error response
                        self.log.warning("API error for %s: %s", ticker, data["error"][:80])
                        self.stats["errors"] += 1
                        time.sleep(5)
                    else:
                        self.stats["skipped"] += 1
                elif resp.status_code == 429:
                    self.log.warning("Rate limited at %d/%d, sleeping...", i, total)
                    time.sleep(5)
                    self.stats["errors"] += 1
                else:
                    self.stats["skipped"] += 1

            except requests.RequestException as e:
                self.log.debug("Fetch error for %s: %s", ticker, e)
                self.stats["errors"] += 1

            # Finnhub free tier: 60/min
            if (i + 1) % 55 == 0:
                self.log.info("  Progress: %d/%d tickers, sleeping for rate limit...", i + 1, total)
                time.sleep(62)

        return raw

    # ── transform ─────────────────────────────────────────────────────

    def transform(self, raw_data, securities):
        from datetime import datetime, timezone
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        rows = []

        # Sentiment scoring: VADER if available, keyword fallback
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
            _use_vader = True
        except ImportError:
            _vader = None
            _use_vader = False

        NEGATIVE_WORDS = {
            "lawsuit", "fraud", "investigation", "subpoena", "indictment",
            "scandal", "recall", "bankruptcy", "layoff", "downgrade",
            "decline", "loss", "miss", "warning", "probe", "penalty",
            "violation", "breach", "hack", "crash", "default", "debt",
            "sinks", "plunge", "tumble", "slump", "falls", "drops",
            "concern", "fears", "crisis", "threat", "risk", "shortage",
            "cuts", "slash", "suspend", "delay", "weak", "disappoints",
        }
        POSITIVE_WORDS = {
            "upgrade", "beat", "growth", "profit", "expansion", "acquisition",
            "partnership", "approval", "innovation", "record", "surge",
            "bullish", "breakout", "rally", "dividend", "buyback",
            "soaring", "jumps", "higher", "gains", "leads", "rises",
            "strong", "exceeds", "outperform", "momentum", "boost",
            "recovery", "rebound", "tops", "climbs", "advances",
        }

        for ticker, articles in raw_data.items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            for a in articles[:10]:  # cap at 10 per ticker
                headline = (a.get("headline") or "")[:500]
                if not headline:
                    continue

                # Timestamp
                ts = a.get("datetime")
                if ts:
                    published = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
                else:
                    published = None

                # Sentiment scoring (-1 to +1)
                if _use_vader:
                    sentiment = _vader.polarity_scores(headline)["compound"]
                else:
                    # Keyword fallback
                    words = headline.lower().split()
                    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
                    pos = sum(1 for w in words if w in POSITIVE_WORDS)
                    sentiment = (pos - neg) / (pos + neg) if (neg + pos) > 0 else 0.0

                rows.append({
                    "security_id": sid,
                    "published_at": published,
                    "headline": headline,
                    "source": (a.get("source") or "")[:200],
                    "url": (a.get("url") or "")[:500],
                    "category": (a.get("category") or "")[:50],
                    "sentiment": round(sentiment, 3),
                })

        return rows

    # ── store ─────────────────────────────────────────────────────────

    def store(self, rows):
        self.log.info("Writing %d news articles...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_news_sentiment
                           (security_id, published_at, headline, source, url, category, sentiment)
                       VALUES %s
                       ON CONFLICT (security_id, headline)
                       DO UPDATE SET last_updated = now()""",
                    [(r["security_id"], r["published_at"], r["headline"],
                      r["source"], r["url"], r["category"], r["sentiment"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    # ── teardown ──────────────────────────────────────────────────────

    def teardown(self):
        self.log.info(
            "News sentiment: %d fetched, %d stored, %d skipped, %d errors",
            self.stats["fetched"], self.stats["stored"],
            self.stats["skipped"], self.stats["errors"],
        )


if __name__ == "__main__":
    run_collector(NewsSentimentCollector)
