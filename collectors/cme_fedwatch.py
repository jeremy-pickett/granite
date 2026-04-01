"""
CME FedWatch Monitor — Federal Reserve rate decision probabilities.

Collector ID: 41 (CME FedWatch Monitor)
Table:        raw_fedwatch

Attempts CME's internal API for FedWatch probabilities. Falls back to
the Alternative.me fear/greed endpoint metadata or FRED data if CME
blocks the request.

Fires prediction_market_heat signals when rate cut or rate hike
probability exceeds 80% — extreme conviction on rate direction
affects the entire equity market.
"""

import sys
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values
import config
import db

CME_URL = "https://www.cmegroup.com/services/fed-funds-target-rate-probabilities"
CME_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
}

# Fallback: FRED effective fed funds rate (free, no key needed for small requests)
FRED_EFFR_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU,DFEDTARL&cosd={start}&coed={end}"


class CMEFedWatchCollector(BaseCollector):

    COLLECTOR_ID = 41
    COLLECTOR_NAME = "CME FedWatch Monitor"
    COLLECTOR_TYPE = "analytics"

    def setup(self):
        self._ensure_table()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_fedwatch (
                        fedwatch_id         SERIAL PRIMARY KEY,
                        observation_date    DATE NOT NULL,
                        meeting_date        DATE NOT NULL,
                        target_rate_low     NUMERIC(5,4),
                        target_rate_high    NUMERIC(5,4),
                        probability         NUMERIC(5,4),
                        implied_rate        NUMERIC(5,4),
                        collected_at        TIMESTAMP DEFAULT now(),
                        UNIQUE(observation_date, meeting_date, target_rate_low)
                    );
                """)

    def fetch(self, securities):
        today = datetime.now(timezone.utc).date()
        rows = []

        # Try CME primary source
        rows = self._fetch_cme(today)

        # Fallback: derive from FRED current rate + market expectations
        if not rows:
            self.log.info("CME fetch failed or empty, trying FRED fallback...")
            rows = self._fetch_fred_fallback(today)

        self.stats["fetched"] = len(rows)
        return rows

    def _fetch_cme(self, today):
        """Try CME FedWatch API."""
        rows = []
        try:
            resp = requests.get(
                CME_URL,
                headers=CME_HEADERS,
                timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                self.log.warning("CME API returned %d", resp.status_code)
                return []

            data = resp.json()
            self.log.info("CME FedWatch data retrieved successfully")

            # CME returns a nested structure with meetings and probabilities
            # The exact format varies; handle both known shapes
            meetings = []
            if isinstance(data, dict):
                # Try common response shapes
                for key in ("meetings", "data", "result"):
                    if key in data and isinstance(data[key], list):
                        meetings = data[key]
                        break
                if not meetings and "meetingDates" in data:
                    meetings = data.get("meetingDates", [])
            elif isinstance(data, list):
                meetings = data

            for meeting in meetings[:4]:  # Next 4 meetings max
                meeting_date_str = (
                    meeting.get("meetingDate")
                    or meeting.get("date")
                    or meeting.get("meeting_date", "")
                )
                if not meeting_date_str:
                    continue

                try:
                    if "/" in meeting_date_str:
                        meeting_date = datetime.strptime(meeting_date_str, "%m/%d/%Y").date()
                    elif "-" in meeting_date_str:
                        meeting_date = datetime.strptime(meeting_date_str[:10], "%Y-%m-%d").date()
                    else:
                        continue
                except (ValueError, TypeError):
                    continue

                # Extract rate probabilities
                probs = (
                    meeting.get("probabilities")
                    or meeting.get("targets")
                    or meeting.get("rates", [])
                )
                if not probs:
                    continue

                implied_rate = 0.0
                for p in probs:
                    rate_low = float(p.get("lowTarget", p.get("low", p.get("target_low", 0))))
                    rate_high = float(p.get("highTarget", p.get("high", p.get("target_high", rate_low + 0.0025))))
                    probability = float(p.get("probability", p.get("prob", 0)))

                    # Normalize probability to 0-1 if given as percentage
                    if probability > 1:
                        probability /= 100.0

                    midpoint = (rate_low + rate_high) / 2
                    implied_rate += midpoint * probability

                    rows.append({
                        "observation_date": today,
                        "meeting_date": meeting_date,
                        "target_rate_low": rate_low,
                        "target_rate_high": rate_high,
                        "probability": round(probability, 4),
                        "implied_rate": None,  # Set after loop
                    })

                # Update implied rate for this meeting's rows
                for r in rows:
                    if r["meeting_date"] == meeting_date and r["implied_rate"] is None:
                        r["implied_rate"] = round(implied_rate, 4)

            self.log.info("  Parsed %d rate probability rows from CME", len(rows))

        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            self.log.warning("CME API error: %s", e)
            self.stats["errors"] += 1

        return rows

    def _fetch_fred_fallback(self, today):
        """
        Fallback: get current fed funds target rate from FRED CSV export.
        We can't get meeting probabilities from FRED, but we can record the
        current rate as a baseline and synthesize a 'no change' probability row.
        """
        rows = []
        start = (today - timedelta(days=30)).isoformat()
        end = today.isoformat()

        try:
            url = FRED_EFFR_URL.format(start=start, end=end)
            resp = requests.get(url, timeout=config.HTTP_TIMEOUT)
            if resp.status_code != 200:
                self.log.warning("FRED CSV returned %d", resp.status_code)
                return []

            lines = resp.text.strip().split("\n")
            if len(lines) < 2:
                return []

            # Parse CSV: DATE,DFEDTARU,DFEDTARL
            latest_line = lines[-1]
            parts = latest_line.split(",")
            if len(parts) < 3:
                return []

            try:
                rate_high = float(parts[1]) / 100  # FRED gives percentage
                rate_low = float(parts[2]) / 100
            except (ValueError, IndexError):
                # Try parsing as "." for missing data
                self.log.warning("Could not parse FRED rate data: %s", parts)
                return []

            self.log.info("  FRED current target rate: %.4f - %.4f", rate_low, rate_high)

            # Synthesize "current rate holds" rows for next ~3 FOMC meetings
            # FOMC meets roughly every 6 weeks
            for i in range(1, 4):
                meeting_approx = today + timedelta(weeks=6 * i)
                rows.append({
                    "observation_date": today,
                    "meeting_date": meeting_approx,
                    "target_rate_low": rate_low,
                    "target_rate_high": rate_high,
                    "probability": 0.5,  # Unknown — 50/50 baseline
                    "implied_rate": round((rate_low + rate_high) / 2, 4),
                })

            self.log.info("  Generated %d baseline rows from FRED", len(rows))

        except requests.RequestException as e:
            self.log.warning("FRED fallback error: %s", e)
            self.stats["errors"] += 1

        return rows

    def transform(self, raw_data, securities):
        # Attach security_id for SPY (market-wide signal)
        spy_sec = next(
            (s for s in securities if s["ticker"] == "SPY"),
            None,
        )
        sid = spy_sec["security_id"] if spy_sec else None

        for row in raw_data:
            row["security_id"] = sid

        return raw_data

    def store(self, rows):
        self.log.info("Writing %d FedWatch records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_fedwatch
                           (observation_date, meeting_date, target_rate_low,
                            target_rate_high, probability, implied_rate)
                       VALUES %s
                       ON CONFLICT (observation_date, meeting_date, target_rate_low)
                       DO UPDATE SET probability = EXCLUDED.probability,
                                     implied_rate = EXCLUDED.implied_rate""",
                    [(r["observation_date"], r["meeting_date"], r["target_rate_low"],
                      r["target_rate_high"], r["probability"], r["implied_rate"])
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("FedWatch: %d fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


# ── Signal extraction ─────────────────────────────────────────────────

def run_signals():
    """Fire prediction_market_heat signals on extreme rate conviction."""
    import logging
    logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
    log = logging.getLogger("fedwatch_signals")

    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today = datetime.now(timezone.utc).date()
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Look up SPY security_id
            try:
                cur.execute(
                    "SELECT security_id FROM securities WHERE ticker = 'SPY' LIMIT 1"
                )
                sec_row = cur.fetchone()
            except Exception:
                sec_row = None

            if not sec_row:
                log.warning("No SPY security found")
                return 0

            spy_sid = sec_row[0]

            # Get most recent observation's data: per meeting, find the
            # highest-probability outcome and check for rate changes
            try:
                cur.execute("""
                    SELECT fw.meeting_date, fw.target_rate_low, fw.target_rate_high,
                           fw.probability, fw.implied_rate
                    FROM raw_fedwatch fw
                    WHERE fw.observation_date = (
                        SELECT MAX(observation_date) FROM raw_fedwatch
                    )
                    ORDER BY fw.meeting_date, fw.probability DESC
                """)
                rows = cur.fetchall()
            except Exception as e:
                log.warning("Query error: %s", e)
                rows = []

            if not rows:
                log.info("No FedWatch data found")
                return 0

            # Get current rate (most common high-probability entry for nearest meeting)
            # Group by meeting, find dominant probability per meeting
            meetings = {}
            for meeting_date, rate_low, rate_high, prob, implied_rate in rows:
                if meeting_date not in meetings:
                    meetings[meeting_date] = []
                meetings[meeting_date].append({
                    "rate_low": float(rate_low),
                    "rate_high": float(rate_high),
                    "probability": float(prob),
                    "implied_rate": float(implied_rate) if implied_rate else None,
                })

            # Get current rate from the implied rate of nearest past or current
            # For simplicity, use the first meeting's highest-prob rate as "current"
            sorted_meetings = sorted(meetings.keys())
            if not sorted_meetings:
                return 0

            # Analyze each meeting for extreme conviction
            for meeting_date in sorted_meetings:
                probs = meetings[meeting_date]
                if not probs:
                    continue

                # Find highest probability outcome
                top = max(probs, key=lambda p: p["probability"])
                max_prob = top["probability"]

                # Compute implied rate for this meeting
                implied = top.get("implied_rate") or (
                    (top["rate_low"] + top["rate_high"]) / 2
                )

                # Check if this represents a cut or hike vs first meeting's top rate
                first_meeting_top = max(
                    meetings[sorted_meetings[0]],
                    key=lambda p: p["probability"],
                )
                current_rate = (first_meeting_top["rate_low"] + first_meeting_top["rate_high"]) / 2

                rate_change = implied - current_rate

                # Only fire on extreme conviction (>80% probability)
                if max_prob < 0.80:
                    continue

                # Rate cut (implied < current)
                if rate_change < -0.001:
                    contribution = round(min((max_prob - 0.80) / 0.20 * 0.5 + 0.3, 1.0), 4)
                    direction = "bullish"  # Rate cuts are generally bullish for equities
                    desc = (
                        f"FedWatch: {max_prob:.0%} probability of rate cut "
                        f"({rate_change*100:+.0f}bps) by {meeting_date.strftime('%b %Y')}"
                    )
                    signals.append({
                        "security_id": spy_sid,
                        "signal_type": "prediction_market_heat",
                        "contribution": contribution,
                        "confidence": round(min(0.60 + max_prob * 0.2, 0.90), 4),
                        "direction": direction,
                        "magnitude": "extreme" if max_prob > 0.90 else "strong",
                        "raw_value": max_prob,
                        "description": desc[:300],
                        "detected_at": now,
                    })

                # Rate hike (implied > current)
                elif rate_change > 0.001:
                    contribution = round(min((max_prob - 0.80) / 0.20 * 0.5 + 0.3, 1.0), 4)
                    direction = "bearish"  # Rate hikes are generally bearish
                    desc = (
                        f"FedWatch: {max_prob:.0%} probability of rate hike "
                        f"({rate_change*100:+.0f}bps) by {meeting_date.strftime('%b %Y')}"
                    )
                    signals.append({
                        "security_id": spy_sid,
                        "signal_type": "prediction_market_heat",
                        "contribution": contribution,
                        "confidence": round(min(0.60 + max_prob * 0.2, 0.90), 4),
                        "direction": direction,
                        "magnitude": "extreme" if max_prob > 0.90 else "strong",
                        "raw_value": max_prob,
                        "description": desc[:300],
                        "detected_at": now,
                    })

    if signals:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO signals
                           (security_id, signal_type, contribution, confidence,
                            direction, magnitude, raw_value, description, detected_at)
                       VALUES %s
                       ON CONFLICT (security_id, signal_type, detected_at)
                       DO UPDATE SET contribution = GREATEST(EXCLUDED.contribution, signals.contribution),
                                     confidence = GREATEST(EXCLUDED.confidence, signals.confidence)""",
                    [(s["security_id"], s["signal_type"], s["contribution"],
                      s["confidence"], s["direction"], s["magnitude"],
                      s["raw_value"], s["description"], s["detected_at"])
                     for s in signals],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                )

    log.info("FedWatch signals: %d fired", len(signals))
    return len(signals)


if __name__ == "__main__":
    run_collector(CMEFedWatchCollector)
