# ADDENDUM I

**The Color of Survival**

**Channel Pair Analysis and the Multi-Scale Diagnostic Architecture**

*Addendum to: Participation Over Permission — March 19, 2026*


---


## I.1 The Question


Every RGB pixel has three values. Every pair of values produces a distance. There are three pairs: |R−G|, |R−B|, |G−B|. The scheme has used |R−G| since its first implementation. This was an arbitrary choice. The question is whether it was the right one.


It was not.


---


## I.2 The YCbCr Coupling


JPEG does not compress RGB. It converts to YCbCr first:


Y  =  0.299 R  +  0.587 G  +  0.114 B


Cb = -0.169 R  -  0.331 G  +  0.500 B


Cr =  0.500 R  -  0.419 G  -  0.081 B


Green dominates luminance (0.587). Red contributes moderately (0.299). Blue contributes almost nothing (0.114). The luminance channel (Y) receives gentle quantization. The chrominance channels (Cb, Cr) receive aggressive quantization.


This conversion couples all three RGB channels. A perturbation in any one RGB channel pair creates signal in all three pairs after the YCbCr round-trip, because changing R or G or B changes Y and Cb and Cr simultaneously, and quantization error in YCbCr redistributes across all RGB channels on decode.


**Consequence: **The three RGB channel pairs are NOT independent information channels through JPEG. A perturbation embedded in |R−G| creates detectable signal in |R−B| and |G−B| as well. Three correlated views of one perturbation, not three independent perturbations.


---


## I.3 The Empirical Finding


### I.3.1 Cross-Pair Leakage


Twin markers embedded in |R−G| only (250 markers, 1024×1024, JPEG Q95):


| Channel Pair | Rate Ratio | p-value | Signal? |
| --- | --- | --- | --- |
| R-G (embedded) | 3.42× | 1.0 × 10⁻²³ | YES |
| R-B (not embedded) | 2.08× | 3.7 × 10⁻⁷ | YES (leaked) |
| G-B (not embedded) | 3.71× | 1.3 × 10⁻²⁴ | YES (leaked) |


**Table I1. ***Cross-pair leakage. Embedding in R-G creates detectable signal in all three pairs. G-B leaked signal is actually STRONGER than the directly embedded R-G signal. The YCbCr coupling distributes the perturbation across all pairs.*


**Notable: **The leaked G-B signal (3.71×) is stronger than the directly embedded R-G signal (3.42×). This is not an error. The perturbation energy that flowed into chrominance through the color space conversion is more detectable in G-B because blue’s low contribution to Y (0.114) means the G-B perturbation is less attenuated by luminance quantization.


### I.3.2 Interference Test


Embedding R-B on top of existing R-G embedding:


**R-G ratio before R-B embedding: **3.65×, p = 2.8 × 10⁻²⁷


**R-G ratio after R-B embedding: **3.40×, p = 3.0 × 10⁻²³


**Degradation: **6.7%. The pairs coexist with minimal destructive interference.


### I.3.3 Cascade Survival by Channel Pair


All three pairs embedded, JPEG compression cascade:


| Quality | R-G ratio | R-G p | R-B ratio | R-B p | G-B ratio | G-B p |
| --- | --- | --- | --- | --- | --- | --- |
| Q95 | 3.41 | 2.4×10⁻²³ | 2.25 | 8.5×10⁻⁹ | 2.41 | 5.8×10⁻⁹ |
| Q85 | 2.61 | 1.1×10⁻¹² | 2.26 | 5.0×10⁻⁹ | 3.91 | 1.4×10⁻²⁸ |
| Q75 | 2.77 | 1.4×10⁻¹⁴ | 2.19 | 4.5×10⁻⁸ | 3.60 | 4.2×10⁻²⁴ |
| Q60 | 2.34 | 2.1×10⁻⁹ | 1.68 | 7.2×10⁻⁴ | 2.53 | 2.2×10⁻¹⁰ |
| Q40 | 1.43 | 2.4×10⁻² | 0.95 | 6.4×10⁻¹ | 1.64 | 2.7×10⁻³ |


**Table I2. ***Cascade survival by channel pair. G-B is empirically superior to R-G at every quality level below Q95. R-B dies at Q40. G-B shows amplification at Q85 (ratio 3.91, higher than Q95). This is the granite effect in the chrominance domain.*


---


## I.4 Why G-B Wins


The explanation follows directly from the YCbCr conversion weights.


**|R−G| perturbation: **Moves the two channels with the highest luminance contribution (R=0.299, G=0.587). Large Y shift. Luminance quantizer sees it. Luminance quantizer is gentle, but it’s still fighting the perturbation. Moderate survival.


**|R−B| perturbation: **Moves R (Y=0.299, Cr=0.500) and B (Y=0.114, Cb=0.500). The perturbation splits across luminance and chrominance with no dominant home. Both quantizers attack it. Neither preserves it. Worst survival.


**|G−B| perturbation: **Moves G (Y=0.587) and B (Y=0.114). The net luminance change is dominated by G, but the difference |G−B| maps primarily to chrominance, specifically to Cb which weights B at 0.500 and G at −0.331. The perturbation energy concentrates in the chrominance domain. Chrominance quantization is more aggressive, which means each compression pass penalizes the perturbation harder, which means the variance anomaly diverges faster from the smooth background. More aggressive quantization drives faster amplification.


The G-B amplification at Q85 (ratio jumping from 2.41 to 3.91) is the granite effect operating in chrominance. The same mechanism, stronger, because the quantization is harsher. The harsher the quantization, the faster the amplification. The chrominance domain is the harshest quantization environment in the codec. G-B thrives there.


*The optimal channel pair is G-B, not R-G. The default in all existing code should be changed. This is not a marginal improvement. At Q85, G-B outperforms R-G by 50% (3.91 vs 2.61). At Q40, G-B is the only pair still detectable. The R-G default was arbitrary. The G-B recommendation is empirical.*


---


## I.5 The Diagnostic Architecture


Although the three channel pairs are not independent information channels (YCbCr coupling prevents independence), they have differentiated survival profiles. The *pattern of which pairs survive a given transform* is diagnostic of the transform class.


### I.5.1 Channel Pair as Transform Classifier


| Transform | R-G | R-B | G-B | Diagnosis |
| --- | --- | --- | --- | --- |
| Light compression (Q85+) | Alive | Alive | Strongest | Benign pipeline |
| Heavy compression (Q40) | Marginal | Dead | Alive | Aggressive pipeline |
| Grayscale conversion | Dead | Dead | Dead | Color destroyed |
| Color balance shift | Shifted | Shifted | Shifted | Selective color manip. |
| Chroma subsample change | Moderate | Damaged | Damaged | Chroma pipeline change |
| Targeted G-B suppression | Alive | Alive | Dead | State D. Deliberate. |


**Table I3. ***Predicted channel pair survival by transform class. The pattern of alive/dead/damaged across three pairs classifies the transformation. Rows marked “predicted” are derived from the YCbCr conversion weights and codec architecture but have not been empirically tested.*


### I.5.2 Integration with Spatial Scale Channels


The channel pair diagnostic is orthogonal to the spatial scale diagnostic from the main scheme. Spatial scales (pixel, subblock, DC) classify the *severity* of the transform. Channel pairs classify the *type* of the transform. Together they form a two-dimensional diagnostic matrix.


Three spatial scales × three channel pairs = nine cells in the diagnostic matrix. Each cell has a binary alive/dead state after a given transform. The pattern across all nine cells is a transformation fingerprint with 2⁹ = 512 possible states. Each state corresponds to a specific combination of transform severity and transform type.


The pixel scale dies under heavy compression but survives resize. The subblock scale survives heavy compression but may not survive aggressive resize. The DC scale survives everything except deliberate DC manipulation. Within each scale, G-B survives longest, R-G survives moderate compression, R-B dies first.


The nine-cell matrix is not nine independent channels. It is three correlated channel pairs observed at three partially independent spatial scales. The effective diagnostic resolution is somewhere between 2³ = 8 states (if channel pairs add no information beyond spatial scales) and 2⁹ = 512 states (if all cells are independent). The empirical resolution requires testing, which has not been performed.


---


## I.6 The Multi-Scale Defense


Every attack that kills one cell of the diagnostic matrix reveals which cell was killed. The identity of the dead cell classifies the attack.


An adversary who knows the scheme and specifically targets G-B at pixel scale (the strongest single channel) must apply per-position smoothing of the blue and green channels at marker positions. This suppresses the G-B pixel-scale cell. But the leaked signal in R-G and R-B at pixel scale survives because the adversary targeted G-B specifically. And the G-B signal at subblock and DC scales survives because the adversary targeted pixel-scale specifically.


To suppress all nine cells, the adversary must: smooth all three channel pair relationships at all three spatial scales at every marker position. That is: per-pixel smoothing of R, G, and B channels; subblock-average equalization across quadrants; and DC-level average shifting across blocks. Three independent spatial operations, each affecting all three color channels, at every marker position in the image.


The cost scales with markers × scales × pairs. The forensic residue scales identically. The legal exposure scales identically. The adversary’s optimal move, as always, is to avoid marked content entirely.


---


## I.7 The Generalized Principle


The channel pair analysis reveals an instance of a broader principle:


*Any system that partitions data into chunks for processing creates a boundary condition. The boundary enforces independence. The interior enforces correlation. Any perturbation embedded in the correlated interior is amplified by the processing that exploits that correlation, because the processing is optimized for the natural statistics of the interior and the perturbation violates those statistics.*


JPEG partitions spatially (8×8 blocks) and spectrally (YCbCr conversion). The spatial partition creates correlated block interiors. The spectral partition creates coupled color channels. The perturbation is amplified by spatial quantization (the granite effect in the block interior) and differentiated by spectral quantization (different channel pairs have different survival profiles because the codec’s color space conversion weights them differently).


The spatial partition gives us detection. The spectral partition gives us diagnosis. Both are consequences of the same architectural principle: the codec’s optimization structure creates exploitable channels in every dimension it partitions.


This principle is not specific to JPEG. Any lossy codec that partitions data spatially (blocks, windows, frames) AND spectrally (color space conversion, psychoacoustic model, frequency decomposition) creates the same two-dimensional diagnostic opportunity. The specific survival profiles differ per codec. The architectural principle is universal.


---


## I.8 Recommendations


**Change the default channel pair from R-G to G-B.** The existing codebase uses |R−G| as DEFAULT_CHANNEL_PAIRS. This should be changed to |G−B| = (1, 2). G-B is empirically superior at every quality level below Q95, shows stronger amplification, and is the last pair standing at Q40. This is a one-line code change with significant survival improvement.


**Measure all three pairs for detection.** Embed in G-B as the primary channel. Measure R-G and R-B as diagnostic echoes. The cost is two additional distance measurements per position, which is trivial. The benefit is transform classification from the channel pair survival pattern.


**Do not attempt to embed independently in all three pairs.** The YCbCr coupling prevents independence. Embedding in multiple pairs does not multiply capacity. It modestly increases detection strength (multiple views of the same perturbation) at the cost of larger pixel-domain changes. The single-pair G-B embedding with three-pair detection is the optimal strategy.


**Incorporate channel pair survival into the four-state model.** State C (degraded signal from benign transforms) can be subclassified by which channel pairs survived and which didn’t. State D (interference) can be subclassified by which pairs were targeted. The diagnostic resolution of the state model increases without additional embedding cost.


---


## I.9 What This Changes


The scheme’s operating capability at heavy compression improves significantly. The Q40 detection threshold, previously marginal on R-G (ratio 1.43, p = 0.024), becomes statistically significant on G-B (ratio 1.64, p = 0.003). The operating envelope at the aggressive-compression end extends deeper into messaging app territory (WhatsApp Q70, Instagram recompression) where survival matters most.


The diagnostic architecture gains a new axis. Spatial scale tells you how severe the transform was. Channel pair tells you what type of transform was applied. The two axes are orthogonal because they exploit different partitioning dimensions of the codec’s architecture (spatial blocks vs. color space conversion). Together they provide a richer transformation fingerprint than either axis alone.


And the finding was hiding in the code since day one. DEFAULT_CHANNEL_PAIRS was always a parameterized constant. The framework always accepted channel pair as an argument. The R-G default was chosen without testing alternatives. The G-B superiority was discovered by asking the simplest possible question: is one channel pair better than the others?


*The answer was in the code. The question had not been asked. The code was ready. The assumption was not examined. That is how axiomatic fictions work. Not by hiding the answer. By discouraging the question.*


*Empirical results from one synthetic image at 1024×1024. Pending validation on real photographs.*


*Channel pair predictions in Table I3 are derived from YCbCr weights, not measured. Each prediction is independently testable.*


***The G-B finding changes the default. The diagnostic architecture extends the scheme. Both were found by asking “what did we assume?”***


Jeremy Pickett — March 19, 2026
