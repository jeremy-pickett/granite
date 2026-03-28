# Participation Over Permission
## Response-Based Image Provenance and the Architecture of Structural Detection

*Jeremy Pickett — March 2026*
*Axiomatic Fictions in LLM Security / Image Provenance Series*

---

> The signal is not what we put into the file — it is what the system does to the file after we touch it.

---

## What This Is Not

This is not a watermarking paper. The distinction matters, and it is not one of framing.

Classical watermarking embeds a value and attempts to preserve it through distortion. The adversary compresses; the watermark resists. The adversary compresses harder; the watermark degrades further. The underlying assumption is that the system being written into is an enemy — something to overcome, to sneak past, to survive.

What this paper describes operates on the opposite premise. The compression pipeline is not the adversary. It is the amplifier. The signal we embed is not the data we write into the file. It is the statistical response the compression system produces when it encounters a file that has been deliberately perturbed. We do not attempt to preserve bits through quantization. We exploit quantization to make our signal more separable than it was before the compressor touched it.

This distinction determines what the system can and cannot claim. It determines how it should be evaluated. And it determines why every piece of prior work we were aware of addressed a fundamentally different problem — not a harder version of the same one.

To be precise about what we are and are not aware of: we know of no prior system that treats the compression system's statistical response as the primary signal rather than the embedded data. This is not a claim of proof. It is an invitation for correction.

---

## The System Model

Let an image be a finite set of pixels P = {p₁, …, pₙ}, each pixel carrying channel values in [0, 255]³.

Define a perturbation function Δ: P → P′ that modifies a subset of pixel channel values according to structural constraints — in our case, prime-gap relationships in channel differences.

Define a compression operator C_k as the composition of the standard JPEG pipeline at quality level k: RGB → YCbCr conversion, 4:2:0 chroma downsampling, 8×8 DCT block decomposition, quantization against a quality-parameterized table, and Huffman coding. C_k is lossy. It cannot be inverted.

Define a transformation sequence T = C_{k₁} ∘ C_{k₂} ∘ … ∘ C_{kₙ} as n successive compressions, each at a potentially different quality level.

The response signal is the statistical difference between the distribution of local spatial variance in T(P′) versus T(P) — the marked image versus an unmarked counterpart after identical transformation. The detection function D maps any image to one of four states:

**D(image) → {A, B, C, D}**

where A is no signal, B is signal intact, C is signal present but degraded by benign transforms, and D is signal interfered with in a pattern inconsistent with benign compression.

The key property that makes the system work is this: Δ(P) induces a perturbation in the DCT coefficient domain that the quantizer cannot resolve cleanly. The quantization error propagates into the spatial domain through the inverse DCT. Under repeated compression, this error amplifies rather than averages out — because the perturbation we introduce is specifically designed to resist the statistical smoothing that JPEG applies to everything else. We are encoding in the frequency domain's rejected material.

Granite under sandstone. The spatial signal is always there. Compression erodes the soft material and exposes it.

---

## What JPEG Actually Does: M=127 as the Motivating Example

Before describing what the system is, it helps to describe one thing we learned JPEG does that we did not expect. This particular failure is the clearest illustration of the system response principle.

The initial sentinel architecture used Mersenne primes as structural markers. In the 8-bit channel-difference range there are four: 3, 7, 31, 127. All four were used. A channel difference of exactly 127 is unusual in a natural image — requiring one channel to sit near the midpoint while the other approaches an extreme — and that rarity was the signal.

The drift characterizer measured what JPEG actually returned after decompression. Across 50 images and five quality levels, the distribution was:

```
Mean absolute drift at Q95 (first encode): 33 counts
p50:  17 counts
p95: 116 counts
Maximum drift observed: 127 counts
```

The maximum drift of 127 counts is not statistical noise. It is the Mersenne value itself. We embedded `|R - G| = 127` and JPEG returned `|R - G| = 0`. The compressor made the channels equal.

This is not a boundary-wrapping artifact. JPEG is not LZW. There are no bit-field boundaries being crossed. The mechanism is this: a channel difference of 127 maps in YCbCr to a large Cb chroma coefficient. At mid-to-low quality levels, the chroma quantization table uses large step sizes — because strong color differences in high-frequency spatial regions are precisely what JPEG is designed to discard. The nearest quantization multiple for that large chroma coefficient is zero. Both channels are made equal. The channel difference collapses to zero.

127 is not a wrapping boundary. It is JPEG's chroma gravity well. We did not place our sentinel at a random value. We placed it at the value that the JPEG pipeline is most aggressively calibrated to erase.

The survival table confirmed this mechanically. At `CANARY_WIDTH = 8`, only 32% of embedded M=127 sentinels survived a single Q95 encode. At `CANARY_WIDTH = 116` — a window covering most of the 8-bit range — recovery reached 95%. But a fuzzy Mersenne detector with window 116 is not a Mersenne detector. It is a noise generator.

There is no parameter setting that fixes absolute Mersenne detection at M=127. The architecture requires a different foundation. The compressor's behavior is not a nuisance parameter to tune around. It is a property of the system being measured. Understanding it is the work.

This failure is the clearest example in the system of the response principle. We did not ask: how do we preserve this value through JPEG? We asked: what does JPEG do to this value, and what does that response tell us? The answer was precise, reproducible, and more informative than the signal we had been trying to preserve.

---

## The Six Wrong Assumptions

The system as it now stands is the product of six architectural failures, each of which revealed something true about JPEG that we did not know going in. The honest record of what broke and why is part of the contribution.

### 1. Frequency detection would work

The initial design used a Kolmogorov-Smirnov test on channel-distance distributions. Mark an image, compress it, scan distances at eligible grid positions, compare against an unmarked version. If the distributions differ significantly, the image is marked.

It worked at generation zero and generation one. At generation four — Q40, four rounds of compression — the frequency detector was at 6–8% detection. Essentially random. The prime-gap values were being smeared into the surrounding distribution by quantization, which is exactly what quantization is designed to do. JPEG reduces statistical irregularities in spatial frequency. Prime-gap structure is precisely the irregularity JPEG is optimized to destroy.

But while the frequency signal was dying, the local spatial variance measurements were going up under compression, not down. At generation zero, the local variance ratio (marked vs unmarked) was approximately 1.05. At generation four it was 1.18. We stopped trying to improve the frequency detector and started characterizing the spatial amplification.

The result was Layer D: a blind KS test on local spatial variance and channel-difference variance distributions. At the validated operating point — prime floor 43, 8% of eligible grid positions — Layer D achieves 90%+ blind detection after Q40 on a 500-image DIV2K corpus. Layer D is the paper.

### 2. Density means markers, not fraction

A hardcoded marker count of 2,000 produced inconsistent results across image sizes. Fixed by expressing density as a fraction of eligible grid positions: `n_markers = ceil(grid_capacity × density_frac)`. A 1024×680 image has roughly 10,600 eligible positions; at 8% density that is approximately 848 requested and 465 placed (embedding efficiency approximately 0.54, determined by image content).

The density sweep showed detection saturates at 8–10%. Below 8%, spatial detection degrades. Above 12%, PSNR cost rises without detection benefit. 8% is the stable operating point.

### 3. OR logic would improve compound detection

Layer BC — the manifest-mode compound detector — was reporting near-zero detection at generation four. The instinct was that AND logic was too strict. Switch to OR, and any single condition being satisfied should be sufficient.

With OR logic, detection rose from 0% to 2%, and the false positive rate on control positions rose from approximately 22% to approximately 22%. The problem was not the logic. The problem was that the underlying signals were both being destroyed at Q40. The OR logic made this visible: the control rate was higher than the marker rate, meaning the OR condition was being satisfied more often by natural image content than by the markers. Layer BC is a generation zero through two detector. This is an honest result, not a failure.

### 4. Sentinels can survive a prime re-encode

When the Mersenne sentinel layer was introduced, the test pipeline embedded sentinels into pixels and then re-encoded with `encode_prime_jpeg` — the function that writes prime quantization tables into the JPEG container for Layer A. Manifest-mode detection at generation zero: 1.2% intact sections. Every sentinel was dying before the cascade started.

The bug was architectural. Layer A (prime tables) and Layer E (Mersenne sentinels) both operate as provenance signals but in different domains. Prime tables live in the JPEG container — the DQT header segments. Sentinels live in pixel space — specific channel differences at specific positions. Re-encoding with custom quantization tables after pixel-space embedding runs the marked pixels through a table that was designed to shift their decoded values. The channel differences written into those pixels are destroyed.

The fix: use a standard JPEG encode for the pixel-space output. Layer A is embedded through the first encode applied to the original pixels. The second encode wraps the marked pixels without modifying the container structure. These are two operations in two different domains. Conflating them destroyed the sentinel layer in its entirety.

### 5. Adjacency is sufficient for canary detection

The first blind sentinel scanner looked for positions where a channel difference was within `CANARY_WIDTH` of a Mersenne prime, immediately adjacent to a fuzzy prime-gap marker. On clean images: approximately 20 false canaries per image. On marked images: approximately 19. Signal to noise ratio below 1.

Natural images produce `[Mersenne][prime]` pairs by coincidence. Both conditions have non-trivial base rates — roughly 5% of channel differences fall within ±2 of a Mersenne value, roughly 6% are fuzzy primes above floor 43. The joint probability is approximately 0.3% per position; with 5,000 eligible positions, 15 coincidental pairs are expected.

The fix was structural. The required pattern became three positions rather than two: `[Mersenne][prime][prime]` for entry and `[prime][prime][Mersenne]` for exit — structural inverses. The joint false positive probability for a three-position structure is approximately 0.02% per position. With 5,000 positions, one coincidental structure is expected per image, against 50+ intentional structures in a marked image. The mirroring between entry and exit is the discrimination mechanism.

### 6. Absolute Mersenne values survive JPEG

Documented above as the M=127 chroma gravity well finding. This was the major architectural breakthrough. No parameter setting fixes absolute Mersenne detection. Relational encoding within DCT blocks does.

---

## Relational Encoding: A Result, Not a Definition

The solution to the Mersenne drift problem came from a property of JPEG that the drift characterizer revealed accidentally.

The within-block correlation test was designed to ask whether pixels in the same 8×8 DCT block drift together under compression. The first test returned "insufficient pairs" — the grid stride of 8 pixels placed at most one sentinel per block, so there were no same-block pairs to measure. The test design flaw left the hypothesis untested.

We rebuilt the test to inject pairs of sentinel values at adjacent positions within the same 8×8 block and measure whether their drift values were correlated. Across 50 images, every Mersenne value, pixel separations of 1 through 3, and all five cascade generations — all 60 parameter combinations:

```
ALL 60 COMBINATIONS: RELATIONAL WORKS
Pearson correlation p-value throughout: 0.0

M=31, sep=1, Q40: correlation = 0.9619, mean relational residual = 2.44 counts
M=7,  sep=1, Q40: correlation = 0.9425, mean relational residual = 2.42 counts
M=127,sep=1, Q40: correlation = 0.9707, mean relational residual = 3.40 counts
```

When JPEG shifts a pixel's channel difference by δ, an adjacent pixel in the same 8×8 DCT block shifts by approximately δ as well. Both positions experience the same DCT transform, the same quantization table, the same spatial frequency decomposition. Their drift values are nearly identical.

This means the *difference* between two channel differences within a block is nearly invariant under JPEG compression, even when both individual values drift by tens of counts. For pixels p₁ and p₂ in the same block with initial channel differences d(p₁) and d(p₂), and post-compression values d(p₁) + δ₁ and d(p₂) + δ₂:

If we encode a relationship `d(p₂) - d(p₁) = M` for some target value M, then after compression:

`(d(p₂) + δ₂) - (d(p₁) + δ₁) ≈ M + 0 ≈ M`

The differential survives. The absolute values are irrelevant.

Formally: for pixels pᵢ and pⱼ in the same 8×8 DCT block, the relational feature R_{ij} = d(pⱼ) - d(pᵢ) satisfies:

**R_{ij}(T(P′)) ≈ R_{ij}(T(P))**

because compression induces correlated drift. We are encoding relationships, not values. Structure, not bits. This is the property that makes the architecture work across five generations of aggressive compression.

The M=127 correlation data also explained why it must be permanently excluded. The both-catastrophic rate for M=127 at Q40 was 97.6%: JPEG zeroes both pixels simultaneously, coherently, because they share the same 2×2 chroma sample in the 4:2:0 subsampling step — which occurs before the DCT, before the quantization, before anything else we were measuring. The differential (0 − 0 = 0) technically survives. But a detector looking for a differential of zero cannot distinguish a deliberately embedded M=127 sentinel from any pair of naturally low-chroma adjacent pixels. M=127 is excluded not because the correlation fails — it is actually the highest, 0.9707 — but because the surviving differential is indistinguishable from the background.

M=31 both-catastrophic rate: 0.8%. Production entry value. M=7 both-catastrophic rate: 3.6%. Production exit value.

---

## The Architecture

The system comprises five active layers. Each answers a different question. No single layer is sufficient for a strong provenance claim. All together answer three distinct questions: was this image marked, was this marked image tampered with, and whose is it.

### Layer A — Container (DQT Prime Tables)

The JPEG quantization table for luminance is written with prime-shifted values at positions 0–11, with a magic byte sentinel (value 42, shifted to 43 as the nearest prime) at position 0. Detection is O(1): check positions 0 and 1 for the magic pattern.

Layer A survives only lossless JPEG passthrough. It dies at the first re-encode. This is not a failure. A Layer A signal means the container has not been modified since embedding. Its absence after any re-encode is expected and should not be interpreted as evidence of tampering.

Layer A answers: was this file created by a provenance-aware tool, with the original container intact?

### Layer B/C — Frequency (Compound Twin Markers)

Pixel positions are selected deterministically from the embedding seed. At each selected position, a compound marker satisfies three simultaneous conditions: primary channel difference in a prime-gap pair, twin channel difference (adjacent pixel) also satisfying the prime-gap constraint, and a magic byte (blue channel ≈ 42) encoding the Douglas Rule sentinel.

Verification requires the manifest. Conditions are evaluated with AND logic — any single condition failing invalidates the marker. Control positions are sampled identically for false positive characterization.

Layer B/C is reliable through generation two. At generation four — Q40 — compound frequency detection degrades to chance. This is documented honestly. It is a generation zero through two detector.

### Layer D — Spatial (Blind KS Variance Test)

A blind Kolmogorov-Smirnov test on local spatial variance and channel-difference variance distributions at 8-pixel grid positions. No manifest required. The test measures whether the variance distribution at marked-grid positions differs significantly from the distribution at control positions.

Layer D has two documented failure modes and a constraint that makes it reliable.

**Failure mode 1** (v1): Comparing grid positions against off-grid positions in JPEG. JPEG's 8-pixel DCT blocks create blocking artifacts that naturally elevate variance at grid-aligned positions in every JPEG, marked or not. Clean images scored 0.89. The test was measuring the compression artifact.

**Failure mode 2** (v2): Comparing |R−G| variance against |R−B| variance at the same grid positions, intending to cancel the blocking artifact. Natural photographs have chromatic content — R ≠ G ≠ B. Almost every natural image produces |R−G| ≠ |R−B| by construction. Clean images scored 0.98. The test was measuring the image's own color.

**The architectural constraint**: Layer D enters the combined score only when at least one manifest-mode layer (A, B/C, E, or F) has already established a non-zero score. Layer D cannot distinguish "this image was marked" from "this image has natural chromatic asymmetry" without manifest context. It is corroborating evidence. Absence of manifest context means Layer D's score is zero.

With this constraint: marked images with manifest evidence score high on Layer D. Clean images with no manifest evidence score zero on Layer D. The false positive rate from Layer D collapses from 98% to 0%.

This is the distinction between absence of evidence and evidence of absence. A layer scoring zero because it was never supposed to fire should not penalize layers scoring one for the right reason.

### Layer E — Sentinel (Spanning Relational Mersenne)

Entry and exit sentinels bracket sections of primary markers. Each sentinel is a spanning structure of up to five pixels within the same 8×8 DCT block:

```
TIER_24 (primary):    [p-2][p-1][ANCHOR][p+1][p+2]
TIER_16 (boundary):   [p-1][ANCHOR][p+1]
TIER_8  (edge):       [ANCHOR]
```

The anchor carries the Mersenne identity (M=31 for entry, M=7 for exit). Flanking pixels carry the same channel difference as the anchor — their target differential from the anchor is zero. After compression, all five pixels drift by approximately the same δ. The anchor is still findable because its absolute value remains near the Mersenne target. The flanking pixels are verifiable because their differential from the anchor remains near zero.

When the span approaches an image edge or block boundary, the structure degrades gracefully to TIER_16 or TIER_8. Demotion is not failure — it is counted at the appropriate tier.

The sentinel architecture defines a formal contract: for every entry sentinel in section N, there exists a corresponding exit sentinel. Contract violations are classified by a blind scanner into nine tamper classes in increasing order of attacker sophistication, from full wipe (attacker had no protocol knowledge) to structural inversion (attacker understood the mirroring but implemented it incorrectly) to interior anomaly (attacker understood the boundary protocol and the interior count invariant, and modified the content between intact sentinels).

The tamper class is itself evidence. Interior anomaly requires the attacker to have had both the specification and the tooling. That level of investment is a detection signal.

**Validated across 500 DIV2K images, Q95 through Q40:**

```
Generation  Quality  TIER_24  Demoted to T16/T8  Overall
G0          95       99.2%    14.6%               99.2%
G1          85       98.2%    8.9%                98.2%
G2          75       98.0%    8.6%                98.0%
G3          60       98.3%    14.6%               98.3%
G4          40       98.6%    28.6%               98.6%

Effective detection at any tier: >99%
```

The 28.4% demotion rate at G4 means graceful demotion is working. Sentinels that lose flanking pixels to boundary conditions at high compression are still detected and still vote.

### Layer F — Payload (Position-Offset Majority Vote)

Layer F is the architectural resolution of the payload problem, and it came from understanding what JPEG cannot corrupt.

JPEG compresses values. It cannot move a pixel from column 47 to column 48. The position of a pixel is fixed by definition in the JPEG format. We had been trying to encode payload in channel difference values — specific numeric relationships between pixels. Every attempt failed because quantization normalizes those values. We were writing in pencil on the face of the eraser.

The correct carrier is the offset — how far a sentinel is shifted from its natural section boundary position. A sentinel that would naturally be placed at column 44 is instead placed at column 45, encoding a bit. After any number of JPEG re-encodes, that sentinel is still at column 45. The position was chosen. The choice survives.

Each section boundary entry sentinel takes one of four offset positions:

```
offset  0 → bits 00
offset +1 → bits 01
offset +2 → bits 10
offset -1 → bits 11
```

A 24-bit payload — creator identifier fragment (8 bits), perceptual hash fragment (8 bits), protocol version (4 bits), flags (4 bits) — requires 216 raw bits across approximately 108 sections. Each of the 24 bit positions receives 9 independent votes from the 9 sections that encode it. Entry and exit sentinels in each section encode identical bits; their agreement is the section integrity check. Majority vote fails only if more than 4 of 9 votes are corrupted — which would itself be detectable as a Layer E contract violation.

The margin metric is the honesty check: a bit position where votes are split evenly (margin 0.0) is uncertain, reported as such, and excluded from the recovery claim.

**Validated across 800 images, Q95 through Q40:**

```
Creator ID match:      800/800  (100%)
Hash fragment match:   800/800  (100%)
Protocol version:      800/800  (100%)
Mean bit margin:       1.000
Uncertain bits:        0
```

The mean bit margin of 1.000 is the critical number. Unanimous. Every vote agreed. 9 for 9 on every bit position. This is not robustness — it is invariance. Positions do not drift. The arithmetic is just arithmetic.

---

## Experimental Methodology

**Dataset**: DIV2K high-resolution image corpus. 500 images for Layers D and E validation. 800 images for Layer F validation. 50 images each for clean baseline and marked corpus in the final combined harness.

**Compression cascade**: Q95 → Q85 → Q75 → Q60 → Q40, five generations. Q40 is the most aggressive quality level at which we claim reliable detection. Lower quality levels have not been characterized and results should not be extrapolated.

**Parameters**: Prime floor 43 (the optimal operating point identified in the resonance hypothesis sweep, validated at Q40). Marker density 8% of eligible grid positions. Window width 8 pixels. Sentinel canary ratio 8 markers per section. These are protocol constants. They are not tunable without revalidating against a minimum of 500 images.

**Statistical method**: KS test for Layer D distributions. Pearson correlation for relational encoding characterization. Majority vote with margin scoring for Layer F recovery.

**False positive reporting**: Layer E: 0 false State D detections across 250 image-generation combinations in the full harness. Layer F: 0 uncertain bit positions across 800 images. Combined harness clean baseline: 0/50 false positives (0%). The correct statement is: zero false positives were observed over these sample sizes. Confidence intervals at 95% using a one-sided exact binomial test: the false positive rate is bounded above by 5.8% for the 50-image clean baseline, and by 0.36% for the 800-image Layer F corpus.

**Codec characterization**: All results are from Pillow's libjpeg implementation. Behavior under MozJPEG, libjpeg-turbo, and hardware-accelerated codecs has not been characterized. Behavior under neural compression codecs (HEIC, AVIF learned codecs) is unknown and out of scope.

**Reproducibility**: The full corpus, embedding parameters, and detection scripts are not yet publicly released. The parameter constants documented above are sufficient to reproduce the Layer D and Layer E results on any random sample of DIV2K images. Discrepancies should be reported.

---

## Contrast With Classical Watermarking

| Property | Classical Watermarking | GRANITE |
|---|---|---|
| Signal | Embedded value | System response |
| Domain | Pixel / transform coefficient | Relational + statistical |
| Goal | Preserve bits through distortion | Amplify separability under distortion |
| Relationship to compressor | Adversarial | Instrumental |
| Detection | Recover signal, compare to known | Classify distribution |
| Manifest requirement | Optional | Required for most layers |
| Blind detection | Possible | Layer D only, corroborating |
| Tamper characterization | Binary (present / absent) | Nine-class taxonomy |

The critical distinction is in the third row. Classical systems attempt to preserve signal through distortion. Granite constructs signals that become more separable through distortion. This is not an incremental improvement on classical watermarking. It is a different problem formulation. The threat model is different. The evaluation criteria are different. The correct comparison class is not prior watermarking systems — it is prior systems that treat the compression pipeline's statistical response as primary evidence.

We are not aware of prior systems in that comparison class. This claim should be challenged.

---

## Threat Model

**Benign transformations**: recompression, platform re-encoding, format conversion, resizing. These produce State C: signal degraded, benign transform pattern. No tamper class is raised. The system documents what happened without attributing intent.

**Opportunistic adversary**: unaware of GRANITE, performs normal editing (color grading, cropping, filters). Produces State C or, for heavy spatial crops, partial Layer E damage with a localized tamper signature that is geometrically consistent with cropping rather than targeted removal.

**Informed adversary** (knows the protocol exists, does not know parameters): will attempt general compression attacks. At Q40 with five generations, the system detects above 99% via Layer E and 100% via Layer F. Full wipe via extreme compression (Q10 or below) is the most effective attack in this class. Q10 is not characterizable by this system.

**Targeted adversary** (has the specification, knows M=31 and M=7 are sentinel values): must identify all anchor positions, reconstruct the section structure, and modify or replace every span of five correlated pixels without producing a detectable spatial variance anomaly. Removing sentinels correctly requires understanding that the flanking pixels form a correlated span. Getting this wrong triggers Layer D. Getting it right requires re-implementing the injector — which is substantially harder than removing a classical watermark. The adversary who attacks the sentinel layer is simultaneously fighting Layer D.

**Forger** (attempts to inject false payload into a marked image): must reproduce the full correlated span structure with correct Mersenne anchor, correct flanking differentials, correct position offsets for the target payload, all surviving the JPEG pipeline that will follow. Step 4 — producing correct post-compression differentials — requires knowing the quantization table and local DCT coefficients at each embedding position. This is re-implementing the injector with knowledge of the specific image's compression path.

**Success conditions**:

| Goal | Success condition |
|---|---|
| Detection | Distinguish marked from unmarked |
| Attribution (weak) | Consistent State B classification |
| Payload recovery | Creator ID and hash fragment at 100% margin |
| Tamper indication | State D classification on targeted removal |
| Tamper characterization | Nine-class taxonomy output |

---

## The Four Observable States

Every image passing through a compliant detection pipeline produces one of four states. These are operational outputs, not theoretical categories. Each is validated with empirical ground truth.

**State A** — No signal, no claim. The image was not marked, or any marking has been removed beyond recovery. The combined provenance score is 0.0. No manifest evidence exists. Layer D is excluded. Nothing is asserted. Validated: 50/50 clean baseline images scored 0.0000.

**State B** — Signal coherent, provenance preserved. The embedded structure is intact. The sentinel contract holds. The payload is recoverable with unanimous margins. Layer A may be absent (if the container was re-encoded, which is expected). Combined score ≥ 0.96. Validated: 50/50 marked images scored State B at generation zero.

**State C** — Signal degraded, benign transforms. Manifest layers are partially degraded. Layer E shows graceful demotion but not contract violation. Layer D amplifies. Combined score between State A and State B thresholds. Normal platform handling. State C is proof of participation — the image was marked, it has been processed, no tampering is indicated. Validated: 500 images at Q40 in the Layer E corpus produced consistent State C when Layer A was excluded from scoring.

**State D** — Signal interfered, selective removal or structural artifacts. The sentinel contract is broken in a pattern inconsistent with benign compression. A tamper class is logged. Evidence is preserved. Zero false State D detections were observed across 250 image-generation combinations in the harness. The tamper detector does not fire on natural degradation.

---

## The Gap

The final validated result, across the combined detection harness on 50 marked and 50 clean images:

```
Marked images (50):  mean combined score = 0.9988,  State B = 50/50
Clean images  (50):  mean combined score = 0.0000,  false positives = 0/50
Gap: 0.9988
```

The distributions do not touch. The detection threshold can be placed anywhere in the range (0.1, 0.96) and achieve perfect classification accuracy on this corpus. The classifier is not operating near a decision boundary. It is operating across a chasm.

Layer E and Layer F are the primary signal carriers. Layer A is a container-layer timestamp. Layer D corroborates when manifest evidence is already established. Layer B/C is reliable through generation two.

---

## Limitations

These are not caveats added for rhetorical balance. They are genuine scope boundaries that determine where the system's claims should and should not be trusted.

**Geometric transforms**: The sentinel and payload layers are based on pixel positions within the raster scan. Rotation, non-integer scaling, and affine transforms change which pixel occupies which position. The system has not been characterized under geometric transforms. Cropping destroys markers in the cropped region but leaves the remainder intact; the tamper class signature for cropping is geometrically directional and distinguishable from targeted removal.

**Neural compression codecs**: HEIC, AVIF with learned codecs, and similar formats do not use the 8×8 DCT quantization pipeline. The correlated drift property that makes relational encoding work is a JPEG-specific property of DCT block quantization. Behavior under neural codecs is unknown and should be treated as undefined until characterized.

**Corpus size**: The false positive bound of 5.8% (95% CI, one-sided) from the 50-image clean baseline is conservative. The Layer F corpus at 800 images provides a tighter bound of 0.36%. Neither is a sufficient basis for production deployment at scale. Larger corpus validation is the next experimental milestone.

**Q10 and below**: System behavior at extreme compression quality levels has not been characterized. Q40 is the tested lower bound. Claims about survival below Q40 are not supported by this data.

**Codec implementation variance**: All results are from Pillow's libjpeg implementation. MozJPEG, libjpeg-turbo, and hardware-accelerated implementations may produce different quantization decisions at the pixel level, which could affect the relational residual distribution. This has not been tested.

**Attribution vs detection**: The system detects participation. It does not identify actors. A State B result establishes that an image was processed by a provenance-aware tool. It does not establish *who* processed it. Attribution — "this was marked by this entity" — requires a registry. The matching service is a separate system with its own security and privacy properties. Do not conflate the detection claim with the attribution claim.

---

## What the Signal Proves and What It Does Not

The architecture answers three questions and does not answer a fourth.

It answers: was this image processed by a provenance-aware tool. It answers: has the signal been tampered with, and if so, how. It answers: what does the embedded payload say — creator identifier, hash fragment, protocol version.

It does not answer: who. That is the matching service's question, and it is conditional on registration. The signal proves participation. The matching service proves identity, given that the relevant entity registered. These are two different claims and must not be conflated in any compliance framework, legal proceeding, or policy document that relies on this work.

**Participation Over Permission.** The signal does not require platform cooperation to survive. It does not require the viewer's knowledge to be present. It does not require the adversary's consent to document their interference. An entity that processes images passes through a provenance pipeline or they do not. The system records which.

It does not compel disclosure. It documents participation.

---

## What Comes Next

**Layer F position-offset validation at scale**: The 800-image corpus at Q40 is the current result. Scale validation to 5,000 images and characterize behavior at Q20–Q30. Determine whether the unanimous margin result holds at edge cases.

**Geometric transform characterization**: Implement and test rotation-invariant and scale-invariant variants of the sentinel architecture. The position-offset approach is inherently sensitive to transforms that change pixel order. A transform-invariant variant would likely require a different embedding surface.

**Neural codec characterization**: HEIC and AVIF with learned codecs are the dominant next-generation formats. The relational encoding property needs to be characterized from scratch for non-DCT pipelines. This may require a fundamentally different architecture.

**Formal release and independent validation**: The parameter constants, detection scripts, and DIV2K embedding pipeline should be released for independent reproduction. Third-party validation on a separate image corpus is the prerequisite for any publication claim.

**The matching service**: Detection infrastructure is complete. The attribution claim — this image was marked by this entity — requires a registry. That is a separate system with its own security, privacy, and governance implications. It is the next major milestone beyond the current scope.

---

## Key Constants

Do not modify these values without revalidating on a minimum of 500 images.

```python
FLOOR                   = 43    # prime basket floor — resonance hypothesis validated
DENSITY_FRAC            = 0.08  # 8% of eligible positions
WINDOW_W                = 8     # pixel window for marker search
SENTINEL_CANARY_RATIO   = 8     # markers per sentinel section — protocol constant
SENTINEL_MERSENNE_ENTRY = 31    # M=127 excluded permanently: chroma gravity well
SENTINEL_MERSENNE_EXIT  = 7
TIER_24_ANCHOR_TOL      = 64    # wide: anchor is findability
TIER_24_DIFF_TOL        = 6     # tight: differential is the signal
TIER_16_ANCHOR_TOL      = 64
TIER_16_DIFF_TOL        = 8
TIER_8_ANCHOR_TOL       = 16
CASCADE_QUALITIES       = [95, 85, 75, 60, 40]
MIN_VALIDATED_IMAGES    = 500
```

`SENTINEL_CANARY_RATIO` is a protocol constant, not a configuration option. The matching service depends on this value being uniform across all images. Changing it per-image creates a private namespace the scanner cannot index into. If empirical testing establishes that 8 is the wrong number, bump the protocol version. Do not expose it as a dial.

---

## Layer Summary

```
Layer A  Container    DQT prime tables           G0 only, O(1) scan
Layer BC Frequency    Twin prime compound        G0–G2, manifest required
Layer D  Spatial      KS variance test           Corroborating, manifest required
Layer E  Sentinel     Spanning relational M=31   G0–G4, 98.6% at Q40 (500 images)
Layer F  Payload      Position-offset vote       G0–G4, 100% at Q40 (800 images)
```

---

## Canonical Phrases

*"Granite under sandstone."*

*"Participation Over Permission."*

*"The signal proves participation. The matching service proves identity. These are different claims."*

*"127 is not a wrapping boundary. It is JPEG's chroma gravity well."*

*"The adversary who compresses to destroy the frequency signal is constructing the spatial variance detection signal."*

*"Positions survive JPEG. Values do not."*

*"Layer D is corroborating evidence, not primary evidence."*

*"When in doubt, measure the difference or correlation between two or more points."*

*"The gap between marked and clean is 0.9988. The distributions do not touch."*

---

*Licensed under BSD 2-Clause License.*
*Copyright © 2026 Jeremy Pickett. All rights reserved.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
