# Collector & Signal Audit — Full Inventory, Ideas, and Roadmap

**Generated:** 2026-03-31
**Scope:** 21 collectors, 16 signal extractors, 24 active signals

---

# Table of Contents

1. [Cross-Cutting Architectural Observations](#cross-cutting)
2. [SEC / Governance Collectors](#sec-governance)
   - Auditor Changes
   - C-Suite Departures
   - Concentration Disclosure
   - Material Weakness (composite: late filings, restatements, going concern)
   - SEC 13F Holdings
   - Congressional Trades
   - Insider Trades
3. [Market / Trading Collectors](#market-trading)
   - Market Data (7 signals)
   - Analyst Actions
   - FTD Patterns
   - Options Flow
   - Short Interest
   - Sector Correlation
4. [Alt-Data / Blockchain Collectors](#alt-data)
   - News Sentiment
   - Prediction Markets
   - Crypto Whale Tracker
   - Exchange Flow Monitor
   - On-Chain Activity
   - Crypto Exposure Estimator

---

<a id="cross-cutting"></a>
# Cross-Cutting Architectural Observations

These patterns recur across all collectors and represent the highest-leverage systemic improvements.

### 1. No Cross-Signal Correlation at the Signal Level
Each signal extractor operates in isolation. The score_engine applies cluster discounts after the fact, but extractors cannot boost confidence when corroborating signals exist. A dedicated **cross-signal correlation pass** (run after all extractors, before score_engine) would unlock the highest-value composite patterns. Example: auditor change + CFO departure + late filing within 180 days should score as a multiplicative compound, not an additive sum.

### 2. EDGAR Filing Text Is Never Downloaded or Parsed
Every EDGAR-based collector works from metadata only (form type, date, accession number). Downloading even the first 10KB of actual filing text and running keyword extraction would transform signal quality — distinguishing disclosures from remediations, resignations from dismissals, new problems from resolved ones.

### 3. No Backtesting Framework
None of the signals are validated against historical price outcomes. A simple "did the stock underperform in the 30/90/180 days after this signal fired?" metric would enable data-driven calibration of contribution scores, confidence levels, and severity thresholds.

### 4. CIK Cache Loaded Redundantly
Seven EDGAR-based collectors each independently load the CIK cache. A shared `edgar_utils.py` module would eliminate redundant API calls.

### 5. Signal Deduplication Is Fragile
The `ON CONFLICT (security_id, signal_type, detected_at) DO NOTHING` pattern deduplicates by timestamp precision. If an extractor runs twice in the same second, it deduplicates; a minute later, it creates a duplicate. Consider `detected_at::date` for inherently daily signals.

### 6. Exchange Flow Data Is Collected But Not Used
`exchange_flow.py` runs daily and stores snapshots, but `blockchain_signals.py` never reads from `raw_exchange_flows`. Exchange net flow is widely considered the strongest on-chain leading indicator.

### 7. Crypto Exposure Table Is Built But Not Wired In
Designed to enable cross-asset signal propagation from blockchain events to equities, but no downstream consumer reads it.

### 8. Direction Is Underutilized
The prediction market signal always emits "neutral." News sentiment emits direction but it is not used by the score engine. Adding directional scoring would roughly double the information content.

---

<a id="sec-governance"></a>
# SEC / Governance Collectors

---

## 1. Auditor Changes (`auditor_changes.py` + `auditor_signals.py`)

**Signal:** `auditor_change` — Tier B, weight 1.35, half-life 720h

### Summary
Monitors SEC 8-K Item 4.01 filings (Changes in Registrant's Certifying Accountant) via EDGAR. Counts auditor changes over a 2-year window and assigns severity based on frequency.

### Feature Inventory
- **Auditor identity extraction**: Does not parse which auditor departed/was appointed. "Deloitte replaced EY" vs. "unknown regional firm replaced PwC" is fundamentally different risk.
- **Resignation vs. dismissal classification**: Item 4.01 distinguishes these; collector treats them identically.
- **Disagreement detection**: 8-K Item 4.01 requires disclosure of disagreements with the outgoing auditor — the nuclear indicator. Not parsed.
- **Big 4 / tier tracking**: No classification of auditor tier. Downgrading from Big 4 to a regional firm is a massive red flag.
- **Temporal decay**: Binary confidence split (0.80 if <1 year, 0.60 otherwise) rather than smooth decay.
- **Co-occurrence with other signals**: No cross-referencing with material weakness, late filing, or C-suite departures.
- **Historical baseline**: No per-security baseline of normal auditor change frequency.

### 5 Creative Ideas for the Collector
1. **Parse 8-K filing text** to extract predecessor/successor auditor names and whether "disagreements" or "reportable events" are disclosed. A disagreement + resignation is 10x stronger than routine rotation. Would have flagged SMCI months earlier.
2. **Build an auditor quality score**: Maintain a tier lookup (Big 4 = tier 1, BDO/Grant Thornton/RSM = tier 2, etc.). Track direction of change — downgrading tiers is Arthur Andersen territory.
3. **Cross-signal compound scoring**: When auditor change co-occurs within 180 days of late filing, material weakness, or C-suite departure, multiply contribution 2-3x. Enron had all of these in the same window.
4. **Track successor auditor client base**: If a tiny firm suddenly picks up 3-4 companies that lost Big 4 auditors, it is becoming a "dumping ground" for troubled companies. Network-level signal.
5. **Monitor auditor "musical chairs"** across the entire universe: build a graph of auditor-company relationships and detect when the overall rate of changes spikes industry-wide.

### 5 Creative Ideas for the `auditor_change` Signal
1. **"Silence before the storm" detector**: Flag companies with the SAME auditor for 10+ years that suddenly change. Long tenure followed by disruption is more alarming than regular rotation.
2. **Weight by market cap**: Inverse log of market cap — an auditor change at a $500M company is more individually impactful than at a $500B company.
3. **Timing relative to fiscal year end**: A change 30 days before filing deadline is exponentially more concerning than one 8 months out.
4. **"Boomerang" auditor detection**: Company fires auditor A, hires B, then B resigns within 12 months. Two auditors refusing to sign off = extreme magnitude.
5. **Correlate with short interest**: When auditor changes coincide with rising short interest, the shorts often know first. Wire in as confidence booster.

---

## 2. C-Suite Departures (`csuite_departures.py` + `csuite_signals.py`)

**Signal:** `csuite_exodus` — Tier B, weight 1.25, half-life 336h

### Summary
Monitors SEC 8-K Item 5.02 filings. Identifies companies with 6+ departures/year or 3+ in 90 days. Severity scales with departure velocity.

### Feature Inventory
- **Role extraction**: Does not parse which role departed (CEO vs. VP of Marketing).
- **Departure vs. appointment**: Treats the raw 8-K as a single event without differentiating.
- **Reason for departure**: Not parsed (voluntary, personal reasons, disagreements).
- **Replacement timing**: Whether a successor was immediately named or role left vacant.
- **Board vs. executive differentiation**: Directors departing en masse vs. officers is different.
- **Net flow calculation**: No tracking of appointments vs. departures.
- **Industry baseline**: No adjustment for industry norms.

### 5 Creative Ideas for the Collector
1. **Parse filing text for departing person's title**: Weight CFO/CAO departures 3x heavier — when the person responsible for the numbers leaves, it is the single strongest pre-collapse signal.
2. **"CFO + Auditor" compound alarm**: CFO departure within 90 days of auditor change fires a dedicated ultra-high-severity signal. This preceded Enron, Wirecard, and Luckin Coffee.
3. **Track departure-to-replacement gap**: CEO position vacant 60+ days escalates to "extreme."
4. **Named-entity cross-reference with insider trades**: When a departing executive also appears with recent large sales, the combined signal is far stronger.
5. **Detect "quiet quitting at the top"**: Track 8-K/A amendments to departure filings — extremely rare and almost always bad news.

### 5 Creative Ideas for the `csuite_exodus` Signal
1. **Departure velocity acceleration**: Compute the derivative — going from 1/quarter to 3/quarter is more alarming than steady 2/quarter.
2. **"Key person" risk multiplier**: Cross-reference with DEF 14A proxy statement.
3. **Board independence changes**: When independent directors depart and are replaced by insiders.
4. **Seasonal adjustment**: Mid-cycle departures (outside Q1/Q4) are more likely unplanned.
5. **"Successor quality" score**: Check if replacement has a history as "turnaround" or "interim" officer.

---

## 3. Concentration Disclosure (`concentration_disclosure.py` + `concentration_signals.py`)

**Signal:** `concentration_shift` — Tier B, weight 1.25, half-life 336h

### Summary
Monitors SC 13D (activist) and SC 13G (passive) filings via EDGAR. Flags securities with 3+ filings in 2 years or first-ever activist filings.

### Feature Inventory
- **Ownership percentage extraction**: Does not parse actual ownership percentage from filing.
- **13D vs. 13G distinction in scoring**: Counted separately but not weighted differently.
- **Filer identity**: Captures company name, not the institutional investor.
- **Amendment direction**: Does not distinguish accumulation from disposition.
- **Filer reputation**: No tracking of who the institution is.
- **Filing lag detection**: Disclosure date vs. threshold-crossing date not captured.

### 5 Creative Ideas for the Collector
1. **Parse 13D/13G filing text** to extract ownership percentage, filer identity, and position direction.
2. **"Smart money tracker"**: Curated list of 50-100 known activists (Icahn, Elliott, Ackman, etc.) weighted 3-5x.
3. **Detect 13G-to-13D conversion**: Explicit declaration of hostile intent. Should fire independent high-severity signal.
4. **Cross-reference with congressional and insider trades**: Multi-table temporal clustering.
5. **Track "wolf pack" formation**: Multiple unrelated institutions filing 13D/13Gs on the same security within 30 days.

### 5 Creative Ideas for the `concentration_shift` Signal
1. **Direction awareness**: Cluster of decreasing amendments = bearish; increasing 13D filings = potential takeover premium.
2. **Concentration Herfindahl index**: One holder at 25% is very different from five holders at 6% each.
3. **Track filing speed**: Late 13D filings (> 10 calendar days after threshold) indicate intentional delay.
4. **"Poison pill" trigger detection**: Cross-reference with shareholder rights plan thresholds.
5. **"Orphan stock" detector**: 13G holders reducing positions AND no new 13D filers = institutional abandonment.

---

## 4. Material Weakness (`material_weakness.py` + `material_weakness_signals.py`)

**Signal:** `material_weakness` — Tier A, weight 1.50, half-life 720h (composite from 4 raw tables)

### Summary
EDGAR EFTS full-text search for "material weakness" in 10-K/10-Q filings. Signal is a composite engine aggregating material weaknesses (1x), late filings (2x), financial restatements (2x), and going concern opinions (3x).

### Feature Inventory
- **Text context extraction**: Does not determine if mention is NEW weakness vs. REMEDIATION of prior one.
- **Weakness category**: Revenue recognition, IT controls, segregation of duties — not parsed. Revenue recognition weaknesses correlate highest with fraud.
- **Remediation tracking**: No tracking of whether weaknesses were subsequently remediated.
- **False positive filtering**: "We did NOT identify any material weakness" matches the search.
- **Auditor opinion integration**: No cross-reference with auditor opinion type.
- **Company size normalization**: Material weakness at micro-cap is structurally more common.

### 5 Creative Ideas for the Collector
1. **Negation-aware text parsing**: Check for "no material weakness," "did not identify," "remediated." Eliminates the largest class of false positives.
2. **"Weakness timeline" per security**: Track from disclosure through remediation. Un-remediated by Q3 escalates to extreme. Exactly what happened with Luckin Coffee.
3. **Categorize by type**: Revenue recognition and related party weaknesses have highest fraud correlation. Weight accordingly.
4. **Cross-reference with stock price reaction**: If the market ignored the disclosure (no drop), the signal is stronger — information not yet priced in.
5. **"Contagion map"**: If Deloitte discloses weakness at one bank, proactively flag other Deloitte-audited banks.

### 5 Creative Ideas for the `material_weakness` Signal
1. **Multiplicative interaction terms**: Going concern AND restatement should be 3x2=6x, not 3+2=5x.
2. **Exponential time decay**: `confidence = 0.90 * exp(-days/365)` instead of binary split.
3. **"Domino sequence" state machine**: material weakness -> late filing -> restatement -> going concern. Each step escalates exponentially.
4. **Integrate with analyst revision data**: Same problem detected from different angle = strong corroboration.
5. **"First-timer" premium**: First-ever material weakness deserves higher contribution.

### Sub-Collector: Late Filings (`late_filings.py`)

**5 Creative Ideas:**
1. Parse NT filing text to extract stated reason and extension days requested.
2. Detect "NT cascade" — consecutive NT filings = escalation pattern (SMCI trajectory).
3. Cross-reference with auditor change timing — NT within 90 days of auditor change is high-probability fraud.
4. Track whether the late filing was eventually filed — if never filed, far worse signal.
5. "Deadline clock" — filing NT on last possible day vs. proactively conveys different information.

### Sub-Collector: Financial Restatements (`financial_restatements.py`)

**5 Creative Ideas:**
1. Extract restatement dollar impact — 30% revenue restatement scores differently from 0.5% reclassification.
2. Classify "Big R" vs. "little r" — full re-filing vs. embedded revision.
3. Serial restatement detector — multiple corrections to same periods = fundamentally unreliable books.
4. Cross-reference with class action lawsuits (PACER or free legal databases).
5. Track auditor response post-restatement — auditor leaving after restatement = "we can't trust these people."

### Sub-Collector: Going Concern (`going_concern.py`)

**5 Creative Ideas:**
1. Section-aware parsing — distinguish auditor's report (most severe) from MD&A (moderate) from risk factors boilerplate (low).
2. "Going concern journey" state machine — no concern -> risk discussion -> emphasis of matter -> full opinion -> auditor resignation.
3. Extract cash runway data — going concern + <6 months cash = maximum severity.
4. Normalize by market cap — going concern on $10B company is more shocking than on $100M company.
5. Detect going concern removal — actually a bullish signal (company survived).

---

## 5. SEC 13F Holdings (`sec_13f.py` + `sec_13f_signals.py`)

**Signal:** `institutional_filing_spike` — Tier D, weight 0.90, half-life 168h

### Summary
Monitors quarterly 13F-HR filings for unusual filing frequency (5+/year or 2+ amendments). **Critical architectural issue**: 13F filings are filed BY fund managers, but the collector indexes by the company's CIK, meaning it finds companies that are themselves 13F filers (e.g., Berkshire), not companies being held by 13F filers.

### Feature Inventory
- **No actual holdings data**: Stores filing metadata but does not parse the 13F information table XML.
- **Filer/subject confusion**: See above — the architecture is inverted.
- **No period-of-report tracking**: Column exists but never populated.
- **Always neutral direction**: Does not know what positions changed.

### 5 Creative Ideas for the Collector
1. **Parse 13F information table XML**: Extract CUSIP, shares, value per holding. Transform from "someone filed paperwork" to "Bridgewater dumped 80% of AAPL."
2. **Fix the filer/subject architecture**: Build a reverse lookup — parse holdings tables to find which securities appear in which filings.
3. **"Smart money consensus" metric**: Aggregate top 50 institutions' positions, detect rolling consensus shifts.
4. **"Herding" and "crowded trade" detection**: Herfindahl index of institutional ownership concentration.
5. **Track new-position and full-exit events**: Brand-new positions and complete exits are the highest-signal events.

### 5 Creative Ideas for the `institutional_filing_spike` Signal
1. **Add directional awareness**: Amendments outnumbering regular filings → bearish.
2. **Weight by filer AUM**.
3. **Seasonal adjustment** for expected quarterly filing patterns.
4. **Cross-reference with market volatility**: Normalize by VIX.
5. **Detect "delayed disclosure" games**: Late filers may be hiding position changes.

---

## 6. Congressional Trades (`congressional_trades.py` + `congressional_signals.py`)

**Signal:** `congressional_trade` — Tier A, weight 1.45, half-life 168h

### Summary
Collects Congress member stock trades from QuiverQuant API. Groups by security, detects clusters, infers direction from buy/sell ratio.

### Feature Inventory
- **Committee membership tracking**: No correlation between committee assignments and traded security's industry.
- **Disclosure delay**: Stored but not used in scoring. Long delays may indicate awareness of sensitivity.
- **Historical performance tracking**: No backtesting.
- **Party-level pattern detection**: No party-wide aggregation.
- **Trade-to-legislation timing**: No upcoming vote tracking.

### 5 Creative Ideas for the Collector
1. **Committee-sector correlation matrix**: Banking Committee member trading bank stocks = 3x multiplier. The core of the STOCK Act's intent.
2. **"Disclosure lag" sub-signal**: Trades disclosed on day 44 of 45 are more suspicious than day 5. Late disclosures = separate high-severity signal.
3. **"Bipartisan consensus" detector**: Both parties trading same direction within 30 days = genuine information advantage, not ideology. Weight 3x.
4. **Track individual representative performance**: Rolling 12-month returns per representative. Consistent outperformers get higher weights.
5. **Correlate with upcoming legislation**: congress.gov API for bills in committee. Trading in affected industries = "legislative timing" signal at maximum severity.

### 5 Creative Ideas for the `congressional_trade` Signal
1. **"Pre-announcement" detector**: Retrospectively upgrade representatives whose trades preceded material announcements.
2. **Weight by trade size relative to representative's portfolio**.
3. **"Inverse signal" tracking**: When representatives sell and price drops, confirm the signal. Track hit rate.
4. **"Family office" tracker**: Trades by same last name or known family relationships.
5. **"Hearing calendar" overlay**: Committee member traded before a hearing involving that company/industry.

---

## 7. Insider Trades (`insider_trades.py` + `insider_signals.py`)

**Signals:** `insider_sale_cluster` (Tier B, weight 1.30) + `insider_large_sale` (Tier C, weight 1.10)

### Summary
Collects SEC Form 4 data via Finnhub. Two signals: sale clusters (3+ insiders in 30 days) and large individual sales (>50K shares).

### Feature Inventory
- **Dollar value**: Only share counts. 50K shares at $0.50 = $25K; at $500 = $25M.
- **Insider role/title**: Available in Finnhub but not stored. CEO sales are far more significant.
- **Purchase signals (bullish)**: Completely ignored. Insider purchases are among the strongest bullish signals in finance.
- **10b5-1 plan distinction**: Pre-scheduled (less informative) vs. discretionary (more informative) not captured.
- **Holding change percentage**: `shares_after` stored but not used. Selling 90% of holdings is a different signal from 5%.
- **Transaction price**: Not captured.
- **20-trade limit**: `trades[:20]` silently drops data for companies with many insiders.

### 5 Creative Ideas for the Collector
1. **Dollar-value thresholds**: Replace 50K shares with $500K. A $500K sale is material regardless of share count.
2. **"Percentage of holdings" signal**: Insider selling 80%+ = evacuation. New `insider_liquidation` signal.
3. **Filter out 10b5-1 plan sales**: Discretionary C-suite sales are 3-5x more predictive.
4. **Add insider PURCHASE signals**: `insider_purchase_cluster` and `insider_large_purchase` with bullish direction. Peter Lynch's entire philosophy.
5. **"CEO exit strategy" detector**: Sustained monthly selling over 6+ months, steadily reducing holdings. Kenneth Lay sold $70M over 12 months.

### 5 Creative Ideas for `insider_sale_cluster`
1. **Weight by insider role**: CEO/CFO 3x, other officers 2x, directors 1.5x, 10% owners 1x.
2. **Temporal velocity**: 3 insiders selling on the same day is far more alarming than 3 over 28 days.
3. **Cross-reference with blackout windows**: Sales immediately after blackout opens = insider was waiting.
4. **Per-security baseline**: Some companies have regular quarterly sales from compensation plans.
5. **"Sell despite good news" detector**: Insiders selling into earnings beats, analyst upgrades, 52-week highs. The most Enron-like pattern.

### 5 Creative Ideas for `insider_large_sale`
1. **Multi-factor gate**: Fire when ANY of: dollar value > $500K, shares > 25% of holdings, or largest sale in 2 years.
2. **"Filing speed" multiplier**: Late Form 4s (day 2 or later) suggest reluctant disclosure.
3. **"Salami slicing" detection**: Aggregate daily sales by same insider over 5-day rolling window.
4. **Correlate with options activity**: Insider sells + unusual put activity within a week = overwhelming.
5. **"First sale in N years" flag**: Breaking a long holding streak deserves boosted contribution.

---

<a id="market-trading"></a>
# Market / Trading Collectors

---

## 8. Market Data (`market_data.py` + `market_signals.py`)

**Signals (7):** `volume_spike` (D), `price_gap` (D), `unusual_range` (E), `relative_volume` (E), `price_momentum` (E), `volatility_compression` (E), `closing_strength` (E)

### Summary
Fetches 5-day OHLCV from Yahoo Finance via yfinance. Signal extractor reads 25-day history and derives seven signals.

### Feature Inventory
- **Intraday granularity**: Daily bars only. No flash crash or intraday reversal detection.
- **Extended lookback**: Only 25 days. No 50/200-day MAs, annual seasonality, or multi-regime volatility.
- **VWAP / dollar volume**: Volume is share-count only. No normalization for small-caps vs. large-caps.
- **Multi-timeframe momentum**: Only 5-day.
- **Gap fill tracking**: Detects gaps but does not track whether they fill.
- **Pre-market data**: yfinance supports `prepost=True` but not enabled.
- **Relative strength vs. index**: No SPY/QQQ-relative tracking.
- **Market breadth context**: No VIX, advance/decline, sector rotation.
- **Crypto weekend handling**: Crypto trades 24/7; weekend gaps structurally different from equity.

### 5 Creative Ideas for the Collector
1. **Overnight Drift Detector**: Compare after-hours close to next-day open. Persistent overnight drift = distribution phase. Enron frequently gapped down at open while drifting up after hours.
2. **Volume Climax Pattern Recognition**: Detect exhaustion peaks (5-10x volume on large bar, next bar reverses). Preceded Bear Stearns' collapse (March 14-17, 2008).
3. **Synthetic Dark Pool Volume Estimator**: Compare reported exchange volume against FINRA ADF/TRF ratios. 60%+ off-exchange = institutional block trading the market signal isn't capturing.
4. **Fractal Volatility Regime Detection**: Compute Hurst exponent on 20-day windows. H > 0.6 = trending, H < 0.4 = mean-reverting, H ~ 0.5 = random walk. Regime shifts precede blow-ups.
5. **Cross-Asset Contagion Radar**: Also fetch VIX, HYG, TLT, gold. When a stock starts correlating with HYG instead of its sector ETF, the market is pricing in credit risk. This is what happened to Bear Stearns 3 months before failure.

### Signal-Specific Ideas

#### `volume_spike`
1. Relative dollar-volume spike (weight by price).
2. Volume persistence scoring (3 consecutive 2x days > 1 day at 3x).
3. Sector-relative volume (if every tech stock is 3x, it's the sector, not the stock).
4. Volume vs. ATR normalization (spike on 0.5% move = accumulation, spike on 5% = news event).
5. Time-of-day profiling (last 30 minutes = institutional).

#### `price_gap`
1. Gap classification (breakaway, runaway, exhaustion, common).
2. Gap fill probability tracking per security.
3. Gap + volume confluence (gap on 5x volume is categorically different).
4. Earnings gap isolation via earnings calendar cross-reference.
5. Counter-direction gap chains (alternating gaps = distribution).

#### `unusual_range`
1. Range expansion after compression (volatility squeeze, not just average).
2. Key reversal detection (wide range, close opposite of open).
3. Range vs. ATR percentile (99th vs. 75th is categorically different).
4. Inside bar sequencing (more compression = more explosive breakout).
5. Tail ratio analysis (upper tail = rejection, lower tail = absorption).

#### `relative_volume`
1. Time-weighted relative volume (2pm already at 1.5x = projected 3x).
2. Volume regime detection (20-day vs. 60-day MA crossover).
3. Volume autocorrelation (sustained vs. one-time event).
4. Pre-event volume creep (steady 1.3-1.5x over 5-10 days = smart money accumulating).
5. Options-volume cross-reference for confidence boost.

#### `price_momentum`
1. Momentum divergence (price new highs but momentum declining).
2. Acceleration/deceleration (second derivative).
3. Drawdown-relative momentum (+10% from bottom of 30% drawdown vs. from ATH).
4. Peer-relative momentum ranking.
5. Momentum factor exposure shifts.

#### `volatility_compression`
1. Multi-timeframe squeeze detection (5d, 20d, 60d nested compression).
2. Bollinger Bandwidth integration (6-month low = major move imminent).
3. Historical compression outcome analysis per security.
4. Implied vs. realized volatility divergence (if options data available).
5. Sector-relative compression (whole sector compressed vs. just this stock).

#### `closing_strength`
1. Consecutive close positioning (5 days closing in bottom 20% = distribution).
2. Close position vs. volume interaction.
3. Open-to-close range vs. full range (who won the day).
4. Doji detection (close ~50%, small range after trend = reversal potential).
5. Institutional close analysis (last 15 minutes = MOC orders).

---

## 9. Analyst Actions (`analyst_actions.py` + `analyst_signals.py`)

**Signal:** `analyst_consensus_shift` — Tier D, weight 0.90, half-life 120h

### Summary
Fetches monthly analyst recommendation aggregates from Finnhub. Fires when month-over-month bull ratio shift exceeds 5%.

### Feature Inventory
- **Price target data**: Not collected. Consensus "buy" at $50 while trading at $48 vs. $20 is very different.
- **Individual analyst tracking**: Only aggregates. High-accuracy analyst changes matter more.
- **Upgrade/downgrade events**: Finnhub's `/stock/upgrade-downgrade` endpoint not used.
- **Earnings estimate revisions**: One of the strongest known predictive factors. Not collected.
- **Target price dispersion**: Wide disagreement = uncertainty. Not captured.
- **Analyst count trends**: Coverage dropping is itself a warning sign.
- **Sell rating rarity**: A first-ever sell rating is a categorical event.

### 5 Creative Ideas for the Collector
1. **Analyst Accuracy Weighting**: Build a historical accuracy database per analyst. Before Enron, several high-accuracy energy analysts quietly dropped coverage rather than downgrade — track coverage drops as shadow signal.
2. **Consensus vs. Price Divergence Alarm**: Strongly bullish consensus (>80% buy) while stock at 52-week lows = someone is wrong. Preceded Luckin Coffee, Wirecard.
3. **Herding Detection**: All analysts rapidly converging. Maximum herding (100% buy, 0 sell) is a contrarian warning.
4. **Silent Coverage Drop Tracker**: 20 analysts to 15 in 6 months = 5 analysts walked away without writing sell reports.
5. **Earnings Revision Momentum Engine**: Collect `/stock/eps-estimate`. Stocks where EPS estimates quietly revised down 5%+ while maintaining "buy" = highest-risk category. Would have flagged Wirecard 4 months early.

### 5 Creative Ideas for the `analyst_consensus_shift` Signal
1. **Velocity scoring**: Same magnitude shift in 1 month vs. 4 months is categorically different.
2. **Asymmetric weighting**: Bearish shifts 1.5x — analysts are reluctant to downgrade.
3. **Cross-reference with insider activity**: Consensus bearish + insider selling = confidence jumps to 0.95.
4. **Sector-relative consensus**: Only boost when shift is idiosyncratic vs. sector average.
5. **First-sell-rating detector**: Separate high-tier signal for first sell rating in years.

---

## 10. FTD Patterns (`ftd_patterns.py` + `ftd_signals.py`)

**Signal:** `ftd_spike` — Tier B, weight 1.30, half-life 168h

### Summary
Downloads SEC fail-to-deliver CSV data (biweekly ZIPs, 6-month lookback). Fires when total quantity > 500K shares or FTDs appear on 5+ distinct settlement dates in 60 days.

### Feature Inventory
- **Dollar-value normalization**: 100K FTDs on $5 stock ($500K) vs. $500 stock ($50M). Not normalized.
- **Float normalization**: 500K FTDs on 10M float (5%) is catastrophic; on AAPL (15B shares) is noise.
- **Trend detection**: 60-day aggregate only, no increasing/decreasing/spiking detection.
- **T+35 threshold monitoring**: Forced buy-in deadline not tracked.
- **Concentration analysis**: No per-date vs. spread-across analysis.
- **Cross-reference with short interest**: FTDs + high SI = naked short selling signature.
- **Recency weighting**: No decay within 60-day window.

### 5 Creative Ideas for the Collector
1. **T+35 Threshold Calendar**: Alert 5 days before large FTD blocks hit forced buy-in deadline. Exactly the mechanism behind the GameStop squeeze.
2. **FTD Cluster Topology Analyzer**: When FTDs spike on same dates across multiple same-sector securities, it suggests a single prime broker in distress. Preceded Bear Stearns collapse.
3. **FTD-to-Float Ratio as Tier S Signal**: When FTDs exceed 1% of float, almost always problematic. GameStop hit 140%.
4. **FTD Momentum Gradient**: Exponential growth trajectory (10K -> 50K -> 200K -> 800K over 4 weeks) matters more than absolute number.
5. **Synthetic Short Detection via ETF Arbitrage**: ETF FTDs spiking while constituent FTDs don't = someone shorting the ETF for synthetic sector exposure.

### 5 Creative Ideas for the `ftd_spike` Signal
1. **Float-normalized contribution**: Join with short interest collector's float data.
2. **Acceleration scoring**: Positive second derivative of FTDs = 30% contribution boost.
3. **Recency decay within window**: Exponential decay so recent FTDs weight more.
4. **Cross-signal confidence boost**: `ftd_spike` + `short_interest_spike` = confidence 0.95, the naked short fingerprint.
5. **Consecutive-day persistence bonus**: 5 consecutive days far more alarming than 5 scattered.

---

## 11. Options Flow (`options_flow.py` + `options_signals.py`)

**Signal:** `options_unusual_activity` — Tier A, weight 1.45, half-life 72h

### Summary
Scans 50 equities per day (rotating) via Polygon.io. Three sub-signals: volume concentration, deep OTM loading, and put/call skew.

### Feature Inventory
- **Open interest**: Missing (Polygon free tier limitation). Volume/OI ratio is the most critical metric.
- **Implied volatility**: Not captured. IV skew is one of the strongest crash predictors.
- **Time to expiration weighting**: No differentiation between expiring tomorrow vs. 6 months.
- **Greeks**: No delta, gamma, or vega.
- **Block trade detection**: No minimum size filter.
- **Dollar-notional volume**: 1000 contracts of $0.05 option ($5K) vs. $50 option ($5M).
- **Earnings proximity**: Activity near earnings is normal; far from any catalyst is suspicious.
- **Coverage rotation**: At 50/day, full universe coverage takes many days. High-priority tickers should scan daily.

### 5 Creative Ideas for the Collector
1. **Expiration Clustering Alarm**: 70%+ volume in single non-standard expiration = someone has a specific timeline. Enron puts were concentrated in December 2001 months before collapse.
2. **Synthetic Position Detector**: Deep OTM puts + ATM calls in equal notional = synthetic short (risk reversal). Detect paired structures.
3. **Options Volume vs. Stock Volume Divergence**: When options-implied share volume is 3x stock volume, smart money is in options. This ratio exceeds 1.0 before virtually every acquisition.
4. **Put Skew Persistence Tracker**: 5 consecutive days of put/call ratio > 2.0. Would have flagged Bear Stearns (extreme put skew for 2 weeks before collapse).
5. **Smart Money vs. Dumb Money Classifier**: Score trades by: block-sized, illiquid contract, far OTM, short expiry, bought on the ask.

### 5 Creative Ideas for the `options_unusual_activity` Signal
1. **Notional-dollar contribution**: $50M in put notional >> 10K contracts at $0.10.
2. **Catalyst proximity adjustment**: Suppress 50% if known catalyst (expected hedging), boost 50% if no catalyst.
3. **Time-to-expiration urgency**: <2 weeks = 1.5x, >6 months = 0.7x.
4. **Multi-day persistence tracking**: Same directional bias for 3+ days = Tier A; single-day = Tier C.
5. **Dynamic threshold by security**: 30-day baseline per security instead of absolute medians.

---

## 12. Short Interest (`short_interest.py` + `short_interest_signals.py`)

**Signal:** `short_interest_spike` — Tier B, weight 1.25, half-life 168h

### Summary
Fetches exchange-reported short interest from yfinance (biweekly). Composite score from percent-of-float (50%), month-over-month change (30%), and days-to-cover (20%).

### Feature Inventory
- **Historical time series**: Only most recent report. No multi-month trends.
- **Borrow rate / cost to borrow**: Not available from free tier. Most direct squeeze-risk measure.
- **Utilization rate**: Not available.
- **Sector-relative short interest**: No comparison against sector median.
- **Days-to-cover trend**: Not tracked because no historical preservation.
- **Reporting lag**: ~2 week delay. No staleness penalty.

### 5 Creative Ideas for the Collector
1. **Short Squeeze Pressure Score**: Combine SI + FTDs + put/call ratio + days-to-cover. When all exceed thresholds simultaneously, squeeze probability is extreme. Would have flagged GameStop 3 weeks early.
2. **SI Divergence from Fundamentals**: SI rising while financial health improving = contrarian bet worth investigating. SI rising AND material weaknesses = shorts are probably right.
3. **Stealth Short Accumulation Detector**: Use indirect signals (options put skew, FTDs, sector underperformance) to detect accumulation before official SI number publishes. 2-week edge.
4. **SI Mean Reversion Timer**: At 95th percentile of own history, start countdown. The longer extreme SI persists, the more likely a violent resolution.
5. **Crowded Short vs. Isolated Short Classifier**: Many funds short (crowded, high squeeze risk, see VW 2008) vs. one/two large funds (thesis may be well-researched). Cross-reference 13F data.

### 5 Creative Ideas for the `short_interest_spike` Signal
1. **Historical percentile scoring**: Where current SI falls in stock's own 2-year history, not fixed thresholds.
2. **Momentum weighting on log scale**: Remove the 50% MoM cap. Going from 5% to 10% SI (+100%) is a red alert.
3. **Days-to-cover step function**: DTC > 5 = moderate, > 7 = strong, > 10 = extreme.
4. **Float accuracy check**: Cross-validate against 10-K reported shares outstanding.
5. **Reporting lag decay**: Reduce confidence 3% per day since report date.

---

## 13. Sector Correlation (`sector_correlation.py` + `sector_correlation_signals.py`)

**Signal:** `sector_divergence` — Tier D, weight 0.90, half-life 72h

### Summary
Computes 15-day rolling Pearson correlations between each equity and its sector ETF. Fires when correlation drops below 0.3 or residual return exceeds 3%.

### Feature Inventory
- **Short window**: 15 days is the minimum. 30d and 60d would capture slower decorrelation.
- **Single metric**: Only Pearson. Spearman is more robust to outliers.
- **No correlation change detection**: Only current level, not drop from 0.9 to 0.3.
- **Beta instability**: Not tracked. Jumping beta = regime change.
- **Subsector granularity**: Only broad sector ETFs. Semiconductor stock vs. XLK may just be tracking SMH.
- **Factor exposure decomposition**: No multi-factor model.

### 5 Creative Ideas for the Collector
1. **Correlation Regime Change Detector**: Chow test or CUSUM test for structural breaks. Wirecard's correlation broke structurally 6 months before fraud confirmed.
2. **Cross-Sector Migration Detector**: Compute correlation against all 11 sector ETFs simultaneously. When highest-correlation sector changes, signals fundamental business shift. AIG was financials but shifted to insurance/catastrophe factors months before CDO exposure surfaced.
3. **Contagion Propagation Map**: Model which stock decorrelated first within each sector. First-mover is either source of stress or most exposed.
4. **5-Factor Attribution**: Sector ETF + SPY + HYG + VIX + size factor. Large residual after all 5 = genuine idiosyncratic component.
5. **Correlation Dispersion Index**: Per-sector cross-sectional dispersion. Healthy sectors have tight dispersion; stressed sectors have wide dispersion. New market-level signal.

### 5 Creative Ideas for the `sector_divergence` Signal
1. **Correlation delta scoring**: Score the change, not the level. Drop from 0.85 to 0.25 in 2 weeks >> stock that's always at 0.25.
2. **Multi-window confirmation**: Only fire when decorrelation in BOTH 15d and 30d windows.
3. **Residual return persistence**: 3 consecutive 1.5% days > 1 day at 3%.
4. **Peer-group validation**: If 3+ stocks decorrelate, downgrade (sector fracturing). If only 1, upgrade (company-specific).
5. **Cross-signal conditional confidence**: Decorrelation + insider selling/FTD spike/material weakness within 7 days = confidence 0.85.

---

<a id="alt-data"></a>
# Alt-Data / Blockchain Collectors

---

## 14. News Sentiment (`news_sentiment.py` + `news_signals.py`)

**Signals:** `news_sentiment_extreme` (Tier E, weight 0.75) + `news_volume_spike` (Tier D, weight 0.85)

### Summary
Fetches company-specific headlines from Finnhub over a rolling 3-day window. Keyword-based sentiment scoring (~65 words). Fires on sentiment extremes (avg outside +/-0.3) and volume spikes (3x+ median).

### Feature Inventory
- **NLP model-based sentiment**: Keyword bag is ~65 words. "Faces headwinds but analysts remain cautiously optimistic" scores 0.0 when it should score slightly negative. FinBERT or VADER would dramatically improve.
- **Source credibility weighting**: Reuters/Bloomberg/WSJ should carry more weight than PR Newswire.
- **Temporal decay**: Headline from 6 hours ago matters more than 2.5 days ago. All equally weighted.
- **Duplicate detection**: Wire stories reprinted across 5-10 outlets inflate both volume and sentiment.
- **Category-aware scoring**: `category` field stored but never used.
- **Missing `last_updated` column**: Schema bug — `ON CONFLICT` references it but CREATE TABLE doesn't define it.
- **Crypto skipped**: Explicit skip of crypto tickers despite Finnhub having crypto news endpoints.

### 5 Creative Ideas for the Collector
1. **Narrative Arc Tracking**: Track sentiment derivative over time. Neutral to sharply negative over 48 hours is different from consistently negative for a month.
2. **Cross-Security Contagion Detection**: 5+ securities in same GICS sector all spike negative within 24 hours = sector sentiment contagion meta-signal.
3. **Headline Embedding Anomaly Detection**: sentence-transformers embeddings, rolling centroid per security. New headline far from centroid = "narrative break" signal.
4. **Regulatory Language Classifier**: Detect SEC enforcement patterns (subpoena, consent decree, Wells notice) and bypass normal pipeline for high-confidence governance signal.
5. **Counter-Narrative Detection**: 9 positive headlines + 1 strongly negative from credible source. "Dissent score" measuring variance across sources.

### Signal Ideas: `news_sentiment_extreme`
1. Tier promotion via back-testing against 2 years of market data.
2. Source-weighted sentiment contribution.
3. Earnings window suppression (3 days around earnings).
4. Cross-signal amplification with `insider_sale_cluster` (1.3x when co-occurring within 7 days).
5. Sentiment persistence scoring — only fire when sustained 48+ hours.

### Signal Ideas: `news_volume_spike`
1. Directional volume — split into positive and negative spike sub-signals.
2. Pre-event detection — volume before known events more interesting than on event date.
3. Relative-to-sector volume (utility getting 20 articles when sector averages 3 is extreme).
4. Volume-sentiment divergence — volume spike + neutral sentiment = complex event unfolding.
5. Wire duplication discount — cluster near-duplicates before counting.

---

## 15. Prediction Markets (`prediction_markets.py` + `prediction_market_signals.py`)

**Signal:** `prediction_market_heat` — Tier C, weight 1.10, half-life 168h

### Summary
Scrapes Polymarket (CLOB API) and Kalshi for active markets. Maps to securities via keyword matching on ~40 topic-to-ticker mappings. Fires when security has 2+ markets or >$100K volume.

### Feature Inventory
- **Probability delta tracking**: Only latest snapshot. Should fire on changes (0.30 to 0.75 in 48h is far more interesting than sitting at 0.75).
- **Market liquidity weighting**: Volume used in scoring but not as confidence weight on probability.
- **Bid-ask spread as uncertainty proxy**: Fetched but not used.
- **Time-to-expiry normalization**: Not captured.
- **Missing platforms**: Only 2 sources. Metaculus, Manifold Markets, PredictIt would increase coverage.
- **Direction inference**: Always "neutral." "Will BTC exceed $100K?" at 0.90 is clearly bullish.
- **No resolution tracking**: No comparison of outcome to signal-fire probability for backtesting.
- **Topic-ticker mapping is static**: Hardcoded dict requires manual updates.

### 5 Creative Ideas for the Collector
1. **Probability Velocity Alerts**: 15+ percentage point move in 24h on >$50K volume = "extreme belief shift." Contribution proportional to velocity * sqrt(volume).
2. **Implied Probability Disagreement**: Polymarket vs. Kalshi disagree by >15 points = signal itself (one has better info, or there's an arb).
3. **Conditional Market Chaining**: "Fed cuts rates" at 0.80 * "If Fed cuts, TLT rises 5%+" at 0.65 = 0.52 implied. Compound reasoning more powerful than either alone.
4. **Smart Money vs. Crowd Divergence**: Large trades push one way, retail pushes the other. Historically, whales win. Build "smart money flow" layer on CLOB data.
5. **Resolution-Based Calibration Scoring**: Track Brier scores per source/topic. Dynamically adjust `base_weight` based on calibration.

### 5 Creative Ideas for the `prediction_market_heat` Signal
1. **Probability change as primary driver**: `|prob_today - prob_7d_ago|` instead of static extremity.
2. **Directional inference**: Parse market question to determine bull/bear.
3. **Volume-weighted probability**: $10M market at 0.70 and $50K market at 0.30 should weight to ~0.70.
4. **Resolution feedback loop**: Brier scores per topic category for dynamic weight adjustment.
5. **Event-specific sub-signals**: Split into `pm_rate_decision`, `pm_price_target`, `pm_bankruptcy`, etc.

---

## 16. Crypto Whale Tracker (`crypto_whale.py` + `blockchain_signals.py`)

**Signal:** `blockchain_anomaly` — Tier B, weight 1.20, half-life 48h

### Summary
Monitors BTC mempool for large transactions (>10 BTC). Tags as exchange-bound (selling pressure) or exchange-outbound (accumulation). Combined with exchange flows and on-chain metrics.

### Feature Inventory
- **BTC-only**: No ETH whale tracking despite ETH-USD in securities universe.
- **Small exchange wallet list**: Only 9 addresses across 5 exchanges.
- **No wallet clustering**: Unknown addresses receiving from known exchange addresses not flagged.
- **Mempool-only**: Confirmed blocks with whale transactions missed between collection runs.
- **No UTXO age analysis**: Satoshi-era coins moving is qualitatively different from mining pool payouts.
- **Exchange balance deltas not computed**: `exchange_flow.py` data collected but never queried by signals.
- **Static 10 BTC threshold**: Should be dynamic based on recent average.
- **Malformed Kraken address**: The Kraken bech32 address appears truncated or invalid.

### 5 Creative Ideas for the Collector
1. **Dormant Wallet Resurrection Alerts**: Track top 1000 largest BTC wallets. Dormant >2 years suddenly moving = high-priority. Historically precedes 10-20% swings within 72 hours.
2. **Exchange Net Flow Delta Signal**: Actually USE the `raw_exchange_flows` data: `today - yesterday` per exchange. Aggregate net flow > +/- 5000 BTC/24h = directional signal. Data already collected, just not used.
3. **Miner Capitulation Detection**: Hash rate drops + BTC outflows from mining pool addresses = miner capitulation (historically a bottom signal).
4. **Multi-Chain Whale Correlation**: BTC + ETH whales moving simultaneously in same direction = stronger than either alone.
5. **Transaction Graph Clustering**: Common-input-ownership heuristics. New entity appearing with >100 BTC = OTC desk or undisclosed institutional entry.

### 5 Creative Ideas for the `blockchain_anomaly` Signal
1. **Decompose into sub-signals**: `whale_movement`, `exchange_net_flow`, `chain_congestion` with independent weights.
2. **Actually incorporate exchange flow data**: Day-over-day balance deltas from `raw_exchange_flows`.
3. **Cross-asset propagation via crypto_exposure**: When fires for BTC-USD, propagate to MSTR, COIN, MARA scaled by exposure_score.
4. **Whale direction consensus**: `net_direction = (from_exchange - to_exchange) / total`. Strong positive = accumulation.
5. **Temporal clustering detection**: 10 transactions in 30 minutes (panic/coordination) >> 10 over 24 hours. Use sub-hourly timestamps.

---

## 17. Exchange Flow Monitor (`exchange_flow.py`)

**Feeds:** `blockchain_signals.py` (but currently NOT consumed)

### Summary
Daily snapshots of known exchange wallet balances on Bitcoin via Blockchain.com. **Critical issue**: output is never queried by signal extractor.

### Feature Inventory
- **Not consumed**: `blockchain_signals.py` never queries `raw_exchange_flows`.
- **Only 4 exchanges, 7 addresses**.
- **BTC only**: No ETH exchange flow tracking.
- **No delta computation**: Only raw balances stored.
- **No stablecoin flows**: USDT/USDC flows are a leading indicator.
- **Single daily snapshot**: Balances change dramatically intraday.

### 5 Creative Ideas
1. **Multi-Exchange Flow Correlation Matrix**: Consensus moves vs. divergent moves across all exchanges.
2. **Stablecoin Precursor Signal**: Monitor Tether Treasury + Circle for mint/burn events. Large mints precede rallies by 24-72 hours.
3. **Exchange Reserve Ratio**: `exchange_total_btc / total_supply` as macro indicator.
4. **Withdrawal Spike Detection**: Rate of withdrawals (retail buying) vs. deposits (selling pressure).
5. **Cross-reference with options and prediction markets**: Exchange inflows + put/call spike + prediction markets down = multi-source convergence meta-signal.

---

## 18. On-Chain Activity (`onchain_activity.py`)

**Feeds:** `blockchain_signals.py`

### Summary
Daily chain-level metrics for BTC and ETH: tx counts, mempool, hash rate, difficulty, block size, gas prices.

### Feature Inventory
- **Only mempool congestion used**: Hash rate, difficulty, tx count, block size, gas price all collected and ignored.
- **No historical comparison**: Static thresholds (BTC >50K, ETH >100K). No rolling average comparison.
- **No active address counts**: One of the strongest on-chain fundamentals. Available but not fetched.
- **No Layer 2 data**: Lightning Network, Arbitrum, Optimism, Base.
- **Single daily snapshot**: On-chain metrics most useful for intraday spike detection.

### 5 Creative Ideas
1. **NVT Ratio**: `market_cap / daily_tx_volume_usd`. High = overvalued, low = undervalued. All inputs already collected.
2. **Hash Rate Cliff Detection**: >10% drop in single day. Correlated with miner distress, geographic bans.
3. **Gas/Fee Spike Regime Detection**: Classify chain into regimes (calm/active/congested/crisis). Track transitions.
4. **Active Address Momentum**: 7d/30d active address ratio. >1.5x = new users flooding in (bullish). <0.7x = users leaving (bearish).
5. **Cross-Chain Divergence Signal**: BTC and ETH metrics diverge = relative performance predictor. Fire when z-scores differ by >2 std devs.

---

## 19. Crypto Exposure Estimator (`crypto_exposure.py`)

**Supporting collector — not a direct signal producer**

### Summary
Classifies securities by crypto exposure level (PURE_PLAY, HIGH, MODERATE, LOW, NONE) via curated list, keyword scanning, and Finnhub profile analysis.

### Feature Inventory
- **Static known list**: Holdings change quarterly. MicroStrategy's position changes weekly.
- **No holdings quantification**: Categorical estimate, not dollar amounts.
- **Keyword matching fragile**: "Blockchain is not part of our business" matches positive.
- **Not consumed downstream**: Despite docstring claims, whale tracker doesn't query this table.
- **ETF holdings not decomposed**: SPY contains COIN, MSTR but gets NONE exposure.
- **Duplicate COIN entry**: Appears twice in `KNOWN_CRYPTO_HOLDINGS`.

### 5 Creative Ideas
1. **SEC 10-K Mining**: Search EDGAR for "bitcoin," "digital asset," "cryptocurrency" and parse surrounding text for dollar amounts.
2. **On-Chain Proof of Treasury**: For companies disclosing wallet addresses, verify holdings on-chain in real time. Discrepancy = flag.
3. **Dynamic Exposure from Price Beta**: Rolling 30-day beta vs. BTC-USD. Empirical approach catches indirect exposure.
4. **ETF Look-Through Decomposition**: Fetch ETF holdings, compute weighted exposure score.
5. **Crypto Exposure as Contagion Weight**: When `blockchain_anomaly` fires for BTC-USD, propagate fraction to every equity weighted by exposure_score. Turns the table into a cross-asset contagion transmission matrix.

---

# Summary Statistics

| Category | Collectors | Signals | Ideas Generated |
|----------|-----------|---------|-----------------|
| SEC/Governance | 10 | 10 | ~100 |
| Market/Trading | 6 | 14 | ~100 |
| Alt-Data/Blockchain | 6 | 4 | ~80 |
| Cross-Cutting | — | — | 8 |
| **Total** | **21** | **24** | **~288** |
