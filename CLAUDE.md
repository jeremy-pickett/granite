# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Always check `TODO.md` at the start of every session.** It tracks in-progress experimental layers, integration status, and open items. If the user references ongoing work without context, the answer is probably in there.

## Project Overview

Granite Under Sandstone is a research project implementing **Compression-Amplified Provenance Signal Detection** for digital media. It embeds imperceptible statistical perturbations (provenance signals) into images that survive and amplify under lossy JPEG compression. The key insight: the signal is not the perturbation itself—it's the system's statistical response to the perturbation over multiple compression generations.

## Setup & Dependencies

Pure Python, no build system. Install dependencies:
```bash
pip3 install Pillow numpy scipy matplotlib
```

Dataset: DIV2K (validation set = 100 images, training set = 800 images) downloaded separately.

## Running Tests

There is no unit test suite or pytest configuration. Tests are experimental harnesses run manually.

**Main validation test (The Granite Test):**
```bash
# Quick sanity check (5 images)
python backend/tests/div2k_harness_v2.py -i /path/to/DIV2K_valid_HR -o results -n 5

# Validation set (100 images)
python backend/tests/div2k_harness_v2.py -i /path/to/DIV2K_valid_HR -o results

# Full training set (800 images)
python backend/tests/div2k_harness_v2.py -i /path/to/DIV2K_train_HR -o results
```

**Other test harnesses** (all in `backend/tests/`):
- `cascade_test.py` — Multi-generation JPEG cascade survival
- `scale_test.py` — Scale/resize/fingerprint stability
- `channel_pair_test.py` — RGB channel pair independence
- `jpeg_to_webp.py` — Cross-codec boundary testing
- `slice_attack.py` — Slice-and-stitch attack simulation
- `rotation_attack.py` — Geometric attack simulation
- `prime_floor_sweep.py` — Basket floor parameter sweep

No linting or formatting configuration exists.

## Critical Design Rule: Blind Detection is Priority One

**Blind detection must work robustly before anything else matters.** Manifest-based detection (known marker positions) is for internal QA only — it will never be used in production. Every embedding strategy and every detection layer must be validated against the blind verifier (`src/verify_image.py`) with zero shared state: inject → save to disk → hand the file to the verifier with no manifest, no positions, no seed.

**Fixed (2026-03-30):** Three bugs in the compound marker pipeline were fixed:
1. **Grid alignment**: Replaced entropy-biased random position selection with deterministic stride-based selection. Verifier can now reconstruct marker grid without a manifest.
2. **Luma domain**: Migrated Layer 2 from R-G inter-channel distance (destroyed by JPEG 4:2:0 chroma subsampling) to adjacent-pixel luma difference |Y(r,c)-Y(r,c+1)|. Luma survives because Y is not subsampled. Natural false positive rate dropped from ~12% to ~0%.
3. **Dynamic density**: Replaced hardcoded n_markers=400 with dynamic ceil(grid_capacity * 0.15). Embed rate ~85% (515/615 on 512px image).
Results: Blind detection CONFIRMED (3 signals) lossless, PROBABLE (2 signals) through Q85. Known-position detection p<1e-51 through Q75.

**Sanity check:** `backend/tests/sanity_inject_verify.py` runs the full inject→verify pipeline on the DIV2K test images. Run this before claiming any detection layer works.

**All-layers rule:** Unless specifically instructed otherwise, when working with ANY layer, work with ALL layers. They inform each other — a change to one layer's embedding or detection affects the signal environment for others. Always test the full multi-layer pipeline (inject all layers → verify all layers), never a single layer in isolation.

## Architecture

### Detection Layers

1. **Layer 1 — DQT Prime Tables** (`src/dqt_prime.py`): Replaces JPEG quantization table entries with nearest primes. The table itself is the provenance signal. Survives re-encoding as double-quantization artifacts.

2. **Layer 2 — Compound Markers** (`src/compound_markers.py`, `src/layer2_detect.py`): Embeds prime luma-pair distances at deterministic grid positions. Distance metric: |Y(r,c) - Y(r,c+1)| (adjacent-pixel luma difference — survives JPEG 4:2:0). Compound strategies (twin + magic sentinel + rare basket) reduce false positive probability. Natural false positive rate: ~0%.

3. **Layer 3 — Rare Basket** (via `src/smart_embedder.py`): Position pattern derived from 256-bit seed via HMAC-SHA512, enabling attribution through Jaccard similarity at corpus scale.

4. **Layer G — Radial Halos** (`src/halo.py`): Two-zone radial lensing field around Mersenne sentinel positions. Inner disk |R-G|=98, outer ring |R-G|=60. Three detection states: PRESENT, VOID (sentinel removed, halo remains), ABSENT. Rotation-invariant. Wired into inject→verify pipeline.

5. **Layer H — Spatial Rulers** (`src/layer_h_ruler.py`): 16px-wide bands with |R-G|=198 (vertical) or |G-B|=198 (horizontal) at deterministic fractions of image dimensions. Encodes original dimensions, timestamp, and session hash. Detects crop and stitch attacks. JPEG survival: zero bit errors Q30-Q95. Wired into inject→verify pipeline.

### Core Modules (`backend/src/`)

- **`pgps_detector.py`** — Foundation: prime utilities (sieve), sampling strategies, distance extraction, statistical tests (chi-squared, KS). Entry point for blind aggregate detection.
- **`compound_markers.py`** — Marker embedding strategies: Rare Basket, Twin Markers, Magic Sentinel, and Compound (all three combined).
- **`dqt_prime.py`** — Prime quantization table embedding and detection (Strategy 4 / Douglas Rule).
- **`smart_embedder.py`** — Format-aware embedding with file-type profiles (JPEG, PNG, WebP, Audio) and entropy gating. Doctrine: "The injector does the homework so the detector doesn't have to."
- **`layer2_detect.py`** — Known-position detection. Solves the false positive problem by comparing marker vs. non-marker positions within the same image.
- **`fp_forensics.py`** — False positive forensics: per-distance breakdown, chi-squared analysis, DCT grid mapping. Used to understand why JPEG structure can mimic prime-gap signals.

### Signal Pipeline

Embedding → JPEG cascade (Q95→85→75→60→40) → Detection via KS test, variance ratio, enrichment ratio, and amplification pattern → Verdict (CONFIRMED / PARTIAL / NOT CONFIRMED).

### Key Metrics

- **KS p-value**: Kolmogorov-Smirnov test comparing marker vs control distance distributions
- **Variance ratio**: Marker position variance / control position variance (>1.0 = signal present)
- **Enrichment ratio**: Marker prime hit rate / control prime hit rate
- **Amplification**: Whether variance ratio increases across compression generations

### Output Files

Test harnesses produce: `results.jsonl` (per-image metrics), `aggregate.json` (summary stats), `VERDICT.txt` (final determination), and `granite_test.png` (visualization).

## Key Results (800-image DIV2K)

- G-B channel detection rate: 96.4% (KS p<0.05)
- R-G channel detection rate: 90.1%
- Amplification confirmed in 48.1% of images
- Verdict: GRANITE PARTIAL — effect is real but content-class dependent

## Format Performance Notes

Most testing has been in adversarial environments (JPEG cascades, cross-codec transcoding, geometric attacks). For lossless formats like PNG, the signal works near-perfectly without the edge cases that aggressive compression introduces. Initial testing on MP3, H.264/H.265, and other lossy media formats using quantization schemes has exceeded expectations — the partition→transform→quantize mechanism is universal.

## Alidade / IALD Scoring System

### Design Philosophy: Assume Every Asset Is Pre-Collapse

Every security in the system should be treated as a potential Enron, Bear Stearns, or WeWork. The default posture is suspicion — filings, advisories, warnings, auditor changes, executive departures, ownership concentration shifts, all of it matters. Collectors exist to surface the early signals that precede catastrophic failure. When building or extending a collector, ask: "Would this have caught Enron six months earlier?" If it wouldn't have, it's not aggressive enough.

### IALD Signal Count Rule

**`collectors/signal_config.py` is the single source of truth for all IALD signals.** The `_DECLARED_COUNT` constant at the bottom of that file MUST match the actual number of active signals in `SIGNAL_CONFIG`. The file has a runtime assertion that enforces this. When adding or removing a signal, update both the dict and the count. Do NOT add aspirational/placeholder signals — every entry must have a live collector or derived-signal job that writes to the `signals` table.

### Scoring Pipeline

```
collectors/           → write to raw_* tables (e.g. raw_market_data)
market_signals.py     → read raw tables, detect anomalies, write to `signals` table
score_engine.py       → read `signals`, apply weights/decay/clusters, write to `iald_scores`
                        then refresh `score_aggregates`
```

Run the full pipeline: `python collectors/collectors_run.py`

### IALD Score Scale

Scores are **0.0 to 1.0** everywhere: database, API, frontend. Verdicts:
- >= 0.75 → CRITICAL (red)
- >= 0.50 → ELEVATED (amber)
- >= 0.25 → MODERATE (blue)
- < 0.25  → LOW (dim)

### Collector Framework

All collectors live in `collectors/` and inherit from `BaseCollector` in `base.py`. Lifecycle: `setup() → fetch() → transform() → store() → teardown()`. Copy `_template.py` to start a new one. Register in `collectors_run.py` REGISTRY dict.

**Collector checklist** — when creating or modifying a collector:
1. Every collector must run once per day via cron (staggered at 15-min intervals starting 06:00 UTC). Add the cron entry and verify it with `crontab -l`.
2. All `raw_*` tables must have both `collected_at` (first seen) and `last_updated` (last confirmed) columns. On duplicate insert, use `ON CONFLICT ... DO UPDATE SET last_updated = now()` — never `DO NOTHING`.
3. Verify the collector runs end-to-end against the full securities list before considering it done.

### Collector Status (as of 2026-03-31)

**18 live collectors**, 22 active signals, 12 daily cron jobs (06:00–07:14 UTC staggered).

Live — sec_filing: Auditor Change Monitor, C-Suite Departure Tracker, Concentration Disclosure, Material Weakness Scanner (+ Late Filings, Financial Restatements, Going Concern feeding composite signal), SEC 13F Monitor, SEC Form 4 Parser.

Live — market_data: Market Data (Daily), Earnings Calendar, Analyst Revision Tracker, FTD Pattern Analyzer, Options Flow Scanner.

Live — blockchain: Crypto Whale Tracker (BTC mempool whale txs), Exchange Flow Monitor (daily exchange wallet balance snapshots), On-Chain Activity (BTC/ETH chain metrics via blockchain.com + blockchair + etherscan v2). Required adding BTC-USD and ETH-USD to the securities table.

Live — other: Congressional Trade Feed, Social Velocity Scanner (news sentiment via Finnhub), Crypto Exposure Estimator, Prediction Market Feed (Polymarket + Kalshi).

**Dark (need paid APIs):** Short Interest Tracker (5), Stock Loan Rate Monitor (6), Dark Pool Volume (7), ADR Spread Monitor (13), Convertible Spread Tracker (14). **Derivable from existing data:** Sector Correlation Engine (15).

### Key Tables

- `signals` — normalized signal rows (security_id, signal_type, contribution, confidence, direction, magnitude)
- `iald_scores` — daily scores per security (score, verdict, active_signals)
- `score_aggregates` — rolling 30d stats (avg, min, max, volatility, trend)
- `raw_market_data` — OHLCV from market_data collector
- `collectors` — registry of all 23 collectors with run status
- `collector_coverage` — per-security data availability per collector
