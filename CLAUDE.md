# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
python granite/tests/div2k_harness_v2.py -i /path/to/DIV2K_valid_HR -o results -n 5

# Validation set (100 images)
python granite/tests/div2k_harness_v2.py -i /path/to/DIV2K_valid_HR -o results

# Full training set (800 images)
python granite/tests/div2k_harness_v2.py -i /path/to/DIV2K_train_HR -o results
```

**Other test harnesses** (all in `granite/tests/`):
- `cascade_test.py` — Multi-generation JPEG cascade survival
- `scale_test.py` — Scale/resize/fingerprint stability
- `channel_pair_test.py` — RGB channel pair independence
- `jpeg_to_webp.py` — Cross-codec boundary testing
- `slice_attack.py` — Slice-and-stitch attack simulation
- `rotation_attack.py` — Geometric attack simulation
- `prime_floor_sweep.py` — Basket floor parameter sweep

No linting or formatting configuration exists.

## Architecture

### Three Detection Layers

1. **Layer 1 — DQT Prime Tables** (`src/dqt_prime.py`): Replaces JPEG quantization table entries with nearest primes. The table itself is the provenance signal. Survives re-encoding as double-quantization artifacts.

2. **Layer 2 — Compound Markers** (`src/compound_markers.py`, `src/layer2_detect.py`): Embeds twin-prime markers at known positions. Detection compares prime-gap hit rate at marker positions vs. control positions in the same image (image is its own control group). Compound strategies (twin + magic sentinel + rare basket) reduce false positive probability.

3. **Layer 3 — Rare Basket** (via `src/smart_embedder.py`): Position pattern derived from 256-bit seed via HMAC-SHA512, enabling attribution through Jaccard similarity at corpus scale.

### Core Modules (`granite/src/`)

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
