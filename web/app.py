"""
Alidade IALD Web Dashboard — security scores, signals, and analyst ratings.

Usage:
    python web/app.py              # run on port 5000
    python web/app.py --port 8080  # custom port

Serves a single-page dashboard with:
  - All securities ranked by IALD score
  - Drill-down per security with live quote, signals, analyst consensus
  - Color-coded tiers (S/A/B/C/D/E)
  - Tooltips explaining every metric
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, jsonify

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "collectors"))
import config
import db
from signal_config import SIGNAL_CONFIG, SignalTier

app = Flask(__name__, template_folder="templates", static_folder="static")


# ── helpers ──────────────────────────────────────────────────────────

TIER_COLORS = {
    "S": "#22c55e", "A": "#4ade80", "B": "#86efac",
    "C": "#fbbf24", "D": "#9ca3af", "E": "#6b7280",
    "P": "#4b5563", "X": "#374151",
}

VERDICT_COLORS = {
    "VERY HIGH": "#ef4444", "HIGH": "#f59e0b",
    "MEDIUM": "#3b82f6", "LOW": "#6b7280", "VERY LOW": "#374151",
}


def _get_scored_securities():
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.security_id, s.ticker, s.name, s.security_type,
                       i.score, i.verdict, i.active_signals, i.score_date,
                       a.avg_score_30d, a.volatility_30d, a.score_trend,
                       a.min_score_30d, a.max_score_30d
                FROM securities s
                LEFT JOIN LATERAL (
                    SELECT * FROM iald_scores
                    WHERE security_id = s.security_id
                    ORDER BY score_date DESC LIMIT 1
                ) i ON true
                LEFT JOIN score_aggregates a ON a.security_id = s.security_id
                ORDER BY COALESCE(i.score, 0) DESC
            """)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _get_signals(security_id):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=168)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT signal_type, contribution, confidence, direction,
                       magnitude, description, detected_at
                FROM signals
                WHERE security_id = %s AND detected_at > %s
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY contribution DESC
            """, (security_id, cutoff))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _get_consensus(security_id):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM raw_analyst_consensus
                WHERE security_id = %s
                ORDER BY snapshot_date DESC LIMIT 1
            """, (security_id,))
            if cur.description:
                cols = [d[0] for d in cur.description]
                row = cur.fetchone()
                return dict(zip(cols, row)) if row else None
    return None


def _get_recent_ratings(security_id):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rating_date, company, action, from_rating, to_rating
                FROM raw_analyst_ratings
                WHERE security_id = %s
                ORDER BY rating_date DESC LIMIT 10
            """, (security_id,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _get_llm_outlook(security_id):
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT direction, analysis, model, query_seconds, outlook_date
                    FROM raw_llm_outlooks
                    WHERE security_id = %s
                    ORDER BY outlook_date DESC LIMIT 1
                """, (security_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "direction": row[0], "analysis": row[1], "model": row[2],
                        "query_seconds": float(row[3]), "outlook_date": str(row[4]),
                    }
    except Exception:
        pass
    return None


def _enrich_signal(sig):
    """Add tier, weight, color info from SIGNAL_CONFIG."""
    cfg = SIGNAL_CONFIG.get(sig["signal_type"], {})
    tier = cfg.get("tier", SignalTier.E)
    sig["tier"] = tier.value
    sig["tier_color"] = TIER_COLORS.get(tier.value, "#6b7280")
    sig["weight"] = cfg.get("base_weight", 0.0)
    sig["half_life"] = cfg.get("half_life_hours", 0)
    sig["cluster"] = cfg.get("correlation_cluster", "")

    age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - sig["detected_at"]).total_seconds() / 3600
    decay = 2.0 ** (-age_h / sig["half_life"]) if sig["half_life"] > 0 else 1.0
    sig["age_hours"] = round(age_h, 1)
    sig["decay"] = round(decay, 3)
    sig["weighted_contribution"] = round(
        float(sig["contribution"]) * float(sig["confidence"]) * sig["weight"] * decay, 4
    )
    return sig


# ── routes ───────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/securities")
def api_securities():
    securities = _get_scored_securities()
    for s in securities:
        s["score"] = float(s["score"]) if s["score"] else 0.0
        s["verdict_color"] = VERDICT_COLORS.get(s.get("verdict", ""), "#6b7280")
        for k in ("avg_score_30d", "volatility_30d", "min_score_30d", "max_score_30d"):
            s[k] = float(s[k]) if s.get(k) else None
        s["score_date"] = str(s["score_date"]) if s.get("score_date") else None
    return jsonify(securities)


@app.route("/api/security/<int:security_id>")
def api_security_detail(security_id):
    signals = _get_signals(security_id)
    for s in signals:
        s["contribution"] = float(s["contribution"])
        s["confidence"] = float(s["confidence"])
        s["detected_at"] = s["detected_at"].isoformat()
        _enrich_signal(s)

    consensus = _get_consensus(security_id)
    if consensus:
        for k, v in consensus.items():
            if hasattr(v, "__float__"):
                consensus[k] = float(v)
            elif hasattr(v, "isoformat"):
                consensus[k] = v.isoformat()

    ratings = _get_recent_ratings(security_id)
    for r in ratings:
        r["rating_date"] = str(r["rating_date"]) if r.get("rating_date") else None

    llm_outlook = _get_llm_outlook(security_id)

    return jsonify({
        "signals": signals,
        "consensus": consensus,
        "recent_ratings": ratings,
        "llm_outlook": llm_outlook,
        "tier_colors": TIER_COLORS,
    })


# ── main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5000
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])
    app.run(host="0.0.0.0", port=port, debug=True)
