# ADDENDUM J

**The Thermodynamic Tax**

**Energy Asymmetry, Temporal Asymmetry, and the Thermal Limit on Suppression**

*Addendum to: Participation Over Permission — March 19, 2026*


---


## J.1 The Proposition


Bitcoin mining established a principle: rewriting history has a thermodynamic floor. The energy required to forge a blockchain is not a software parameter. It is a physical constraint. The compute produces heat. The heat costs money. The money is a discoverable budget line item. The physics constrains the economics.


Provenance suppression has the same property. Stripping provenance from a corpus of marked images requires compute that cannot be reduced below a physical minimum. The minimum exists because the suppression operation requires decoding, scanning, per-position decision-making, modification, verification, and re-encoding. Each step consumes energy. The energy is a function of image count, marker density, scale count, and channel pair count. The function has a floor. The floor is thermodynamic.


This addendum quantifies the asymmetry between embedding, detection, and suppression across three dimensions: energy, time, and discoverability.


---


## J.2 The Three Operations


### J.2.1 Embedding (The Creator)


The creator saves an image. The embedding adds: one HMAC-SHA512 derivation (microseconds), k pixel modifications at known positions (k ≈ 200), and the normal JPEG encode that was happening anyway. The marginal energy cost above a normal save is approximately 0.01 joules. The marginal time cost is negligible. The embedding rides the save operation. It does not create a new operation.


### J.2.2 Detection (The Observer)


**Tier 1 (DQT scan): **Read 128 bytes from the file header. Count primes. No decode required. No pixel access. Cost: approximately 0.0001 joules. Runs at disk I/O speed. A single core can scan millions of files per hour.


**Tier 2 (known-position detection): **Full image decode (the expensive part), then k position reads and distance measurements. Cost: approximately 0.1 joules, dominated entirely by the JPEG decode. The provenance measurement itself is negligible relative to the decode.


**Tier 3 (blind variance scan): **Full decode plus variance measurement at all m eligible positions (m ≈ 4,000 at 1024×1024). Cost: approximately 0.1–0.2 joules. Still dominated by the decode.


**Critical property: **Detection has no timing constraint. It is a read operation. It can run as a batch job, a cron task, a background process during off-peak hours. It can be amortized across hours, days, or weeks. The cost per image approaches the theoretical minimum because there is no deadline and no latency requirement.


### J.2.3 Suppression (The Adversary)


The adversary must decode the image, scan all eligible positions at all spatial scales across all channel pairs, distinguish real markers from natural prime-distance coincidences (which they cannot do without the seed), make per-position suppression decisions, apply pixel modifications, verify the modifications did not create visible artifacts, and re-encode. This is a full image processing pipeline dedicated entirely to provenance removal.


Cost per image: approximately 0.5–2.0 joules depending on image size, marker density, and the number of scales and channel pairs that must be suppressed. This is 50–200× the energy cost of detection and 50–20,000× the marginal cost of embedding.


**Critical property: **Suppression is a synchronous write operation. It must complete before the image is served. If the adversary serves the image before suppression completes, the unsuppressed image with intact provenance is delivered to the requester. The suppression pipeline sits in the hot path between upload receipt and content availability. Every millisecond of suppression latency is a millisecond added to the upload-to-live pipeline. This is SLA territory.


---


## J.3 The Three-Axis Asymmetry


| Dimension | Embedder | Detector | Suppressor |
| --- | --- | --- | --- |
| Energy per image | ~0.01 J (marginal) | ~0.1 J (decode-dominated) | ~0.5–2 J (full pipeline) |
| Timing constraint | None. Embeds at save time. | None. Batch. Lazy. Off-peak. | Synchronous. Hot path. Before serving. |
| Scaling model | Per-creator. Runs on their device. | Horizontal. Add readers. Partition corpus. | Vertical. Peak-provisioned. SLA-bound. |
| Failure mode | No provenance. Benign. | Missed image. Catch later. Benign. | Served unsuppressed. Signal leaked. Catastrophic. |
| Cost at 1M images/day | Negligible (creator’s device) | Modest (batch overnight) | Substantial (real-time pipeline, peak-provisioned) |
| Infrastructure | None beyond normal save | Any server, any time | Dedicated pipeline. Monitoring. Alerting. On-call. |
| Discoverability | None (normal save operation) | None (normal scan operation) | High (compute bills, team, code, SLAs, incident reports) |


**Table J1. ***Three-axis asymmetry. The embedder and detector operate off the clock with benign failure modes. The suppressor operates on the clock with catastrophic failure modes. The economics penalize suppression on every axis.*


---


## J.4 The Informational Asymmetry


The energy and timing asymmetries are compounded by an informational asymmetry that multiplies the suppressor’s per-image cost.


The embedder knows the seed. The seed derives the exact marker positions. The embedder touches exactly k positions (k ≈ 200). No wasted work. Perfect targeting.


The adversary does not know the seed. The adversary observes approximately m positions with prime-valued channel distances (m ≈ 440 at 1024×1024). Of these, k are real markers and (m − k) are natural coincidences. The adversary cannot distinguish real from natural without the seed. The adversary must process all m candidates.


The blind work multiplier is m/k ≈ 440/200 ≈ 2.2× per channel pair. Across three channel pairs and three spatial scales, the candidate count multiplies. The adversary processes approximately m × s × p candidates while the embedder touched k positions. The ratio:


Suppression candidates: m × s × p ≈ 440 × 3 × 3 = 3,960


Embedding positions:    k = 200


Blind work multiplier:  3,960 / 200 ≈ 20×


The adversary does twenty times more per-position work than the embedder, per image, at minimum. This multiplier increases with higher marker density, more spatial scales, and more channel pairs. The multiplier is structural. It cannot be reduced without the seed.


---


## J.5 The Temporal Trap


Detection is a read operation. Reads are lazy. Reads are eventually consistent. Reads can be deferred, batched, parallelized, and amortized. A missed read is caught on the next pass. The failure mode is delay, not loss.


Suppression is a write operation. Writes are synchronous. Writes must complete before the content is served. A missed write means the unsuppressed content is delivered with provenance intact. The failure mode is leakage, not delay.


The temporal trap: the suppressor must maintain 100% uptime on a synchronous processing pipeline that adds latency to every upload. Any pipeline failure — a crashed worker, a queue overflow, a capacity shortfall during a traffic spike — results in unsuppressed content escaping into the delivery path. Achieving 100% suppression uptime requires monitoring, alerting, on-call rotation, capacity planning, incident response, and post-incident review. Each of these is an operational cost. Each is documented. Each is discoverable.


The detector has no such constraint. The detector can crash, restart, skip files, reprocess files, run during off-peak, pause during traffic spikes, and still produce the same final result: a complete scan of the corpus, eventually. The detector’s reliability requirement is zero. Its consistency requirement is eventual. Its SLA is “whenever.”


**The asymmetry in operational burden: **the suppressor must run a production-grade, SLA-bound, real-time processing pipeline with incident response. The detector must run a batch job. The operational cost ratio is not 20×. It is orders of magnitude, because production-grade real-time pipelines cost orders of magnitude more to operate than batch jobs.


---


## J.6 The Thermal Limit


Bitcoin mining established that rewriting blockchain history requires energy proportional to the hash rate of the honest network. The energy cost is physical. It cannot be reduced by better software. It can only be reduced by reducing the work, and reducing the work means reducing the security.


Provenance suppression has an analogous thermal limit. Suppressing the signal from a marked image requires a minimum number of computational operations: decode, scan, decide, modify, verify, re-encode. Each operation consumes energy. The energy is proportional to image size, marker density, and the number of independent channels (scales × pairs) that must be suppressed.


The thermal floor for suppressing one 1024×1024 image with 200 markers across 3 scales and 3 channel pairs is approximately 0.5–2.0 joules. This floor cannot be reduced by algorithmic optimization because the operations are inherently sequential (modify depends on decide, which depends on scan, which depends on decode) and each operation has a physical minimum cost.


At corpus scale:


| Corpus Size | Suppression Energy (low) | Suppression Energy (high) | Equivalent |
| --- | --- | --- | --- |
| 1,000 images/day | 500 J/day | 2,000 J/day | Negligible |
| 1M images/day | 500 kJ/day | 2 MJ/day | A server running continuously |
| 100M images/day | 50 MJ/day | 200 MJ/day | A data center wing |
| 1B images/day | 500 MJ/day | 2 GJ/day | A power plant’s output for minutes |


**Table J2. ***Thermal floor for provenance suppression at scale. At hyperscale (1B images/day), the suppression energy approaches the output of industrial power generation. These estimates are lower bounds based on computational operation counts and do not include cooling, networking, storage, or operational overhead.*


These numbers are the theoretical minimum. Real-world suppression includes overhead: pipeline coordination, quality verification, failure handling, re-processing of failed images, storage of intermediate states, and monitoring. The actual energy cost is typically 3–10× the theoretical minimum for production pipelines.


---


## J.7 The Incentive Structure


The thermodynamic tax creates a natural incentive gradient:


**Serving provenance-marked content as-is: **Zero additional cost. The content passes through the normal pipeline unchanged. The provenance signal rides for free. The platform expends no energy on provenance. The signal is present in the served content. This is the cheapest possible operation.


**Detecting provenance at ingestion: **Minimal additional cost. A DQT scan at 0.0001 J per file. A batch variance scan at 0.1 J per file, run overnight. The detection cost is dwarfed by the normal pipeline cost of processing the upload (resize, thumbnail, re-encode). Detection adds single-digit percentage overhead to existing operations.


**Suppressing provenance before serving: **Substantial additional cost. A dedicated real-time pipeline at 0.5–2.0 J per file. Synchronous. Peak-provisioned. SLA-bound. The suppression cost may exceed the normal pipeline cost for each image. At hyperscale, the suppression pipeline is a significant infrastructure investment with discoverable operational footprint.


The gradient points in one direction: **serve authentic, unaltered provenance-marked files.** That is the minimum-energy state. Any deviation from that state — any attempt to modify, suppress, or strip provenance — costs energy, costs time, costs operational complexity, and produces discoverable evidence of the attempt.


The scheme does not prevent suppression. The scheme makes suppression *expensive*. The expense is not a design parameter. It is a thermodynamic property. The adversary cannot negotiate with the physics. The physics sets the floor. The floor is the tax.


---


## J.8 The Bitcoin Parallel


The analogy to Bitcoin proof-of-work is precise in structure but different in mechanism.


**Bitcoin: **Rewriting history requires re-computing the proof-of-work for every block in the chain. The energy cost scales linearly with chain length. The cost is borne by the attacker. The honest network’s energy expenditure creates the cost floor. The attacker must exceed the honest network’s cumulative work to succeed.


**Provenance suppression: **Suppressing provenance requires per-image, per-position, per-scale, per-pair processing. The energy cost scales linearly with corpus size and multiplicatively with signal complexity (markers × scales × pairs). The cost is borne entirely by the suppressor. No honest network needs to expend energy to create the cost floor — the signal itself, embedded once at negligible cost, creates the suppression floor. The creator’s one-time embedding creates a permanent energy obligation for any adversary who wants to remove it.


The key difference: Bitcoin requires continuous energy expenditure by the honest network to maintain security. The provenance scheme requires *zero* continuous energy expenditure after the initial embedding. The signal is self-sustaining. The amplification is free — the adversary’s own compression pipeline provides it. The cost floor exists without ongoing investment by the creator.


The creator spends 0.01 joules once. The adversary spends 0.5–2.0 joules per image, per encounter, forever, across every copy of the file, at every scale and every channel pair, with synchronous timing constraints and catastrophic failure modes.


*Bitcoin’s security costs the honest network energy. Provenance security costs the honest creator almost nothing. The thermodynamic tax is paid entirely by the adversary. The creator sets the trap by saving a file. The physics collects the tax.*


---


## J.9 Measurability


The thermodynamic tax is empirically measurable. Time the embedding function. Time the detection function. Time a blind suppression function. Compute the energy from the wall-clock time and the processor’s TDP. The ratio between suppression energy and embedding energy is the tax rate. The ratio between suppression energy and detection energy is the enforcement asymmetry.


These measurements belong in the paper as a table. The measurements are reproducible. The code is BSD licensed. Any reader can run the same timing benchmarks on their own hardware and verify the asymmetry. The tax rate is not a claim. It is a measurement. Measurements are not debatable.


The measurement also serves as a deterrent. An adversary reading the paper sees the tax rate, multiplies by their corpus size, and computes their suppression budget. The budget either fits their economics or it doesn’t. If it doesn’t, the rational response is to not suppress. The paper’s publication of the tax rate is itself an economic signal to potential adversaries: the cost is known, the cost is quantified, and the cost is your problem.


---


## J.10 The Minimum-Energy State


Thermodynamic systems tend toward their minimum-energy state. A ball rolls downhill. A gas fills its container. A market finds its equilibrium.


The minimum-energy state for a platform processing provenance-marked images is: **serve them as-is.** Don’t suppress. Don’t modify. Don’t strip. Let the signal ride through the normal pipeline. The signal’s presence costs nothing. The signal’s removal costs energy, time, complexity, and legal exposure.


The scheme does not force platforms to serve provenance. It makes serving provenance the state the system naturally falls into when no additional energy is expended. Suppression requires sustained energy input against the gradient. Release the energy input and the system returns to the minimum-energy state: provenance preserved.


This is not an analogy. This is a description of the energy landscape. The platform that serves provenance is at rest. The platform that suppresses provenance is climbing uphill. The hill never ends because every new image requires new suppression energy. The moment the suppression pipeline stops, the provenance signal reappears in every subsequently processed image.


*The scheme incentivizes serving authentic, unaltered provenance-marked files. Not through policy. Not through legislation. Not through cooperation. Through thermodynamics. The minimum-energy state is creator protection. Every other state costs more. Physics does not negotiate.*


*Energy estimates are order-of-magnitude calculations based on computational operation counts.*


*Precise measurements require benchmark implementations on representative hardware, which have not been performed.*


***The asymmetry is structural. The specific ratios are approximate. The gradient is not.***


Jeremy Pickett — March 19, 2026
