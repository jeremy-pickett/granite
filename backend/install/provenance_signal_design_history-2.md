# Provenance Signal — Design History
## How We Got Here, and Why Every Assumption Got Tested

*Jeremy Pickett — March 2026*
*For the project record. Internal use and future presentations.*
*Claude Code: this document is the canonical internal history of architectural decisions.
Read it entirely before modifying any detection or embedding code. Every section
describes a real failure, why it failed, and what the correct architecture is.*

---

### What I Was Trying to Do

The original question was narrow: can you embed a signal in an image that survives
the kind of aggressive JPEG compression that social media platforms apply, and can
you detect that signal later without knowing where it was placed?

The "without knowing where" part was the constraint that made everything else
interesting. A watermark you can only verify if you have the original embed receipt
is useful for private provenance chains. It is not useful for detecting whether an
image circulating on the internet was marked before it got there. I wanted the second
thing.

The hypothesis was that prime-gap distributions in pixel channel differences are
statistically distinctive enough to survive compression. If you embed a cluster of
positions where |R-G| is a prime above some floor, and JPEG can't smooth that pattern
away completely, a blind scan that measures the aggregate distribution should be able
to distinguish a marked image from an unmarked one.

That hypothesis was wrong in the way it was stated, and figuring out *how* it was
wrong led to the actual result.

---

### The First Wrong Assumption: Frequency Detection Would Work

The initial design used a KS test on channel-distance distributions. Mark an image,
compress it, scan the distances at all eligible grid positions, compare against an
unmarked version of the same image. If the distributions differ significantly, the
image was marked.

It worked at gen0 (immediately after embedding) and at gen1 (one re-encode). At gen4
(Q40, four generations of compression), the frequency detector was at 6-8% —
essentially random.

But while we were watching the frequency signal die, we noticed something in the
local spatial variance measurements: the numbers were going *up* under compression,
not down. At gen0, the local variance ratio (marked / unmarked) was around 1.05. At
gen4 it was 1.18. The adversary who compresses to destroy the frequency signal is
building the spatial variance detection signal.

The mechanism: when JPEG quantizes a DCT coefficient that was deliberately perturbed
to satisfy a prime-gap constraint, the quantization decision propagates into adjacent
pixels through the inverse DCT. The prime-gap perturbation creates a spatial anomaly
that compression smears outward, making it *more* detectable in the spatial domain
than it was before compression. Granite under sandstone.

This changed the entire detection architecture. Layer D: a blind KS test on local
spatial variance and channel-difference variance distributions. At the validated
operating point — floor 43, 8% of eligible grid positions — Layer D achieves 90%+
blind detection after Q40 on a 500-image DIV2K corpus. Layer D is the paper.

---

### The Second Wrong Assumption: Density Means Markers, Not Fraction

Hardcoded `n_markers = 2000` produced inconsistent results across image sizes.
Fixed by expressing density as `n_markers = ceil(grid_capacity × density_frac)`.
The density sweep showed detection saturates at 8-10%. Below 8%, spatial detection
degrades. Above 12%, PSNR cost rises without detection benefit. 8% is the stable
operating point.

---

### The Third Wrong Assumption: Compound Detection Would Improve With OR Logic

Layer BC frequency signal is destroyed at Q40. OR logic exposed this rather than
fixed it — control rate was higher than marker rate with OR. Reverted to AND.
Layer BC is a gen0-gen2 detector. This is an honest result, not a failure.

---

### The Fourth Wrong Assumption: Sentinels Can Survive a Prime Re-encode

Embedding sentinels then calling `encode_prime_jpeg` destroyed the sentinels before
cascade started. Layer A (prime DQT tables, container domain) and Layer E (Mersenne
sentinels, pixel domain) are different operations in different domains. Do not
conflate them. Gen0 pipeline: `encode_prime_jpeg(original)` → embed sentinels →
`to_jpeg(marked)`. Not `encode_prime_jpeg(marked)`.

---

### The Fifth Wrong Assumption: Adjacency Is Sufficient for Canary Detection

Two-position `[Mersenne][prime]` pairs: SNR < 1.0 on 500-image corpus. Natural
images produce them by coincidence. Fix: matched entry+exit pairs at
`SENTINEL_CANARY_RATIO × WINDOW_W` pixels of raster separation. Spatial constraint
collapses joint FP rate to near zero.

---

### The Sixth Wrong Assumption: Absolute Mersenne Values Survive JPEG

**This is the major architectural breakthrough of March 2026.**

The sentinel drift characterizer measured actual drift across 50 images:

```
DRIFT DISTRIBUTION AT Q95 (G0, first encode):
  mean drift: 33.07 counts
  p50:  17.0   p95: 116.0   max: 127.0 — THE MERSENNE VALUE ITSELF

SURVIVAL RATE AT CANARY_WIDTH=8:   32% at G0
SURVIVAL RATE AT CANARY_WIDTH=116: 95% at G0
```

The max drift of 127 is not noise. JPEG is consistently zeroing out `|R-G| = 127`
to `|R-G| = 0`. This is chroma neutralization, not wrapping.

**JPEG pipeline (not LZW):**
1. RGB → YCbCr
2. 4:2:0 chroma downsampling (every 2×2 pixel block shares one Cb/Cr sample)
3. DCT on 8×8 blocks
4. Quantization (lossy — step sizes in DQT table)
5. Huffman coding (lossless)

`|R-G| = 127` creates a large Cb value. At mid-to-low quality, chroma quantization
step sizes are large. The nearest quantization multiple is 0. JPEG makes both
channels equal. Drift = 127. No window fixes this.

**M=127 is JPEG's chroma gravity well, not a wrapping boundary.**

Note on boundary intuition: the instinct to test at boundary values is correct.
127 is a boundary — the maximum signed 8-bit value, the maximum single-channel
Mersenne prime. The test revealed the mechanism: JPEG treats large chroma differences
as high-frequency noise to be eliminated. The boundary is real and exploitable,
just not in the direction of wrapping. It is the edge of what JPEG will preserve.

---

### The Solution: Relational Encoding Within DCT Blocks

**Core insight:** JPEG quantization error is spatially correlated within 8×8 DCT
blocks. Both positions drift by approximately δ. The difference `d(p2) - d(p1)` drifts
by `δ2 - δ1 ≈ 0`. The differential survives when the absolute values do not.

**Same-block correlation test across 50 images, all 60 parameter combinations:**

```
ALL 60 COMBINATIONS VERDICT: RELATIONAL WORKS ✓  (p=0.0 throughout)

M=31, sep=1, G4 (Q40):  corr=0.9619  rel_residual=2.44  both_cat=0.8%
M=7,  sep=1, G4 (Q40):  corr=0.9425  rel_residual=2.42  both_cat=3.6%
M=127,sep=1, G4 (Q40):  corr=0.9707  rel_residual=3.40  both_cat=97.6%
```

M=127 both_cat=97.6%: JPEG zeroes both pixels simultaneously. Differential
(0-0=0) survives but anchor is invisible in blind mode. Permanently excluded.

M=31 both_cat=0.8%: anchor survives, differential survives. Production entry value.
M=7  both_cat=3.6%: same. Production exit value.
REL_WIDTH=6 captures 95%+ of relational residuals at G4.

---

### The Spanning Architecture: 24/16/8-bit Tiered Detection

Rather than hoping for natural block cohabitation, deliberately embed across a
multi-pixel span within the same 8×8 DCT block. All pixels in the span drift
together (correlated). Differential across the span is preserved.

```
TIER_24 — 5-pixel span (primary):
  [p-2][p-1][ANCHOR][p+1][p+2]  same row, same DCT block
  Anchor: d = M31 (entry) or M7 (exit)
  Flanking: d = anchor_value (target differential = 0)
  Detect: anchor within ANCHOR_TOL + ≥3 flanking within DIFF_TOL

TIER_16 — 3-pixel span (boundary fallback):
  [p-1][ANCHOR][p+1]  when p±2 crosses block boundary

TIER_8 — anchor only (edge fallback):
  [ANCHOR]  at image edges only
```

**Calibrated tolerances (from correlation test data):**
```python
SENTINEL_MERSENNE_ENTRY = 31    # M=127 excluded permanently
SENTINEL_MERSENNE_EXIT  = 7
TIER_24_ANCHOR_TOL      = 64    # wide: anchor is findability, not verification
TIER_24_DIFF_TOL        = 6     # tight: differential is the real signal
TIER_16_ANCHOR_TOL      = 64
TIER_16_DIFF_TOL        = 8
TIER_8_ANCHOR_TOL       = 16
```

**Validated across 500 DIV2K images, cascade Q95→Q85→Q75→Q60→Q40:**

```
 Gen    Q     T24%     T16%      T8%   Overall%   T24_demoted%
 G0    95    99.2%     1.4%     0.3%      99.2%          14.3%
 G1    85    98.2%     1.4%     0.3%      98.2%           8.6%
 G2    75    98.0%     1.4%     0.1%      98.0%           8.5%
 G3    60    98.3%     1.4%     0.2%      98.3%          14.4%
 G4    40    98.6%     1.4%     0.2%      98.6%          28.4%

gen4_t24_intact: 98.63%
gen4_t16_intact: 1.4%   (demoted, still detected)
gen4_t8_intact:  0.2%   (demoted, still detected)
effective_detection_any_tier: >99%
```

28.4% T24_demoted at G4 means graceful demotion is working. These sentinels are
detected at lower tier, not lost. Include all tiers in matched-pair analysis.

---

### What Comes Next: The Payload Encoder

**Architecture ready. Implementation pending. This is the next major milestone.**

Current state: spanning pixels carry redundant information (all flanking = anchor).
Next state: each flanking pixel carries a different 8-bit payload field.

```
[anchor: M=31/M=7 — entry/exit identity]
[flank-1: section_index mod 256]
[flank-2: image_hash_fragment, 8 bits]
[flank-3: creator_id_fragment, 8 bits]
[flank-4: protocol_version + timestamp_fragment]
```

Encoding: `d_flank = d_anchor + payload_byte`
Recovery: `payload_byte ≈ d_flank_actual - d_anchor_actual`
Error: ±rel_residual (2-5 counts at G4). Correctable with rounding if payload
values are pre-quantized to step sizes > 2×rel_residual.

The image becomes a signed document. No manifest required for basic attestation.
No external database required to read creator ID or section index. Self-describing.

Forgery resistance: reproducing the full correlated span structure with correct
Mersenne anchor, correct flanking differentials, correct payload fields, all
surviving JPEG — requires re-implementing the injector. That is a much harder
problem than removing a watermark.

---

### Layer Summary (Claude Code Reference)

```
Layer A (container):  DQT prime tables — G0 only by design
Layer BC (frequency): twin prime compound markers — G0-G2
Layer D (spatial):    blind KS test on local variance — 90%+ at G4 ✓ (500 images)
Layer E (sentinel):   spanning relational Mersenne — 98.6% at G4 ✓ (500 images)
Layer F (payload):    structured flanking payload — READY, NOT YET TESTED
```

---

### Key Constants — Do Not Change Without Re-validating on 500 Images

```python
FLOOR                   = 43
DENSITY_FRAC            = 0.08
WINDOW_W                = 8
SENTINEL_CANARY_RATIO   = 8
SENTINEL_MERSENNE_ENTRY = 31    # M=127 excluded: JPEG chroma gravity well
SENTINEL_MERSENNE_EXIT  = 7
TIER_24_ANCHOR_TOL      = 64
TIER_24_DIFF_TOL        = 6
TIER_16_ANCHOR_TOL      = 64
TIER_16_DIFF_TOL        = 8
TIER_8_ANCHOR_TOL       = 16
CASCADE_QUALITIES       = [95, 85, 75, 60, 40]
MIN_VALIDATED_IMAGES    = 500
```

---

### Position-Based Payload (Layer F) — Validated

*March 2026*

v1 of Layer F encoded payload in the differential between flanking pixel channel
differences and the anchor. Failed because the same correlation property that makes
the sentinel relational (Pearson r=0.96, mean rel_residual=2.44 at Q40) means JPEG
makes same-block pixels drift together. We proved 0 is preserved. We then asked it
to encode 48. Those are directly opposite requirements.

v2 is architectural, not parametric. **JPEG corrupts pixel values. It cannot corrupt
pixel positions.** A sentinel placed at column 47 is at column 47 after any number
of JPEG re-encodes. The payload is encoded in the offset of the sentinel from its
natural section boundary position.

```
offset  0 → bits 00
offset +1 → bits 01
offset +2 → bits 10
offset -1 → bits 11
```

2 bits per section × ~108 sections per image = 216 raw bits. With a 24-bit payload,
each bit position gets 9 votes. Majority vote fails only if more than 4 of 9 votes
are corrupted.

**Validated result: 800/800 images, 100% CID match, 100% hash match, unanimous
margins (1.000), at Q40. Zero uncertain bits.**

Positions survive JPEG. Values do not.

---

### The Detection Harness and the Gap

*March 2026*

With all layers validated individually, we built a detection harness that runs every
layer against the same image, computes per-layer scores, and combines them into a
single provenance score.

**Scoring design: non-zero denominator.** The first version penalized images for
the absence of layers that were never supposed to fire. Layer A (DQT) is 0.0 after
any re-encode by design. Layer BC is 0.0 when the compound detector is run through
a pipeline that double-encodes. Including these zeros in the denominator produced
systematically deflated scores — marked images classifying as State C rather than B.

The fix: denominator = count of layers with non-zero scores only. A layer scoring
0.0 means it has no active signal, not that it detected absence. This is the same
distinction as "absence of evidence" versus "evidence of absence."

**Result: marked images score 0.9988 mean. Clean images must score 0.0.**

---

### Layer D: Two Failure Modes and the Architectural Fix

*March 2026*

Layer D was the blind spatial variance detector — the only layer that fires without
a manifest. It had two sequential failure modes.

**Layer D v1 failure: JPEG blocking artifact.**
Compared |R-G| variance at 8-pixel grid positions vs random off-grid positions.
JPEG DCT blocks are also 8 pixels wide. Block boundary artifacts naturally elevate
variance at grid-aligned positions in every JPEG, marked or not. Clean images scored
0.89. The test measured the compression artifact, not the signal.

**Layer D v2 failure: natural chromatic asymmetry.**
To cancel the JPEG artifact, v2 compared |R-G| variance vs |R-B| variance at the
*same* grid positions. The intent was that JPEG blocking would affect both equally,
leaving only the marker signal in the difference. The flaw: natural photographs have
chromatic content. In almost every natural image, R≠G≠B, so |R-G| ≠ |R-B| by
construction. Clean images scored 0.98. The test measured the image's own color,
not the signal.

Only image 0014 scored 0.0 in the v2 clean baseline — because it happened to be
nearly desaturated, making R≈G≈B. One image out of fifty. That's not a detector.
That's a color saturation meter.

**The architectural fix: Layer D is corroborating evidence, not primary evidence.**

Layer D fires on pixel statistics alone. In the absence of any manifest evidence,
it has no anchor — it cannot distinguish "this image has our signal" from "this
image has natural chromatic content." It is therefore excluded from the combined
score unless at least one manifest-mode layer (A, BC, E, or F) is also non-zero.

```
Clean image:  A=0, BC=0, E=0, F=0 → no manifest → Layer D excluded → score = 0.0
Marked image: A=1, E=1, F=1 → manifest present → Layer D included → score ≈ 0.999
```

This single constraint collapses the false positive rate from 98% to 0%.

The deeper lesson: a blind detector that fires on image content rather than
embedding presence is not a detector. It is a classifier of the image itself.
Layer D is genuine signal — it amplifies under compression, it responds to the
prime-gap anomalies — but it cannot stand alone. It requires the manifest layers
to establish the context in which its evidence means something.

---

### Final Validated Results

```
Marked corpus:    50 images, mean combined = 0.9988, State B = 50/50 (100%)
Clean baseline:   50 images, mean combined = 0.0000, false positives = 0/50 (0%)
Gap:              0.9988
Separation:       CLEAR — distributions do not touch
CID recovered:    50/50 (100%)
```

The threshold for classification can be set anywhere in the range (0.1, 0.96)
and achieve perfect separation on this corpus. Layer E (sentinel contract) and
Layer F (payload recovery) are the primary signal carriers. Layer A (DQT) is
a container-layer timestamp. Layer D corroborates when manifest evidence is
already present.

---

### Updated Layer Summary

```
Layer A (container):  DQT prime tables — G0 only by design
Layer BC (frequency): twin prime compound markers — G0-G2
Layer D (spatial):    channel-controlled KS — corroborating only, requires manifest
Layer E (sentinel):   spanning relational Mersenne — 98.6% at G4 (500 images)
Layer F (payload):    position-offset, majority vote — 100% at Q40 (800 images)
```

---

### Canonical Phrases

*"Granite under sandstone."*
*"Participation Over Permission."*
*"Proves Participation."* (NOT enforcement)
*"The signal proves participation. The matching service proves identity."*
*"127 is not a wrapping boundary. It is JPEG's chroma gravity well."*
*"When in doubt, measure the difference or correlation between two or more points."*
*"The adversary who compresses to destroy the frequency signal is constructing
the spatial variance detection signal."*
*"Positions survive JPEG. Values do not."*
*"Layer D is corroborating evidence, not primary evidence."*
*"Absence of evidence is not evidence of absence — but a layer scoring zero
for the right reason should not penalize layers scoring one for the right reason."*

---

*Licensed under BSD 2-Clause License.*
*Copyright (c) 2026, Jeremy Pickett. All rights reserved.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
