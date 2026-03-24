# Provenance Signal — Design History
## How We Got Here, and Why Every Assumption Got Tested

*Jeremy Pickett — March 2026*
*For the project record. Internal use and future presentations.*

---

### What I Was Trying to Do

The original question was narrow: can you embed a signal in an image that survives the kind of aggressive JPEG compression that social media platforms apply, and can you detect that signal later without knowing where it was placed?

The "without knowing where" part was the constraint that made everything else interesting. A watermark you can only verify if you have the original embed receipt is useful for private provenance chains. It is not useful for detecting whether an image circulating on the internet was marked before it got there. I wanted the second thing.

The hypothesis was that prime-gap distributions in pixel channel differences are statistically distinctive enough to survive compression. If you embed a cluster of positions where |R-G| is a prime above some floor, and JPEG can't smooth that pattern away completely, a blind scan that measures the aggregate distribution should be able to distinguish a marked image from an unmarked one.

That hypothesis was wrong in the way it was stated, and figuring out *how* it was wrong led to the actual result.

---

### The First Wrong Assumption: Frequency Detection Would Work

The initial design used a KS test on channel-distance distributions. Mark an image, compress it, scan the distances at all eligible grid positions, compare against an unmarked version of the same image. If the distributions differ significantly, the image was marked.

It worked at gen0 (immediately after embedding) and at gen1 (one re-encode). At gen4 (Q40, four generations of compression), the frequency detector was at 6-8% — essentially random. The prime-gap values we had embedded were being smeared into the surrounding distribution by quantization.

The temptation was to fix this by embedding more markers, or by choosing a higher floor. We tried both. Neither helped enough. The frequency signal is fundamentally at odds with what JPEG does: JPEG quantizes DCT coefficients in a way that is specifically designed to reduce statistical irregularities in spatial frequency. The prime-gap structure is exactly the kind of irregularity JPEG is optimized to destroy.

But while we were watching the frequency signal die, we noticed something in the local spatial variance measurements: the numbers were going *up* under compression, not down. At gen0, the local variance ratio (marked / unmarked) was around 1.05. At gen4 it was 1.18. The adversary who compresses to destroy the frequency signal is building the spatial variance detection signal.

The mechanism: when JPEG quantizes a DCT coefficient that was deliberately perturbed to satisfy a prime-gap constraint, it cannot resolve that coefficient cleanly. The quantization decision propagates into adjacent pixels through the inverse DCT — a 2D basis function. The prime-gap perturbation creates a spatial anomaly that compression smears outward, making it *more* detectable in the spatial domain than it was before compression.

We called this granite under sandstone. The spatial signal is always there; the compression just erodes the soft material and exposes it.

This changed the entire detection architecture. We stopped trying to improve the frequency detector and started characterizing the spatial amplification. The result was Layer D: a blind KS test on local spatial variance and channel-difference variance distributions. At the validated operating point — floor 43, 8% of eligible grid positions, approximately 465 markers per 1024px image — Layer D achieves 90% blind detection after Q40 on a 50-image DIV2K corpus. Layer D is the paper.

---

### The Second Wrong Assumption: Density Means Markers, Not Fraction

The original scripts used a hardcoded `n_markers = 2000`. This produced inconsistent results across images of different sizes and made it impossible to reason about the relationship between marker density and detection rate.

The fix was to express density as a fraction of the image's eligible grid positions: `n_markers = ceil(grid_capacity × density_frac)`. A 1024×680 image has roughly 10,600 eligible positions; at 8% density that's about 848 requested markers and approximately 465 actually placed (embedding efficiency ~0.54, set by image content).

This change also revealed that the 2000-marker runs we had been using were at roughly 20-25% density for typical DIV2K images — much higher than necessary, and explaining why the PSNR numbers were below our 40 dB target.

The density sweep from 3% to 25% showed that detection saturates around 8-10%: below 8%, spatial detection starts to degrade; above 12%, you're paying PSNR cost without additional detection benefit. The 90% threshold at 8% is a stable operating point, not a local maximum.

---

### The Third Wrong Assumption: Compound Detection Would Improve With OR Logic

Layer BC — the known-position compound detector — uses the manifest (embed receipt) to check whether markers survived compression. In testing, it was reporting near-zero detection at gen4.

The instinct was that the AND logic was too strict: requiring primary prime-gap AND twin prime-gap AND magic byte (blue channel ≈ 42) simultaneously meant that any single condition failing killed the whole detection. Switch to OR — any condition is sufficient — and detection should rise.

It did not. With OR logic, the detection rose from 0% to 2%, and the false positive rate on control positions rose from ~22% to ~22%. The problem was not AND versus OR. The problem was that the underlying signals — primary R-G prime-gap and Douglas Rule magic byte — were both being destroyed at Q40. The OR logic exposed this by making visible what was always true: the control rate was *higher* than the marker rate, meaning the OR condition was being satisfied more often by natural image content than by the markers themselves.

We reverted to AND logic and documented the honest result: Layer BC is a gen0-gen2 detector. By gen4, the compound frequency signal is gone and the spatial signal is carrying the detection. This is not a failure; it is a clean characterization of which layers do what work at which compression level.

---

### The Fourth Wrong Assumption: Sentinels Can Survive a Prime Re-encode

When we introduced the Mersenne sentinel architecture, the test pipeline embedded sentinels into pixels and then re-encoded the result using `encode_prime_jpeg` — the same function that writes prime quantization tables into the JPEG container for Layer A.

The manifest-mode detection reported 1.2% intact sections at gen0. Every sentinel was being destroyed before the cascade even started.

The bug was architectural: Layer A (prime tables) and Layer E (sentinels) are both provenance signals, but they operate in different domains. Prime tables live in the JPEG container — the DQT segments of the file header. Sentinels live in pixel space — specific channel differences at specific positions. Re-encoding with `encode_prime_jpeg` after embedding sentinels runs the marked pixels through a custom quantization table, which shifts the decoded pixel values and destroys the channel differences we just wrote.

The fix was to use a plain `to_jpeg` call for gen0 after pixel-space embedding. Layer A is already baked in through the first `encode_prime_jpeg` call applied to the original pixels. The second encode wraps the marked pixels in a standard JPEG container. These are two different operations in two different domains, and conflating them destroyed the sentinel layer entirely.

After the fix, manifest-mode detection at gen0 jumped to expected levels. This was the biggest single bug in the implementation.

---

### The Fifth Wrong Assumption: Adjacency Is Sufficient for Canary Detection

The first version of the blind sentinel scanner looked for positions where a channel difference was within `CANARY_WIDTH` of a Mersenne prime and the immediately adjacent position was a fuzzy prime-gap marker. Two-position pairs: `[Mersenne][prime]` or `[prime][Mersenne]`.

On clean (unmarked) images, the scanner found approximately 20 false canaries per image. On marked images, it found approximately 19. The signal-to-noise ratio was worse than noise.

Natural images produce `[Mersenne][prime]` pairs by coincidence because both conditions have non-trivial base rates: roughly 5% of channel differences fall within ±2 of a Mersenne value, and roughly 6% are fuzzy primes above floor 43. The joint probability is ~0.3% per position, and with ~5,000 eligible positions per image, you expect about 15 coincidental pairs.

The fix required thinking about what distinguishes an intentionally placed sentinel from a coincidental one. The answer was already in the embedding design: markers are *twin* markers — two adjacent positions both satisfying the prime-gap constraint. A sentinel flanks a twin pair, not a single marker. The required structure becomes:

```
[Mersenne] [prime] [prime]   ← entry
[prime] [prime] [Mersenne]   ← exit
```

The joint false positive rate for a three-position structure is `0.05 × 0.06 × 0.06 ≈ 0.0002` per position. With 5,000 positions, you expect about 1 coincidental three-position structure per image — which is distinguishable from the 50+ intentional structures in a marked image.

The mirroring between entry and exit is not just structural elegance. It is the discrimination mechanism. A `[Mersenne][prime][prime]` structure says "I am opening." A `[prime][prime][Mersenne]` structure says "I am closing." These are inverse patterns. Natural images do not produce matched pairs of inverse three-position structures at regular spatial intervals. That regularity, combined with the entry/exit typing, is what makes the blind scanner work.

---

### What the Tamper Taxonomy Tells You About Your Attacker

The nine tamper classes — none, full_wipe, tail_truncation, head_truncation, tail_sweep, head_sweep, scattered, structural_inversion, interior_anomaly — are ordered by attacker sophistication, and that ordering has practical implications.

**Classes 1-3 (none, full_wipe, scattered)** require no knowledge of the protocol. A full wipe comes from aggressive re-encoding. Scattered damage comes from targeted pixel modification without spatial awareness. You cannot distinguish deliberate full-wipe tampering from severe platform transcoding without corroborating evidence.

**Classes 4-5 (tail/head truncation, tail/head sweep)** require the attacker to know that boundary markers exist and to apply a spatially directional operation. A tail sweep — consecutive sections with exits removed but entries intact — cannot happen by accident. It implies either a directional crop operation or a targeted search-and-destroy of exit patterns. Either way, the directionality is evidence. Random compression does not produce runs of missing exits.

Severity: medium. Detection: high. These attacks are detectable with near certainty because the pattern is geometrically specific.

**Class 6 (structural_inversion)** requires the attacker to understand the distinction between entry and exit sentinels — that they are not interchangeable, that the mirroring encodes direction. An attacker who swaps entries and exits either read the specification or reverse-engineered it from examples. This is a protocol-aware attacker.

Severity: high (implies significant knowledge). Detection: high (the inversion is unambiguous). Difficulty to implement: moderate (requires tools that can identify and swap sentinel types). Difficulty to detect: low (the structural violation is structurally obvious).

**Class 7 (interior_anomaly)** requires the attacker to understand both the boundary protocol and the interior count invariant — that the number of markers between a matched entry/exit pair is protocol-specified. An attacker who injects or deletes markers between intact sentinels has either read the source code or conducted extensive empirical testing to understand the density structure.

Severity: very high (most sophisticated attack in the taxonomy). Detection: moderate (requires precise interior count measurement, which the current implementation approximates). Difficulty to implement: high (requires correct sentinel placement *and* knowledge of the expected interior count to avoid detection). Difficulty to detect: moderate to high depending on implementation fidelity.

The practical upshot: most attackers will produce Class 1-3 damage through ignorance or blunt instrument. The existence of Class 5-7 attacks tells you something about threat models: if you are seeing structural inversions or interior anomalies in production, you have a sophisticated adversary who has invested significant resources in understanding the protocol. That is itself a detection signal.

---

### What Comes Next

The remaining known gaps:

**Interior count measurement is approximate.** The current implementation uses sentinel count per section as a proxy for interior marker count. A precise implementation would count actual twin prime-gap positions between each sentinel pair and compare against `SENTINEL_CANARY_RATIO`. This is a straightforward improvement deferred to the next sprint.

**Version 2 embedding: pixel value spanning.** The current embedder can only place a marker at position (r, col) if the pixel values at that position allow a prime-gap adjustment within the 20-235 channel value range. Approximately 46% of eligible positions fail this test, giving an embedding efficiency of ~0.54. Version 2 would allow the embedder to span adjacent pixels — treating two or more pixels as a single logical unit — to dramatically increase the set of positions where embedding is feasible.

**API-first refactor.** The current codebase is a research prototype with a collection of scripts. The next major milestone is a clean API that exposes embed/detect as first-class operations with well-defined input/output contracts. This is the prerequisite for any production deployment or integration into existing pipelines.

**The matching service.** Everything described here is detection infrastructure. The attribution claim — "this image was marked by this entity" — requires a registry. That is a separate system with its own security and privacy implications. It is mentioned here because the architecture is designed to support it, not because it is currently implemented.

---

*The signal proves participation. The matching service proves identity. These are different claims.*

*Licensed under Creative Commons Attribution 4.0 International.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
