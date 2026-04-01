"""
CryptoPanic News Collector — hot crypto news with sentiment.

Collector ID: 25 (CryptoPanic News Feed)
Table:        raw_news_sentiment (shared with Finnhub news)

CryptoPanic aggregates crypto news from hundreds of sources and provides
crowd-voted sentiment (bullish/bearish). Hot filtered news with negative
sentiment on BTC or ETH is an early warning signal.

Data source:
  - CryptoPanic API v1 (requires auth_token)
  - Endpoint: /api/v1/posts/?filter=hot&currencies=BTC,ETH
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

CRYPTOPANIC_API = "https://cryptopanic.com/api/v1/posts/"

# Map CryptoPanic currency codes to our ticker symbols
CURRENCY_TICKER_MAP = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}


class CryptoPanicNewsCollector(BaseCollector):

    COLLECTOR_ID = 25
    COLLECTOR_NAME = "CryptoPanic News Feed"
    COLLECTOR_TYPE = "social"
    SECURITY_TYPE_FILTER = "crypto"

    def setup(self):
        if not config.CRYPTOPANIC_API_KEY:
            raise RuntimeError("CRYPTOPANIC_API_KEY not set")
        self._ensure_table()

    def _ensure_table(self):
        """Ensure raw_news_sentiment exists (same table as Finnhub news)."""
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
                    CREATE INDEX IF NOT EXISTS idx_rns_security
                        ON raw_news_sentiment (security_id, published_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_rns_date
                        ON raw_news_sentiment (published_at DESC);
                """)

    def fetch(self, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        raw_posts = []

        self.log.info("Fetching CryptoPanic hot news...")

        try:
            resp = requests.get(
                CRYPTOPANIC_API,
                params={
                    "auth_token": config.CRYPTOPANIC_API_KEY,
                    "filter": "hot",
                    "currencies": "BTC,ETH",
                },
                timeout=config.HTTP_TIMEOUT,
            )

            if resp.status_code == 403:
                self.log.warning("CryptoPanic 403 — API token may be invalid")
                return []
            if resp.status_code != 200:
                self.log.warning("CryptoPanic returned %d", resp.status_code)
                return []

            data = resp.json()
            posts = data.get("results", [])
            self.log.info("CryptoPanic returned %d posts", len(posts))

            for post in posts:
                # Map currencies mentioned in post to our securities
                currencies = post.get("currencies", [])
                if not currencies:
                    continue

                for curr in currencies:
                    code = curr.get("code", "").upper()
                    ticker = CURRENCY_TICKER_MAP.get(code)
                    if not ticker or ticker not in sec_lookup:
                        continue

                    raw_posts.append({
                        "security_id": sec_lookup[ticker],
                        "post": post,
                        "currency_code": code,
                    })

            self.stats["fetched"] += len(raw_posts)

        except requests.RequestException as e:
            self.log.warning("CryptoPanic error: %s", e)
            self.stats["errors"] += 1

        return raw_posts

    def transform(self, raw_data, securities):
        rows = []

        # Try VADER for sentiment scoring
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
            _use_vader = True
        except ImportError:
            _vader = None
            _use_vader = False

        for item in raw_data:
            post = item["post"]
            sid = item["security_id"]

            title = (post.get("title") or "")[:500]
            if not title:
                continue

            # Parse published timestamp
            published = None
            pub_str = post.get("published_at")
            if pub_str:
                try:
                    published = datetime.fromisoformat(
                        pub_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass

            # Sentiment scoring
            if _use_vader:
                sentiment = _vader.polarity_scores(title)["compound"]
            else:
                # Estimate from CryptoPanic votes
                votes = post.get("votes", {})
                positive = votes.get("positive", 0)
                negative = votes.get("negative", 0)
                total = positive + negative
                if total > 0:
                    sentiment = (positive - negative) / total
                else:
                    sentiment = 0.0

            source_info = post.get("source", {})
            source_name = source_info.get("title", "") if isinstance(source_info, dict) else str(source_info)

            rows.append({
                "security_id": sid,
                "published_at": published,
                "headline": title,
                "source": source_name[:200],
                "url": (post.get("url") or "")[:500],
                "category": "crypto",
                "sentiment": round(sentiment, 3),
            })

        return rows

    def store(self, rows):
        self.log.info("Writing %d CryptoPanic news articles...", len(rows))
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

    def teardown(self):
        self.log.info("CryptoPanic news: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(CryptoPanicNewsCollector)
