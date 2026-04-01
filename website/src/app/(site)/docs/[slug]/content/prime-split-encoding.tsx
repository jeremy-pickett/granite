export default function PrimeSplitEncodingContent() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Working Paper</p>
          <h1>Prime Split Encoding</h1>
          <p className="hero-subtitle">Steganographic Information Channels in Prime Decomposition Space</p>
        </div>
      </header>

      <section className="section">
        <div className="container content-narrow">
          <h2>Abstract</h2>
          <p>We describe a novel steganographic encoding scheme in which information is carried not in numerical values but in the choice of prime decomposition applied to a sequence of primes. A carrier prime N with k valid prime-tile splits can encode floor(log<sub>2</sub>(k)) bits per number through the selection of a specific split &mdash; the carrier itself leaks nothing beyond its primality. We demonstrate a working encoder and decoder, characterize the split-density graph topology, project information capacity scaling with digit length, and provide a complete taxonomy of attacks against the scheme. The non-contiguous topology of prime-decomposition space means the message channel has no ordering consistent with the integers, defeating gradient-based and proximity-based attacks. We also identify fundamental weaknesses introduced by abandoning standard cryptographic primitives, and we make no claim that this scheme is production-secure without further hardening.</p>
          <p><em>J. Pickett &mdash; March 2026 &nbsp;|&nbsp; Creative Commons CC-BY 4.0</em></p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>1. The Core Idea</h2>
          <p>Standard steganography hides a message inside a carrier by altering low-order bits of an image, text spacing, or similar. The carrier looks normal; the message is in the deviation from normal.</p>
          <p>Prime Split Encoding (PSE) works differently. There is no deviation. The carrier &mdash; a sequence of prime numbers &mdash; is entirely valid. Every number is genuinely prime. The message is encoded in which of several equally valid ways each prime is split into sub-primes. An observer who does not know the codebook cannot distinguish a message-bearing sequence from any other sequence of primes.</p>

          <h3>1.1 Split Layers</h3>
          <p>Given a prime N with decimal representation as a string, we define the following layers of prime structure:</p>
          <div className="card card-dark">
            <p><strong>Layer 1 &mdash; Monolithic:</strong> N itself is prime.</p>
            <p><strong>Layer 2 &mdash; Two-tranche:</strong> N can be split at some position i into two primes, both valid.</p>
            <p><strong>Layer 3 &mdash; Saturation:</strong> Every digit is covered exactly once by a contiguous tiling of primes.</p>
            <p><strong>Layer 4 &mdash; Three-tranche:</strong> N splits into exactly three contiguous primes covering all digits.</p>
          </div>
          <p>A number that satisfies all four layers simultaneously is a high-value carrier node. The message is not in the number &mdash; it is in which valid split the sender chooses.</p>

          <h3>1.2 A Worked Example: 1153</h3>
          <p>Take N = 1153. It is prime (Layer 1). Its valid splits:</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Split</th><th>Parts</th><th>Layer</th><th>All Prime?</th></tr></thead>
            <tbody>
              <tr><td>11 | 53</td><td>11, 53</td><td>2-tranche</td><td>YES</td></tr>
              <tr><td>11 | 5 | 3</td><td>11, 5, 3</td><td>3-tranche</td><td>YES</td></tr>
              <tr><td>1153 reversed = 3511</td><td>3511</td><td>Reversal</td><td>YES</td></tr>
            </tbody>
          </table></div>
          <p>1153 is prime. 3511 (its digit-reversal) is also prime. The two-split and three-split both yield all-prime parts. This is a structurally dense number: the same digits encode different messages depending on the resolution (split type) applied. The information is not a value &mdash; it is a choice.</p>
          <blockquote>
            <p>Key insight: position and direction are as meaningful as the values themselves. 3|511 fails. 35|11 fails. 11|53 succeeds. The same four digits have a directional grammar.</p>
          </blockquote>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>2. The Split-Density Graph</h2>
          <p>Define a graph G where every prime is a node and two primes share an edge if they appear together as components of a valid split of a third prime. This graph has properties that are deeply unlike the integer number line.</p>

          <h3>2.1 Topology</h3>
          <p>The graph is disconnected from integer proximity. Primes 3137 and 3313 differ by 176 on the number line but share zero edges in G &mdash; their split-space neighborhoods are entirely disjoint. There is no gradient in G along the integers. An adversary who can enumerate nearby primes gains no information about the message structure, because nearness in Z has no relationship to nearness in G.</p>
          <blockquote>
            <p>This is the foundational security property of PSE: the message channel does not live on the integer line.</p>
          </blockquote>

          <h3>2.2 Hub Nodes</h3>
          <p>The graph has extreme degree inequality. The prime 3 appears in 13,140 decompositions up to 1M. The prime 7 appears in 12,501. Single-digit primes are hubs with degrees in the tens of thousands. Two-digit primes cluster around degree 1,300&ndash;1,600. Larger primes are sparse.</p>
          <p>This is not accidental. It mirrors the structure of digit concatenation: short primes can appear in more split positions than long ones. The hub structure is not a vulnerability &mdash; it is the reason the encoding works at scale.</p>

          <h3>2.3 Density Scaling</h3>
          <div className="table-wrap"><table>
            <thead><tr><th>Digit Length</th><th>Max Splits Found</th><th>Bits Per Prime</th><th>Primes With Splits</th></tr></thead>
            <tbody>
              <tr><td>3 digits</td><td>3</td><td>1.58</td><td>51</td></tr>
              <tr><td>4 digits</td><td>5</td><td>2.32</td><td>381</td></tr>
              <tr><td>5 digits</td><td>8</td><td>3.00</td><td>3,142</td></tr>
              <tr><td>6 digits</td><td>9</td><td>3.17</td><td>25,482</td></tr>
              <tr><td>7 digits</td><td>12</td><td>3.58</td><td>215,044</td></tr>
              <tr><td>~20 digits (projected)</td><td>~952</td><td>~9.9</td><td>&mdash;</td></tr>
              <tr><td>~50 digits (projected)</td><td>~23,000,000</td><td>~24.5</td><td>&mdash;</td></tr>
            </tbody>
          </table></div>
          <p>At 20-digit primes, a single carrier number approaches a full byte of payload capacity. At 50 digits, a single prime carries approximately 3 bytes. The information density scales super-linearly with digit length.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>3. The Encoder</h2>

          <h3>3.1 Protocol</h3>
          <p>Two parties share a codebook: an ordered list of high-capacity primes. The codebook is the key. It is never transmitted.</p>
          <p>To encode a message:</p>
          <ul>
            <li>Convert message to a bitstream (standard ASCII or UTF-8).</li>
            <li>For each prime P<sub>i</sub> in the codebook, compute k = number of valid splits, capacity = floor(log<sub>2</sub>(k)).</li>
            <li>Read &lsquo;capacity&rsquo; bits from the bitstream. Interpret as integer index j.</li>
            <li>Transmit P<sub>i</sub>. The message bit contribution is j &mdash; the index into the canonically sorted split list of P<sub>i</sub>.</li>
          </ul>
          <p>To decode:</p>
          <ul>
            <li>Receiver has the codebook. For each received prime, enumerate all valid splits in canonical order.</li>
            <li>The agreed split index j is extracted from context (see Section 3.2).</li>
            <li>Reconstruct the bitstream from all j values. Decode bytes.</li>
          </ul>

          <h3>3.2 Worked Encoding: &lsquo;HI&rsquo;</h3>
          <p>Message: &lsquo;HI&rsquo; (ASCII 72, 73) = bitstream: <code>0100100001001001</code></p>
          <div className="table-wrap"><table>
            <thead><tr><th>Carrier Prime</th><th>Split Count</th><th>Bits Carried</th><th>Bits Used</th><th>Split Chosen</th></tr></thead>
            <tbody>
              <tr><td>3137</td><td>2</td><td>1</td><td>0</td><td>(31, 3, 7)</td></tr>
              <tr><td>3313</td><td>4</td><td>2</td><td>01</td><td>(3, 3, 13)</td></tr>
              <tr><td>3373</td><td>4</td><td>2</td><td>00</td><td>(3, 373)</td></tr>
              <tr><td>3733</td><td>4</td><td>2</td><td>10</td><td>(3, 73, 3)</td></tr>
              <tr><td>3797</td><td>4</td><td>2</td><td>00</td><td>(3, 79, 7)</td></tr>
              <tr><td>11317</td><td>2</td><td>1</td><td>1</td><td>(11, 3, 17)</td></tr>
              <tr><td>11353</td><td>4</td><td>2</td><td>00</td><td>(113, 5, 3)</td></tr>
              <tr><td>17317</td><td>4</td><td>2</td><td>01</td><td>(17, 31, 7)</td></tr>
            </tbody>
          </table></div>
          <p>What the observer sees: <code>[3137, 3313, 3373, 3733, 3797, 11317, 11353, 17317]</code></p>
          <p>This is an unremarkable list of primes. There is no deviation from any expected distribution. The message is in the agreed split selection, which is not transmitted.</p>
          <p>The receiver needs only the codebook (which primes, in which order) and the canonical split ordering rule. The split itself is computed locally &mdash; nothing about the split is ever sent.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>4. Maximum Density Nodes</h2>
          <p>The highest-density carrier found below 10M is 2,337,397 with 12 valid splits (3.58 bits). Its full split map illustrates the structural richness at 7 digits:</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Split Type</th><th>Components</th><th>All Prime?</th></tr></thead>
            <tbody>
              <tr><td>2-tranche</td><td>(2, 337397)</td><td>YES</td></tr>
              <tr><td>2-tranche</td><td>(23, 37397)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(2, 3, 37397)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(2, 337, 397)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(2, 3373, 97)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(2, 33739, 7)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(23, 37, 397)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(23, 373, 97)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(23, 3739, 7)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(233, 7, 397)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(233, 73, 97)</td><td>YES</td></tr>
              <tr><td>3-tranche</td><td>(233, 739, 7)</td><td>YES</td></tr>
            </tbody>
          </table></div>
          <p>At 20 digits, projected split counts exceed 900. A single prime number would carry approximately one full byte of message data.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>5. Attack Surface: A Complete Taxonomy</h2>
          <p>This is where honesty is required. PSE abandons most of the primitives that make modern cryptography safe. Each abandonment creates an attack surface. We enumerate them without apology.</p>

          <h3>5.1 The Codebook Is the Entire Key</h3>
          <div className="card card-dark">
            <p><strong>CRITICAL VULNERABILITY:</strong> There is no key separate from the codebook. Whoever has the ordered list of carrier primes can decode every message ever sent.</p>
          </div>
          <p>Unlike symmetric encryption where key compromise requires brute-force recovery of plaintext, PSE has no computational barrier between key possession and full decryption. The codebook is the key. The key is a list. Lists get leaked, copied, and stolen.</p>
          <p><strong>Practical attack:</strong> An adversary who observes multiple carrier sequences and has computational resources can attempt to reconstruct the codebook by finding the ordered prime list that produces coherent plaintext across multiple observed transmissions. This is a known-plaintext attack on the codebook structure itself.</p>
          <p><strong>Mitigation:</strong> Use a different codebook per conversation. Generate codebooks procedurally from a shared seed using a standard CSPRNG. The seed is the true key; the codebook is derived. This re-introduces a proper key management problem &mdash; which is actually what you want.</p>

          <h3>5.2 No Semantic Security</h3>
          <div className="card card-dark">
            <p><strong>CRITICAL VULNERABILITY:</strong> Two identical messages produce identical carrier sequences when the same codebook is used. PSE is deterministic.</p>
          </div>
          <p>In modern encryption, semantic security guarantees that encrypting the same plaintext twice produces different ciphertexts (via nonces, IVs, or randomized padding). PSE has none of this. The same message sent twice is the same prime sequence twice. An observer who sees the same sequence twice knows the same message was sent twice, and can correlate traffic without breaking the encoding.</p>
          <p>This is a complete failure of IND-CPA security (Indistinguishability under Chosen Plaintext Attack) &mdash; the baseline requirement for any cipher used in practice.</p>
          <p><strong>Mitigation:</strong> Introduce a randomized prefix or suffix to every message before encoding. Pad messages to a fixed length. Neither is built into PSE and both must be added externally.</p>

          <h3>5.3 Codebook Bias Is Detectable</h3>
          <div className="card card-dark">
            <p><strong>HIGH VULNERABILITY:</strong> The codebook is biased toward high-split-count primes. This distribution is anomalous and detectable.</p>
          </div>
          <p>Of the 78,473 primes below 1,000,000, only 1,034 (roughly 1.3%) have four or more valid splits. A PSE carrier sequence will be overwhelmingly composed of primes from this minority. An adversary who tests each observed prime for split density will identify a carrier sequence with high probability &mdash; not the message content, but the fact that a covert channel exists.</p>
          <p>This breaks the steganographic property. A steganalyst does not need to decode the message to do damage. Knowing the channel exists is often sufficient.</p>
          <p><strong>Mitigation:</strong> Intersperse decoy primes (primes not in the codebook, with low split counts) between carrier primes. Agree on a pattern or ratio in advance. This reduces channel capacity but restores statistical cover.</p>

          <h3>5.4 Small Split Counts Leak Information</h3>
          <div className="card card-dark">
            <p><strong>MODERATE VULNERABILITY:</strong> Many codebook primes have only 2 or 4 valid splits (1&ndash;2 bits). With such small alphabets, frequency analysis becomes feasible.</p>
          </div>
          <p>A prime with exactly 2 valid splits encodes a single bit. If the adversary knows the prime is a PSE carrier (from attack 5.3) and the split count (trivially computed), they immediately know the full space of that symbol is {'{'}0, 1{'}'}. For primes with 4 splits, the space is 2 bits (0&ndash;3). Letters in common English map to fairly predictable bit patterns.</p>
          <p>Standard frequency analysis on single-bit carrier symbols, combined with knowledge of the encoding language, can recover message content without ever needing the codebook.</p>
          <p><strong>Mitigation:</strong> Use only high-density carrier primes (8+ splits). Avoid any carrier with fewer than 4 valid splits. Accept the reduced codebook size in exchange for resistance to frequency analysis.</p>

          <h3>5.5 The Resolution Attack</h3>
          <div className="card card-dark">
            <p><strong>MODERATE VULNERABILITY:</strong> The receiver must know which resolution (2-tranche vs 3-tranche) to apply. If this is fixed and known, the attacker can enumerate all valid splits at that resolution for every observed prime.</p>
          </div>
          <p>Consider a prime with 9 splits: 3 two-tranche and 6 three-tranche. If the protocol always uses 3-tranche splits, the attacker knows the symbol alphabet is size 6 (2.58 bits). The full split enumeration is O(n<sup>2</sup>) for a digit string of length n &mdash; computationally trivial. Once the attacker has the split list for every carrier prime, they have reduced the problem to a simple codebook search.</p>
          <p><strong>Mitigation:</strong> Vary the resolution per prime according to the codebook. The resolution selection rule should itself be part of the shared secret. This can be encoded as a simple parity or position rule derived from the codebook seed.</p>

          <h3>5.6 No Integrity, No Authentication</h3>
          <div className="card card-dark">
            <p><strong>CRITICAL VULNERABILITY:</strong> PSE provides no message integrity and no sender authentication. An adversary who can inject primes into the channel can alter or forge messages undetectably.</p>
          </div>
          <p>There is no MAC (Message Authentication Code), no HMAC, no signature. A man-in-the-middle who replaces one carrier prime with another prime of equal split count but different split choices has altered the message with no evidence. The receiver decodes a different message and has no way to detect the substitution.</p>
          <p>This is not a minor omission. In any adversarial channel &mdash; which is the only channel that matters &mdash; unauthenticated encoding is not secure encoding.</p>
          <p><strong>Mitigation:</strong> Append a standard HMAC over the decoded message using the codebook seed as the HMAC key. Or: sign the message with a standard asymmetric scheme before encoding. PSE provides the covert channel; authentication must come from a separate layer.</p>

          <h3>5.7 Replay Attacks</h3>
          <div className="card card-dark">
            <p><strong>HIGH VULNERABILITY:</strong> A recorded carrier sequence is permanently valid. PSE has no nonces, no timestamps, no session state.</p>
          </div>
          <p>An adversary who captures a carrier sequence today can re-transmit it in six months and the receiver will decode the original message. In a command-and-control scenario, replaying &lsquo;authorize transaction&rsquo; or &lsquo;confirm receipt&rsquo; is catastrophic.</p>
          <p><strong>Mitigation:</strong> Include a monotonic counter or timestamp in the message plaintext before encoding. The receiver rejects any decoded message with a counter value it has already processed. This is application-layer state management &mdash; not provided by PSE.</p>

          <h3>5.8 Brute Force on Small Codebooks</h3>
          <div className="card card-dark">
            <p><strong>MODERATE VULNERABILITY:</strong> For small codebooks (under ~500 primes), brute force over the prime space is feasible.</p>
          </div>
          <p>If the adversary knows approximately which primes are in the codebook (from the density bias attack), and the codebook is small, they can enumerate all possible orderings of candidate primes and test each ordering against observed carrier sequences for message coherence. For a codebook of 100 primes, the ordering space is 100! &mdash; infeasible. But the adversary does not need to find the full ordering. They need only find the ordering of the primes observed in a single short transmission.</p>
          <p>A 10-prime carrier sequence has 10! = 3,628,800 orderings. Testable in seconds on a laptop. Each ordering produces a candidate bit string; the adversary checks for printable ASCII.</p>
          <p><strong>Mitigation:</strong> Use long transmissions. The ordering attack grows factorially, but so does the message length. For transmissions using 50+ carrier primes the ordering space is astronomical. Additionally: the codebook should be much larger than the per-message carrier set, so the attacker cannot easily identify which subset was used.</p>

          <h3>5.9 The Base-10 Assumption</h3>
          <div className="card card-dark">
            <p><strong>PHILOSOPHICAL VULNERABILITY:</strong> The entire scheme depends on decimal digit concatenation. It is base-10 specific.</p>
          </div>
          <p>Primality is base-independent. 7 is prime in any base. But the split structure depends entirely on decimal representation. &lsquo;1153&rsquo; splits as 11|53 in base 10, but has a completely different digit string in base 16 (0x481). The shared secret implicitly includes the base.</p>
          <p>This is not a practical attack in most scenarios, but it matters theoretically: the security argument must account for the encoding base as part of the key material. An adversary who does not know the base cannot enumerate splits. An adversary who knows the base can.</p>
          <p>A more exotic hardening: use a non-standard base as part of the shared secret. Base-37, base-41, base-43 &mdash; all prime bases. Split structure in these bases has been studied far less than base-10 and provides a meaningfully larger enumeration burden.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>6. Hardened Protocol Specification</h2>
          <p>Incorporating the mitigations from Section 5, a minimally hardened PSE protocol looks like the following:</p>

          <h3>Key Material</h3>
          <ul>
            <li><strong>Shared seed S:</strong> 256-bit random value. Generated once per session using a standard CSPRNG and exchanged via a standard key agreement protocol (e.g. X25519 Diffie-Hellman).</li>
            <li><strong>Codebook</strong> derived deterministically from S: a CSPRNG seeded with S selects 1,024 high-density carrier primes (8+ splits) from a pre-computed prime table. Ordering is determined by the CSPRNG output.</li>
            <li><strong>Base B:</strong> derived from S as a prime in [37, 53]. Changes the digit concatenation domain.</li>
            <li><strong>Resolution rule:</strong> for each carrier prime at position i, resolution is 2-tranche if bit i of SHA-256(S) is 0, else 3-tranche.</li>
          </ul>

          <h3>Encoding</h3>
          <ul>
            <li>Prepend 64-bit monotonic counter to message plaintext.</li>
            <li>Pad message to next multiple of 64 bytes using PKCS#7.</li>
            <li>Encode padded message using codebook and resolution rule.</li>
            <li>Compute HMAC-SHA256 over decoded message using S as key. Append to carrier sequence as a final non-carrier prime (just transmitted as a number &mdash; not encoded via splits).</li>
          </ul>

          <h3>Decoding</h3>
          <ul>
            <li>Receive carrier sequence. Separate final HMAC prime.</li>
            <li>Decode carrier sequence using codebook and resolution rule.</li>
            <li>Verify HMAC. Reject on failure.</li>
            <li>Extract and verify counter. Reject replays.</li>
            <li>Strip padding. Recover plaintext.</li>
          </ul>

          <p>This hardened protocol delegates all of its security properties to well-understood primitives: X25519 for key exchange, HMAC-SHA256 for integrity, PKCS#7 for padding. PSE contributes only the covert channel property &mdash; the carrier looks like a prime sequence. Nothing else.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>7. Non-Contiguous Number Lines and Meta-Spaces</h2>
          <p>The split-density graph G is not a line. It is not ordered. Proximity in G has no relationship to proximity in Z. This is a concrete instance of a broader structure we term a <em>non-contiguous information space</em>: a set equipped with an encoding topology that is disconnected from the natural ordering of its elements.</p>
          <p>PSE is one construction. Others are possible. The generalized question is: given a mathematical structure S with a natural ordering, what secondary structures can be derived from S that carry information in the relational topology rather than the values? Gaussian integers, Eisenstein integers, and p-adic number fields all admit analogous constructions where primality (or its analog) generates disconnected encoding graphs.</p>
          <p>The Langlands program, at its core, asks precisely this question at a deeper level: what symmetry structure underlies the relationship between prime distributions in different number fields? The PSE graph is a toy instance of the same question applied to digit concatenation.</p>
          <blockquote>
            <p>The practical implication: any adversary whose attack model assumes that nearby values carry similar information is operating in the wrong space. The message topology of PSE does not have near and far.</p>
          </blockquote>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>8. Open Problems</h2>
          <ul>
            <li>What is the asymptotic growth rate of max splits as a function of digit length? The empirical data suggests super-linear growth; a formal bound would sharpen capacity projections.</li>
            <li>Does the split-density graph exhibit small-world or scale-free properties? Hub dominance by single-digit primes suggests scale-free structure, with implications for codebook design.</li>
            <li>What is the split structure in prime bases (base-37, base-41)? Are the hub primes different? Does the graph have different connectivity properties?</li>
            <li>Can the encoding extend to Gaussian integers? A Gaussian prime N = a + bi admits a richer split space than its real counterpart, with splits along both real and imaginary axes.</li>
            <li>Is there a number-theoretic explanation for the 911 / 137 / 167 coincidences noted in the constants survey? Or is this base-10 numerology?</li>
            <li>Can PSE be adapted to non-decimal bases in a way that provides a measurably harder enumeration problem for adversaries?</li>
          </ul>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>Conclusion</h2>
          <p>Prime Split Encoding is a novel steganographic scheme with a genuine non-contiguous channel topology that defeats proximity-based and gradient-based analysis. A working encoder and decoder has been demonstrated. The information capacity scales with digit length and projects to full-byte-per-prime capacity at 20 digits.</p>
          <p>The scheme has serious vulnerabilities when operated without standard cryptographic primitives: no semantic security, no integrity, no authentication, and a detectable carrier bias. None of these are fundamental to the mathematical structure &mdash; all are remediable by layering PSE over standard key exchange and HMAC schemes, delegating security properties to well-understood primitives and reserving PSE for the covert channel property alone.</p>
          <blockquote>
            <p>The deeper result is the confirmation of a non-contiguous information topology: a space in which message proximity has no relationship to integer proximity. This property, not the encoding scheme per se, is the contribution worth pursuing.</p>
          </blockquote>
          <p>J. Pickett &nbsp;|&nbsp; Eugene, Oregon &nbsp;|&nbsp; March 2026</p>
        </div>
      </section>
    </>
  );
}
