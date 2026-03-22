# ADDENDUM K

**The Fuse and the Fire**

**Formal Foundations, the Sawtooth Mechanism, and the Systems-Level Contribution**

*Addendum to: Participation Over Permission — March 19, 2026*


---


## K.1 Scope and Purpose


This addendum serves three functions. First, it provides formal mathematical definitions for the scheme’s core operations. Second, it identifies the sawtooth quantization error mechanism that explains the observed amplification effect. Third, it provides an honest assessment of what is novel in this work and what is prior art, and frames the contribution at the systems level where the novelty claim is defensible.


This is the document that grounds the research. It is intended to be read by reviewers, collaborators, and the authors themselves as a check against overclaiming.


---


## K.2 Formal Definitions


### K.2.1 The Perturbation


Let I be an image represented as I(x, y, c) where (x, y) is spatial position and c ∈ {R, G, B}. For a channel pair (a, b), the inter-channel distance at position (x, y) is:


δ(x, y) = |I(x, y, a) − I(x, y, b)|


The embedding selects position pairs P = {(p₁, p₁′), ..., (pₖ, pₖ′)} where each pair consists of adjacent positions (twins). At each twin pair, pixel values are modified such that:


δ(pᵢ) ∈ 𝔹  and  δ(pᵢ′) ∈ 𝔹


where 𝔹 is the prime basket — a subset of primes with a minimum floor (≥ 53). The modification is the minimum perturbation that achieves membership in 𝔹.


### K.2.2 The Natural Background


For an unperturbed natural image, δ(x, y) follows a content-dependent distribution F_nat. The probability of a random δ landing on a basket prime is p_nat ≈ 0.05–0.10. The probability of BOTH twins hitting basket primes is:


p_twin_nat = p_nat² ≈ 0.0025–0.01


### K.2.3 The Enrichment Ratio


Let M be marker positions and C be control positions. The enrichment ratio is:


ER = [count(δ(m) ∈ 𝔹 for m ∈ M) / |M|] / [count(δ(c) ∈ 𝔹 for c ∈ C) / |C|]


At generation 0 after one JPEG pass, empirically measured ER ≈ 3.4× for R-G and 3.9× for G-B at Q85.


### K.2.4 The Transform Operator


Let T_q denote a lossy compression-decompression cycle at quality q. For a pixel at position (x, y) in block B:


T_q[I](x, y, c) = IDCT(round(DCT(B_c) / Q_c) × Q_c)(x, y)


T_q is nonlinear, many-to-one, block-local, and deterministic given the quantization tables.


### K.2.5 The Variance Anomaly


For a position p with neighborhood N(p):


V(p) = Var({δ(x, y) : (x, y) ∈ N(p)})


The variance anomaly is:


VA = V(marker positions) / V(control positions)


The central empirical observation: VA(n+1) > VA(n) for moderate n and moderate q. The variance anomaly increases under iterated compression.


---


## K.3 The Sawtooth Mechanism


### K.3.1 The Quantization Error Function


The quantization error for a DCT coefficient with true value x and quantization step Q is:


e(x) = x − Q × round(x / Q)


This function ramps linearly from −Q/2 to +Q/2 as x moves across one quantization step, then snaps back to −Q/2 at the boundary. This is, by definition, a sawtooth wave with period Q and amplitude Q/2.


Every DCT coefficient in every block of every JPEG has a quantization error that follows this sawtooth function. The period is the quantization step size for that coefficient from the quantization table. Low-frequency coefficients: small Q, tight sawtooth, small amplitude. High-frequency coefficients: large Q, wide sawtooth, large amplitude.


### K.3.2 Boundary Crossings


A coefficient sitting near a sawtooth boundary (close to a snap point) is unstable under recompression. A small shift from the encode-decode cycle tips it across the boundary. Large error jump. A coefficient sitting near the middle of a ramp segment is stable. The next compression shifts it slightly but it remains on the same segment. Small error change.


After the first compression, smooth regions of the image have coefficients that sit near quantized levels — near the stable parts of the sawtooth. This is by design: the quantization grid was optimized for natural image statistics. Natural images produce coefficients that tend to converge toward grid lines.


Marker positions have coefficients that were displaced by the perturbation to unusual regions of the sawtooth. Some of these coefficients sit near boundaries. They are unstable. They cross boundaries on subsequent compression passes. Each crossing produces a discrete error event.


### K.3.3 Interference


A reconstructed pixel value at any position is the inverse DCT — a weighted sum of all 64 coefficients in the block. Each coefficient contributes with a specific basis function amplitude at that position. When a coefficient crosses a quantization boundary, the reconstructed pixel shifts by the quantization step times the basis function amplitude.


Multiple coefficients crossing boundaries at the same generation create interference. If their basis functions have the same sign at the marker position: constructive interference, the marker moves further from its neighbors. If opposite signs: destructive interference, the marker moves back toward its neighbors.


**The non-monotonic amplification curve is an interference pattern.** Some generations produce constructive interference (variance ratio increases). Some produce destructive interference (variance ratio dips). The generation-to-generation behavior oscillates because the set of boundary-crossing coefficients changes with each pass.


### K.3.4 Why the Trend Is Upward


Smooth positions: their coefficients converge toward grid lines with each generation. Fewer boundary crossings. Less error variation. The smooth background approaches a fixed point. The denominator of VA decreases.


Marker positions: their coefficients were kicked to unusual sawtooth regions by the perturbation. They keep hitting boundaries that smooth coefficients don’t hit. The crossings persist longer. The numerator of VA decreases more slowly than the denominator.


**The amplification is not “the signal gets louder.” The amplification is “the background stops oscillating and the marker doesn’t.”** The granite doesn’t get harder. The sandstone erodes.


### K.3.5 The Harmonic Interpretation


The 64 DCT basis functions are orthogonal cosine waves at different spatial frequencies. The quantization boundary crossings excite specific combinations of these waves. The reconstructed pixel value at the marker position is the superposition — an interference pattern of contributions from all 64 basis functions.


Block center is the position of maximum constructive interference for low-frequency components. The low-frequency basis functions have their antinodes at center. These components have the smallest quantization steps and therefore the most frequent boundary crossings per unit of perturbation magnitude. The perturbation rings longest at center because the components that carry it there are the ones the codec preserves most carefully.


This is mathematically equivalent to the harmonic structure of a vibrating string. The perturbation is the pluck. The DCT basis functions are the resonant modes. The quantization steps are the energy levels. The compression generations are the sustain. The variance anomaly is the amplitude at the measurement position.


---


## K.4 The Fuse and the Fire


### K.4.1 The Separation


The scheme has two cleanly independent components:


**The embedding theory (the fuse): **How to place coefficients at specific positions on the sawtooth landscape. This is where primes, baskets, channel pairs, position selection, and ASLR live. This is engineering. The fuse is consumed. The prime values are destroyed by the first compression. The initial condition ceases to exist in its original form.


**The amplification theory (the fire): **Why those positions diverge from the background under iterated compression. This is where the sawtooth error function, the DCT basis function interference, and the differential convergence rates live. This is physics. The fire spreads. The variance anomaly grows. The system dynamics persist long after the initial condition is gone.


**The fuse is not the signal. The fuse is the initial condition that starts the signal.** The fire is the signal. The fire doesn’t care what lit it.


### K.4.2 Implications for Detection


**The twin prime test (fuse detector): **Asks whether the initial condition is preserved. Are the channel distances still prime? Works at generation 0. Degrades rapidly. Measures the fuse.


**The variance anomaly test (fire detector): **Asks whether the system dynamics are still active. Are marker positions still statistically distinguishable from their neighbors? Works at generation 0 AND strengthens with each generation. Measures the fire.


Detection power transfers from the fuse detector to the fire detector as compression generations increase. At gen 0, both work. At gen 4+, only the fire detector works. The scheme’s robustness comes from the fire, not from the fuse.


### K.4.3 Implications for Generalization


The embedding theory (fuse) is format-specific. JPEG requires pixel-domain perturbation of inter-channel distances at block-center positions. MP3 would require time-domain perturbation of inter-frame energy relationships at MDCT-window-optimal positions. Different formats require different fuses.


The amplification theory (fire) is format-agnostic. Any system that partitions data, transforms it, and quantizes it creates a sawtooth error landscape. Any perturbation that places values at unusual positions on that landscape will experience differential convergence relative to natural content. The fire burns in any medium that has the three primitives: partition, transform, quantize.


The JPEG paper describes one fuse and measures one fire. The generalized theory states that the fire is universal. Each new format (MP3, H.264, AVIF) requires a new fuse design and empirical validation that the fire burns in that specific medium.


---


## K.5 Why Primes?


Given that the fire doesn’t care what lit it, why use primes specifically?


Any perturbation that places coefficients into unusual sawtooth regions would produce amplification. Primes are not special in the amplification theory. Fibonacci numbers, powers of two, or arbitrary rare values would start the same fire.


**Primes earn their place in the embedding theory, not the amplification theory:**


**1. Efficient detection: **Primality is testable in O(1) with a lookup table. The gen-0 fuse detector is a table lookup per position. No other mathematical set provides faster membership testing with comparable sparsity in the inter-channel distance domain.


**2. Natural rarity: **Primes become sparser as values increase (prime number theorem). The basket uses primes ≥ 53, where prime density is approximately 15–20% of integers. Twin primes (both positions prime) have a natural coincidence rate of ~2.5–4%. This provides a clean separation between embedded signal and natural background.


**3. Mathematical structure: **The basket is defined by a simple rule (primes above a floor), not by an arbitrary list. This is important for Kerckhoffs’s principle: the basket definition is publishable without leaking any information beyond what the algorithm description already reveals.


**4. Cultural resonance: **Primes are universally understood as structured and non-random. A reviewer who sees “we embedded prime-valued distances” immediately understands the signal is intentional. This is not a technical argument. It is a communication argument. It matters for adoption.


---


## K.6 Novelty Assessment


**This section is an honest accounting of what is and is not new in this work. It is written for the authors as a check against overclaiming and for reviewers as evidence of intellectual honesty.**


### K.6.1 What Is NOT New


**Robust watermarking: **A fifty-year-old field. Embedding perturbations that survive compression is the research program of Cox, Fridrich, and hundreds of others.


**Quantization Index Modulation (QIM): **Chen and Wornell, 2001. Explicitly embeds information by controlling which quantization bin a coefficient lands in. This is embedding relative to the quantization grid.


**The sawtooth error function of quantization: **Textbook signal processing. Every EE undergraduate learns this.


**DCT basis function analysis at block positions: **Standard. The frequency-domain behavior at block center versus block edge is well characterized.


**Mathematical structures in watermarking: **Primes, lattices, and other mathematical sets have been explored as embedding domains.


**Perceptual hashing for image identification: **Well-established field with production systems (Google, Facebook).


**Content ID-style matching services: **YouTube has operated Content ID since 2007.


### K.6.2 What Is Probably New


**1. Compression-as-amplifier paradigm: **The watermarking literature frames compression as the enemy of watermark survival. This scheme frames compression as the detection amplifier. The perturbation is not preserved through compression. The perturbation triggers a system dynamic (the fire) that amplifies under compression. We are not aware of a published paper that frames compression amplification as the primary detection strategy, but the literature is vast and this assessment may be incorrect.


**2. The fuse/fire separation: **The explicit separation of the initial condition (destroyed by compression) from the system dynamics (amplified by compression) as two independent theories with different generalization properties. Most watermarking papers try to preserve the embedded data through the transform. This scheme does not preserve anything. It triggers a process. This framing may exist in information-theoretic terms in the capacity literature, but we have not found it stated explicitly.


**3. The multi-channel diagnostic matrix: **Using an intentionally embedded signal’s differential survival across nine channels (three spatial scales × three channel pairs) as a transformation classifier, where the failure pattern diagnoses the transform class. Detection plus diagnosis from one embedding is architecturally distinct from detection alone.


**4. The economic architecture: **The thermodynamic tax, the lazy-versus-synchronous asymmetry, and the mechanism design argument that matching services are economically inevitable without altruism. Watermarking papers do not typically include economic analysis of suppression cost at corpus scale.


**5. The generalization to a universal principle: **The claim that any system built on partition-transform-quantize creates exploitable channels where perturbations amplify, and that this principle applies across image codecs, audio codecs, and potentially any chunked lossy processing system. The breadth of this claim is new even if individual instances may have been observed.


### K.6.3 What Must Be Verified


Before claiming novelty in print, the following literature searches must be performed:


Google Scholar: "compression amplification watermarking"


Google Scholar: "iterative compression watermark detection"


Google Scholar: "quantization noise amplification embedding"


Google Scholar: "variance ratio watermark detection"


Google Scholar: "differential degradation watermark forensics"


Google Scholar: "QIM amplification recompression"


ACM DL + IEEE Xplore: "robust watermark JPEG cascade"


If these searches return papers describing the amplification effect, they must be cited. The contribution is then framed as: building on the observed amplification, this work provides the first complete system architecture exploiting it for provenance detection, multi-channel diagnosis, permissionless attribution, and self-enforcing economics.


If these searches return nothing relevant, the amplification observation itself becomes a contribution. But the primary contribution remains the systems architecture regardless.


---


## K.7 The Systems-Level Contribution


The defensible novelty claim is at the systems level. Individual components may have prior art. The integration does not.


*We observe that lossy compression amplifies structured perturbations (citing relevant prior work if it exists). We exploit this property within a system that combines multi-scale embedding, differential channel diagnosis, position-based attribution, permissionless matching services, and self-enforcing economics. The system as a whole produces properties that no individual component provides: transformation-resilient provenance that amplifies under compression, classifies the transformation pipeline from the failure pattern, and creates economic incentives for protection without requiring cooperation or altruism.*


This framing is robust to prior art discovery. If someone observed amplification before, we cite them and build on their work. If someone built a matching service, we cite them and integrate their approach. If someone analyzed suppression economics, we cite them and extend their analysis. The contribution is the architecture that integrates all of these components into a self-reinforcing system.


### K.7.1 The Gear Analogy


The concept of gear teeth is ancient. Variable gears with differential tooth strategies are not. The individual teeth are known. The gear as an integrated mechanism that converts the teeth into a specific torque profile is new.


Similarly: sawtooth quantization error is known. DCT basis function analysis is known. Prime number sparsity is known. Position-based fingerprinting is known. Matching service economics are known. The system that combines these into a provenance architecture where compression amplification drives detection, channel pair analysis drives diagnosis, position patterns drive attribution, and thermodynamic asymmetry drives adoption — that system is the contribution.


The teeth are the literature. The gear is the paper.


---


## K.8 Required Literature Review


The following must be completed before the main paper is submitted to any venue. The results of the literature review will determine the framing of Section 4 (amplification) and the novelty claims throughout.


| Search Query | Looking For | Impact If Found |
| --- | --- | --- |
| compression amplification watermarking | Any paper observing that watermark detectability increases under compression | Cite as foundation. Reframe our contribution as the system built on their observation. |
| iterative JPEG watermark variance | Empirical observation of variance anomaly growth across JPEG generations | Cite as prior observation. Our contribution adds the mechanism explanation and the system architecture. |
| QIM recompression robustness | Analysis of QIM behavior under iterative compression | Cite and compare. QIM tries to preserve bin assignment. Our scheme doesn’t. Different mechanism. |
| differential channel watermark forensics | Using multiple measurement channels to classify transforms | Cite and extend. Our nine-channel matrix may generalize their approach. |
| watermark suppression cost economics | Economic analysis of adversarial watermark removal at scale | Cite and build on. Our thermodynamic tax extends their analysis with energy quantification. |


**Table K1. ***Literature review requirements. Each search either confirms novelty or identifies prior art to cite. Both outcomes strengthen the paper.*


---


## K.9 What a Formal Proof Requires


The amplification argument in K.3 is an argument, not a proof. A formal proof would require:


**1. **Explicit computation of DCT basis function amplitudes at block center for all 64 coefficients.


**2. **Explicit bounds on the quantization residual for a localized spike input versus a smooth input of equal energy, under the standard JPEG quantization tables.


**3. **A convergence argument showing that the ratio β/α > 1 (marker deviation shrinks more slowly than smooth deviation) holds for at least K generations under standard tables at quality levels Q40–Q95.


**4. **Extension to the multi-channel case accounting for the YCbCr color space conversion and chrominance subsampling.


This is a tractable problem in linear algebra and fixed-point analysis. It is the kind of problem a graduate student in signal processing could formalize in a few weeks. The empirical data strongly suggests the proof exists. The proof itself has not been constructed.


The paper should state the argument and present the empirical data. The formal proof is future work. This is honest and standard practice in systems papers that present empirical observations with conjectured explanations.


---


## K.10 Positioning


The paper is a systems paper, not a signal processing theory paper. The contribution is the architecture. The amplification is the enabling observation. The formal mathematics supports the observation but does not need to be proved in the paper.


The correct venue is a systems security conference (USENIX Security, DEF CON) or a multimedia security workshop (ACM IH&MMSec), not a signal processing theory venue (ICASSP). The theory supports the system. The system is the contribution.


If the formal proof is later completed (by the authors or by a collaborator with signal processing theory expertise), it becomes a companion paper at a theory venue. The two papers cite each other. The systems paper demonstrates the effect empirically. The theory paper proves why it occurs. Both are stronger together than either alone.


---


*The teeth are known. The gear is new. The individual components of this system — quantization error, DCT analysis, prime sparsity, position fingerprinting, matching economics — each have prior art. The architecture that integrates them into a self-reinforcing provenance system where compression amplifies detection, channel analysis enables diagnosis, position patterns enable attribution, and thermodynamic asymmetry enables adoption is the contribution. The novelty is at the systems level. The literature review will determine whether individual components also contribute novel observations. Either outcome produces a publishable paper. The honest framing is the strongest framing.*


*The fuse is engineering. The fire is physics. They are independent. The fuse can change without affecting the fire. The fire generalizes without requiring a specific fuse. The JPEG paper describes one fuse and one fire. The generalized theory claims the fire is universal. Each new format tests the claim. The claim stands or falls on empirical evidence, not on the elegance of the argument.*


*This addendum is the authors’ honest assessment of their own work.*


*It identifies what is known, what is probably new, and what must be verified.*


*It is written to be read by hostile reviewers and to withstand their scrutiny.*


***The strongest position is the honest position. Overclaiming is the only fatal error.***


Jeremy Pickett — March 19, 2026


*Co-developed with Claude (Anthropic), reviewed by Gemini (Google) and GPT-4o (OpenAI).*


*Human-directed. AI-assisted. Friction welcome and required.*
