"""
LLM Outlook Collector — daily AI-generated price direction assessment per security.

Collector ID: 37 (LLM Outlook)
Table:        raw_llm_outlooks

Uses Anthropic Claude Haiku (fastest model) to assess each security's
near-term price direction based on the last week of public news.
Stores plain-text analysis with no markup. Logs query duration.

Schedule: once per day, after all other collectors and signal extraction.
"""

import sys
import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("llm_outlook")

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are a concise equity/crypto analyst. Respond with plain text only. "
    "No markdown, no bullet points, no asterisks, no formatting characters. "
    "Be very concise and factual. No inefficient words or commentary. "
    "Just analysis and why you came to this position."
)

USER_TEMPLATE = (
    "Is the security {ticker} ({name}), based on the last week's worth of "
    "public news, in your opinion likely to rise in share price, stay around "
    "the same, or lose share price? And why?"
)


def _strip_formatting(text):
    """Remove any markdown/control characters that slip through."""
    text = re.sub(r'[*_`#~\[\]|>]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('\r', '')
    return text.strip()


def _classify_direction(text):
    """Extract direction from the LLM response text."""
    lower = text.lower()
    # Check for explicit direction statements
    rise_words = ["likely to rise", "will rise", "upward", "bullish", "increase in share price",
                  "higher", "gain", "positive momentum", "price appreciation"]
    fall_words = ["likely to lose", "will lose", "will fall", "downward", "bearish",
                  "decline", "decrease in share price", "lower", "drop", "negative pressure",
                  "lose share price"]
    same_words = ["stay around the same", "relatively flat", "sideways", "neutral",
                  "remain stable", "trade in a range", "consolidate"]

    rise_hits = sum(1 for w in rise_words if w in lower)
    fall_hits = sum(1 for w in fall_words if w in lower)
    same_hits = sum(1 for w in same_words if w in lower)

    if rise_hits > fall_hits and rise_hits > same_hits:
        return "bullish"
    if fall_hits > rise_hits and fall_hits > same_hits:
        return "bearish"
    if same_hits > 0:
        return "neutral"
    # Fallback: check first sentence
    first_sentence = lower.split('.')[0]
    if any(w in first_sentence for w in ["rise", "higher", "bullish", "gain"]):
        return "bullish"
    if any(w in first_sentence for w in ["lose", "fall", "bearish", "decline", "drop"]):
        return "bearish"
    return "neutral"


class LLMOutlookCollector(BaseCollector):

    COLLECTOR_ID = 37
    COLLECTOR_NAME = "LLM Outlook"
    COLLECTOR_TYPE = "analytics"

    def setup(self):
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to collectors/.env:\n"
                "  ANTHROPIC_API_KEY=sk-ant-..."
            )
        self._client = None
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_llm_outlooks (
                        outlook_id      SERIAL PRIMARY KEY,
                        security_id     INT NOT NULL REFERENCES securities(security_id),
                        outlook_date    DATE NOT NULL,
                        model           VARCHAR(60) NOT NULL,
                        direction       VARCHAR(10) NOT NULL,
                        analysis        TEXT NOT NULL,
                        query_seconds   NUMERIC(8,3) NOT NULL,
                        input_tokens    INT,
                        output_tokens   INT,
                        collected_at    TIMESTAMP DEFAULT now(),
                        UNIQUE(security_id, outlook_date, model)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rlo_security
                        ON raw_llm_outlooks (security_id, outlook_date DESC);
                    CREATE INDEX IF NOT EXISTS idx_rlo_date
                        ON raw_llm_outlooks (outlook_date DESC);
                """)

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        return self._client

    def _query_llm(self, ticker, name):
        """Send one query to Claude Haiku. Returns (analysis, direction, seconds, in_tokens, out_tokens)."""
        client = self._get_client()
        prompt = USER_TEMPLATE.format(ticker=ticker, name=name or ticker)

        start = time.monotonic()
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed = round(time.monotonic() - start, 3)

            text = response.content[0].text
            text = _strip_formatting(text)
            direction = _classify_direction(text)
            in_tok = response.usage.input_tokens
            out_tok = response.usage.output_tokens

            return text, direction, elapsed, in_tok, out_tok

        except Exception as e:
            elapsed = round(time.monotonic() - start, 3)
            self.log.warning("LLM query failed for %s (%.1fs): %s", ticker, elapsed, e)
            return None, None, elapsed, 0, 0

    def fetch(self, securities):
        """Query Haiku for each security."""
        today = datetime.now(timezone.utc).date()

        # Check which securities already have today's outlook
        existing = set()
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT security_id FROM raw_llm_outlooks WHERE outlook_date = %s AND model = %s",
                    (today, MODEL)
                )
                existing = {row[0] for row in cur.fetchall()}

        targets = [s for s in securities if s["security_id"] not in existing]
        total = len(targets)
        self.log.info("Querying %s for %d securities (%d already done today)...",
                      MODEL, total, len(existing))

        results = []
        for i, s in enumerate(targets):
            ticker = s["ticker"]
            name = s.get("name", "")

            analysis, direction, seconds, in_tok, out_tok = self._query_llm(ticker, name)

            if analysis:
                results.append({
                    "security_id": s["security_id"],
                    "ticker": ticker,
                    "outlook_date": today,
                    "model": MODEL,
                    "direction": direction,
                    "analysis": analysis,
                    "query_seconds": seconds,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                })
                self.stats["fetched"] += 1
                self.log.info("  [%d/%d] %s → %s (%.1fs, %d tok)",
                              i + 1, total, ticker, direction, seconds, out_tok)
            else:
                self.stats["errors"] += 1

            # Gentle pacing — Haiku is fast but let's not slam the API
            time.sleep(0.3)

        return results

    def transform(self, raw_data, securities):
        return raw_data  # already in row format

    def store(self, rows):
        if not rows:
            return
        self.log.info("Writing %d LLM outlooks...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_llm_outlooks
                           (security_id, outlook_date, model, direction, analysis,
                            query_seconds, input_tokens, output_tokens)
                       VALUES %s
                       ON CONFLICT (security_id, outlook_date, model)
                       DO UPDATE SET direction = EXCLUDED.direction,
                                     analysis = EXCLUDED.analysis,
                                     query_seconds = EXCLUDED.query_seconds,
                                     input_tokens = EXCLUDED.input_tokens,
                                     output_tokens = EXCLUDED.output_tokens,
                                     collected_at = now()""",
                    [(r["security_id"], r["outlook_date"], r["model"],
                      r["direction"], r["analysis"], r["query_seconds"],
                      r["input_tokens"], r["output_tokens"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        total_time = sum(r.get("query_seconds", 0) for r in getattr(self, '_last_rows', []))
        self.log.info(
            "LLM outlooks: %d fetched, %d errors, %d stored",
            self.stats["fetched"], self.stats["errors"], self.stats["stored"],
        )


if __name__ == "__main__":
    run_collector(LLMOutlookCollector)
