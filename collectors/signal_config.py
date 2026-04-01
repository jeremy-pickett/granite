"""
SIGNAL_CONFIG — single source of truth for all IALD signal definitions.

Rules:
  - Every entry here MUST have a collector or derived-signal job that feeds it.
  - Do NOT add aspirational signals. If nothing writes to the signals table
    for a signal_type, it does not belong here.
  - When adding a signal: add the config here, then add the extractor that
    writes it. When removing: delete both.

Current count: 33 active signals (update this when you add/remove)
"""

from enum import Enum
from typing import Dict, Any


class SignalTier(Enum):
    S = "S"   # Exceptional:   1.60-1.70x, >70% accuracy
    A = "A"   # Very Strong:   1.40-1.55x, >65% accuracy
    B = "B"   # Strong:        1.20-1.35x, >60% accuracy
    C = "C"   # Moderate:      1.00-1.15x, >55% accuracy
    D = "D"   # Supporting:    0.85-0.95x, >52% accuracy
    E = "E"   # Context:       0.70-0.80x, >50% accuracy
    P = "P"   # Probationary:  0.50-0.65x, unvalidated
    X = "X"   # Experimental:  0.30-0.45x, research-only


# ── Signal definitions ────────────────────────────────────────────────
# Only signals with live data pipelines belong here.

SIGNAL_CONFIG: Dict[str, Dict[str, Any]] = {

    # -- Derived from raw_market_data (market_signals.py) ----------------

    "volume_spike": {
        "tier": SignalTier.D,
        "base_weight": 0.90,
        "half_life_hours": 48,
        "correlation_cluster": "trading",
        "description": "Volume >2x 20-day average",
        "source": "market_signals.py",
        "active": True,
    },

    "price_gap": {
        "tier": SignalTier.D,
        "base_weight": 0.85,
        "half_life_hours": 48,
        "correlation_cluster": "trading",
        "description": "Open >2% away from prior close",
        "source": "market_signals.py",
        "active": True,
    },

    "unusual_range": {
        "tier": SignalTier.E,
        "base_weight": 0.75,
        "half_life_hours": 48,
        "correlation_cluster": "trading",
        "description": "Daily range >2x 20-day average range",
        "source": "market_signals.py",
        "active": True,
    },

    # -- Baseline signals (fire for every security with data) ---------------

    "relative_volume": {
        "tier": SignalTier.E,
        "base_weight": 0.70,
        "half_life_hours": 24,
        "correlation_cluster": "baseline",
        "description": "Today's volume vs 20-day average (continuous)",
        "source": "market_signals.py",
        "active": True,
    },

    "price_momentum": {
        "tier": SignalTier.E,
        "base_weight": 0.70,
        "half_life_hours": 48,
        "correlation_cluster": "baseline",
        "description": "5-day return magnitude and direction",
        "source": "market_signals.py",
        "active": True,
    },

    "volatility_compression": {
        "tier": SignalTier.E,
        "base_weight": 0.70,
        "half_life_hours": 72,
        "correlation_cluster": "baseline",
        "description": "Current range vs historical range (squeeze detection)",
        "source": "market_signals.py",
        "active": True,
    },

    "closing_strength": {
        "tier": SignalTier.E,
        "base_weight": 0.65,
        "half_life_hours": 24,
        "correlation_cluster": "baseline",
        "description": "Where price closed within day's range",
        "source": "market_signals.py",
        "active": True,
    },

    # -- Derived from raw_insider_trades (insider_signals.py) ---------------

    "insider_sale_cluster": {
        "tier": SignalTier.A,
        "base_weight": 1.45,
        "half_life_hours": 168,
        "correlation_cluster": "insider",
        "description": "Multiple insiders selling within 30 days",
        "source": "insider_signals.py",
        "active": True,
    },

    "insider_large_sale": {
        "tier": SignalTier.C,
        "base_weight": 1.10,
        "half_life_hours": 168,
        "correlation_cluster": "insider",
        "description": "Single insider sale >$500K or >50K shares",
        "source": "insider_signals.py",
        "active": True,
    },

    "insider_purchase_cluster": {
        "tier": SignalTier.A,
        "base_weight": 1.40,
        "half_life_hours": 168,
        "correlation_cluster": "insider",
        "description": "Multiple insiders buying within 30 days (bullish)",
        "source": "insider_signals.py",
        "active": True,
    },

    # -- Derived from raw_congressional_trades (congressional_signals.py) ---

    "congressional_trade": {
        "tier": SignalTier.A,
        "base_weight": 1.45,
        "half_life_hours": 168,
        "correlation_cluster": "governance",
        "description": "Congress member traded this security",
        "source": "congressional_signals.py",
        "active": True,
    },

    # -- Derived from raw_analyst_actions (analyst_signals.py) --------------

    "analyst_consensus_shift": {
        "tier": SignalTier.D,
        "base_weight": 0.90,
        "half_life_hours": 120,
        "correlation_cluster": "analyst",
        "description": "Month-over-month shift in analyst consensus",
        "source": "analyst_signals.py",
        "active": True,
    },

    # -- Derived from raw_news_sentiment (news_signals.py) ------------------

    "news_sentiment_extreme": {
        "tier": SignalTier.E,
        "base_weight": 0.75,
        "half_life_hours": 48,
        "correlation_cluster": "alternative",
        "description": "Strong negative or positive news sentiment cluster",
        "source": "news_signals.py",
        "active": True,
    },

    "news_volume_spike": {
        "tier": SignalTier.D,
        "base_weight": 0.85,
        "half_life_hours": 48,
        "correlation_cluster": "alternative",
        "description": "Unusually high news volume for this security",
        "source": "news_signals.py",
        "active": True,
    },

    # -- Derived from raw_concentration_disclosures (concentration_signals.py) -

    "concentration_shift": {
        "tier": SignalTier.B,
        "base_weight": 1.25,
        "half_life_hours": 336,
        "correlation_cluster": "governance",
        "description": "Unusual 13D/13G filing frequency or new activist investor",
        "source": "concentration_signals.py",
        "active": True,
    },

    # -- Derived from raw_material_weaknesses (material_weakness_signals.py) ---

    "material_weakness": {
        "tier": SignalTier.A,
        "base_weight": 1.50,
        "half_life_hours": 720,
        "correlation_cluster": "governance",
        "description": "SOX material weakness disclosure in 10-K/10-Q filing",
        "source": "material_weakness_signals.py",
        "active": True,
    },

    # -- Derived from raw_ftd_data (ftd_signals.py) ----------------------------

    "ftd_spike": {
        "tier": SignalTier.B,
        "base_weight": 1.30,
        "half_life_hours": 168,
        "correlation_cluster": "trading",
        "description": "Persistent or extreme fail-to-deliver volume",
        "source": "ftd_signals.py",
        "active": True,
    },

    # -- Derived from raw_auditor_changes (auditor_signals.py) -----------------

    "auditor_change": {
        "tier": SignalTier.A,
        "base_weight": 1.45,
        "half_life_hours": 720,
        "correlation_cluster": "governance",
        "description": "Auditor appointment, resignation, or disagreement",
        "source": "auditor_signals.py",
        "active": True,
    },

    # -- Derived from raw_csuite_departures (csuite_signals.py) ----------------

    "csuite_exodus": {
        "tier": SignalTier.A,
        "base_weight": 1.40,
        "half_life_hours": 336,
        "correlation_cluster": "governance",
        "description": "Abnormal rate of executive departures",
        "source": "csuite_signals.py",
        "active": True,
    },

    # -- Derived from raw_13f_holdings (sec_13f_signals.py) --------------------

    "institutional_filing_spike": {
        "tier": SignalTier.D,
        "base_weight": 0.90,
        "half_life_hours": 168,
        "correlation_cluster": "governance",
        "description": "Unusual 13F filing frequency or amendments",
        "source": "sec_13f_signals.py",
        "active": True,
    },

    # -- Derived from raw_options_flow (options_signals.py) --------------------

    "options_unusual_activity": {
        "tier": SignalTier.A,
        "base_weight": 1.45,
        "half_life_hours": 72,
        "correlation_cluster": "trading",
        "description": "Volume concentration, OTM loading, or extreme put/call skew",
        "source": "options_signals.py",
        "active": True,
    },

    # -- Derived from raw_prediction_markets (prediction_market_signals.py) ----

    "prediction_market_heat": {
        "tier": SignalTier.C,
        "base_weight": 1.10,
        "half_life_hours": 168,
        "correlation_cluster": "alternative",
        "description": "High volume or extreme odds on prediction markets",
        "source": "prediction_market_signals.py",
        "active": True,
    },

    # -- Derived from blockchain collectors (blockchain_signals.py) ------------

    "blockchain_anomaly": {
        "tier": SignalTier.B,
        "base_weight": 1.20,
        "half_life_hours": 48,
        "correlation_cluster": "blockchain",
        "description": "Whale movements, exchange flows, or on-chain congestion",
        "source": "blockchain_signals.py",
        "active": True,
    },

    # -- Derived from raw_short_interest (short_interest_signals.py) -----------

    "short_interest_spike": {
        "tier": SignalTier.B,
        "base_weight": 1.25,
        "half_life_hours": 168,
        "correlation_cluster": "trading",
        "description": "High short interest as % of float or significant MoM increase",
        "source": "short_interest_signals.py",
        "active": True,
    },

    # -- Derived from raw_sector_correlations (sector_correlation_signals.py) --

    "sector_divergence": {
        "tier": SignalTier.D,
        "base_weight": 0.90,
        "half_life_hours": 72,
        "correlation_cluster": "trading",
        "description": "Stock decorrelating from sector ETF or large residual return",
        "source": "sector_correlation_signals.py",
        "active": True,
    },

    # -- Compound signals (compound_signals.py) --------------------------------
    # These fire when multiple independent signals co-occur within a time window.

    "governance_crisis": {
        "tier": SignalTier.S,
        "base_weight": 1.70,
        "half_life_hours": 720,
        "correlation_cluster": "governance",
        "description": "Auditor change + C-suite exodus or material weakness within 180 days",
        "source": "compound_signals.py",
        "active": True,
    },

    "short_squeeze_setup": {
        "tier": SignalTier.A,
        "base_weight": 1.50,
        "half_life_hours": 168,
        "correlation_cluster": "trading",
        "description": "Short interest spike + FTD spike + unusual options activity within 14 days",
        "source": "compound_signals.py",
        "active": True,
    },

    "insider_capitulation": {
        "tier": SignalTier.S,
        "base_weight": 1.65,
        "half_life_hours": 168,
        "correlation_cluster": "insider",
        "description": "Insider sale cluster + C-suite exodus or extreme bearish sentiment within 30 days",
        "source": "compound_signals.py",
        "active": True,
    },

    # -- Derived from raw_pe_activity + raw_debt_metrics (pe_signals.py) ------

    "going_private_detected": {
        "tier": SignalTier.B,
        "base_weight": 1.25,
        "half_life_hours": 336,
        "correlation_cluster": "governance",
        "description": "Going-private transaction, tender offer, or merger agreement filing",
        "source": "pe_signals.py",
        "active": True,
    },

    "debt_loading_spike": {
        "tier": SignalTier.A,
        "base_weight": 1.50,
        "half_life_hours": 336,
        "correlation_cluster": "governance",
        "description": "Debt-to-equity >2x increase in 4 quarters or interest >30% of revenue",
        "source": "pe_signals.py",
        "active": True,
    },

    "pe_distress_pattern": {
        "tier": SignalTier.S,
        "base_weight": 1.65,
        "half_life_hours": 720,
        "correlation_cluster": "governance",
        "description": "PE activity + governance distress co-occurrence (strip-and-dump death spiral)",
        "source": "pe_signals.py",
        "active": True,
    },

    # -- Derived from raw_crypto_governance + raw_crypto_death_spiral --------

    "crypto_rug_pull_risk": {
        "tier": SignalTier.S,
        "base_weight": 1.60,
        "half_life_hours": 168,
        "correlation_cluster": "blockchain",
        "description": "Concentrated ownership + abandoned development + collapsing volume",
        "source": "crypto_governance_signals.py",
        "active": True,
    },

    "crypto_death_spiral": {
        "tier": SignalTier.A,
        "base_weight": 1.50,
        "half_life_hours": 72,
        "correlation_cluster": "blockchain",
        "description": "Multi-phase crypto collapse: price + volume + social + dev activity declining",
        "source": "crypto_governance_signals.py",
        "active": True,
    },
}


# ── Derived lookups (auto-built from SIGNAL_CONFIG) ──────────────────

def _active_signals():
    return {k: v for k, v in SIGNAL_CONFIG.items() if v.get("active", False)}

def _build_weights():
    return {k: v["base_weight"] for k, v in SIGNAL_CONFIG.items()}

def _build_half_lives():
    return {k: v["half_life_hours"] for k, v in SIGNAL_CONFIG.items()}

def _build_clusters():
    clusters: Dict[str, set] = {}
    for sig, cfg in SIGNAL_CONFIG.items():
        c = cfg.get("correlation_cluster")
        if c:
            clusters.setdefault(c, set()).add(sig)
    return clusters

ACTIVE_SIGNALS = _active_signals()
SIGNAL_WEIGHTS = _build_weights()
SIGNAL_HALF_LIVES = _build_half_lives()
SIGNAL_CORRELATION_CLUSTERS = _build_clusters()

# Sanity check: the count in the docstring must match
_DECLARED_COUNT = 33  # ← UPDATE THIS when adding/removing signals
_actual = len(ACTIVE_SIGNALS)
assert _actual == _DECLARED_COUNT, (
    f"signal_config.py docstring says {_DECLARED_COUNT} active signals "
    f"but SIGNAL_CONFIG has {_actual}. Update _DECLARED_COUNT."
)
