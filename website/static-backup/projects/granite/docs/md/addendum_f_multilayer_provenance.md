# ADDENDUM F

**Multi-Layer Provenance and Probabilistic Matching**

*Addendum to: Participation Over Permission — March 2026*


---


## F.1 The Scenario


An image passes through multiple hands. Each hand may embed provenance with its own seed. The image accumulates layers. The question: does multi-layer embedding break detection or attribution?


It does neither. It enriches both. But the mechanism requires a precise walkthrough.


---


## F.2 Alice and Bob


J is a clean 1024×1024 JPEG. No provenance.


**Alice** downloads J. Her embedder derives 200 positions from her seed and the image’s content hash. She embeds twin markers at those positions. She registers her fingerprint (the hash of her position set) with a matching service under a pseudonym. She releases the image.


**Bob** downloads Alice’s modified image. He does not know Alice embedded anything. His embedder derives 200 positions from his seed and the image’s content hash — which is different from Alice’s input because Alice modified pixels. Bob gets a different position set. Approximately 10–15 positions overlap with Alice’s by chance. Bob embeds at his positions, overwriting Alice’s values at the overlapping positions. He registers his fingerprint. He releases the image.


The image now carries two layers. Approximately 385–390 unique disrupted positions. Two fingerprints. Two strata.


---


## F.3 What the Detector Sees


The detector has no seeds. No baskets. No knowledge of Alice or Bob. It does one thing: scan every eligible position and measure local variance anomaly. Disrupted or smooth. It produces a binary map with approximately 390 disrupted positions out of 4,000 eligible. It hashes the combined map and submits the whole thing to the matching service.


**The detector does not separate the layers. It does not try. It is a thermometer. It measures heat. It does not know whose heat it is measuring.**


---


## F.4 What the Matching Service Sees


The service receives the combined disruption map. It already holds Alice’s registered fingerprint (her 200 positions) and Bob’s registered fingerprint (his 200 positions). It performs fuzzy subset containment: is Alice’s pattern contained within the combined map? Is Bob’s?


| Pseudonym | Registered | Match Quality | Interpretation |
| --- | --- | --- | --- |
| Alice_001 | March 15 | 185 / 200 | Strong match. ~15 positions overwritten by later embedding. |
| Bob_007 | March 22 | 200 / 200 | Perfect match. Top layer. Nothing overwrote this embedding. |


**Table F1. ***Matching service results for the Alice/Bob scenario. Match quality differential reveals stratigraphic order independently of timestamps.*


The service returns both matches, both timestamps, and both match quality scores. It does not judge which is the “owner.” It reports what it found.


---


## F.5 Stratigraphy


The match quality differential reveals the layering order. Alice has 185/200 because Bob’s embedding overwrote a few of her positions. Bob has 200/200 because he was the last to embed and nothing overwrote him. The top layer is pristine. The bottom layer has small gaps where the top layer landed on the same positions.


If Bob had embedded first and Alice second, the numbers would be reversed: Bob at 185/200, Alice at 200/200. The overwriting direction tells you the order independently of the timestamps. Two independent clocks — the registration timestamp and the match quality degradation — both point in the same direction.


This extends to N layers. Each successive embedding slightly degrades all layers beneath it. The most degraded fingerprint is the oldest. The most pristine is the most recent. The image carries its own handling history in its perturbation strata.


---


## F.6 It’s Always a Probability Cloud


Every layer of this scheme is probabilistic:


The embedding is probabilistic — basket selection, position sampling, survival statistics.


The detection is probabilistic — variance anomaly is a distribution test, not a threshold.


The fingerprint is probabilistic — Jaccard 0.47 across transforms, not 1.0.


The matching is probabilistic — 185 out of 200, not 200 out of 200.


The attribution is probabilistic — “correlates with,” not “belongs to.”


**This is the strength, not the weakness.** An exact system is brittle. Change one bit and the match fails. A probabilistic system degrades gracefully. Change 15 positions and the match quality drops from 200/200 to 185/200. The match still holds. The confidence is reported. The consumer decides what confidence threshold matters.


A court does not need 200/200. A court needs “more likely than not.” 185 out of 200 expected positions showing disruption, against a background expectation of 10 out of 200, is overwhelming. The probability cloud has a sharp peak and the peak is at the right answer.


A system that says “this is definitely Alice’s image” is lying. A system that says “185 out of 200 expected positions show disruption consistent with Alice’s registered fingerprint, with a background expectation of 10 out of 200” is telling the truth. The truth is a probability cloud. The cloud has a shape. The shape is the evidence.


---


*The detector is geology — it measures the rock. The matching service is stratigraphy — it identifies the layers. Two different disciplines. Two different participants. Both necessary. Neither sufficient alone.*


Jeremy Pickett — March 2026
