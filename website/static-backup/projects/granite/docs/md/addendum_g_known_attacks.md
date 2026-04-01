# ADDENDUM G

**Known Attacks and the Ship of Theseus**

*Addendum to: Participation Over Permission — March 2026*


---


## G.1 Posture


This addendum catalogs attacks we have tested, attacks we anticipate but have not tested, and attacks we cannot anticipate. The first category has data. The second has analysis. The third has honesty.


No provenance scheme survives all attacks. A scheme that claims to is lying. The question is not “can the signal be destroyed?” It can. The question is: what does destruction cost, what evidence does destruction leave, and what does the attacker gain by paying that cost?


---


## G.2 Tested Attacks


### G.2.1 Crop to Quadrants


**The attack: **Slice a provenance-marked image into quadrants. Save each independently. Use the fragments separately.


**Result: **Individual quadrants carry a fraction of the original markers. Detection is marginal to absent depending on marker distribution. Attribution is broken because the matching service cannot correlate fragment coordinates against the full-image fingerprint without the crop offset, and the search space for offset recovery is unbounded for unknown source dimensions.


**Assessment: **Crop is an effective attack against attribution. This is a known limitation, not a problem to solve in the signal layer. The mitigation is external: reverse image search connects fragments to originals, and the original carries full provenance. The scheme plus visual search handles crop. The scheme alone does not.


### G.2.2 Slice and Stitch


**The attack: **Slice into quadrants, re-encode each, stitch back together.


**Result (2048×2048, 557 markers): **The stitched image recovers detection (3.6× ratio, p = 1.2 × 10⁻³) and fingerprint (Jaccard 0.56 against intact). Stitch seams are forensically visible at 2–3× the interior pixel difference. After an additional JPEG Q75 re-encode, detection still holds (3.4×, p = 2.7 × 10⁻³, Jaccard 0.50).


**Assessment: **Self-defeating attack. Reassembly restores the coordinate space, which restores the fingerprint. The independently encoded quadrants leave stitch scars that are themselves forensic evidence. The only winning move is to keep the pieces separate, which reduces to the crop attack.


### G.2.3 Flips


**The attack: **Horizontal, vertical, or combined flip.


**Result: **Pure coordinate remap. No interpolation. No value damage. With corrected positions, detection is identical to baseline (3.3×, p ≈ 10⁻⁴²). Without corrected positions, detection fails. The search space for flip state is four possibilities, trivially enumerable.


**Assessment: **Not a meaningful attack. The detector tries all four flip states at negligible cost.


### G.2.4 Small Rotations (1°–15°)


**The attack: **Arbitrary rotation by a small angle, forcing pixel interpolation via bicubic or Lanczos kernel.


| Angle | Corrected Pos. Ratio | Corrected p | Original Pos. Ratio | Original Pos. p |
| --- | --- | --- | --- | --- |
| 1° | 2.2× | 1.3 × 10⁻¹³ | 2.3× | 5.5 × 10⁻¹⁶ |
| 3° | 1.5× | 1.1 × 10⁻³ | 2.2× | 7.8 × 10⁻¹⁴ |
| 5° | 1.4× | 0.014 | 1.7× | 3.3 × 10⁻⁵ |
| 7° | 1.1× | 0.24 | 1.6× | 8.4 × 10⁻⁵ |
| 10° | 0.8× | 0.84 | 1.4× | 0.020 |
| 15°+ | 0.0× | 1.0 | 1.2× | 0.15 |


**Table G2. ***Small rotation survival. Signal survives 1°–3° cleanly, degrades at 5°–7°, and fails above 10°. Uncorrected original positions surprisingly outperform corrected positions at small angles.*


**Unexpected finding: **At small angles (1°–7°), detection using the original marker positions on the rotated image outperforms detection using geometrically corrected positions. The likely cause: coordinate correction introduces rounding error when mapping to integer pixel positions, while at small angles many markers near the image center have not moved far enough from their original positions to lose their perturbation signal.


**Assessment: **Small rotations (≤ 5°) do not kill the signal. Large rotations (≥ 15°) do. In practice, no platform pipeline applies arbitrary small rotations as part of standard processing. The adversary who deliberately rotates 15° has visibly damaged the image. The damage is the evidence.


### G.2.5 The Full Chain (Rotate, Flip, Rotate, Flip)


**The attack: **Rotate 5°, flip horizontal, rotate 7°, flip vertical. Two interpolation passes, two coordinate remaps. A deliberate multi-step geometric attack.


**Result: **After the full chain with corrected positions: 4.2× ratio, p = 9.2 × 10⁻⁵². After an additional JPEG Q85 re-encode: 4.0× ratio, p = 1.3 × 10⁻⁵¹. The signal not only survived the chain but emerged strongly.


**Assessment: **This result requires further investigation. The recovery after the second rotation is stronger than expected and may reflect position correction accuracy in the specific geometric configuration tested. The result should not be generalized without additional testing across varied rotation angle combinations.


---


## G.3 The Ship of Theseus


The most striking result from geometric testing was the inverse round-trip: apply the full chain (rotate 5°, flip H, rotate 7°, flip V), then reverse it exactly (flip V, rotate –7°, flip H, rotate –5°). Four interpolation passes. The result:


| Metric | Value |
| --- | --- |
| Pixels changed | 97.5% of all pixels |
| Mean absolute difference | 12.05 (visible damage) |
| PSNR | 14.9 dB |
| Detection | 3.9× ratio, p = 10⁻⁴⁹ |
| Fingerprint | Jaccard 0.72 (stronger than single JPEG cascade) |


**Table G3. ***The Ship of Theseus. 97.5% of pixels replaced. Detection holds. Fingerprint is more matchable than after a single JPEG compression cascade.*


Nearly every pixel in the image was modified. The image is visibly degraded. Four rounds of bicubic interpolation replaced 97.5% of all pixel values. And the fingerprint Jaccard against the original is 0.72 — higher than the 0.59 measured after a single JPEG Q85 compression.


The reason: interpolation is a smoothing operation. It blends values toward their neighbors. Quantization is a rounding operation that shifts values independently of neighbors. Smoothing reduces local variance anomaly but does not eliminate it, because the anomaly exists in the spatial relationship between positions, not in the absolute values at those positions. The values were replaced. The relationships survived.


*The provenance signal is not in the planks. It is in the shape of the keel. Replace every plank. The ship is still the ship.*


---


## G.4 Anticipated but Untested Attacks


### G.4.1 Targeted Local Smoothing


**The attack: **An adversary who knows the scheme applies Gaussian blur at every eligible position to destroy the perturbation specifically where markers might exist.


**Expected cost: **O(n) per position per image. At corpus scale, this is a computational campaign with discoverable infrastructure.


**Expected evidence: **A grid of locally smoothed pixels at grid-aligned positions is itself forensically detectable. Natural images do not have anomalously low variance at regular spatial intervals. The suppression creates an inverted signal — State D.


### G.4.2 Adversarial Re-embedding


**The attack: **Download a provenance-marked image. Embed a second provenance layer with the adversary’s own seed. Register the adversary’s fingerprint before the original creator registers theirs.


**Expected defense: **Multi-layer stratigraphy (Addendum F). The adversary’s layer is pristine (200/200 match quality). The original creator’s layer is degraded (185/200). The degradation direction reveals the layering order: the adversary’s layer is on top, proving it was applied second. The timestamp race is real but the stratigraphic evidence is independent of timestamps.


### G.4.3 High-Saturation Overwrite


**The attack: **Embed at maximum density — thousands of markers — to overwrite as many of the original creator’s positions as possible.


**Expected evidence: **High saturation itself is detectable. Natural images do not have 30% of eligible positions showing variance anomaly. The overwrite density is evidence of deliberate interference. State D.


### G.4.4 AI-Based Content Reconstruction


**The attack: **Use an image-to-image AI model (inpainting, style transfer, super-resolution) to reconstruct the content. The output is a new image generated by the model, not a transform of the original pixels.


**Expected result: **The provenance signal is destroyed. The model generates new pixels from a latent representation that does not preserve per-pixel perturbation structure. This is the nuclear option: it works, but the output is a different image. The adversary must accept that the AI reconstruction may introduce artifacts, alter fine details, and produce an image that is perceptibly different from the original. For high-fidelity use cases (e-commerce product photos, medical imaging, legal evidence), this is unacceptable. For casual social media sharing, it is overkill.


**Assessment: **AI reconstruction is the one attack that the scheme cannot survive by design. It is not a transformation of the file. It is the creation of a new file that resembles the old one. The defense is not in the signal. The defense is that the attack is expensive, lossy, and produces output that is forensically distinguishable from a photograph (AI-generated image detection is a parallel research area).


---


## G.5 Attacks We Cannot Anticipate


We do not know what we do not know.


Every provenance scheme in history has been broken by attacks its designers did not foresee. The correct posture is not to claim robustness against all attacks. The correct posture is to design for graceful degradation, to measure what survives and what doesn’t, and to publish the results so that others can find the weaknesses we missed.


The code is open. The method is published. The test harness is available. The attacks we have tested are documented with data. The invitation to the community is explicit: find what we missed. Break what we built. Publish the results. The scheme improves by being broken in public.


We have been wrong before — the false positive rate at basket floor 2 was 30%, the aggregate ρ detection approach failed entirely, the 4096×4096 embedding has an engineering bug we haven’t fixed. Each failure was found by testing, acknowledged, and either resolved or documented. The failures we have not yet found will be found by others. That is the point of open publication.


---


## G.6 The Attack Economics


Every attack in this addendum falls into one of three economic categories:


**Free but self-defeating: **Slice-and-stitch, flips, 90° rotations. The attack costs nothing but either undoes itself on reassembly or is trivially corrected by the detector. The attacker gains nothing.


**Cheap but detectable: **Crop, small rotations, same-codec recompression. The attack partially degrades the signal but leaves forensic evidence of the transformation. The attacker gains partial signal reduction at the cost of evidence.


**Expensive and destructive: **Targeted smoothing, high-saturation overwrite, AI reconstruction. The attack destroys the signal but at high computational cost, visible image damage, or both. The attacker gains signal destruction at the cost of image quality, compute budget, and discoverable campaign infrastructure.


No attack is free AND effective AND undetectable. This is the fundamental tradeoff. The adversary’s spreadsheet must account for all three dimensions. The scheme is designed so that every movement in one dimension costs the adversary in at least one other.


*The signal is not fragile. The ambiguity is. Fix the ambiguity and you have something real. Break the signal and you have evidence.*


*All empirical results from synthetic test images. Pending validation on real photographs.*


***The attacks we have not imagined will be found by others. That is the point.***


Jeremy Pickett — March 2026
