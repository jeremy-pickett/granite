"""
Score Engine — reads the signals table, applies IALD formula, writes to iald_scores.

Pipeline:
  1. For each security, load recent signals from the `signals` table
  2. Apply time decay (half-life from SIGNAL_CONFIG)
  3. Apply tier weights
  4. Apply correlation cluster discounts (50% for 2nd+ in same cluster)
  5. Apply independence multiplier (bonus for diverse clusters)
  6. Normalize to 0.0-1.0 via tanh
  7. Write score + verdict to iald_scores
  8. Refresh score_aggregates

Usage:
    python score_engine.py              # score all securities with signals
    python score_engine.py AAPL MSFT    # score specific tickers
    python score_engine.py --dry-run    # calculate but don't write
"""

import sys
import os
import logging
from datetime import datetime, timedelta, timezone
from math import tanh

sys.path.insert(0, os.path.dirname(__file__))

import config
import db
from signal_config import (
    SIGNAL_CONFIG, ACTIVE_SIGNALS, SIGNAL_WEIGHTS,
    SIGNAL_HALF_LIVES, SIGNAL_CORRELATION_CLUSTERS,
)

logging.basicConfig(format=config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT, level=logging.INFO)
log = logging.getLogger("score_engine")


# ── helpers ───────────────────────────────────────────────────────────

def time_decay(age_hours: float, half_life: float) -> float:
    """Exponential decay: 50% weight after half_life hours."""
    if age_hours <= 0:
        return 1.0
    return 2.0 ** (-age_hours / half_life)


def cluster_for(signal_type: str) -> str | None:
    cfg = SIGNAL_CONFIG.get(signal_type, {})
    return cfg.get("correlation_cluster")


def apply_cluster_discounts(contributions: list[dict]) -> list[dict]:
    """50% discount for 2nd+ signal in same correlation cluster."""
    contributions.sort(key=lambda c: abs(c["weighted"]), reverse=True)
    seen: dict[str, int] = {}
    for c in contributions:
        cl = cluster_for(c["signal_type"])
        if cl:
            n = seen.get(cl, 0)
            if n > 0:
                c["weighted"] *= 0.5
            seen[cl] = n + 1
    return contributions


def independence_multiplier(contributions: list[dict]) -> float:
    """Bonus for signals from diverse clusters."""
    clusters = set()
    for c in contributions:
        cl = cluster_for(c["signal_type"])
        if cl:
            clusters.add(cl)
    n = len(clusters)
    if n >= 4:
        return 1.25
    if n == 3:
        return 1.15
    if n == 2:
        return 1.05
    return 1.0


def score_to_verdict(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.50:
        return "ELEVATED"
    if score >= 0.25:
        return "MODERATE"
    return "LOW"


# ── main scoring logic ────────────────────────────────────────────────

def load_signals(security_id: int, lookback_hours: int = 168):
    """Load recent signals for a security."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=lookback_hours)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT signal_type, contribution, confidence, direction,
                          magnitude, raw_value, description, detected_at
                   FROM signals
                   WHERE security_id = %s
                     AND detected_at > %s
                     AND (expires_at IS NULL OR expires_at > now())
                   ORDER BY detected_at DESC""",
                (security_id, cutoff),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def calculate_score(security_id: int, signals: list[dict]) -> dict:
    """
    Calculate IALD score from a list of signal rows.
    Returns dict with score (0-1), verdict, direction, signal_count, details.
    """
    if not signals:
        return {
            "score": 0.0,
            "verdict": "LOW",
            "direction": "neutral",
            "signal_count": 0,
            "active_signals": 0,
            "details": [],
        }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    contributions = []

    for sig in signals:
        stype = sig["signal_type"]
        cfg = SIGNAL_CONFIG.get(stype)
        if not cfg or not cfg.get("active"):
            continue

        age_hours = (now - sig["detected_at"]).total_seconds() / 3600
        half_life = cfg["half_life_hours"]
        decay = time_decay(age_hours, half_life)

        weight = cfg["base_weight"]
        contribution = float(sig["contribution"])
        confidence = float(sig["confidence"])

        weighted = contribution * confidence * weight * decay

        contributions.append({
            "signal_type": stype,
            "contribution": contribution,
            "confidence": confidence,
            "weight": weight,
            "decay": round(decay, 3),
            "weighted": weighted,
            "direction": sig["direction"],
            "description": sig["description"] or stype,
            "age_hours": round(age_hours, 1),
        })

    if not contributions:
        return {
            "score": 0.0,
            "verdict": "LOW",
            "direction": "neutral",
            "signal_count": 0,
            "active_signals": 0,
            "details": [],
        }

    # Apply cluster discounts
    contributions = apply_cluster_discounts(contributions)

    # Independence bonus
    ind_mult = independence_multiplier(contributions)

    # Sum weighted contributions (absolute — IALD measures signal intensity, not direction)
    total = sum(abs(c["weighted"]) for c in contributions)
    total *= ind_mult

    # Normalize to 0-1 via tanh. Saturation ~3.0 maps to ~0.99.
    score = tanh(total / 2.0)
    score = round(min(max(score, 0.0), 1.0), 4)

    # Direction from the net signed sum
    net = sum(c["weighted"] for c in contributions)
    bullish = sum(1 for c in contributions if c["weighted"] > 0)
    bearish = sum(1 for c in contributions if c["weighted"] < 0)
    if net > 0.1 and bullish > bearish:
        direction = "bullish"
    elif net < -0.1 and bearish > bullish:
        direction = "bearish"
    else:
        direction = "neutral"

    verdict = score_to_verdict(score)

    return {
        "score": score,
        "verdict": verdict,
        "direction": direction,
        "signal_count": len(contributions),
        "active_signals": len(contributions),
        "details": sorted(contributions, key=lambda c: abs(c["weighted"]), reverse=True),
    }


# ── persistence ───────────────────────────────────────────────────────

def write_score(security_id: int, result: dict):
    """Upsert into iald_scores for today."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO iald_scores
                       (security_id, score_date, score, verdict, confidence, active_signals)
                   VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
                   ON CONFLICT (security_id, score_date)
                   DO UPDATE SET score = EXCLUDED.score,
                                 verdict = EXCLUDED.verdict,
                                 confidence = EXCLUDED.confidence,
                                 active_signals = EXCLUDED.active_signals""",
                (security_id, result["score"], result["verdict"],
                 round(result["score"], 2), result["active_signals"]),
            )


def refresh_aggregates(security_id: int):
    """Refresh score_aggregates for a security from iald_scores."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO score_aggregates
                       (security_id, avg_score_30d, min_score_30d, max_score_30d,
                        volatility_30d, score_trend, data_points, last_score, last_verdict)
                   SELECT
                       s.security_id,
                       avg(s.score),
                       min(s.score),
                       max(s.score),
                       coalesce(stddev(s.score), 0),
                       CASE
                           WHEN count(*) < 3 THEN 'stable'
                           WHEN (SELECT score FROM iald_scores
                                 WHERE security_id = s.security_id
                                 ORDER BY score_date DESC LIMIT 1)
                                >
                                avg(s.score) + 0.05 THEN 'improving'
                           WHEN (SELECT score FROM iald_scores
                                 WHERE security_id = s.security_id
                                 ORDER BY score_date DESC LIMIT 1)
                                <
                                avg(s.score) - 0.05 THEN 'declining'
                           ELSE 'stable'
                       END,
                       count(*),
                       (SELECT score FROM iald_scores
                        WHERE security_id = s.security_id
                        ORDER BY score_date DESC LIMIT 1),
                       (SELECT verdict FROM iald_scores
                        WHERE security_id = s.security_id
                        ORDER BY score_date DESC LIMIT 1)
                   FROM iald_scores s
                   WHERE s.security_id = %s
                     AND s.score_date > CURRENT_DATE - 30
                   GROUP BY s.security_id
                   ON CONFLICT (security_id)
                   DO UPDATE SET
                       avg_score_30d = EXCLUDED.avg_score_30d,
                       min_score_30d = EXCLUDED.min_score_30d,
                       max_score_30d = EXCLUDED.max_score_30d,
                       volatility_30d = EXCLUDED.volatility_30d,
                       score_trend = EXCLUDED.score_trend,
                       data_points = EXCLUDED.data_points,
                       last_score = EXCLUDED.last_score,
                       last_verdict = EXCLUDED.last_verdict""",
                (security_id,),
            )


# ── runner ────────────────────────────────────────────────────────────

def score_security(security_id: int, ticker: str, dry_run: bool = False) -> dict:
    """Score a single security end-to-end."""
    signals = load_signals(security_id)
    result = calculate_score(security_id, signals)
    if not dry_run and result["signal_count"] > 0:
        write_score(security_id, result)
        refresh_aggregates(security_id)
    return result


def score_all(dry_run: bool = False):
    """Score every security that has at least one signal."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT s.security_id, sec.ticker
                   FROM signals s
                   JOIN securities sec ON sec.security_id = s.security_id
                   WHERE s.detected_at > now() - interval '168 hours'
                     AND (s.expires_at IS NULL OR s.expires_at > now())"""
            )
            targets = cur.fetchall()

    log.info("Scoring %d securities with active signals...", len(targets))
    scored = 0
    for security_id, ticker in targets:
        result = score_security(security_id, ticker, dry_run=dry_run)
        if result["signal_count"] > 0:
            scored += 1
            if result["score"] >= 0.25:
                log.info("  %s: %.4f (%s) — %d signals",
                         ticker, result["score"], result["verdict"], result["signal_count"])

    log.info("Scored %d securities (%d with signals)", scored, len(targets))
    return scored


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    tickers = [a.upper() for a in args if not a.startswith("--")]

    if tickers:
        securities = db.get_securities()
        sec_map = {s["ticker"]: s["security_id"] for s in securities}
        for t in tickers:
            sid = sec_map.get(t)
            if not sid:
                log.warning("Unknown ticker: %s", t)
                continue
            result = score_security(sid, t, dry_run=dry_run)
            log.info("%s: %.4f (%s) — %d signals", t, result["score"], result["verdict"], result["signal_count"])
            for d in result["details"][:5]:
                log.info("  %.3f  %s  [decay=%.2f] %s", d["weighted"], d["signal_type"], d["decay"], d["description"])
    else:
        score_all(dry_run=dry_run)


if __name__ == "__main__":
    main()
