export default function AddendumDAttributionArchitectureContent() {
  return (
    <>
<header className="page-hero">
  <div className="container">
    <p className="hero-series">Addendum D</p>
    <h1>Attribution Architecture</h1>
    <p className="hero-subtitle">Granite Under Sandstone &mdash; Addendum Series</p>
  </div>
</header>

<section className="section">
  <div className="container content-narrow">
    <h2>D.1 The Question After Provenance</h2>
    <p>The provenance signal answers: <em>was a participating system here?</em> The immediate next question is: <em>whose system?</em></p>
    <p>These are different questions. The first is physics. The second is policy. The scheme answers the first. This addendum describes an architecture for answering the second without compromising the properties of the first.</p>
    <p>The requirements are non-negotiable: no PII in the file, no PII in the signal, no infrastructure the creator must depend on, no single point of control, no lock-in, zero trust between all parties, and the creator’s ability to abandon attribution at any time without affecting provenance.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>D.2 The Identity Is in the Positions</h2>
    <p>The scheme embeds twin markers at selected positions across the image. Which positions are selected is determined by the embedder’s parameters. In a 512×512 image with ~4,000 eligible positions, the embedder places markers at approximately 200 of them. The combinatorial space of 200 positions chosen from 4,000 is C(4000, 200), which is approximately 10⁴⁰⁰. This number exceeds the number of atoms in the observable universe by a factor of approximately 10³²⁰.</p>
    <p>The pattern of <em>which positions</em> are disrupted is a fingerprint. Not the prime values at those positions — those are destroyed by compression. Not the ratios between values — those don’t survive either. The binary map of disrupted versus smooth positions. That map survives because the perturbation at each position survives and amplifies under compression. The detector reads it by measuring local variance at every eligible position.</p>
    <p>The identity was always in the file. It was never in the values. It was in the positions. We were looking at the wrong axis.</p>
    <h3>D.2.1 Seed-Based Position Derivation</h3>
    <p>The creator holds one secret: a 256-bit seed. Generated locally. Stored in a password manager or a 24-word mnemonic. Never transmitted. Never leaves the creator’s device. This is the only secret in the entire system.</p>
    <p>For each image, the seed combines with an image-specific context (content hash, dimensions, or other derivable metadata) to produce a deterministic position selection:</p>
    <p>child_key = HMAC-SHA512(seed, image_context)</p>
    <p>positions = select_positions(child_key, eligible_set)</p>
    <p>fingerprint = sha256(canonical_position_list)</p>
    <p>Same seed plus same image always produces the same positions, the same fingerprint, on any machine. Different seed produces different positions. Different image produces different positions. The derivation is one-way: the fingerprint cannot reveal the seed, one image’s positions cannot reveal another image’s positions, and the seed cannot be reconstructed from any number of observed fingerprints.</p>
    <p>This is BIP-32 (hierarchical deterministic key derivation) applied to spatial position selection instead of cryptographic key generation. One seed. Infinite images. Each image’s embedding parameters derived deterministically. Each image’s fingerprint derivable from the public observation. The tree of derivations is one-way.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>D.3 Three Layers of Identity</h2>
    <p>The architecture separates provenance, attribution, and identity into three independent layers. Each is optional. Each is the creator’s choice. Each can be adopted or abandoned independently.</p>
    <div className="table-wrap"><table>
<thead><tr><th>Layer</th><th>What It Proves</th><th>What It Requires</th><th>Reversible?</th><th>Cost</th></tr></thead>
<tbody>
<tr><td>0: Signal</td><td>A participating system touched this file.</td><td>Nothing. The signal is in the file. Detectable by anyone.</td><td>No. The signal is physics.</td><td>Zero.</td></tr>
<tr><td>1: Fingerprint</td><td>This file shares a source with these other files. Temporal priority established.</td><td>Registration of fingerprint(s) with a matching service. Pseudonymous.</td><td>Yes. Delete the registration.</td><td>Free or minimal.</td></tr>
<tr><td>2: Identity</td><td>This specific person controls the seed that produced these fingerprints.</td><td>Creator steps forward with seed and demonstrates derivation.</td><td>Partially. Can’t un-prove, but can abandon service.</td><td>Zero. Math only.</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table D1. </strong><em>Three layers of identity. A creator who does nothing gets Layer 0. Registration adds Layer 1. Stepping forward adds Layer 2. Each layer is independent and optional.</em></p>
    <p>A creator can exist at Layer 0 indefinitely — provenance without attribution, a file that remembers it was touched but doesn’t say by whom. A creator can register at Layer 1 under a pseudonym and later abandon the pseudonym by deleting the registration. The provenance signal remains in the file. The attribution link is severed. The creator chose in. The creator chose out. No authority was involved in either decision.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>D.4 The Matching Service</h2>
    <h3>D.4.1 What It Holds</h3>
    <p>The matching service is a lookup table. Each record is:</p>
    <p>{'{ pseudonym, fingerprint, timestamp, optional_contact }'}</p>
    <p>No PII. The pseudonym is an opaque identifier chosen by the creator. The fingerprint is a hash of the position pattern. The timestamp is when the fingerprint was registered. The optional contact is whatever the creator wants to provide — an email, a URL, a wallet address, a PGP key, or nothing at all.</p>
    <p>A creator accumulates registrations over time: image 1 has fingerprint A, image 2 has fingerprint B, image 3 has fingerprint C. These form a set. The set belongs to the pseudonym. The service stores sets of fingerprints grouped by pseudonym.</p>
    <h3>D.4.2 What It Does</h3>
    <p>A detector scans an image. It produces a noisy disruption map — the set of positions that show anomalous local variance. It hashes the map. This hash is the clue. The clue is submitted to the matching service.</p>
    <p>The service performs a fuzzy nearest-neighbor search across all registered fingerprints. Because compression corrupts some positions (false negatives) and occasionally flags non-marker positions (false positives), the match cannot be exact. It must be approximate. The search operates in Hamming space: how many positions differ between the clue and the registered fingerprint? If 150 out of 200 positions match with a Hamming distance of 50 out of 4,000 total eligible positions, the match is unambiguous. No other fingerprint in the database is close.</p>
    <p>The service returns: “This clue correlates with a fingerprint registered by pseudonym #47291 on March 18, 2026.” That is all it says. It does not say who #47291 is. It does not judge. It reports the match and the timestamp.</p>
    <h3>D.4.3 What It Doesn’t Do</h3>
    <p>It doesn’t know creator identities. Pseudonyms only.</p>
    <p>It doesn’t adjudicate disputes. It reports temporal priority.</p>
    <p>It doesn’t modify files. Read-only access to submitted clues.</p>
    <p>It doesn’t grant or revoke rights. It is not an authority.</p>
    <p>It doesn’t lock creators in. Fingerprints are portable. Register with five services simultaneously. Leave any of them at any time.</p>
    <p>The matching service is Janet. It provides answers. It makes no judgments. It has no authority.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>D.5 The Properties</h2>
    <h3>D.5.1 Zero Trust</h3>
    <p>The creator doesn’t trust the service — they gave it no PII. If the service is compromised, the attacker gets pseudonyms and fingerprint hashes. Neither reveals the creator’s identity or their seed.</p>
    <p>The service doesn’t trust the creator — it has no way to verify that the person registering a fingerprint actually embedded the corresponding signal. It doesn’t need to. The timestamp establishes who registered first. Verification of ownership happens at Layer 2, outside the service, when the creator demonstrates seed derivation.</p>
    <p>The detector doesn’t trust either party — it extracted the clue from the file independently using public mathematics. The clue is a measurement. Measurements don’t require trust.</p>
    <h3>D.5.2 Lazy Consistency</h3>
    <p>The creator can register fingerprints before or after publishing the image. The fingerprint is deterministic — it will be the same whenever it is computed because it derives from the seed and the image context, neither of which change. Publish the image today. Register the fingerprint next month. The math doesn’t know the difference.</p>
    <p>The tradeoff is temporal priority. Early registration establishes a stronger timestamp. Late registration establishes a weaker one. The system is eventually consistent. No ACID transactions. No synchronous operations. No ceremony. The creator registers when convenient. The timestamp records when they did.</p>
    <h3>D.5.3 Voluntary Abandonment</h3>
    <p>A creator who wants to disassociate from their work deletes their registrations from the matching service. The signal in the files remains — the canaries are still singing — but the attribution link is severed. The provenance says “someone was here.” The identity is gone. By the creator’s choice.</p>
    <p>This is a feature. A whistleblower who embedded provenance in leaked documents can abandon the attribution after the documents are public. An artist who changes career can orphan their early work. A person who regrets a publication can sever the link between the file and their identity without the file itself being modified. The file remembers. The service forgets. At the creator’s discretion.</p>
    <h3>D.5.4 Retroactive Claiming</h3>
    <p>A creator who embedded provenance years ago but never registered can register today. The fingerprint is deterministic. The signal is in the file. The registration establishes a timestamp as of today, not as of the original embedding date. This is a weaker claim than early registration but it is still a claim.</p>
    <p>An heir, estate, or institution can claim a deceased creator’s corpus by demonstrating possession of the seed. The seed proves the family of derivations. Each derivation proves a specific image. The corpus is claimed retroactively. The signal waited. The math does not expire.</p>
    <h3>D.5.5 Dispute Resolution</h3>
    <p>When two pseudonyms claim the same fingerprint, the matching service reports both claims and their timestamps. The earlier timestamp has priority. The service does not determine who is “right.” It provides the data. Resolution is external — legal, social, institutional, or simply reputational.</p>
    <p>The service’s dispute resolution policy is the service’s choice. Timestamp priority is the recommended default. Other policies are possible: reputation weighting, stake-based priority, community governance. Different services can implement different policies. The scheme does not mandate a policy. The scheme produces measurements. Policies are human decisions.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>D.6 The Ecosystem Economics</h2>
    <h3>D.6.1 The Incentive Gradient</h3>
    <p>The architecture creates a self-reinforcing incentive structure where no participant needs to be altruistic for the system to produce outcomes that protect creators.</p>
    <div className="table-wrap"><table>
<thead><tr><th>Actor</th><th>Incentive</th><th>Action</th><th>Effect on Creators</th></tr></thead>
<tbody>
<tr><td>Creator</td><td>Establish provenance for free. Optional attribution for stronger claims.</td><td>Embed at creation. Register fingerprint if desired.</td><td>Direct protection. Signal in every file.</td></tr>
<tr><td>Matching service</td><td>Build the most comprehensive fingerprint database. More fingerprints = more matches = more utility = more revenue.</td><td>Accept free registrations from creators. Sell API access to platforms.</td><td>Indirect protection. Service exists because it’s profitable, not because it cares.</td></tr>
<tr><td>Platform</td><td>Reduce legal exposure. Cheapest compliance: query the matching service at ingestion.</td><td>Run DQT scan + query matching service per upload. Log results.</td><td>Indirect protection. Platform checks provenance because it’s cheaper than not checking.</td></tr>
<tr><td>Adversary</td><td>Ingest content at minimum cost.</td><td>Either don’t suppress (signal detected) or suppress (legal exposure, compute cost, forensic residue).</td><td>Both positions lose. Both produce evidence. The adversary’s optimal strategy is to move to unprotected content.</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table D2. </strong><em>Incentive alignment across all actors. No participant needs to care about creators for the system to protect creators. Each actor pursues their own interest. The equilibrium is creator protection.</em></p>
    <h3>D.6.2 The Revenue Model</h3>
    <p>The matching service monetizes on the detection side, not the creation side.</p>
    <p><strong>Creators register for free.</strong> The service wants the largest possible fingerprint database. Charging creators shrinks the database. Free registration maximizes it. The creator is not the customer. The creator is the inventory.</p>
    <p><strong>Platforms pay for API access.</strong> A platform running a billion-image ingestion pipeline needs a fast, reliable provenance check at upload time. The DQT scan is free — it’s 128 bytes of local file reading. But the fingerprint match requires querying the database. That query is the product. The platform pays per query, per month, or per tier. The cost is trivial relative to the platform’s compute budget and the legal exposure it mitigates.</p>
    <p><strong>Legal and forensic practitioners pay for advanced queries.</strong> Corpus-level analysis: “show me all registered fingerprints that match content in this training dataset.” Temporal analysis: “what was the earliest registration of any fingerprint matching this file?” Expert reports: “quantitative analysis of provenance signal survival in this specific file, suitable for legal proceedings.” Premium services built on the same database.</p>
    <p>The money flows from those who have it (platforms, legal practitioners) to the service, which exists because those payments are profitable. The service protects creators as a byproduct of serving paying customers. The creators pay nothing. The system works because the system profits.</p>
    <h3>D.6.3 Competing Services</h3>
    <p>The architecture supports and encourages multiple competing matching services. The fingerprint is portable — it’s a hash derived from the signal in the file. Any service can compute it. Any service can store it. A creator can register the same fingerprint with five services simultaneously.</p>
    <p>Services compete on: database comprehensiveness (more fingerprints = better matches), query speed and reliability, dispute resolution policy, pricing, geographic coverage, legal jurisdiction, and trust reputation. No service has a monopoly on the fingerprint format because the format is an open hash of an open measurement.</p>
    <p>If a dominant service becomes adversarial — raises prices, changes policies, sells data — creators migrate to competitors. The migration cost is zero because the fingerprints are recomputable from the creator’s seed. No data is trapped. No lock-in exists. The service that behaves badly loses its database advantage as creators re-register elsewhere.</p>
    <p>This is DNS, not Certificate Authority. Multiple roots. Transparent policies. Ability to switch. The architecture enforces competition by making lock-in structurally impossible.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>D.7 The Mechanism Design Insight</h2>
    <p>Every prior attempt to solve the attribution problem at scale has required someone to care. Legislators must care enough to regulate. Platforms must care enough to cooperate. Consumers must care enough to check provenance. Creators must care enough to organize.</p>
    <p>Each of these has failed at scale because caring does not scale.</p>
    <p>This architecture removes caring from the equation.</p>
    <p>The physics does not care. Compression amplifies the perturbation because that is what block-based transform coding does to locally complex regions. The codec has no opinion about provenance. It has quantization parameters. The amplification is automatic.</p>
    <p>The matching service does not care about creators. It cares about building the largest database because database size determines revenue. Accepting free creator registrations is a business decision, not a moral one. The service protects creators because protecting creators is the profitable byproduct of database growth.</p>
    <p>The platform does not care about attribution. It cares about legal exposure. The cheapest way to reduce legal exposure is to run a DQT scan at upload and query the matching service. The cost is microseconds of compute and pennies of API fees. The alternative is discovery, litigation, and reputation damage. The platform checks provenance because checking is cheaper than not checking.</p>
    <p>The adversary does not care about any of it. But the adversary’s optimal strategy — minimize cost — leads them to avoid provenance-marked content (because suppression is expensive) and ingest unmarked content instead. The marked creator is protected not because the adversary respects them but because the adversary’s spreadsheet says to move to the next file.</p>
    <p className="lead"><strong>Nobody in the system needs to be good. The system produces good outcomes from selfish actors because the incentive gradients all point the same direction.</strong></p>
    <p>The Nash equilibrium of the system is creator protection. Not because anyone chose it. Because the physics, the economics, and the market dynamics converge on it. The creator is protected by the profitable self-interest of every other participant.</p>
    <p className="lead"><em>The scheme protects creators by making it profitable for third parties to protect creators. Nobody needs to care about artists’ rights for artists’ rights to be protected. They just need to care about money. The money aligns with the rights because the physics aligns with the money.</em></p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>D.8 The Closure of Assumption Zero</h2>
    <p>The original paper stated Assumption Zero as an open question: does attribution matter enough to shift corpus-scale economics?</p>
    <p>The architecture described in this addendum answers the question by making it irrelevant.</p>
    <p>Attribution does not need to <em>matter</em> to the adversary. It needs to be <em>profitable</em> to the intermediary. The matching service exists because platforms will pay for provenance queries. Platforms will pay because legal exposure is more expensive than API fees. The matching service accepts creator registrations for free because each registration increases database value. The creator is protected because the service’s profitability depends on having the creator’s fingerprint in the database.</p>
    <p>The question is not “does attribution matter?” The question is “is there a profitable business in resolving attribution queries?” If yes, the ecosystem self-assembles. If no, the provenance signal still exists in every file, the physics still amplifies it, and the scheme still proves participation. The attribution layer is additive. The provenance layer is unconditional.</p>
    <p>Assumption Zero was never the right question. The right question was: can you build an architecture where the answer doesn’t matter? The answer is yes. You build it so that every participant’s self-interest converges on the outcome you want. Then you let the market do the rest.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>D.9 What This Is Not</h2>
    <p><strong>Not a blockchain.</strong> The matching service is a database. It can run on a laptop. It can run on Postgres. It can run on a distributed hash table. The storage technology is irrelevant. The properties that matter are: append-only registration, timestamped records, fuzzy search, and portability. These do not require a blockchain. They require a database with an audit log.</p>
    <p><strong>Not a certificate authority.</strong> No one issues certificates. No one revokes certificates. No one has authority over any other participant. The service stores registrations and reports matches. It has the authority of a phone book, not a court.</p>
    <p><strong>Not DRM.</strong> Nothing is restricted. Nothing is controlled. Nothing is prevented. The system produces measurements and matches. Humans decide what to do with them.</p>
    <p><strong>Not a product we are building.</strong> This addendum describes an architecture. The architecture creates an opportunity for matching services to exist as businesses. Those businesses are not ours to build. The provenance scheme is the commons. The matching service ecosystem is the marketplace. The commons is open. The marketplace is for entrepreneurs. We provide the physics. The market provides the service.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>D.10 Summary</h2>
    <p>The provenance signal proves participation. The position-derived fingerprint enables attribution. The matching service ecosystem resolves identity. Three layers, each optional, each independent, each the creator’s choice.</p>
    <p>The creator embeds for free. The signal is physics. The fingerprint is math. The registration is a choice. The identity is a revelation.</p>
    <p>The system protects creators not because anyone decided to protect them, but because protecting them is the profitable equilibrium of every other actor pursuing their own interest. The physics amplifies the signal. The economics amplify the protection. Neither requires altruism. Neither requires legislation. Neither requires cooperation from the adversary.</p>
    <p>Caring does not scale. Incentives do.</p>
    <p className="lead"><em>Participation over permission. Provenance in the physics. Attribution in the service. Identity in the creator’s hands. Incentives in the market. Protection as equilibrium, not as policy.</em></p>
    <p className="lead"><em>No matching service has been built. No protocol has been specified.</em></p>
    <p className="lead"><em>The architecture is described because we see it, not because we have walked it.</em></p>
    <p className="lead"><strong><em>The market will decide if we see correctly.</em></strong></p>
    <p>Jeremy Pickett — March 2026</p>
  </div>
</section>
    </>
  );
}
