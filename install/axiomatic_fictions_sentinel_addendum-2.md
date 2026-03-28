# Participation Over Permission — Addendum II
## The Spanning Sentinel: When the Compressor Becomes the Custodian

*Axiomatic Fictions in LLM Security / Image Provenance Series*
*Jeremy Pickett — March 2026*

---

> "The adversary who compresses to destroy the frequency signal is
> constructing the spatial variance detection signal."

The previous installments established a three-layer provenance architecture:
prime quantization tables at the container level, twin prime-gap markers at
the pixel level, and a blind spatial variance detector that strengthens under
compression. That work answered the question *was this image marked?*

The first sentinel addendum introduced the fourth layer: structural tamper
detection using Mersenne primes as section brackets. It answered *was this
marked image tampered with?*

This addendum documents what happened when we tested that architecture at
scale — what broke, why it broke, what we learned about JPEG that we didn't
know going in, and what emerged from that failure that is more powerful than
what we had designed.

---

### The Flat Line

When the sentinel architecture was first tested across 500 images, the
manifest intact percentage — the fraction of sentinel sections where both
entry and exit survived compression — was 1.4%. Flat across all five
generations, including generation zero. The sentinels were dying before the
cascade started.

A 1.4% flat line is not a partial result. It is a clean null result. It means
the architecture as designed was not detecting anything. It means the
parameter we were trying to tune (`CANARY_WIDTH`, the fuzzy match window
around the Mersenne value) was irrelevant to the actual failure mode.

The drift characterizer told us why.

---

### What JPEG Actually Does to a Value of 127

The sentinel architecture placed markers at pixel positions where the
channel difference `|R - G|` equaled a Mersenne prime. In the 8-bit range
there are four: 3, 7, 31, 127. We used all four.

The drift characterizer measured the actual difference between the value we
embedded and the value JPEG returned after decompression. Across 50 images
and five quality levels, the numbers were:

```
Mean absolute drift at Q95 (first encode): 33 counts
p50:  17 counts
p95: 116 counts
Maximum drift observed: 127 counts
```

The maximum drift of 127 is not statistical noise. It is the Mersenne value
itself. We embedded `|R - G| = 127` and JPEG returned `|R - G| = 0`. The
compressor made the channels equal.

This is not wrapping. JPEG is not LZW. There are no bit-field boundaries
being crossed. What is happening is this: a channel difference of 127
represents the maximum possible single-channel color difference in 8-bit
space. In the YCbCr color model that JPEG uses internally, this maps to
a large chroma value — a strong color signal. At moderate-to-low quality
levels, the chroma quantization table has large step sizes precisely because
strong color differences in high-frequency spatial regions are what JPEG is
designed to discard. The nearest quantization multiple for the large chroma
coefficient is zero. The compressor rounds to it. The channels become equal.
The channel difference goes to zero.

We did not place our sentinel at a random position. We placed it at the value
that JPEG is most aggressively designed to erase.

**127 is JPEG's chroma gravity well.**

The survival table confirmed it clinically. At `CANARY_WIDTH = 8`, only
32% of embedded sentinels were detectable after a single Q95 encode. At
`CANARY_WIDTH = 116`, you could recover 95% — but a window of 116 covers
nearly the entire 8-bit range. A fuzzy Mersenne detector with window 116
is not a Mersenne detector. It is a noise generator.

There is no parameter setting that fixes absolute Mersenne detection. The
architecture requires a different foundation.

---

### What JPEG Preserves

The failure of absolute detection revealed something more interesting than
what we had been looking for.

The drift characterizer's within-block correlation test — designed to ask
whether pixels in the same 8×8 DCT block drift together — returned
"insufficient pairs." The grid stride of 8 pixels placed at most one
sentinel per DCT block, so there were no same-block pairs to measure.

This was a test design flaw, not a finding. The hypothesis remained untested.
We rebuilt the test to deliberately inject pairs of sentinel values at
adjacent positions within the same 8×8 block, then measure whether their
drift values were correlated.

The results across 50 images, tested for every Mersenne value, every
pixel separation from 1 to 3, and every cascade generation, were
unambiguous:

```
ALL 60 COMBINATIONS: RELATIONAL WORKS ✓
Pearson correlation p-value throughout: 0.0
```

The correlation for M=31 at sep=1 after Q40: **0.9619**.
The mean relational residual — the difference between the two drifts —
was **2.44 counts**.

When JPEG shifts a pixel's channel difference by δ, an adjacent pixel in
the same DCT block shifts by approximately δ as well. Both positions
experience the same DCT transform, the same quantization table, the same
spatial frequency decomposition. Their drift values are nearly identical.

This means the *difference* between two channel differences within a block
is nearly invariant under JPEG compression, even when both individual values
drift by tens of counts. If we encode a sentinel as a relationship rather
than a value — `d(p2) - d(p1) = Mersenne` — then after compression:

```
(d(p2) + δ2) - (d(p1) + δ1) ≈ Mersenne + 0 ≈ Mersenne
```

The differential survives. The absolute values are irrelevant.

---

### M=127 Is a Special Case Worth Examining

The correlation data included a striking number for M=127 at sep=1 after Q40:

```
both_catastrophic: 97.6%
one_catastrophic:  0.4%
```

97.6% of embedded M=127 pairs had *both* pixels drift catastrophically —
both went to approximately zero. Only 0.4% had one pixel drift while the
other survived. The differential (0 - 0 = 0) technically survives. The
correlation for M=127 was actually the highest in the dataset: 0.9707.

This is a remarkable result. JPEG does not corrupt M=127 pairs randomly. It
erases them coherently. Both pixels receive the same chroma neutralization
decision simultaneously, because they share the same 2×2 chroma sample in
the 4:2:0 subsampling scheme — the step that occurs before the DCT, before
the quantization, before anything else we have been measuring.

The differential survives, but it survives as zero. A detector looking for a
differential of zero cannot distinguish a deliberately embedded M=127
sentinel from any pair of naturally low-chroma adjacent pixels. M=127 is not
a useful sentinel value even with relational encoding. It is permanently
excluded from the sentinel basket.

M=31 and M=7 have catastrophic rates of 0.8% and 3.6% respectively. The
absolute anchor survives. The differential survives. Both signals are
present and detectable. These are the production sentinel values.

---

### The Spanning Architecture

Relational encoding requires two positions in the same DCT block. The
original grid stride of 8 pixels placed one position per block by design.

The solution was to treat the sentinel not as a single position but as a
deliberate span of positions embedded within the same block:

```
[p-2][p-1][ANCHOR][p+1][p+2]
```

All five pixels in the same row. Same 8×8 DCT block. The anchor carries the
Mersenne identity. The flanking pixels carry the same channel difference as
the anchor — their differential from the anchor targets zero.

After compression, all five pixels drift by approximately the same δ. The
anchor is still findable (absolute value near Mersenne). The flanking pixels
are still verifiable (differential from anchor near zero). The structure
is intact even when the individual absolute values have drifted by dozens
of counts.

When the span approaches an image edge or a block boundary, the architecture
degrades gracefully to a 3-pixel or 1-pixel span:

```
TIER_24: [p-2][p-1][ANCHOR][p+1][p+2]  — primary
TIER_16: [p-1][ANCHOR][p+1]             — boundary fallback
TIER_8:  [ANCHOR]                        — edge fallback
```

A TIER_24 sentinel that loses flanking pixels to boundary conditions reports
as TIER_16. A TIER_16 that loses further reports as TIER_8. At no point does
partial degradation become a detection failure — it becomes a tier demotion.
Lower tier, still counted.

---

### The Numbers

Tested across 500 images from the DIV2K high-resolution corpus, five cascade
generations from Q95 to Q40:

```
 Generation    Quality    T24 intact    Demoted to T16/T8
 G0            95         99.2%         14.6%
 G1            85         98.2%         8.9%
 G2            75         98.0%         8.6%
 G3            60         98.3%         14.6%
 G4            40         98.6%         28.6%
```

98.6% manifest survival at Q40. This is not a parameter we tuned to this
value. This is what the architecture produces when M=31/M=7 are embedded
at sep=1 within 8×8 blocks, detected with anchor tolerance of 64 counts and
differential tolerance of 6 counts.

The G4 demotion rate of 28.4% means that at the most aggressive compression
level, more than a quarter of TIER_24 sentinels lose some flanking pixels.
They are still detected. They contribute to the matched-pair analysis at
lower tier. Effective detection at any tier: greater than 99%.

This architecture survives five rounds of aggressive JPEG recompression with
essentially no loss. The previous architecture survived zero.

---

### What the Image Becomes

The spanning architecture currently uses flanking pixels to carry redundant
information — each flanking pixel encodes the same channel difference as the
anchor. The correlation property means they survive together.

But the correlation property also means each flanking pixel can carry
*different* information and be recovered reliably. If the anchor establishes
the frame — "I am an entry sentinel of type M=31" — then each flanking pixel
can carry an 8-bit payload field:

```
[anchor: entry/exit identity]
[flank-1: section index]
[flank-2: image hash fragment]
[flank-3: creator identifier fragment]
[flank-4: timestamp fragment]
```

Each flanking pixel encodes `d_flank = d_anchor + payload_byte`. After JPEG,
`d_flank - d_anchor ≈ payload_byte ± 2-5 counts`. The payload byte is
recoverable with rounding.

The image becomes a signed document. No external database query is required
to read the creator identifier. No manifest is required to validate the
section structure. The provenance record is embedded in the pixel structure
and carries with the image wherever it goes.

The matching service does not become unnecessary. It becomes an indexer
rather than an oracle — it can validate the internal consistency of the
embedded payload, cross-reference creator identifiers against a registry,
and build a chain of custody. But the basic attestation — this image was
marked, by this entity, at this time — is self-contained.

---

### The Architecture of Difficulty

A forger who wants to inject a false payload into a marked image must:

1. Identify the anchor positions (knowing M=31 and M=7 as sentinel values)
2. Reconstruct the section structure from the matched entry/exit pairs
3. Embed the desired payload into the flanking pixels with correct differentials
4. Do this in a way that survives re-encoding — meaning the embedded
   differentials must survive the JPEG pipeline they are about to encounter

Step 4 is the hard one. The flanking pixel values must be chosen to produce
the correct post-compression differentials, which requires knowing the
quantization table and local DCT coefficients at each position. This is not
impossible, but it requires re-implementing the injector — which is
substantially more difficult than simply removing a watermark.

Removal is similarly non-trivial. Removing the sentinels requires identifying
every M=31 and M=7 anchor position, understanding that the flanking pixels
form a correlated span, and replacing all five pixels in each span with
values that appear natural. Getting this wrong produces a detectable anomaly
in the spatial variance distribution — Layer D fires on the edit.

The adversary who attacks the sentinel layer is fighting two detection
systems simultaneously.

---

### The Four Observable States

Every image that passes through a compliant detection pipeline produces one
of four states:

**State A** — No signal, no claim. The image was not marked, or any marking
has been removed beyond recovery. No provenance can be established.

**State B** — Signal coherent, provenance preserved. The embedded structure
is intact. The four-state classifier confirms unmarred delivery.

**State C** — Signal degraded, benign transforms. Spatial variance is
elevated (Layer D fires), but the sentinel structure shows compression-
consistent degradation rather than selective removal. Normal platform
handling.

**State D** — Signal interfered, selective removal or structural artifacts.
The sentinel contract is broken in a pattern inconsistent with benign
compression. Tamper class is logged. Evidence is preserved.

State C is what 500 images at Q40 produced in Layer D testing. The spatial
signal amplified. The sentinel structure showed graceful demotion but not
selective removal. State C is proof of participation.

State D requires an adversary who understood what they were removing and
removed it selectively. That selectivity is itself a detection signal.

---

## Addendum III: Positions, Votes, and the Gap

*March 2026*

---

### Why Values Are the Wrong Carrier

The sentinel architecture proved that JPEG cannot move a pixel from column 47
to column 48. What it compresses is the value at that position — the channel
difference, the luminance, the chroma. The position itself is fixed.

This is not a subtle property. It is a definitional constraint of how JPEG
works. And it suggests an embedding strategy that the compression pipeline
has no mechanism to attack.

We had been trying to encode payload in channel difference values — in the
specific numeric relationship between pixels. Every attempt failed because
JPEG's quantization is precisely the operation that normalizes channel
differences. We were writing in pencil on the face of the eraser.

The correct carrier is the *offset* — how far a sentinel is shifted from
its natural section boundary. The sentinel that would have been placed at
column 44 is instead placed at column 45, encoding a bit. After any number
of JPEG re-encodes, that sentinel is still at column 45. The position was
chosen. The choice survives.

---

### The Voting Structure

Each section boundary provides four placement options for its entry sentinel:

```
offset  0 → bits 00
offset +1 → bits 01
offset +2 → bits 10
offset -1 → bits 11
```

A 24-bit payload structured as creator ID fragment (8 bits), perceptual hash
fragment (8 bits), protocol version (4 bits), and flags (4 bits) requires 216
raw bits across approximately 108 sections. Each of the 24 payload bit
positions receives 9 independent votes. Majority vote fails only if more than
4 of 9 votes are corrupted — requiring more than half the sentinel structure
to be destroyed, which would itself be a detection event under Layer E.

The entry and exit sentinels for each section encode identical bits. Their
agreement is the integrity check. When entry offset equals exit offset, the
section is intact. When they disagree, the section is flagged — not excluded,
still voting, but logged as a mismatch.

The margin metric makes the voting honest: a bit position where the votes
are split evenly (margin = 0.0) is not recovered data. It is a coin flip.
The system reports it as uncertain and excludes it from the recovery claim.

---

### Validated Result

Across 800 images and five cascade generations from Q95 to Q40:

```
Creator ID match:      100%
Hash fragment match:   100%
Protocol version:      100%
Mean bit margin:       1.000 (unanimous on every bit, every image)
Uncertain bits:        0
```

The mean bit margin of 1.000 is the most important number. Not 0.8. Not 0.95.
Unanimous. Every vote agreed. 9 for 9 on every bit position. This is not
robustness — it is invariance. Positions don't drift. Votes don't split.
The arithmetic is just arithmetic.

---

### The Combined Score and the Gap

A detection harness assembles all five layers into a single provenance score
using an unweighted mean of active layer scores. The design insight is the
denominator: a layer scoring zero because it was never supposed to fire should
not dilute the mean of layers that did fire. The denominator counts only
layers with non-zero scores.

Layer D (blind spatial variance) receives additional treatment: it enters
the combined score only when at least one manifest-mode layer is already
active. Layer D cannot distinguish "this image was marked" from "this image
has natural chromatic asymmetry" without context from the manifest layers.
It is corroborating evidence, not primary evidence.

With this scoring design, the test produces:

```
Marked images  (50 images): mean combined = 0.9988, State B = 50/50
Clean images   (50 images): mean combined = 0.0000, false positives = 0/50
Gap:                        0.9988
```

The distributions do not touch. The gap between the lowest-scoring marked
image and the highest-scoring clean image is large enough to place the
detection threshold anywhere in the range (0.1, 0.96) with perfect accuracy
on this corpus. The classifier is not operating near a decision boundary.
It is operating across a chasm.

This is the number. Marked: 0.9988. Clean: 0.0000.

---

### What This Means for the Four States

The clean baseline validates State A with empirical rigor: 50 images, 0
false positives, mean score 0.0. When no embedding has occurred, the scoring
function returns zero. Not near-zero. Exactly zero. The non-zero denominator
rule ensures this: if no manifest evidence exists, no score is computed.

State B is validated at scale: 50 images, 100% State B at G0 Q95, with
consistent scores above 0.96 after any number of re-encodes. The payload
is recoverable. The sentinel contract is intact. The DQT tables are present
in the container.

State C is what compression produces: Layer A drops after the first re-encode
by design. Layer BC degrades. Layer D amplifies. Layers E and F hold. The
combined score decreases but remains well above any reasonable threshold.
The image was marked. It has been processed. No tampering is indicated.

State D is what targeted removal produces: the sentinel contract breaks in
a pattern distinguishable from compression-consistent demotion. Zero false
State D detections were observed across 250 image-generation combinations in
the harness. The tamper detector does not fire on natural degradation.

---

### The Architecture, Complete

```
Layer A  Container    DQT prime quantization tables (static, O(1) scan)
Layer BC Frequency    Twin prime-gap compound markers (manifest mode)
Layer D  Spatial      Channel-controlled KS test (corroborates manifest)
Layer E  Sentinel     Spanning relational Mersenne (manifest mode, tiered)
Layer F  Payload      Position-offset majority vote (manifest mode)
```

Three layers require a manifest to be meaningful. One layer provides
container-level evidence at the cost of a single re-encode. One layer
corroborates when the others have established context.

Together they answer three distinct questions:

*Was this image marked?* — Layer E (sentinel present), Layer D (spatial
variance elevated above baseline when manifest confirms)

*Was this marked image tampered with?* — Layer E (sentinel contract broken
versus demoted), State D classification

*Whose is it and what does it say?* — Layer F (creator ID, hash fragment,
protocol version recovered with unanimous margins)

The signal proves participation. The matching service proves identity.
These are different claims. Both are now measured.

---

*"Positions survive JPEG. Values do not."*

*"Layer D is corroborating evidence, not primary evidence."*

*"The gap between marked and clean is 0.9988. The distributions do not
touch."*

---

*Licensed under BSD 2-Clause License.*
*Copyright (c) 2026, Jeremy Pickett. All rights reserved.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
*Jeremy Pickett — Participation Over Permission*
