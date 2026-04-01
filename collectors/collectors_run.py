"""
Collector runner — execute one, some, or all collectors + scoring pipeline.

Usage:
    python collectors_run.py                   # run all collectors → signals → scores
    python collectors_run.py market_data       # run one collector by name
    python collectors_run.py 3                 # run one collector by ID
    python collectors_run.py --signals         # extract signals only (skip collection)
    python collectors_run.py --score           # run score engine only
    python collectors_run.py --list            # show registered collectors
"""

import sys
import os
import time
import importlib
import logging

sys.path.insert(0, os.path.dirname(__file__))

import config
import db

logging.basicConfig(
    format=config.LOG_FORMAT,
    datefmt=config.LOG_DATE_FORMAT,
    level=logging.INFO,
)
log = logging.getLogger("runner")

# Map of module_name → collector class name
# Add an entry here for each new collector
REGISTRY = {
    "market_data": "MarketDataCollector",
    "insider_trades": "InsiderTradesCollector",
    "analyst_actions": "AnalystActionsCollector",
    "congressional_trades": "CongressionalTradesCollector",
    "news_sentiment": "NewsSentimentCollector",
    "auditor_changes": "AuditorChangeCollector",
    "csuite_departures": "CSuiteDepartureCollector",
    "concentration_disclosure": "ConcentrationDisclosureCollector",
    "material_weakness": "MaterialWeaknessCollector",
    "late_filings": "LateFilingCollector",
    "financial_restatements": "FinancialRestatementCollector",
    "going_concern": "GoingConcernCollector",
    "sec_13f": "SEC13FCollector",
    "ftd_patterns": "FTDPatternCollector",
    "options_flow": "OptionsFlowCollector",
    "prediction_markets": "PredictionMarketCollector",
    "crypto_whale": "CryptoWhaleCollector",
    "exchange_flow": "ExchangeFlowCollector",
    "onchain_activity": "OnChainActivityCollector",
    "short_interest": "ShortInterestCollector",
    "sector_correlation": "SectorCorrelationCollector",
    "lunarcrush_social": "LunarCrushSocialCollector",
    "santiment_onchain": "SantimentOnchainCollector",
    "tiingo_data": "TiingoDataCollector",
    "nasdaq_data": "NasdaqDataLinkCollector",
    "metaculus_markets": "MetaculusMarketCollector",
    "cryptopanic_news": "CryptoPanicNewsCollector",
    "newsapi_headlines": "NewsAPIHeadlinesCollector",
    "pe_activity": "PEActivityCollector",
    "debt_monitor": "DebtMonitorCollector",
    "crypto_governance": "CryptoGovernanceCollector",
    "crypto_death_spiral": "CryptoDeathSpiralCollector",
    "market_snapshot": "MarketSnapshotCollector",
    "analyst_ratings": "AnalystRatingsCollector",
    "llm_outlook": "LLMOutlookCollector",
    "coinglass_derivatives": "CoinglassDerivativesCollector",
    "fear_greed": "FearGreedCollector",
    "defillama_tvl": "DefiLlamaTVLCollector",
    "cme_fedwatch": "CMEFedWatchCollector",
    "executive_profiles": "ExecutiveProfilesCollector",
    "corporate_records": "CorporateRecordsCollector",
    "executive_background": "ExecutiveBackgroundCollector",
}


def load_collector(module_name):
    """Import a collector module and return its class."""
    mod = importlib.import_module(module_name)
    cls_name = REGISTRY[module_name]
    return getattr(mod, cls_name)


def list_collectors():
    """Print registered collectors and their DB status."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT collector_id, collector_name, collector_type, is_active, "
                "last_success_at, records_total, coverage_pct "
                "FROM collectors ORDER BY collector_id"
            )
            rows = cur.fetchall()

    print(f"\n{'ID':>4}  {'Name':<30} {'Type':<14} {'Active':<8} {'Last Run':<20} {'Records':>8} {'Cov%':>6}")
    print("-" * 100)
    for r in rows:
        cid, name, ctype, active, last, records, cov = r
        last_str = last.strftime("%Y-%m-%d %H:%M") if last else "never"
        impl = "  *" if any(cid == load_collector(m).COLLECTOR_ID for m in REGISTRY) else ""
        print(f"{cid:>4}  {name:<30} {ctype:<14} {'yes' if active else 'no':<8} {last_str:<20} {records or 0:>8} {cov or 0:>6}{impl}")

    print(f"\n  * = has implementation in collectors/")
    print(f"  {len(REGISTRY)} of {len(rows)} collectors implemented\n")


def run_signals():
    """Extract derived signals from all raw data tables."""
    import market_signals
    market_signals.run()

    import congressional_signals
    congressional_signals.run()

    import insider_signals
    insider_signals.run()

    import analyst_signals
    analyst_signals.run()

    import news_signals
    news_signals.run()

    import concentration_signals
    concentration_signals.run()

    import material_weakness_signals
    material_weakness_signals.run()

    import ftd_signals
    ftd_signals.run()

    import auditor_signals
    auditor_signals.run()

    import csuite_signals
    csuite_signals.run()

    import sec_13f_signals
    sec_13f_signals.run()

    import options_signals
    options_signals.run()

    import prediction_market_signals
    prediction_market_signals.run()

    import blockchain_signals
    blockchain_signals.run()

    import lunarcrush_social
    lunarcrush_social.run_signals()

    import santiment_onchain
    santiment_onchain.run_signals()

    import coinglass_derivatives
    coinglass_derivatives.run_signals()

    import fear_greed
    fear_greed.run_signals()

    import defillama_tvl
    defillama_tvl.run_signals()

    import cme_fedwatch
    cme_fedwatch.run_signals()

    import crypto_governance_signals
    crypto_governance_signals.run()

    import short_interest_signals
    short_interest_signals.run()

    import sector_correlation_signals
    sector_correlation_signals.run()

    import pe_signals
    pe_signals.run()

    # Compound signals run LAST — they read from the signals table
    import compound_signals
    compound_signals.run()


def run_scoring():
    """Run score engine across all securities with signals."""
    import score_engine
    score_engine.score_all()


def run_one(module_name):
    """Run a single collector by module name."""
    cls = load_collector(module_name)
    collector = cls()
    collector.run()
    return collector.stats


def run_all():
    """Run all registered collectors sequentially."""
    results = {}
    for module_name in REGISTRY:
        log.info("── Running %s ──", module_name)
        try:
            stats = run_one(module_name)
            results[module_name] = {"status": "ok", **stats}
        except Exception as e:
            log.error("── %s FAILED: %s ──", module_name, e)
            results[module_name] = {"status": "error", "error": str(e)}
    return results


def find_module_by_id(collector_id):
    """Find module name by collector ID."""
    for module_name in REGISTRY:
        cls = load_collector(module_name)
        if cls.COLLECTOR_ID == collector_id:
            return module_name
    return None


def main():
    args = sys.argv[1:]

    if not args:
        # Full pipeline: collect → extract signals → score
        log.info("=== Full pipeline: collect → signals → score ===")
        t0 = time.time()

        # Step 1: Run all collectors
        log.info("── Step 1: Collectors ──")
        results = run_all()
        for name, r in results.items():
            status = r["status"]
            if status == "ok":
                log.info("  %s: %d stored, %d errors", name, r.get("stored", 0), r.get("errors", 0))
            else:
                log.error("  %s: FAILED — %s", name, r.get("error", "unknown"))

        # Step 2: Extract derived signals
        log.info("── Step 2: Signal extraction ──")
        run_signals()

        # Step 3: Score
        log.info("── Step 3: Scoring ──")
        run_scoring()

        elapsed = round(time.time() - t0, 2)
        log.info("=== Full pipeline done in %.2fs ===", elapsed)
        failed = sum(1 for r in results.values() if r["status"] != "ok")
        sys.exit(1 if failed else 0)

    if args[0] == "--list":
        list_collectors()
        return

    if args[0] == "--signals":
        run_signals()
        return

    if args[0] == "--score":
        run_scoring()
        return

    target = args[0]

    # Try as module name first
    if target in REGISTRY:
        run_one(target)
        return

    # Try as collector ID
    try:
        cid = int(target)
        module_name = find_module_by_id(cid)
        if module_name:
            run_one(module_name)
            return
        else:
            log.error("No implementation found for collector ID %d", cid)
            log.error("Registered: %s", ", ".join(f"{load_collector(m).COLLECTOR_ID}={m}" for m in REGISTRY))
            sys.exit(1)
    except ValueError:
        pass

    log.error("Unknown collector: %s", target)
    log.error("Available: %s", ", ".join(REGISTRY.keys()))
    sys.exit(1)


if __name__ == "__main__":
    main()
