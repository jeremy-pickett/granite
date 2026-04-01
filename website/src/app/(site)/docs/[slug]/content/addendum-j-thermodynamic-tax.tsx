export default function AddendumJThermodynamicTaxContent() {
  return (
    <>
<header className="page-hero">
  <div className="container">
    <p className="hero-series">Addendum J</p>
    <h1>The Thermodynamic Tax</h1>
    <p className="hero-subtitle">Granite Under Sandstone &mdash; Addendum Series</p>
  </div>
</header>

<section className="section">
  <div className="container content-narrow">
    <h2>J.1 The Proposition</h2>
    <p>Bitcoin mining established a principle: rewriting history has a thermodynamic floor. The energy required to forge a blockchain is not a software parameter. It is a physical constraint. The compute produces heat. The heat costs money. The money is a discoverable budget line item. The physics constrains the economics.</p>
    <p>Provenance suppression has the same property. Stripping provenance from a corpus of marked images requires compute that cannot be reduced below a physical minimum. The minimum exists because the suppression operation requires decoding, scanning, per-position decision-making, modification, verification, and re-encoding. Each step consumes energy. The energy is a function of image count, marker density, scale count, and channel pair count. The function has a floor. The floor is thermodynamic.</p>
    <p>This addendum quantifies the asymmetry between embedding, detection, and suppression across three dimensions: energy, time, and discoverability.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>J.2 The Three Operations</h2>
    <h3>J.2.1 Embedding (The Creator)</h3>
    <p>The creator saves an image. The embedding adds: one HMAC-SHA512 derivation (microseconds), k pixel modifications at known positions (k ≈ 200), and the normal JPEG encode that was happening anyway. The marginal energy cost above a normal save is approximately 0.01 joules. The marginal time cost is negligible. The embedding rides the save operation. It does not create a new operation.</p>
    <h3>J.2.2 Detection (The Observer)</h3>
    <p><strong>Tier 1 (DQT scan): </strong>Read 128 bytes from the file header. Count primes. No decode required. No pixel access. Cost: approximately 0.0001 joules. Runs at disk I/O speed. A single core can scan millions of files per hour.</p>
    <p><strong>Tier 2 (known-position detection): </strong>Full image decode (the expensive part), then k position reads and distance measurements. Cost: approximately 0.1 joules, dominated entirely by the JPEG decode. The provenance measurement itself is negligible relative to the decode.</p>
    <p><strong>Tier 3 (blind variance scan): </strong>Full decode plus variance measurement at all m eligible positions (m ≈ 4,000 at 1024×1024). Cost: approximately 0.1–0.2 joules. Still dominated by the decode.</p>
    <p><strong>Critical property: </strong>Detection has no timing constraint. It is a read operation. It can run as a batch job, a cron task, a background process during off-peak hours. It can be amortized across hours, days, or weeks. The cost per image approaches the theoretical minimum because there is no deadline and no latency requirement.</p>
    <h3>J.2.3 Suppression (The Adversary)</h3>
    <p>The adversary must decode the image, scan all eligible positions at all spatial scales across all channel pairs, distinguish real markers from natural prime-distance coincidences (which they cannot do without the seed), make per-position suppression decisions, apply pixel modifications, verify the modifications did not create visible artifacts, and re-encode. This is a full image processing pipeline dedicated entirely to provenance removal.</p>
    <p>Cost per image: approximately 0.5–2.0 joules depending on image size, marker density, and the number of scales and channel pairs that must be suppressed. This is 50–200× the energy cost of detection and 50–20,000× the marginal cost of embedding.</p>
    <p><strong>Critical property: </strong>Suppression is a synchronous write operation. It must complete before the image is served. If the adversary serves the image before suppression completes, the unsuppressed image with intact provenance is delivered to the requester. The suppression pipeline sits in the hot path between upload receipt and content availability. Every millisecond of suppression latency is a millisecond added to the upload-to-live pipeline. This is SLA territory.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>J.3 The Three-Axis Asymmetry</h2>
    <div className="table-wrap"><table>
<thead><tr><th>Dimension</th><th>Embedder</th><th>Detector</th><th>Suppressor</th></tr></thead>
<tbody>
<tr><td>Energy per image</td><td>~0.01 J (marginal)</td><td>~0.1 J (decode-dominated)</td><td>~0.5–2 J (full pipeline)</td></tr>
<tr><td>Timing constraint</td><td>None. Embeds at save time.</td><td>None. Batch. Lazy. Off-peak.</td><td>Synchronous. Hot path. Before serving.</td></tr>
<tr><td>Scaling model</td><td>Per-creator. Runs on their device.</td><td>Horizontal. Add readers. Partition corpus.</td><td>Vertical. Peak-provisioned. SLA-bound.</td></tr>
<tr><td>Failure mode</td><td>No provenance. Benign.</td><td>Missed image. Catch later. Benign.</td><td>Served unsuppressed. Signal leaked. Catastrophic.</td></tr>
<tr><td>Cost at 1M images/day</td><td>Negligible (creator’s device)</td><td>Modest (batch overnight)</td><td>Substantial (real-time pipeline, peak-provisioned)</td></tr>
<tr><td>Infrastructure</td><td>None beyond normal save</td><td>Any server, any time</td><td>Dedicated pipeline. Monitoring. Alerting. On-call.</td></tr>
<tr><td>Discoverability</td><td>None (normal save operation)</td><td>None (normal scan operation)</td><td>High (compute bills, team, code, SLAs, incident reports)</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table J1. </strong><em>Three-axis asymmetry. The embedder and detector operate off the clock with benign failure modes. The suppressor operates on the clock with catastrophic failure modes. The economics penalize suppression on every axis.</em></p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>J.4 The Informational Asymmetry</h2>
    <p>The energy and timing asymmetries are compounded by an informational asymmetry that multiplies the suppressor’s per-image cost.</p>
    <p>The embedder knows the seed. The seed derives the exact marker positions. The embedder touches exactly k positions (k ≈ 200). No wasted work. Perfect targeting.</p>
    <p>The adversary does not know the seed. The adversary observes approximately m positions with prime-valued channel distances (m ≈ 440 at 1024×1024). Of these, k are real markers and (m − k) are natural coincidences. The adversary cannot distinguish real from natural without the seed. The adversary must process all m candidates.</p>
    <p>The blind work multiplier is m/k ≈ 440/200 ≈ 2.2× per channel pair. Across three channel pairs and three spatial scales, the candidate count multiplies. The adversary processes approximately m × s × p candidates while the embedder touched k positions. The ratio:</p>
    <p>Suppression candidates: m × s × p ≈ 440 × 3 × 3 = 3,960</p>
    <p>Embedding positions:    k = 200</p>
    <p>Blind work multiplier:  3,960 / 200 ≈ 20×</p>
    <p>The adversary does twenty times more per-position work than the embedder, per image, at minimum. This multiplier increases with higher marker density, more spatial scales, and more channel pairs. The multiplier is structural. It cannot be reduced without the seed.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>J.5 The Temporal Trap</h2>
    <p>Detection is a read operation. Reads are lazy. Reads are eventually consistent. Reads can be deferred, batched, parallelized, and amortized. A missed read is caught on the next pass. The failure mode is delay, not loss.</p>
    <p>Suppression is a write operation. Writes are synchronous. Writes must complete before the content is served. A missed write means the unsuppressed content is delivered with provenance intact. The failure mode is leakage, not delay.</p>
    <p>The temporal trap: the suppressor must maintain 100% uptime on a synchronous processing pipeline that adds latency to every upload. Any pipeline failure — a crashed worker, a queue overflow, a capacity shortfall during a traffic spike — results in unsuppressed content escaping into the delivery path. Achieving 100% suppression uptime requires monitoring, alerting, on-call rotation, capacity planning, incident response, and post-incident review. Each of these is an operational cost. Each is documented. Each is discoverable.</p>
    <p>The detector has no such constraint. The detector can crash, restart, skip files, reprocess files, run during off-peak, pause during traffic spikes, and still produce the same final result: a complete scan of the corpus, eventually. The detector’s reliability requirement is zero. Its consistency requirement is eventual. Its SLA is “whenever.”</p>
    <p><strong>The asymmetry in operational burden: </strong>the suppressor must run a production-grade, SLA-bound, real-time processing pipeline with incident response. The detector must run a batch job. The operational cost ratio is not 20×. It is orders of magnitude, because production-grade real-time pipelines cost orders of magnitude more to operate than batch jobs.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>J.6 The Thermal Limit</h2>
    <p>Bitcoin mining established that rewriting blockchain history requires energy proportional to the hash rate of the honest network. The energy cost is physical. It cannot be reduced by better software. It can only be reduced by reducing the work, and reducing the work means reducing the security.</p>
    <p>Provenance suppression has an analogous thermal limit. Suppressing the signal from a marked image requires a minimum number of computational operations: decode, scan, decide, modify, verify, re-encode. Each operation consumes energy. The energy is proportional to image size, marker density, and the number of independent channels (scales × pairs) that must be suppressed.</p>
    <p>The thermal floor for suppressing one 1024×1024 image with 200 markers across 3 scales and 3 channel pairs is approximately 0.5–2.0 joules. This floor cannot be reduced by algorithmic optimization because the operations are inherently sequential (modify depends on decide, which depends on scan, which depends on decode) and each operation has a physical minimum cost.</p>
    <p>At corpus scale:</p>
    <div className="table-wrap"><table>
<thead><tr><th>Corpus Size</th><th>Suppression Energy (low)</th><th>Suppression Energy (high)</th><th>Equivalent</th></tr></thead>
<tbody>
<tr><td>1,000 images/day</td><td>500 J/day</td><td>2,000 J/day</td><td>Negligible</td></tr>
<tr><td>1M images/day</td><td>500 kJ/day</td><td>2 MJ/day</td><td>A server running continuously</td></tr>
<tr><td>100M images/day</td><td>50 MJ/day</td><td>200 MJ/day</td><td>A data center wing</td></tr>
<tr><td>1B images/day</td><td>500 MJ/day</td><td>2 GJ/day</td><td>A power plant’s output for minutes</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table J2. </strong><em>Thermal floor for provenance suppression at scale. At hyperscale (1B images/day), the suppression energy approaches the output of industrial power generation. These estimates are lower bounds based on computational operation counts and do not include cooling, networking, storage, or operational overhead.</em></p>
    <p>These numbers are the theoretical minimum. Real-world suppression includes overhead: pipeline coordination, quality verification, failure handling, re-processing of failed images, storage of intermediate states, and monitoring. The actual energy cost is typically 3–10× the theoretical minimum for production pipelines.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>J.7 The Incentive Structure</h2>
    <p>The thermodynamic tax creates a natural incentive gradient:</p>
    <p><strong>Serving provenance-marked content as-is: </strong>Zero additional cost. The content passes through the normal pipeline unchanged. The provenance signal rides for free. The platform expends no energy on provenance. The signal is present in the served content. This is the cheapest possible operation.</p>
    <p><strong>Detecting provenance at ingestion: </strong>Minimal additional cost. A DQT scan at 0.0001 J per file. A batch variance scan at 0.1 J per file, run overnight. The detection cost is dwarfed by the normal pipeline cost of processing the upload (resize, thumbnail, re-encode). Detection adds single-digit percentage overhead to existing operations.</p>
    <p><strong>Suppressing provenance before serving: </strong>Substantial additional cost. A dedicated real-time pipeline at 0.5–2.0 J per file. Synchronous. Peak-provisioned. SLA-bound. The suppression cost may exceed the normal pipeline cost for each image. At hyperscale, the suppression pipeline is a significant infrastructure investment with discoverable operational footprint.</p>
    <p>The gradient points in one direction: <strong>serve authentic, unaltered provenance-marked files.</strong> That is the minimum-energy state. Any deviation from that state — any attempt to modify, suppress, or strip provenance — costs energy, costs time, costs operational complexity, and produces discoverable evidence of the attempt.</p>
    <p>The scheme does not prevent suppression. The scheme makes suppression <em>expensive</em>. The expense is not a design parameter. It is a thermodynamic property. The adversary cannot negotiate with the physics. The physics sets the floor. The floor is the tax.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>J.8 The Bitcoin Parallel</h2>
    <p>The analogy to Bitcoin proof-of-work is precise in structure but different in mechanism.</p>
    <p><strong>Bitcoin: </strong>Rewriting history requires re-computing the proof-of-work for every block in the chain. The energy cost scales linearly with chain length. The cost is borne by the attacker. The honest network’s energy expenditure creates the cost floor. The attacker must exceed the honest network’s cumulative work to succeed.</p>
    <p><strong>Provenance suppression: </strong>Suppressing provenance requires per-image, per-position, per-scale, per-pair processing. The energy cost scales linearly with corpus size and multiplicatively with signal complexity (markers × scales × pairs). The cost is borne entirely by the suppressor. No honest network needs to expend energy to create the cost floor — the signal itself, embedded once at negligible cost, creates the suppression floor. The creator’s one-time embedding creates a permanent energy obligation for any adversary who wants to remove it.</p>
    <p>The key difference: Bitcoin requires continuous energy expenditure by the honest network to maintain security. The provenance scheme requires <em>zero</em> continuous energy expenditure after the initial embedding. The signal is self-sustaining. The amplification is free — the adversary’s own compression pipeline provides it. The cost floor exists without ongoing investment by the creator.</p>
    <p>The creator spends 0.01 joules once. The adversary spends 0.5–2.0 joules per image, per encounter, forever, across every copy of the file, at every scale and every channel pair, with synchronous timing constraints and catastrophic failure modes.</p>
    <p className="lead"><em>Bitcoin’s security costs the honest network energy. Provenance security costs the honest creator almost nothing. The thermodynamic tax is paid entirely by the adversary. The creator sets the trap by saving a file. The physics collects the tax.</em></p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>J.9 Measurability</h2>
    <p>The thermodynamic tax is empirically measurable. Time the embedding function. Time the detection function. Time a blind suppression function. Compute the energy from the wall-clock time and the processor’s TDP. The ratio between suppression energy and embedding energy is the tax rate. The ratio between suppression energy and detection energy is the enforcement asymmetry.</p>
    <p>These measurements belong in the paper as a table. The measurements are reproducible. The code is BSD licensed. Any reader can run the same timing benchmarks on their own hardware and verify the asymmetry. The tax rate is not a claim. It is a measurement. Measurements are not debatable.</p>
    <p>The measurement also serves as a deterrent. An adversary reading the paper sees the tax rate, multiplies by their corpus size, and computes their suppression budget. The budget either fits their economics or it doesn’t. If it doesn’t, the rational response is to not suppress. The paper’s publication of the tax rate is itself an economic signal to potential adversaries: the cost is known, the cost is quantified, and the cost is your problem.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>J.10 The Minimum-Energy State</h2>
    <p>Thermodynamic systems tend toward their minimum-energy state. A ball rolls downhill. A gas fills its container. A market finds its equilibrium.</p>
    <p>The minimum-energy state for a platform processing provenance-marked images is: <strong>serve them as-is.</strong> Don’t suppress. Don’t modify. Don’t strip. Let the signal ride through the normal pipeline. The signal’s presence costs nothing. The signal’s removal costs energy, time, complexity, and legal exposure.</p>
    <p>The scheme does not force platforms to serve provenance. It makes serving provenance the state the system naturally falls into when no additional energy is expended. Suppression requires sustained energy input against the gradient. Release the energy input and the system returns to the minimum-energy state: provenance preserved.</p>
    <p>This is not an analogy. This is a description of the energy landscape. The platform that serves provenance is at rest. The platform that suppresses provenance is climbing uphill. The hill never ends because every new image requires new suppression energy. The moment the suppression pipeline stops, the provenance signal reappears in every subsequently processed image.</p>
    <p className="lead"><em>The scheme incentivizes serving authentic, unaltered provenance-marked files. Not through policy. Not through legislation. Not through cooperation. Through thermodynamics. The minimum-energy state is creator protection. Every other state costs more. Physics does not negotiate.</em></p>
    <p className="lead"><em>Energy estimates are order-of-magnitude calculations based on computational operation counts.</em></p>
    <p className="lead"><em>Precise measurements require benchmark implementations on representative hardware, which have not been performed.</em></p>
    <p className="lead"><strong><em>The asymmetry is structural. The specific ratios are approximate. The gradient is not.</em></strong></p>
    <p>Jeremy Pickett — March 19, 2026</p>
  </div>
</section>
    </>
  );
}
