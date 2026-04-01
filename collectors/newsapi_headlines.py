"""
NewsAPI General News Collector — headline news with VADER sentiment.

Collector ID: 26 (NewsAPI Headlines)
Table:        raw_news_sentiment (shared with Finnhub/CryptoPanic news)

NewsAPI provides general news coverage across thousands of sources.
We query for each equity ticker and score headlines with VADER sentiment.
Free tier: 100 requests/day, so we limit to top 50 tickers.

Data source:
  - NewsAPI v2 (requires API key)
  - Endpoint: /v2/everything?q={ticker}&sortBy=publishedAt&pageSize=10
"""

import sys
import os
import time
import requests
from datetime import datetime, date, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

# Max tickers to query (NewsAPI free tier = 100 req/day, leave headroom)
MAX_TICKERS = 50


class NewsAPIHeadlinesCollector(BaseCollector):

    COLLECTOR_ID = 26
    COLLECTOR_NAME = "NewsAPI Headlines"
    COLLECTOR_TYPE = "social"

    def setup(self):
        if not config.NEWSAPI_API_KEY:
            raise RuntimeError("NEWSAPI_API_KEY not set")
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

    def _select_tickers(self, securities):
        """Pick top tickers to query, prioritizing those with recent signal activity."""
        # Try to get tickers ranked by recent signal count
        priority_sids = set()
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT security_id
                        FROM signals
                        WHERE detected_at > now() - INTERVAL '7 days'
                        GROUP BY security_id
                        ORDER BY COUNT(*) DESC
                        LIMIT %s
                    """, (MAX_TICKERS,))
                    priority_sids = {row[0] for row in cur.fetchall()}
        except Exception:
            pass  # signals table may not exist yet

        # Build ordered list: priority tickers first, then fill with equities
        equities = [s for s in securities if s["security_type"] == "equity"]
        priority = [s for s in equities if s["security_id"] in priority_sids]
        rest = [s for s in equities if s["security_id"] not in priority_sids]

        selected = priority + rest
        return selected[:MAX_TICKERS]

    def fetch(self, securities):
        selected = self._select_tickers(securities)
        self.log.info("Fetching NewsAPI headlines for %d tickers (of %d total)...",
                      len(selected), len(securities))

        from_date = (date.today() - timedelta(days=3)).isoformat()
        raw = {}
        total = len(selected)

        for i, s in enumerate(selected):
            ticker = s["ticker"]
            try:
                resp = requests.get(
                    NEWSAPI_BASE,
                    params={
                        "q": ticker,
                        "apiKey": config.NEWSAPI_API_KEY,
                        "sortBy": "publishedAt",
                        "pageSize": 10,
                        "from": from_date,
                        "language": "en",
                    },
                    timeout=config.HTTP_TIMEOUT,
                )

                if resp.status_code == 401:
                    self.log.warning("NewsAPI 401 — API key may be invalid")
                    break
                if resp.status_code == 429:
                    self.log.warning("NewsAPI rate limited at %d/%d tickers", i, total)
                    self.stats["errors"] += 1
                    break
                if resp.status_code != 200:
                    self.log.debug("NewsAPI %d for %s", resp.status_code, ticker)
                    self.stats["skipped"] += 1
                    continue

                data = resp.json()
                articles = data.get("articles", [])
                if articles:
                    raw[ticker] = articles
                    self.stats["fetched"] += 1
                else:
                    self.stats["skipped"] += 1

            except requests.RequestException as e:
                self.log.debug("NewsAPI error for %s: %s", ticker, e)
                self.stats["errors"] += 1

            # Small delay to stay well under rate limits
            if (i + 1) % 10 == 0:
                time.sleep(1)

        return raw

    def transform(self, raw_data, securities):
        sec_lookup = {s["ticker"]: s["security_id"] for s in securities}
        rows = []

        # VADER for sentiment scoring
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
        }
        POSITIVE_WORDS = {
            "upgrade", "beat", "growth", "profit", "expansion", "acquisition",
            "partnership", "approval", "innovation", "record", "surge",
            "bullish", "breakout", "rally", "dividend", "buyback",
            "soaring", "jumps", "higher", "gains", "leads", "rises",
        }

        for ticker, articles in raw_data.items():
            sid = sec_lookup.get(ticker)
            if not sid:
                continue

            for a in articles[:10]:
                title = (a.get("title") or "")[:500]
                if not title or title == "[Removed]":
                    continue

                # Parse timestamp
                published = None
                pub_str = a.get("publishedAt")
                if pub_str:
                    try:
                        published = datetime.fromisoformat(
                            pub_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        pass

                # Sentiment scoring: VADER on headline + description
                text_for_sentiment = title
                desc = a.get("description") or ""
                if desc and desc != "[Removed]":
                    text_for_sentiment = f"{title} {desc[:200]}"

                if _use_vader:
                    sentiment = _vader.polarity_scores(text_for_sentiment)["compound"]
                else:
                    words = text_for_sentiment.lower().split()
                    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
                    pos = sum(1 for w in words if w in POSITIVE_WORDS)
                    sentiment = (pos - neg) / (pos + neg) if (neg + pos) > 0 else 0.0

                source_info = a.get("source", {})
                source_name = source_info.get("name", "") if isinstance(source_info, dict) else ""

                rows.append({
                    "security_id": sid,
                    "published_at": published,
                    "headline": title,
                    "source": source_name[:200],
                    "url": (a.get("url") or "")[:500],
                    "category": "general",
                    "sentiment": round(sentiment, 3),
                })

        return rows

    def store(self, rows):
        self.log.info("Writing %d NewsAPI articles...", len(rows))
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
        self.log.info("NewsAPI headlines: %d fetched, %d stored, %d skipped, %d errors",
                      self.stats["fetched"], self.stats["stored"],
                      self.stats["skipped"], self.stats["errors"])


if __name__ == "__main__":
    run_collector(NewsAPIHeadlinesCollector)
