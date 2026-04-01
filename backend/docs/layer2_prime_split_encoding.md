**PRIME SPLIT ENCODING**

Steganographic Information Channels in Prime Decomposition Space

J. Pickett

March 2026  |  Working Paper  |  Creative Commons CC-BY 4.0

## **Abstract**

We describe a novel steganographic encoding scheme in which information is carried not in numerical values but in the choice of prime decomposition applied to a sequence of primes. A carrier prime N with k valid prime-tile splits can encode floor(log2(k)) bits per number through the selection of a specific split — the carrier itself leaks nothing beyond its primality. We demonstrate a working encoder and decoder, characterize the split-density graph topology, project information capacity scaling with digit length, and provide a complete taxonomy of attacks against the scheme. The non-contiguous topology of prime-decomposition space means the message channel has no ordering consistent with the integers, defeating gradient-based and proximity-based attacks. We also identify fundamental weaknesses introduced by abandoning standard cryptographic primitives, and we make no claim that this scheme is production-secure without further hardening.

# **1\.  The Core Idea**

Standard steganography hides a message inside a carrier by altering low-order bits of an image, text spacing, or similar. The carrier looks normal; the message is in the deviation from normal.

Prime Split Encoding (PSE) works differently. There is no deviation. The carrier — a sequence of prime numbers — is entirely valid. Every number is genuinely prime. The message is encoded in which of several equally valid ways each prime is split into sub-primes. An observer who does not know the codebook cannot distinguish a message-bearing sequence from any other sequence of primes.

## **1.1  Split Layers**

Given a prime N with decimal representation as a string, we define the following layers of prime structure:

Layer 1 — Monolithic: N itself is prime.

Layer 2 — Two-tranche: N can be split at some position i into two primes, both valid.

Layer 3 — Saturation: Every digit is covered exactly once by a contiguous tiling of primes.

Layer 4 — Three-tranche: N splits into exactly three contiguous primes covering all digits.

A number that satisfies all four layers simultaneously is a high-value carrier node. The message is not in the number — it is in which valid split the sender chooses.

## **1.2  A Worked Example: 1153**

Take N \= 1153\. It is prime (Layer 1). Its valid splits:

| Split | Parts | Layer | All Prime? |
| :---- | :---- | :---- | :---- |
| 11 | 53 | 11, 53 | 2-tranche | YES |
| 11 | 5 | 3 | 11, 5, 3 | 3-tranche | YES |
| 1153 reversed \= 3511 | 3511 | Reversal | YES |

1153 is prime. 3511 (its digit-reversal) is also prime. The two-split and three-split both yield all-prime parts. This is a structurally dense number: the same digits encode different messages depending on the resolution (split type) applied. The information is not a value — it is a choice.

Key insight: position and direction are as meaningful as the values themselves. 3|511 fails. 35|11 fails. 11|53 succeeds. The same four digits have a directional grammar.

# **2\.  The Split-Density Graph**

Define a graph G where every prime is a node and two primes share an edge if they appear together as components of a valid split of a third prime. This graph has properties that are deeply unlike the integer number line.

## **2.1  Topology**

The graph is disconnected from integer proximity. Primes 3137 and 3313 differ by 176 on the number line but share zero edges in G — their split-space neighborhoods are entirely disjoint. There is no gradient in G along the integers. An adversary who can enumerate nearby primes gains no information about the message structure, because nearness in Z has no relationship to nearness in G.

This is the foundational security property of PSE: the message channel does not live on the integer line.

## **2.2  Hub Nodes**

The graph has extreme degree inequality. The prime 3 appears in 13,140 decompositions up to 1M. The prime 7 appears in 12,501. Single-digit primes are hubs with degrees in the tens of thousands. Two-digit primes cluster around degree 1,300-1,600. Larger primes are sparse.

This is not accidental. It mirrors the structure of digit concatenation: short primes can appear in more split positions than long ones. The hub structure is not a vulnerability — it is the reason the encoding works at scale.

## **2.3  Density Scaling**

| Digit Length | Max Splits Found | Bits Per Prime | Primes With Splits |
| :---- | :---- | :---- | :---- |
| 3 digits | 3 | 1.58 | 51 |
| 4 digits | 5 | 2.32 | 381 |
| 5 digits | 8 | 3.00 | 3,142 |
| 6 digits | 9 | 3.17 | 25,482 |
| 7 digits | 12 | 3.58 | 215,044 |
| \~20 digits (projected) | \~952 | \~9.9 | — |
| \~50 digits (projected) | \~23,000,000 | \~24.5 | — |

At 20-digit primes, a single carrier number approaches a full byte of payload capacity. At 50 digits, a single prime carries approximately 3 bytes. The information density scales super-linearly with digit length.

# **3\.  The Encoder**

## **3.1  Protocol**

Two parties share a codebook: an ordered list of high-capacity primes. The codebook is the key. It is never transmitted.

To encode a message:

* Convert message to a bitstream (standard ASCII or UTF-8).

* For each prime P\_i in the codebook, compute k \= number of valid splits, capacity \= floor(log2(k)).

* Read 'capacity' bits from the bitstream. Interpret as integer index j.

* Transmit P\_i. The message bit contribution is j — the index into the canonically sorted split list of P\_i.

To decode:

* Receiver has the codebook. For each received prime, enumerate all valid splits in canonical order.

* The agreed split index j is extracted from context (see Section 3.2).

* Reconstruct the bitstream from all j values. Decode bytes.

## **3.2  Worked Encoding: 'HI'**

Message: 'HI'  (ASCII 72, 73\)  \=  bitstream: 0100100001001001

| Carrier Prime | Split Count | Bits Carried | Bits Used | Split Chosen |
| :---- | :---- | :---- | :---- | :---- |
| 3137 | 2 | 1 | 0 | (31, 3, 7\) |
| 3313 | 4 | 2 | 01 | (3, 3, 13\) |
| 3373 | 4 | 2 | 00 | (3, 373\) |
| 3733 | 4 | 2 | 10 | (3, 73, 3\) |
| 3797 | 4 | 2 | 00 | (3, 79, 7\) |
| 11317 | 2 | 1 | 1 | (11, 3, 17\) |
| 11353 | 4 | 2 | 00 | (113, 5, 3\) |
| 17317 | 4 | 2 | 01 | (17, 31, 7\) |

What the observer sees: \[3137, 3313, 3373, 3733, 3797, 11317, 11353, 17317\]

This is an unremarkable list of primes. There is no deviation from any expected distribution. The message is in the agreed split selection, which is not transmitted.

The receiver needs only the codebook (which primes, in which order) and the canonical split ordering rule. The split itself is computed locally — nothing about the split is ever sent.

# **4\.  Maximum Density Nodes**

The highest-density carrier found below 10M is 2,337,397 with 12 valid splits (3.58 bits). Its full split map illustrates the structural richness at 7 digits:

| Split Type | Components | All Prime? |
| :---- | :---- | :---- |
| 2-tranche | (2, 337397\) | YES |
| 2-tranche | (23, 37397\) | YES |
| 3-tranche | (2, 3, 37397\) | YES |
| 3-tranche | (2, 337, 397\) | YES |
| 3-tranche | (2, 3373, 97\) | YES |
| 3-tranche | (2, 33739, 7\) | YES |
| 3-tranche | (23, 37, 397\) | YES |
| 3-tranche | (23, 373, 97\) | YES |
| 3-tranche | (23, 3739, 7\) | YES |
| 3-tranche | (233, 7, 397\) | YES |
| 3-tranche | (233, 73, 97\) | YES |
| 3-tranche | (233, 739, 7\) | YES |

At 20 digits, projected split counts exceed 900\. A single prime number would carry approximately one full byte of message data.

# **5\.  Attack Surface: A Complete Taxonomy**

This is where honesty is required. PSE abandons most of the primitives that make modern cryptography safe. Each abandonment creates an attack surface. We enumerate them without apology.

## **5.1  The Codebook Is the Entire Key**

CRITICAL VULNERABILITY: There is no key separate from the codebook. Whoever has the ordered list of carrier primes can decode every message ever sent.

Unlike symmetric encryption where key compromise requires brute-force recovery of plaintext, PSE has no computational barrier between key possession and full decryption. The codebook is the key. The key is a list. Lists get leaked, copied, and stolen.

Practical attack: An adversary who observes multiple carrier sequences and has computational resources can attempt to reconstruct the codebook by finding the ordered prime list that produces coherent plaintext across multiple observed transmissions. This is a known-plaintext attack on the codebook structure itself.

Mitigation: Use a different codebook per conversation. Generate codebooks procedurally from a shared seed using a standard CSPRNG. The seed is the true key; the codebook is derived. This re-introduces a proper key management problem — which is actually what you want.

## **5.2  No Semantic Security**

CRITICAL VULNERABILITY: Two identical messages produce identical carrier sequences when the same codebook is used. PSE is deterministic.

In modern encryption, semantic security guarantees that encrypting the same plaintext twice produces different ciphertexts (via nonces, IVs, or randomized padding). PSE has none of this. The same message sent twice is the same prime sequence twice. An observer who sees the same sequence twice knows the same message was sent twice, and can correlate traffic without breaking the encoding.

This is a complete failure of IND-CPA security (Indistinguishability under Chosen Plaintext Attack) — the baseline requirement for any cipher used in practice.

Mitigation: Introduce a randomized prefix or suffix to every message before encoding. Pad messages to a fixed length. Neither is built into PSE and both must be added externally.

## **5.3  Codebook Bias Is Detectable**

HIGH VULNERABILITY: The codebook is biased toward high-split-count primes. This distribution is anomalous and detectable.

Of the 78,473 primes below 1,000,000, only 1,034 (roughly 1.3%) have four or more valid splits. A PSE carrier sequence will be overwhelmingly composed of primes from this minority. An adversary who tests each observed prime for split density will identify a carrier sequence with high probability — not the message content, but the fact that a covert channel exists.

This breaks the steganographic property. A steganalyst does not need to decode the message to do damage. Knowing the channel exists is often sufficient.

Mitigation: Intersperse decoy primes (primes not in the codebook, with low split counts) between carrier primes. Agree on a pattern or ratio in advance. This reduces channel capacity but restores statistical cover.

## **5.4  Small Split Counts Leak Information**

MODERATE VULNERABILITY: Many codebook primes have only 2 or 4 valid splits (1-2 bits). With such small alphabets, frequency analysis becomes feasible.

A prime with exactly 2 valid splits encodes a single bit. If the adversary knows the prime is a PSE carrier (from attack 5.3) and the split count (trivially computed), they immediately know the full space of that symbol is {0, 1}. For primes with 4 splits, the space is 2 bits (0-3). Letters in common English map to fairly predictable bit patterns.

Standard frequency analysis on single-bit carrier symbols, combined with knowledge of the encoding language, can recover message content without ever needing the codebook.

Mitigation: Use only high-density carrier primes (8+ splits). Avoid any carrier with fewer than 4 valid splits. Accept the reduced codebook size in exchange for resistance to frequency analysis.

## **5.5  The Resolution Attack**

MODERATE VULNERABILITY: The receiver must know which resolution (2-tranche vs 3-tranche) to apply. If this is fixed and known, the attacker can enumerate all valid splits at that resolution for every observed prime.

Consider a prime with 9 splits: 3 two-tranche and 6 three-tranche. If the protocol always uses 3-tranche splits, the attacker knows the symbol alphabet is size 6 (2.58 bits). The full split enumeration is O(n^2) for a digit string of length n — computationally trivial. Once the attacker has the split list for every carrier prime, they have reduced the problem to a simple codebook search.

Mitigation: Vary the resolution per prime according to the codebook. The resolution selection rule should itself be part of the shared secret. This can be encoded as a simple parity or position rule derived from the codebook seed.

## **5.6  No Integrity, No Authentication**

CRITICAL VULNERABILITY: PSE provides no message integrity and no sender authentication. An adversary who can inject primes into the channel can alter or forge messages undetectably.

There is no MAC (Message Authentication Code), no HMAC, no signature. A man-in-the-middle who replaces one carrier prime with another prime of equal split count but different split choices has altered the message with no evidence. The receiver decodes a different message and has no way to detect the substitution.

This is not a minor omission. In any adversarial channel — which is the only channel that matters — unauthenticated encoding is not secure encoding.

Mitigation: Append a standard HMAC over the decoded message using the codebook seed as the HMAC key. Or: sign the message with a standard asymmetric scheme before encoding. PSE provides the covert channel; authentication must come from a separate layer.

## **5.7  Replay Attacks**

HIGH VULNERABILITY: A recorded carrier sequence is permanently valid. PSE has no nonces, no timestamps, no session state.

An adversary who captures a carrier sequence today can re-transmit it in six months and the receiver will decode the original message. In a command-and-control scenario, replaying 'authorize transaction' or 'confirm receipt' is catastrophic.

Mitigation: Include a monotonic counter or timestamp in the message plaintext before encoding. The receiver rejects any decoded message with a counter value it has already processed. This is application-layer state management — not provided by PSE.

## **5.8  Brute Force on Small Codebooks**

MODERATE VULNERABILITY: For small codebooks (under \~500 primes), brute force over the prime space is feasible.

If the adversary knows approximately which primes are in the codebook (from the density bias attack), and the codebook is small, they can enumerate all possible orderings of candidate primes and test each ordering against observed carrier sequences for message coherence. For a codebook of 100 primes, the ordering space is 100\! — infeasible. But the adversary does not need to find the full ordering. They need only find the ordering of the primes observed in a single short transmission.

A 10-prime carrier sequence has 10\! \= 3,628,800 orderings. Testable in seconds on a laptop. Each ordering produces a candidate bit string; the adversary checks for printable ASCII.

Mitigation: Use long transmissions. The ordering attack grows factorially, but so does the message length. For transmissions using 50+ carrier primes the ordering space is astronomical. Additionally: the codebook should be much larger than the per-message carrier set, so the attacker cannot easily identify which subset was used.

## **5.9  The Base-10 Assumption**

PHILOSOPHICAL VULNERABILITY: The entire scheme depends on decimal digit concatenation. It is base-10 specific.

Primality is base-independent. 7 is prime in any base. But the split structure depends entirely on decimal representation. '1153' splits as 11|53 in base 10, but has a completely different digit string in base 16 (0x481). The shared secret implicitly includes the base.

This is not a practical attack in most scenarios, but it matters theoretically: the security argument must account for the encoding base as part of the key material. An adversary who does not know the base cannot enumerate splits. An adversary who knows the base can.

A more exotic hardening: use a non-standard base as part of the shared secret. Base-37, base-41, base-43 — all prime bases. Split structure in these bases has been studied far less than base-10 and provides a meaningfully larger enumeration burden.

# **6\.  Hardened Protocol Specification**

Incorporating the mitigations from Section 5, a minimally hardened PSE protocol looks like the following:

### **Key Material**

* Shared seed S: 256-bit random value. Generated once per session using a standard CSPRNG and exchanged via a standard key agreement protocol (e.g. X25519 Diffie-Hellman).

* Codebook derived deterministically from S: a CSPRNG seeded with S selects 1,024 high-density carrier primes (8+ splits) from a pre-computed prime table. Ordering is determined by the CSPRNG output.

* Base B: derived from S as a prime in \[37, 53\]. Changes the digit concatenation domain.

* Resolution rule: for each carrier prime at position i, resolution is 2-tranche if bit i of SHA-256(S) is 0, else 3-tranche.

### **Encoding**

* Prepend 64-bit monotonic counter to message plaintext.

* Pad message to next multiple of 64 bytes using PKCS\#7.

* Encode padded message using codebook and resolution rule.

* Compute HMAC-SHA256 over decoded message using S as key. Append to carrier sequence as a final non-carrier prime (just transmitted as a number — not encoded via splits).

### **Decoding**

* Receive carrier sequence. Separate final HMAC prime.

* Decode carrier sequence using codebook and resolution rule.

* Verify HMAC. Reject on failure.

* Extract and verify counter. Reject replays.

* Strip padding. Recover plaintext.

This hardened protocol delegates all of its security properties to well-understood primitives: X25519 for key exchange, HMAC-SHA256 for integrity, PKCS\#7 for padding. PSE contributes only the covert channel property — the carrier looks like a prime sequence. Nothing else.

# **7\.  Non-Contiguous Number Lines and Meta-Spaces**

The split-density graph G is not a line. It is not ordered. Proximity in G has no relationship to proximity in Z. This is a concrete instance of a broader structure we term a non-contiguous information space: a set equipped with an encoding topology that is disconnected from the natural ordering of its elements.

PSE is one construction. Others are possible. The generalized question is: given a mathematical structure S with a natural ordering, what secondary structures can be derived from S that carry information in the relational topology rather than the values? Gaussian integers, Eisenstein integers, and p-adic number fields all admit analogous constructions where primality (or its analog) generates disconnected encoding graphs.

The Langlands program, at its core, asks precisely this question at a deeper level: what symmetry structure underlies the relationship between prime distributions in different number fields? The PSE graph is a toy instance of the same question applied to digit concatenation.

The practical implication: any adversary whose attack model assumes that nearby values carry similar information is operating in the wrong space. The message topology of PSE does not have near and far.

# **8\.  Open Problems**

* What is the asymptotic growth rate of max splits as a function of digit length? The empirical data suggests super-linear growth; a formal bound would sharpen capacity projections.

* Does the split-density graph exhibit small-world or scale-free properties? Hub dominance by single-digit primes suggests scale-free structure, with implications for codebook design.

* What is the split structure in prime bases (base-37, base-41)? Are the hub primes different? Does the graph have different connectivity properties?

* Can the encoding extend to Gaussian integers? A Gaussian prime N \= a \+ bi admits a richer split space than its real counterpart, with splits along both real and imaginary axes.

* Is there a number-theoretic explanation for the 911 / 137 / 167 coincidences noted in the constants survey? Or is this base-10 numerology?

* Can PSE be adapted to non-decimal bases in a way that provides a measurably harder enumeration problem for adversaries?

## **Conclusion**

Prime Split Encoding is a novel steganographic scheme with a genuine non-contiguous channel topology that defeats proximity-based and gradient-based analysis. A working encoder and decoder has been demonstrated. The information capacity scales with digit length and projects to full-byte-per-prime capacity at 20 digits.

The scheme has serious vulnerabilities when operated without standard cryptographic primitives: no semantic security, no integrity, no authentication, and a detectable carrier bias. None of these are fundamental to the mathematical structure — all are remediable by layering PSE over standard key exchange and HMAC schemes, delegating security properties to well-understood primitives and reserving PSE for the covert channel property alone.

The deeper result is the confirmation of a non-contiguous information topology: a space in which message proximity has no relationship to integer proximity. This property, not the encoding scheme per se, is the contribution worth pursuing.

J. Pickett  |  Eugene, Oregon  |  March 2026