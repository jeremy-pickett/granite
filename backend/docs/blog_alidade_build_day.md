# Building a Financial Early Warning System in One Day

## From 21 Collectors and 24 Signals to 32 Collectors, 33 Signals, and the Question: Would This Have Caught Enron?

*Jeremy Pickett — March 31, 2026*

---

We started the morning with a system that could watch. By evening, we had a system that could warn.

This is the story of what happens when you take a working financial signal detection platform, an audit document full of unrealized potential, a pile of unused API keys, and a single design question — "Would this have caught Enron six months earlier?" — and refuse to stop building until the answer is honest.

---

## Where We Started

The Alidade IALD (Integrated Anomaly & Liquidity Detection) scoring system was already operational. Twenty-one collectors scraped data from SEC EDGAR, Finnhub, Yahoo Finance, Polygon.io, blockchain APIs, and prediction markets. Twenty-four signals detected anomalies ranging from volume spikes to material weaknesses. A score engine aggregated everything into a 0.0-1.0 score per security per day, with verdicts from LOW to CRITICAL.

It worked. It ran on cron. It had coverage.

But the COLLECTOR_SIGNAL_AUDIT.md sitting in the repo told a different story. That document — a comprehensive teardown of every collector, every signal, every gap — contained 288 specific improvement ideas and identified nine unused API keys gathering dust in the `.env` file. More importantly, it identified patterns the system should have been detecting but wasn't: compound governance failures, private equity debt loading, crypto rug pulls, and the temporal co-occurrence patterns that historically preceded the most spectacular corporate collapses.

The audit was a blueprint. We decided to build it.

---

## Phase 1: Fix What's Broken

Before adding anything new, we fixed the foundation.

Three collectors had a schema bug where the `ON CONFLICT` clause referenced a `last_updated` column that didn't exist in their `CREATE TABLE` statement. Every duplicate insert was silently failing. The news sentiment collector, the insider trades collector, and the congressional trades collector all had this same bug. Three `ALTER TABLE` statements and three one-line schema fixes.

The prediction market signal extractor was hardcoding `direction: "neutral"` on every signal, throwing away the probability data it had already fetched. Polymarket was telling us "Bitcoin will exceed $100K" at 90% probability and we were recording "neutral." We added directional inference from probability extremity and event title keywords. Markets betting on bankruptcy at 70%+ now emit bearish. Markets betting on approval at 80%+ now emit bullish. The information was always there; we were ignoring it.

The exchange flow collector had been dutifully recording daily Bitcoin balance snapshots across five exchanges into `raw_exchange_flows` for weeks. The blockchain signal extractor never queried that table. Not once. The docstring claimed it did. The code did not. We wired it in: day-over-day net BTC flow across exchanges, with inflows interpreted as selling pressure (bearish) and outflows as accumulation (bullish). The data had been sitting there, correct and complete, waiting for someone to read it.

Same story with the crypto exposure table. The crypto exposure estimator classified every security in our universe by its Bitcoin/Ethereum exposure — MSTR at 0.95, COIN at 0.85, MARA at 0.90. Nothing downstream consumed this classification. We added a propagation step: when a blockchain anomaly fires for BTC-USD, it now propagates to exposed equities with contribution scaled by exposure score. A whale dump that triggers a 0.80 contribution signal for Bitcoin now also generates a 0.38 signal for MicroStrategy. The cross-asset contagion path that existed in theory now exists in code.

Four bugs. All of them were cases where data was being collected correctly but either stored incorrectly or never read. The most expensive kind of bug: the kind where you're paying for the API calls and the storage but getting zero signal value.

---

## Phase 2: Architectural Fixes

Eight EDGAR-based collectors each independently loaded the SEC's company tickers JSON file to build a CIK lookup cache. During a full pipeline run, the SEC API was being hit eight times for the same 13,000-ticker mapping. We extracted `edgar_utils.py` — a shared module with an idempotent `load_cik_map()` that loads once per process. Eight collectors refactored to import from one shared source.

All sixteen signal extractors used `ON CONFLICT (security_id, signal_type, detected_at) DO NOTHING` with timestamp-precision `detected_at`. Running the pipeline twice within a minute created duplicate signals. Running it twice an hour apart also created duplicates, because the timestamp was different. We truncated `detected_at` to date precision and changed `DO NOTHING` to `DO UPDATE SET contribution = GREATEST(EXCLUDED.contribution, signals.contribution)`. Now re-runs upgrade existing signals rather than duplicating or silently discarding them.

These are the kind of changes that don't show up in demos but determine whether the system is trustworthy at scale. A signal pipeline that produces different results depending on what minute you run it is not a signal pipeline. It's a random number generator with extra steps.

---

## Phase 3: Compound Signals — The Enron Test

This is where the session changed character.

The existing system detected individual anomalies: an auditor changed, a C-suite executive left, a material weakness was disclosed. Each fired independently. The score engine applied cluster discounts to prevent double-counting, but there was no mechanism for *amplification* — for recognizing that three independent signals firing within the same time window for the same security is qualitatively different from any one of them firing alone.

Enron had all three. Auditor change (Arthur Andersen's increasingly compromised position), C-suite departures (Sherron Watkins' memo, Jeffrey Skilling's abrupt resignation), and material weakness (the special purpose entities that turned out to be fiction). These events happened within months of each other. Individually, each was concerning. Together, they were a five-alarm fire.

We built `compound_signals.py` — a signal extractor that runs after all other extractors and reads from the signals table itself. It detects temporal co-occurrence patterns:

**governance_crisis** (Tier S, weight 1.70): Auditor change + C-suite exodus or material weakness within 180 days. The single highest-weighted signal in the system. It has a special sub-pattern — the CFO+Auditor alarm — that fires when specifically the person responsible for the numbers leaves AND the auditor changes within 90 days. This combination preceded Enron, Wirecard, and Luckin Coffee. It forces contribution to 1.0 and confidence to 0.95 — maximum conviction.

**insider_capitulation** (Tier S, weight 1.65): Insider sale cluster + C-suite exodus or extreme bearish news sentiment within 30 days. When the people who know the most are selling AND leaving AND the press is turning negative — that's not a coincidence. That's evacuation.

**short_squeeze_setup** (Tier A, weight 1.50): Short interest spike + FTD spike + unusual options activity within 14 days. This is the GameStop pattern: short sellers piled in, fails-to-deliver accumulating, options market lighting up. Not fraud detection — market microstructure pressure detection.

The governance domino sequence tracks escalation: material weakness, then auditor change or C-suite exodus within a year. Each additional signal in the cascade multiplies severity. The progression from "we have a control problem" to "our auditor won't sign off" to "our CFO just quit" is not a sequence of independent events. It is a narrative of institutional failure, and now the system reads it as one.

---

## Phase 4: The Enron-Catcher Enhancements

With compound signals in place, we went deeper into the individual collectors, adding the forensic capabilities that turn a signal from "something happened" into "here's what it means."

**Auditor disagreement extraction**: The auditor changes collector now downloads the first 10KB of each 8-K Item 4.01 filing and searches for the words that matter most — "disagreement," "reportable event," "resignation." An auditor who is *dismissed* is routine. An auditor who *resigns* and discloses *disagreements* is a nuclear indicator. When found, the signal contribution jumps to 0.90 with extreme magnitude.

**Auditor tier tracking**: A static lookup table classifying audit firms by tier — Big 4, national, regional. Downgrading from Deloitte to a regional firm nobody has heard of is a categorically different event than rotating from EY to PwC. The tier direction now multiplies contribution.

**Silence before the storm**: The system now queries for securities where the current auditor change is the *first change in ten or more years*. A company that has had the same auditor since 2015 suddenly switching is more alarming than a company that rotates every three years. The contribution gets a 1.5x boost, and the description is annotated with "FIRST CHANGE IN 10+ YEARS."

**Sell despite good news**: The insider signals extractor now cross-references insider sales with analyst consensus and 52-week price data. When insiders are selling while analysts are upgrading and the stock is near its all-time high — that's the pattern that preceded Enron's collapse. Kenneth Lay was selling at 52-week highs while telling employees to buy more. The contribution gets a 1.5x boost and the description notes "contrarian: selling into good news."

**CFO exit strategy detection**: A dedicated detection block for C-suite insiders who have sold in four or more distinct months out of the last six, with steadily declining holdings. This is not a one-time liquidity event. This is a systematic liquidation strategy. Kenneth Lay sold $70 million over twelve months. The signal fires at 0.90 contribution with extreme magnitude.

**NT cascade detection**: Consecutive late filings (NT 10-K or NT 10-Q) for the same security are now detected and weighted 3x instead of the default 2x in the material weakness composite. The SMCI trajectory — NT filing, then another NT filing, then auditor resignation — is exactly this pattern.

**Serial restatement detection**: Multiple financial restatements correcting the same fiscal periods now weight 3x instead of 2x. If you're restating the same quarter's numbers twice, the books were never reliable.

**Going concern section-aware parsing**: The going concern collector now downloads filing text and classifies where the mention appears. An auditor's report containing "substantial doubt about the entity's ability to continue as a going concern" (4x weight) is categorically different from a boilerplate risk factor paragraph (1x weight). The signal now knows the difference.

**Put skew persistence**: The options signal extractor now checks whether elevated put/call ratios persist across multiple days. A single day of heavy put buying could be hedging. Five consecutive days of put/call ratio above 2.0 is conviction. This pattern preceded Bear Stearns by two weeks.

**Bipartisan consensus**: When members of both political parties trade the same security in the same direction within 30 days, the contribution gets a 1.5x boost. This isn't ideology — it's information advantage. Both sides of the aisle agreeing on a trade is the strongest form of the congressional trading signal.

---

## Phase 5: Activating the API Keys

Nine API keys had been configured in the `.env` file and loaded by `config.py` but consumed by zero collectors. Nine data sources paying for nothing. We built seven new collectors in an afternoon:

**Metaculus Prediction Markets** — Community forecasting platform with calibrated probability estimates. Writes to the same `raw_prediction_markets` table as Polymarket and Kalshi, so the existing `prediction_market_signals.py` extractor picks it up automatically. Three prediction market sources are better than two.

**CryptoPanic News Feed** — Crypto-specific news aggregator with crowd-voted sentiment. Writes to `raw_news_sentiment` alongside Finnhub headlines, so `news_signals.py` processes it without modification. Sentiment scored with VADER (which we also installed this session, replacing the 65-word keyword bag that had been doing the work of a real NLP model).

**NewsAPI Headlines** — General business news from hundreds of sources. Same integration pattern as CryptoPanic — writes to the existing news table, picked up by the existing signal extractor. Fifty tickers per day, prioritized by recent signal activity, to stay within the free tier's 100 requests/day.

**Tiingo Market Data** — Alternative OHLCV source using adjusted prices. Writes to `raw_market_data` alongside Yahoo Finance data, providing redundancy and gap-filling. When yfinance has a bad day, Tiingo picks up the slack.

**Nasdaq Data Link** — Macro economic indicators: Federal Funds Rate, the 10Y-2Y Treasury spread (yield curve inversion), VIX, high yield credit spreads, unemployment rate, S&P 500 PE ratio. This is the first collector that doesn't map to individual securities — it's market-level context stored in a new `raw_economic_indicators` table.

**LunarCrush Social Sentiment** — Crypto social media metrics including the Galaxy Score (community engagement strength), social volume, and alt-rank. Fires blockchain_anomaly signals when the Galaxy Score drops more than 20% day-over-day or social volume spikes above 3x baseline.

**Santiment On-Chain Analytics** — Deep blockchain metrics via GraphQL: daily active addresses, exchange inflows/outflows, network growth, whale transaction count, social volume, and developer activity. Seven metrics across seven days for both Bitcoin and Ethereum. The developer activity metric is particularly valuable — when GitHub commits go to zero, the project is abandoned regardless of what the marketing says.

The VADER sentiment upgrade deserves its own mention. The news sentiment collector had been scoring headlines with a bag of 65 positive and 65 negative keywords. "Company faces headwinds but analysts remain cautiously optimistic" scored 0.0 because the keyword hits cancelled out. VADER handles negation, intensifiers, degree modifiers, and context. It's the difference between a sentiment thermometer and a sentiment stethoscope. We kept the keyword approach as a fallback for environments where VADER isn't installed.

---

## Phase 6: Private Equity Predatory Detection

This is where the system moved from detecting anomalies to detecting *intent*.

The PE detection system has three layers, tracking the lifecycle of a leveraged buyout gone predatory:

**Layer 1 — Going-Private Detection** (`pe_activity.py`): Searches EDGAR EFTS across five passes for going-private transactions (SC 13E-3), tender offers (SC TO-T/SC TO-C), merger agreements (8-K Item 1.01, PREM14A, DEFM14A), debt offerings, and asset sales. This is early warning — the transaction that starts the clock.

**Layer 2 — Debt Loading Detection** (`debt_monitor.py`): Quarterly balance sheet monitoring via Finnhub. Tracks debt-to-equity ratio changes, interest expense as a percentage of revenue, and free cash flow trends. The signal fires when debt-to-equity increases more than 2x in four quarters or when interest payments consume more than 30% of revenue. This is the exploitation phase — the acquirer loading the acquired company with the debt used to buy it.

**Layer 3 — PE Distress Pattern** (`pe_signals.py`): Cross-references PE activity events with governance distress signals. When a security has a going-private or merger event AND material weakness, auditor change, or C-suite exodus within 365 days — that's the Toys "R" Us pattern, the Sears pattern, the pattern where a company is being systematically dismantled through debt while its governance infrastructure collapses.

The `pe_distress_pattern` signal is Tier S at weight 1.65 — tied for the highest conviction signal in the system alongside `governance_crisis` and `insider_capitulation`. The question "is private equity going to take this company private, load it with debt, and intentionally bankrupt it?" is now a question the system attempts to answer.

Can we detect this in progress, or only after the fact? Both, depending on the phase. Tender offers and going-private filings are public record before the transaction closes — that's Layer 1, and it fires in real time. Debt loading is visible quarter by quarter in the balance sheet — that's Layer 2, detectable within 90 days of inception. The governance collapse that follows is what all our existing Enron-catcher signals were built to detect — it's just that now we know to look for it specifically in the post-acquisition window.

---

## Phase 7: Crypto Governance and the Death Spiral Detector

The crypto market has its own vocabulary of failure, and it requires its own detection apparatus.

**The Governance Profile** (`crypto_governance.py`): For each crypto asset, we build a daily governance snapshot from CoinGecko and Santiment. Circulating-to-total supply ratio (how much of the supply is locked or unreleased — a dilution time bomb). Developer commit count and contributor count (is anyone still building?). Volume-to-market-cap ratio (is the market alive or a ghost town?). The schema includes fields for token holder concentration (Herfindahl-Hirschman Index of top holders), ready for when we expand to individual ERC-20 tokens via Etherscan.

**The Death Spiral Detector** (`crypto_death_spiral.py`): A five-phase classifier that pulls from price data, social metrics, on-chain analytics, and developer activity to classify each crypto asset into a phase:

- **Healthy** — Normal operation. Score below 0.15.
- **Warning** — Price declining plus one other indicator degrading. Score 0.15-0.30.
- **Deteriorating** — Multiple indicators in decline. Volume falling, social engagement dropping, price off 30%+ from peak. Score 0.30-0.50.
- **Critical** — Severe multi-factor collapse. Price off 50%+, volume collapsing, developers gone quiet, exchange inflows sustaining (holders dumping). Score 0.50-0.70.
- **Terminal** — Price off 80%+, volume dead, social abandoned, developer activity zero, sustained exchange inflows. Score above 0.70. The asset has crossed the Rubicon.

The question was asked: "Can we divine statistically at what point a coin's value has crossed the Rubicon into a 0.1% chance of pulling out of the death spiral?" The honest answer is that we can classify the phase, not predict the future. But the historical pattern is clear: when a crypto asset reaches the terminal phase — price collapsed, developers gone, community scattered, liquidity evaporated — the recovery rate is effectively zero. Not exactly zero. Effectively zero. Bitcoin in 2018 was "critical" but had active developers and a committed community. The hundreds of tokens that died in the same period had neither. The difference between a bear market and a death spiral is whether anyone is still building.

**The Rug Pull Risk Signal** (`crypto_rug_pull_risk`, Tier S, weight 1.60): Fires when multiple high-severity indicators align — concentrated ownership, abandoned development, collapsing volume. This is the pattern of intentional fraud: a small group holding most of the supply, no ongoing development, and decreasing market activity that suggests the insiders are quietly exiting while retail holders are stuck.

---

## The Numbers

| Metric | Morning | Evening |
|--------|---------|---------|
| Collectors | 21 | 32 |
| Active signals | 24 | 33 |
| Tier S signals | 0 | 4 |
| Tier A signals | 4 | 10 |
| API keys active | 5 of 14 | 14 of 14 |
| Compound patterns | 0 | 6 |
| Raw data tables | ~20 | 29 |
| Python files | ~45 | 64 |
| Lines of code | ~8,000 | 13,025 |
| Enron-catcher enhancements | 0 | 13 |
| Bugs fixed | — | 4 critical |

The four Tier S signals — the highest-conviction, highest-weight signals in the entire system:

1. **governance_crisis** (1.70) — Auditor change + governance failure compound
2. **insider_capitulation** (1.65) — Insider selling + governance/sentiment failure
3. **pe_distress_pattern** (1.65) — PE activity + governance collapse
4. **crypto_rug_pull_risk** (1.60) — Concentrated ownership + abandoned development

Each represents a distinct category of catastrophic failure: corporate governance fraud, insider evacuation, private equity predation, and crypto project fraud. Together, they are the system's highest-conviction warnings that something is fundamentally wrong — not that a stock had a bad day, but that the institutional structure is failing.

---

## What We Built, and What It Means

The Alidade system now monitors:

**Corporate governance** through SEC EDGAR — auditor changes (with disagreement extraction and tier tracking), C-suite departures, material weaknesses (with negation-aware parsing), late filings (with cascade detection), financial restatements (with serial detection), going concern opinions (with section-aware severity), insider trades (with dollar values, role titles, purchase signals, CFO exit strategy detection, and sell-despite-good-news detection), concentration shifts, 13F institutional filings, and PE activity (going-private transactions, tender offers, debt offerings, asset sales).

**Market microstructure** through daily OHLCV (with Tiingo backup), options flow (with put skew persistence), fail-to-deliver patterns, short interest, sector correlation, and analyst consensus shifts.

**Blockchain and crypto** through whale transaction tracking, exchange flow monitoring (now actually wired in), on-chain activity metrics, LunarCrush social sentiment, Santiment on-chain analytics, crypto project governance profiling, and death spiral phase classification.

**Alternative data** through prediction markets (Polymarket, Kalshi, and now Metaculus), news sentiment (Finnhub, CryptoPanic, and NewsAPI, now with VADER), congressional trades (with bipartisan consensus detection), and macro economic indicators (Fed Funds, yield curve, VIX, credit spreads).

**Compound detection** through six temporal co-occurrence patterns that detect governance crisis, insider capitulation, short squeeze setups, PE distress, CFO+Auditor alarms, and governance domino sequences.

All of it feeds into a single scoring formula: signals weighted by tier, decayed by time, discounted for cluster redundancy, and bonused for cross-cluster independence. The formula hasn't changed. What changed is what flows into it.

---

## The Honest Limitations

We built a lot today. Some of it will work exactly as designed. Some of it will need tuning. Here's what we know we don't know:

The PE detection system can identify going-private filings and debt loading, but it cannot determine *intent*. A leveraged buyout that loads debt onto the acquired company might be a rational capital structure decision or might be predatory extraction. The system detects the pattern. A human decides what it means.

The crypto death spiral classifier uses phase thresholds calibrated from general intuition about crypto market dynamics, not from rigorous backtesting against historical rug pulls. The backtesting framework exists — we built it today — but it hasn't been run against the crypto signals yet. The thresholds should be treated as first drafts.

The VADER sentiment upgrade is a meaningful improvement over the keyword bag, but VADER was designed for social media text, not financial headlines. "Company beats expectations" scores correctly. "Company faces going concern doubt from auditor" may not score as negatively as it should, because VADER doesn't know what a going concern opinion is. FinBERT would be better, but it's a heavy dependency we chose not to take on today.

The compound signals require their constituent signals to have already fired. A governance_crisis compound can only fire if auditor_change AND csuite_exodus or material_weakness have independently fired within the window. If the individual collectors miss the underlying event, the compound will miss it too. The compound amplifies; it does not originate.

None of the new API integrations have been tested against production rate limits under full pipeline load. LunarCrush, Santiment, and CoinGecko all have free-tier rate limits that may require throttling adjustments when running against a full securities universe.

---

## What Comes Next

Tonight: LLM integration. The signals are structured data — contribution scores, confidence levels, directions, magnitudes. They're designed for machines to consume and humans to interpret. An LLM layer that reads the day's signals for a security and produces a narrative summary — "AAPL has three active governance signals: an auditor change first seen in 10 years, a C-suite departure cluster, and insiders selling into analyst upgrades. Combined IALD score: 0.72 ELEVATED." — turns a dashboard of numbers into a briefing.

This week: Run the backtesting framework against all 33 signals. The `signal_backtests` table is ready. We need 30-day, 90-day, and 180-day forward return data to validate the tier assignments. Any signal whose hit rate doesn't match its tier gets recalibrated. The tiers are hypotheses until the backtest validates them.

This month: Expand the crypto governance system to individual ERC-20 tokens. The `raw_crypto_governance` table schema already has columns for holder concentration (HHI) and top-holder percentages. Etherscan's token holder list API is the data source. When we can profile individual tokens — not just BTC and ETH — the rug pull detector gets real teeth.

The question we started with — "Would this have caught Enron six months earlier?" — is now a question we can start to answer empirically. The governance_crisis compound signal, the auditor disagreement extractor, the CFO exit strategy detector, the sell-despite-good-news enhancement: every one of these was designed to detect a pattern that was present in the Enron data. The backtest will tell us if they would have fired, how early, and at what confidence.

The signal proves the anomaly. The compound proves the pattern. The score proves the severity. What the human does with it is still the human's call.

That's the system. Thirty-two collectors, thirty-three signals, thirteen thousand lines of code, and one design question that refused to accept a comfortable answer.

---

*Licensed under BSD 2-Clause License.*
*Copyright (c) 2026, Jeremy Pickett. All rights reserved.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
