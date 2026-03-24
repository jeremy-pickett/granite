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

*"The signal proves participation. The matching service proves identity.
These are different claims."*

*"127 is not a wrapping boundary. It is JPEG's chroma gravity well."*

*"When in doubt, measure the difference or correlation between two or more
points."*

---

*Licensed under Creative Commons Attribution 4.0 International.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
*Jeremy Pickett — Participation Over Permission*
