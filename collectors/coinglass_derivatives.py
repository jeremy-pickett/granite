"""
Coinglass Derivatives Collector — Funding rates across 21 exchanges.

Collector ID: 38 (Coinglass Derivatives)
Table:        raw_coinglass_funding

Tracks perpetual futures funding rates for 1000+ crypto symbols.
Extreme funding rates signal overcrowded positioning — a leading
indicator of liquidation cascades and forced reversals.

Data source:
  - Coinglass Open API v2 /funding endpoint (requires API key)
  - Single call returns all symbols across all exchanges
"""

import sys
import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from statistics import median

sys.path.insert(0, os.path.dirname(__file__))

from base import BaseCollector, run_collector
from psycopg2.extras import execute_values, Json
import config
import db

log = logging.getLogger("coinglass_derivatives")

API_BASE = "https://open-api.coinglass.com/public/v2"


class CoinglassDerivativesCollector(BaseCollector):

    COLLECTOR_ID = 38
    COLLECTOR_NAME = "Coinglass Derivatives"
    COLLECTOR_TYPE = "blockchain"

    def setup(self):
        if not config.COINGLASS_API_KEY:
            self.log.warning("COINGLASS_API_KEY not set — collector will fail")
        self._ensure_table()
        self._load_security_map()

    def _ensure_table(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_coinglass_funding (
                        funding_id SERIAL PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        security_id INT REFERENCES securities(security_id),
                        snapshot_time TIMESTAMP NOT NULL,
                        exchange_count INT,
                        mean_funding_rate NUMERIC(12,8),
                        median_funding_rate NUMERIC(12,8),
                        min_funding_rate NUMERIC(12,8),
                        max_funding_rate NUMERIC(12,8),
                        funding_dispersion NUMERIC(12,8),
                        positive_exchanges INT,
                        negative_exchanges INT,
                        consensus_direction VARCHAR(10),
                        index_price NUMERIC(16,4),
                        mark_price NUMERIC(16,4),
                        top_exchange_name VARCHAR(30),
                        top_exchange_rate NUMERIC(12,8),
                        raw_rates JSONB,
                        collected_at TIMESTAMP DEFAULT now(),
                        UNIQUE(symbol, snapshot_time)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rcf_symbol
                        ON raw_coinglass_funding (symbol, snapshot_time DESC);
                    CREATE INDEX IF NOT EXISTS idx_rcf_security
                        ON raw_coinglass_funding (security_id, snapshot_time DESC);
                """)

    def _load_security_map(self):
        """Build mapping from Coinglass symbol (e.g. 'BTC') to security_id."""
        self._sym_to_secid = {}
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT security_id, ticker FROM securities WHERE security_type = 'crypto'"
                )
                for sec_id, ticker in cur.fetchall():
                    # ticker is like "BTC-USD" → strip suffix
                    base = ticker.split("-")[0].upper()
                    self._sym_to_secid[base] = sec_id
        self.log.info("Mapped %d crypto securities for symbol lookup", len(self._sym_to_secid))

    def fetch(self, securities):
        """Single API call to get funding rates for all symbols."""
        self.log.info("Fetching funding rates from Coinglass...")
        headers = {
            "coinglassSecret": config.COINGLASS_API_KEY,
            "accept": "application/json",
        }
        try:
            resp = requests.get(
                f"{API_BASE}/funding",
                headers=headers,
                timeout=config.HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != "0" and body.get("success") is not True:
                self.log.error("Coinglass API error: %s", body.get("msg", body))
                self.stats["errors"] += 1
                return []
            data = body.get("data", [])
            self.stats["fetched"] = len(data)
            self.log.info("Received funding data for %d symbols", len(data))
            return data
        except requests.RequestException as e:
            self.log.error("Coinglass API request failed: %s", e)
            self.stats["errors"] += 1
            return []

    def transform(self, raw_data, securities):
        """Compute per-symbol aggregate funding metrics."""
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
        rows = []

        for item in raw_data:
            symbol = item.get("symbol", "")
            u_margin_list = item.get("uMarginList") or []

            # Filter to active exchanges only
            active_rates = []
            rate_details = []
            for entry in u_margin_list:
                if entry.get("status") != 1:
                    continue
                rate = entry.get("rate")
                if rate is None:
                    continue
                exchange = entry.get("exchangeName", "unknown")
                active_rates.append(rate)
                rate_details.append({"exchange": exchange, "rate": rate})

            if not active_rates:
                continue

            # Compute aggregates
            mean_rate = sum(active_rates) / len(active_rates)
            med_rate = median(active_rates)
            min_rate = min(active_rates)
            max_rate = max(active_rates)
            dispersion = max_rate - min_rate

            pos_count = sum(1 for r in active_rates if r > 0)
            neg_count = sum(1 for r in active_rates if r < 0)

            if pos_count > neg_count:
                consensus = "bullish"
            elif neg_count > pos_count:
                consensus = "bearish"
            else:
                consensus = "neutral"

            # Top exchange = largest absolute rate
            top_entry = max(rate_details, key=lambda x: abs(x["rate"]))

            index_price = item.get("uIndexPrice")
            mark_price = item.get("uPrice")

            rows.append({
                "symbol": symbol,
                "security_id": self._sym_to_secid.get(symbol.upper()),
                "snapshot_time": now,
                "exchange_count": len(active_rates),
                "mean_funding_rate": mean_rate,
                "median_funding_rate": med_rate,
                "min_funding_rate": min_rate,
                "max_funding_rate": max_rate,
                "funding_dispersion": dispersion,
                "positive_exchanges": pos_count,
                "negative_exchanges": neg_count,
                "consensus_direction": consensus,
                "index_price": index_price,
                "mark_price": mark_price,
                "top_exchange_name": top_entry["exchange"],
                "top_exchange_rate": top_entry["rate"],
                "raw_rates": rate_details,
            })

        self.log.info("Transformed %d symbols with active funding data", len(rows))
        return rows

    def store(self, rows):
        if not rows:
            return
        self.log.info("Writing %d funding rate records...", len(rows))
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO raw_coinglass_funding
                           (symbol, security_id, snapshot_time, exchange_count,
                            mean_funding_rate, median_funding_rate,
                            min_funding_rate, max_funding_rate,
                            funding_dispersion, positive_exchanges, negative_exchanges,
                            consensus_direction, index_price, mark_price,
                            top_exchange_name, top_exchange_rate, raw_rates)
                       VALUES %s
                       ON CONFLICT (symbol, snapshot_time)
                       DO UPDATE SET
                           mean_funding_rate = EXCLUDED.mean_funding_rate,
                           median_funding_rate = EXCLUDED.median_funding_rate,
                           funding_dispersion = EXCLUDED.funding_dispersion,
                           exchange_count = EXCLUDED.exchange_count,
                           collected_at = now()""",
                    [(r["symbol"], r["security_id"], r["snapshot_time"],
                      r["exchange_count"], r["mean_funding_rate"],
                      r["median_funding_rate"], r["min_funding_rate"],
                      r["max_funding_rate"], r["funding_dispersion"],
                      r["positive_exchanges"], r["negative_exchanges"],
                      r["consensus_direction"], r["index_price"], r["mark_price"],
                      r["top_exchange_name"], r["top_exchange_rate"],
                      Json(r["raw_rates"]))
                     for r in rows],
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    page_size=config.DB_BATCH_SIZE,
                )
        super().store(rows)

    def teardown(self):
        self.log.info("Coinglass: %d symbols fetched, %d stored, %d errors",
                      self.stats["fetched"], self.stats["stored"], self.stats["errors"])


# ─── Signal extraction ────────────────────────────────────────────────

def run_signals():
    """
    Derive blockchain_anomaly signals from raw_coinglass_funding data.

    Triggers:
      1. Extreme funding (>1% or <-1%) — overcrowded positioning, contrarian signal
      2. Funding divergence (>2% spread) — exchange disagreement
      3. Consensus flip — sentiment reversal from yesterday
    """
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    signals = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Get latest snapshot for each symbol (today)
            cur.execute("""
                SELECT DISTINCT ON (symbol)
                    symbol, security_id, mean_funding_rate, funding_dispersion,
                    consensus_direction, positive_exchanges, negative_exchanges,
                    top_exchange_name, top_exchange_rate
                FROM raw_coinglass_funding
                WHERE snapshot_time >= %s AND security_id IS NOT NULL
                ORDER BY symbol, snapshot_time DESC
            """, (now - timedelta(days=1),))
            today_rows = {r[0]: r for r in cur.fetchall()}

            # Get yesterday's consensus for flip detection
            cur.execute("""
                SELECT DISTINCT ON (symbol)
                    symbol, consensus_direction
                FROM raw_coinglass_funding
                WHERE snapshot_time >= %s AND snapshot_time < %s
                      AND security_id IS NOT NULL
                ORDER BY symbol, snapshot_time DESC
            """, (now - timedelta(days=2), now - timedelta(days=1)))
            yesterday_consensus = {r[0]: r[1] for r in cur.fetchall()}

    for symbol, row in today_rows.items():
        (_, security_id, mean_rate, dispersion, consensus,
         pos_ex, neg_ex, top_ex_name, top_ex_rate) = row

        if security_id is None:
            continue

        # Signal 1: Extreme funding rate (cap at 10% to filter data errors)
        if mean_rate is not None and abs(float(mean_rate)) > 0.01 and abs(float(mean_rate)) < 0.10:
            mean_f = float(mean_rate)
            contribution = min(abs(mean_f) / 0.02, 1.0)
            # Contrarian: positive funding = longs overcrowded = bearish signal
            direction = "bearish" if mean_f > 0 else "bullish"
            signals.append({
                "security_id": security_id,
                "signal_type": "blockchain_anomaly",
                "contribution": round(contribution, 4),
                "confidence": 0.80,
                "direction": direction,
                "magnitude": abs(mean_f),
                "raw_value": mean_f,
                "description": (
                    f"Extreme funding rate {mean_f:+.4f} across exchanges "
                    f"({symbol}) — {direction} contrarian signal"
                ),
                "detected_at": now,
            })

        # Signal 2: Funding divergence
        if dispersion is not None and float(dispersion) > 0.02:
            disp_f = float(dispersion)
            contribution = min(disp_f / 0.05, 0.5)
            # Direction based on which side has more extreme outlier
            if top_ex_rate is not None:
                direction = "bearish" if float(top_ex_rate) > 0 else "bullish"
            else:
                direction = "neutral"
            signals.append({
                "security_id": security_id,
                "signal_type": "blockchain_anomaly",
                "contribution": round(contribution, 4),
                "confidence": 0.65,
                "direction": direction,
                "magnitude": disp_f,
                "raw_value": disp_f,
                "description": (
                    f"Funding rate divergence {disp_f:.4f} between exchanges "
                    f"({symbol}) — outlier at {top_ex_name}"
                ),
                "detected_at": now,
            })

        # Signal 3: Consensus flip
        prev_consensus = yesterday_consensus.get(symbol)
        if prev_consensus and consensus and prev_consensus != consensus:
            # Only fire on bullish↔bearish flips, not neutral transitions
            if prev_consensus in ("bullish", "bearish") and consensus in ("bullish", "bearish"):
                signals.append({
                    "security_id": security_id,
                    "signal_type": "blockchain_anomaly",
                    "contribution": 0.70,
                    "confidence": 0.75,
                    "direction": consensus,
                    "magnitude": 1.0,
                    "raw_value": None,
                    "description": (
                        f"Funding consensus flipped {prev_consensus}→{consensus} "
                        f"({symbol}) — sentiment reversal"
                    ),
                    "detected_at": now,
                })

    # Deduplicate: keep strongest signal per (security_id, signal_type, detected_at)
    best = {}
    for s in signals:
        key = (s["security_id"], s["signal_type"], s["detected_at"])
        if key not in best or s["contribution"] > best[key]["contribution"]:
            best[key] = s
    signals = list(best.values())

    # Write signals
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

    log.info("Coinglass signals: %d signals fired", len(signals))
    return len(signals)


if __name__ == "__main__":
    run_collector(CoinglassDerivativesCollector)
