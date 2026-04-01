# Detection Test Results — 2026-03-30

Systematic investigation into why the web inject→verify pipeline returns PARTIAL (only DQT detected) even on freshly injected images.

## Test Image Set

10 DIV2K validation samples in `backend/test-images/`:
0057.png, 0185.png, 0259.png, 0348.png, 0487.png, 0538.png, 0588.png, 0683.png, 0710.png, 0786.png

All high-resolution PNG, ranging from 936×2040 to 1356×2040.

---

## Test 1: Blind Inject → Verify (Same Pipeline as Web UI)

Injected with `injection_report.generate_injection_report()` (compound profile), verified with `verify_image.verify_image()`. Zero shared state.

| Image | Format | Verdict | DQT | PrimeRate | TwinRate | MagicRate | Signals |
|-------|--------|---------|-----|-----------|----------|-----------|---------|
| 0057.png | JPEG | PARTIAL | YES | 0.0215 | 0.0156 | 0.0003 | 1 |
| 0185.png | JPEG | PARTIAL | YES | 0.0300 | 0.0166 | 0.0007 | 1 |
| 0259.png | JPEG | PARTIAL | YES | 0.0155 | 0.0109 | 0.0002 | 1 |
| 0348.png | JPEG | PARTIAL | YES | 0.0084 | 0.0023 | 0.0001 | 1 |
| 0487.png | JPEG | PARTIAL | YES | 0.0096 | 0.0025 | 0.0004 | 1 |
| 0538.png | JPEG | PARTIAL | YES | 0.0024 | 0.0009 | 0.0003 | 1 |
| 0588.png | JPEG | PARTIAL | YES | 0.0234 | 0.0066 | 0.0017 | 1 |
| 0683.png | JPEG | PARTIAL | YES | 0.0531 | 0.0288 | 0.0011 | 1 |
| 0710.png | JPEG | PARTIAL | YES | 0.0116 | 0.0039 | 0.0003 | 1 |
| 0786.png | JPEG | PARTIAL | YES | 0.0364 | 0.0327 | 0.0001 | 1 |

**Result: 10/10 PARTIAL. Only DQT detected. All Layer 2+ signals invisible.**

Detection thresholds: PrimeEnrich > 0.20 | TwinRate > 0.04 | MagicRate > 0.008

---

## Test 2: Grid Alignment Diagnostic

Compared where the injector places markers vs where the blind verifier scans.

| Image | Injected | Verifier Grid | On Grid | Missed | Overlap% | Dilution |
|-------|----------|--------------|---------|--------|----------|----------|
| 0057.png | 362 | 86,700 | 181 | 181 | 50.0% | 479.0x |
| 0185.png | 538 | 73,440 | 269 | 269 | 50.0% | 273.0x |
| 0259.png | 502 | 82,620 | 251 | 251 | 50.0% | 329.2x |
| 0348.png | 434 | 80,580 | 217 | 217 | 50.0% | 371.3x |
| 0487.png | 360 | 86,700 | 180 | 180 | 50.0% | 481.7x |
| 0538.png | 504 | 86,700 | 252 | 252 | 50.0% | 344.0x |
| 0588.png | 326 | 86,700 | 163 | 163 | 50.0% | 531.9x |
| 0683.png | 396 | 86,700 | 198 | 198 | 50.0% | 437.9x |
| 0710.png | 390 | 59,670 | 195 | 195 | 50.0% | 306.0x |
| 0786.png | 492 | 86,700 | 246 | 246 | 50.0% | 352.4x |

**Result: 50% of markers land off-grid (invisible to verifier). ~390x dilution.**

Root cause: `embed_compound()` uses entropy-biased random position selection from the top 50% of grid positions. The blind verifier scans all grid positions uniformly, drowning the sparse signal.

---

## Test 3: Density Sweep (10%–90% of grid, blind detection)

Single image (0538.png), compound profile, varying `n_markers` as percentage of grid capacity (43,350 positions).

| Density | Requested | Placed | Verdict | DQT | PrimeRate | TwinRate | MagicRate |
|---------|-----------|--------|---------|-----|-----------|----------|-----------|
| 10% | 4,335 | 2,677 | PARTIAL | YES | 0.0008 | 0.000185 | 0.000000 |
| 20% | 8,670 | 5,358 | PARTIAL | YES | 0.0018 | 0.000161 | 0.000000 |
| 30% | 13,005 | 8,009 | PARTIAL | YES | 0.0028 | 0.000554 | 0.000000 |
| 40% | 17,340 | 10,640 | PARTIAL | YES | 0.0041 | 0.000854 | 0.000000 |
| 50% | 21,675 | 13,306 | PARTIAL | YES | 0.0039 | 0.000784 | 0.000000 |
| 60% | 26,010 | 16,742 | PARTIAL | YES | 0.0042 | 0.000761 | 0.000000 |
| 70% | 30,344 | 20,409 | PARTIAL | YES | 0.0051 | 0.000807 | 0.000000 |
| 80% | 34,680 | 24,272 | PARTIAL | YES | 0.0066 | 0.001223 | 0.000023 |
| 90% | 39,015 | 28,290 | PARTIAL | YES | 0.0069 | 0.001453 | 0.000000 |

**Result: Even at 90% density, blind detection fails. PrimeRate 0.007 vs threshold 0.20.**

This proved density is not the primary issue — JPEG encoding is destroying the signal before the verifier even looks.

---

## Test 4: Naive Full-Image Scan (Where Are the Primes After JPEG?)

Injected 0538.png at 50% density (26,612 marker positions). Scanned every pixel for prime |R-G| ≥ 53.

### Prime pixel counts

| Stage | Prime pixels | Of 2,766,240 total |
|-------|-------------|-------------------|
| Clean image (no injection) | 23 | 0.00% |
| Post-injection (pre-JPEG) | 31,108 | 1.12% |
| Post-JPEG Q95 | 33 | 0.00% |

### What happened to injected distances after JPEG?

| Outcome | Count | Rate |
|---------|-------|------|
| Survived exact (same prime) | 0 | 0.0% |
| Survived fuzzy ±1 (still prime) | 0 | 0.0% |
| Survived fuzzy ±2 (still prime) | 0 | 0.0% |
| Destroyed (no longer prime) | 26,612 | 100.0% |

### Distance shift distribution

- Mean shift: **-91**
- Median shift: **-86**
- Std: 37.2
- Range: -189 to -13

**Result: 100% of markers destroyed. JPEG systematically collapses |R-G| toward zero (mean shift -91). The signal isn't hiding elsewhere — it's gone.**

### Per-prime survival

| Prime | Injected | Survived | Post-JPEG avg distance |
|-------|----------|----------|----------------------|
| 53 | 990 | 0 | 16.7 |
| 67 | 1,079 | 0 | 17.9 |
| 97 | 1,099 | 0 | 20.2 |
| 127 | 989 | 1 | 23.1 |
| 151 | 836 | 3 | 25.9 |
| 181 | 583 | 3 | 30.0 |
| 199 | 174 | 0 | 31.9 |

No prime value survives. All distances collapse to ~17–32 regardless of original value.

---

## Test 5: Chroma Subsampling — The Root Cause

Compared `encode_prime_jpeg`, normal Pillow JPEG (4:2:0 default), 4:4:4 (no chroma subsampling), and PNG.

| Encoding | Subsampling | Survived (of 26,612) | Rate | Mean shift |
|----------|------------|---------------------|------|------------|
| PNG lossless | n/a | 26,612 | 100.0% | 0 |
| JPEG Q100 4:4:4 | none | 10,148 | 38.1% | +0.4 |
| JPEG Q95 4:4:4 | none | 1,336 | 5.0% | +1.2 |
| JPEG Q85 4:4:4 | none | 395 | 1.5% | -16.5 |
| JPEG Q75 4:4:4 | none | 37 | 0.1% | -69.3 |
| JPEG Q100 4:2:0 | 2×2 avg | 0 | 0.0% | -89.9 |
| JPEG Q95 4:2:0 | 2×2 avg | 0 | 0.0% | -91.3 |
| Normal JPEG Q95 | 2×2 avg | 0 | 0.0% | -91.3 |
| Prime JPEG Q95 | 2×2 avg | 0 | 0.0% | -91.3 |

**Root cause confirmed: JPEG 4:2:0 chroma subsampling averages R and G channels across 2×2 blocks, collapsing inter-channel distances toward zero. This is an instant kill for any R-G distance-based signal.**

Even with 4:4:4 (no subsampling), DCT quantization below Q95 destroys most of the signal.

`encode_prime_jpeg` is not the culprit — normal Pillow JPEG produces identical destruction.

---

## Test 6: Manifest-Based Detection Across Encodings

Using `layer2_detect()` with full knowledge of marker positions. 10 images, 50% density.

| Encoding | Detection rate | Avg marker ρ | Avg control ρ | Avg ratio | Avg χ² p |
|----------|---------------|-------------|--------------|-----------|----------|
| PNG lossless | 10/10 (100%) | 1.0000 | 0.0038 | inf | 0.00e+00 |
| JPEG Q100 4:4:4 | 10/10 (100%) | 0.3974 | 0.0041 | inf | 0.00e+00 |
| JPEG Q95 4:4:4 | 10/10 (100%) | 0.2020 | 0.0043 | inf | 0.00e+00 |
| JPEG Q85 4:4:4 | 10/10 (100%) | 0.1490 | 0.0046 | 268.0x | 0.00e+00 |
| JPEG Q75 4:4:4 | 10/10 (100%) | 0.0650 | 0.0047 | 42.7x | 9.57e-179 |
| JPEG Q100 4:2:0 | 9/10 (90%) | 0.0147 | 0.0038 | inf | 4.08e-03 |
| JPEG Q95 4:2:0 | 9/10 (90%) | 0.0131 | 0.0039 | inf | 6.16e-02 |
| JPEG Q85 4:2:0 | 5/10 (50%) | 0.0052 | 0.0042 | inf | 1.86e-01 |
| JPEG Q75 4:2:0 | 3/10 (30%) | 0.0045 | 0.0043 | inf | 2.75e-01 |
| Prime JPEG Q95 | 9/10 (90%) | 0.0129 | 0.0039 | inf | 4.04e-02 |

**Even with the manifest, 4:2:0 at Q85 is coin-flip (50%) and Q75 is worse (30%).** The signal is too damaged for even known-position detection to recover.

4:4:4 is solid: 100% detection from Q100 down to Q75 with the manifest.

---

## Summary of Findings

### What works
- **DQT prime tables (Layer 1)**: Survives all JPEG encoding because it's in file metadata, not pixel data.
- **Pixel-domain signal + PNG**: 100% perfect. The embedding math is correct.
- **Pixel-domain signal + JPEG 4:4:4 + manifest**: 100% detection down to Q75.

### What doesn't work
- **Blind detection of Layer 2+**: Broken at any JPEG quality. Grid alignment mismatch + signal destruction.
- **Any pixel-domain signal + JPEG 4:2:0**: 0% marker survival. Chroma subsampling is an instant kill.
- **Manifest detection + JPEG 4:2:0**: Marginal at Q95 (90%), coin-flip at Q85 (50%), broken at Q75 (30%).

### Root causes (stacked)
1. **Chroma subsampling (4:2:0)** averages R and G across 2×2 blocks, collapsing |R-G| distances toward zero (mean shift: -91). This is the universal default in all JPEG encoders, social media platforms, and image hosts.
2. **DCT quantization** further destroys the signal even at 4:4:4 below Q95.
3. **Grid alignment mismatch**: The injector uses entropy-biased random position selection; the blind verifier scans a fixed grid. 50% of markers are invisible, rest diluted ~390x.
4. **Hardcoded n_markers=400**: At the default compound config, marker density is 0.9% of grid — far too sparse for blind detection even if the signal survived JPEG.

### Fundamental issue
The R-G inter-channel distance domain is incompatible with real-world JPEG pipelines where 4:2:0 chroma subsampling is the universal default. This is not a tuning problem — it's the wrong signal domain for the threat model.
