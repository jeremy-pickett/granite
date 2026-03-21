# Granite Under Sandstone

**A Pre-Cryptographic Evidentiary Substrate for Transformed Media**

*Participation Over Permission — Provenance Signal Detection*

[![License: BSD 2-Clause](https://img.shields.io/badge/License-BSD_2--Clause-blue.svg)](LICENSE)

---

## What This Is

A statistical perturbation scheme that embeds provenance signal into digital media files. The signal **survives and amplifies** under lossy compression and transcoding. It requires no infrastructure beyond the file itself. It collapses plausible deniability at scale.

**The signal is not the perturbation. The signal is the system's response to the perturbation over time.**

## What This Is Not

- Not a watermark (encodes a relationship, detects a distribution, not a mark)
- Not steganography (hides nothing; the signal is a statistical property)
- Not DRM (enforces nothing; produces measurements)
- Not a certificate authority (no one issues or revokes)

## Key Finding

On **800 real photographs** (DIV2K dataset), after **four generations** of JPEG compression (Q95→Q85→Q75→Q60→Q40):

| Metric | Result |
|--------|--------|
| Detection (either channel pair, KS p<0.05) | **99.6%** (797/800) |
| Detection (G-B alone) | 96.4% |
| Detection (R-G alone) | 90.1% |
| G-B wins head-to-head | 59.75% |
| Amplification confirmed | 48.1% (G-B) |

The signal gets **louder** under compression, not quieter. The granite under the sandstone.

## How It Works (30-Second Version)

1. **Embed**: At save time, force inter-channel distances at selected pixel positions to prime-valued gaps. Cost: ~0.01 joules. Imperceptible.

2. **Compress**: The codec's block-based quantization penalizes the perturbation's local complexity. Each compression generation amplifies the variance anomaly at marker positions relative to smooth surroundings.

3. **Detect**: Measure the statistical distribution of inter-channel distances at candidate positions. Compare against control positions in the same image. The image is its own control group.

4. **Attribute**: The positions are derived from a 256-bit seed via HMAC-SHA512. The position pattern is the fingerprint. C(4000, 200) ≈ 10⁴⁰⁰ possible patterns. Fuzzy matching via Jaccard similarity.

## The Fuse and the Fire

The prime values are the **fuse**. They're destroyed by the first compression. The variance anomaly is the **fire**. It persists and amplifies because the codec's quantization creates a sawtooth error landscape where the perturbation's coefficients cross quantization boundaries that smooth background coefficients don't.

The fuse is engineering (format-specific, replaceable). The fire is physics (universal to any partition-transform-quantize system).

## Repository Structure

```
granite-under-sandstone/
├── LICENSE                          # BSD 2-Clause
├── README.md                        # This file
├── SETUP.md                         # Installation and quick start
│
├── src/                             # Core library
│   ├── pgps_detector.py             # Core detector and utilities
│   ├── compound_markers.py          # Twin/magic/compound marker embedding
│   ├── dqt_prime.py                 # Strategy 4: prime quantization tables
│   ├── smart_embedder.py            # File-type profiles and entropy gating
│   ├── layer2_detect.py             # Known-position detection (with receipt)
│   └── fp_forensics.py              # Distance forensics and analysis
│
├── tests/                           # Experimental harnesses
│   ├── div2k_harness_v2.py          # DIV2K validation (the granite test)
│   ├── cascade_test.py              # Multi-generation JPEG cascade
│   ├── scale_test.py                # Scale, resize, fingerprint stability
│   ├── channel_pair_test.py         # RGB channel pair independence
│   ├── jpeg_to_webp.py              # Cross-codec boundary test
│   ├── slice_attack.py              # Slice-and-stitch attack simulation
│   ├── rotation_attack.py           # Geometric attack simulation
│   └── prime_floor_sweep.py         # Basket floor optimization
│
├── results/                         # Experimental data
│   ├── div2k_aggregate.json         # 800-image summary statistics
│   ├── div2k_per_image.jsonl        # Per-image detailed results
│   └── VERDICT.txt                  # The granite verdict
│
├── docs/                            # Papers and addenda
│   ├── paper_architecture_blueprint.docx
│   ├── granite_under_sandstone_draft.docx
│   ├── engineering_design_document_v02.docx
│   ├── div2k_experimental_results.docx
│   ├── participation_over_permission_product_doc.docx
│   ├── addendum_a_video_extension.docx
│   ├── addendum_b_integration_landscape.docx
│   ├── addendum_c_cascading_canary_survival.docx
│   ├── addendum_d_attribution_architecture.docx
│   ├── addendum_f_multilayer_provenance.docx
│   ├── addendum_g_known_attacks.docx
│   ├── addendum_h_thar_be_dragons.docx
│   ├── addendum_i_color_of_survival.docx
│   ├── addendum_j_thermodynamic_tax.docx
│   ├── addendum_k_fuse_and_fire.docx
│   ├── experimental_results_scale_resize.docx
│   ├── technical_notes_advanced_attacks.docx
│   └── technical_notes_nine_satellites.docx
│
└── relational/                      # Exploratory / relational signal analysis
    └── relational_signal.py
```

## Quick Start

```bash
# Clone
git clone https://github.com/jeremypickett/granite-under-sandstone.git
cd granite-under-sandstone

# Install dependencies
pip install Pillow numpy scipy matplotlib

# Run the 5-image sanity check
python tests/div2k_harness_v2.py -i /path/to/images -o results -n 5

# Run the full granite test
python tests/div2k_harness_v2.py -i /path/to/images -o results
```

## Format Performance

The majority of Granite testing has been conducted in highly fluid, adversarial environments — JPEG compression cascades (Q95→Q85→Q75→Q60→Q40), cross-codec transcoding (JPEG→WebP→JPEG), geometric attacks (rotation, flips), and slice-and-stitch reassembly. These represent the hardest cases: aggressive quantization, block boundary realignment, and interpolation damage.

For **lossless and near-lossless formats like PNG**, the signal works virtually flawlessly. Without quantization destroying coefficient precision, the embedded prime-gap perturbations survive intact. The edge cases that dominate JPEG testing — content-class dependence, amplification variance, basket floor sensitivity — largely disappear when the codec preserves pixel values.

Initial testing on **other lossy media formats** — MP3 (audio), H.264/H.265 (video), and other codecs employing quantization schemes and transform coding — has produced results that exceed expectations. The core mechanism (partition → transform → quantize) is universal across these formats, and the perturbation's interaction with their quantization grids follows the same physics. More detailed testing results to follow.

| Format Class | Difficulty | Status |
|-------------|-----------|--------|
| PNG, lossless | Easy — no quantization | Near-perfect detection |
| JPEG, single generation | Moderate — one quantization pass | 99.6% detection (800 images) |
| JPEG, 4-generation cascade | Hard — repeated quantization | 96.4% G-B detection |
| WebP transcode | Hard — different block size/transform | Detected through Q80 |
| MP3, H.264/H.265 | Under testing | Exceeding expectations |

## Threat Model

Assume the adversary has: full source code, the embedding algorithm, the detection algorithm, sample datasets, and the ability to run arbitrary transforms. The only secret is the creator's 256-bit seed.

Everything else is public. BSD licensed. The scheme is secure under Kerckhoffs's principle.

## The Four States

| State | Condition | Interpretation |
|-------|-----------|----------------|
| A | No signal detected | No provenance, or total suppression |
| B | Signal coherent | Provenance preserved |
| C | Signal degraded, consistent pattern | Benign pipeline transforms |
| D | Signal interfered, inconsistent pattern | Deliberate suppression attempted |

## Economic Architecture

| Operation | Energy | Timing | Failure Mode |
|-----------|--------|--------|-------------|
| Embed | ~0.01 J | At save | No provenance (benign) |
| Detect | ~0.1 J | Batch, lazy | Catch later (benign) |
| Suppress | ~0.5-2 J | Synchronous, hot path | Served unsuppressed (catastrophic) |

The minimum-energy state is serving provenance-marked files unaltered. Physics, not policy.

## Citation

```
Jeremy Pickett. "Granite Under Sandstone: Compression-Amplified Provenance
Signals in Transformed Media." SignalDelta / Axiomatic Fictions, March 2026.
```

## Development Process

This work was co-developed with Claude (Anthropic), reviewed by Gemini (Google) and GPT-4o (OpenAI). Human-directed. AI-assisted. Friction welcome and required.

The human asked every question, made every architectural decision, and connected every cross-domain insight. The AI models built what the human pointed at, tested what the human asked, and wrote what the human described.

## Related Work

- Chen & Wornell (2001) — Quantization Index Modulation
- Cox, Miller & Bloom (2002) — Digital Watermarking (textbook)
- Farid (2009) — JPEG Ghost detection and image forensics
- Fridrich, Goljan & Du (2001) — Steganalysis and color channel coupling
- Anderson (2001) — Why Information Security is Hard (economic framing)

## License

BSD 2-Clause. See [LICENSE](LICENSE).

The code is open. The method is published. The economics are self-enforcing.

---

*"The signal is not fragile. The ambiguity is."*
