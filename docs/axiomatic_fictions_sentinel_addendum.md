# Participation Over Permission — Addendum
## The Sentinel Contract: Structural Tamper Detection in Provenance Signals

*Axiomatic Fictions in LLM Security / Image Provenance Series*
*Jeremy Pickett — March 2026*

---

> "The adversary who compresses to destroy the frequency signal is constructing the spatial variance detection signal."

The previous installments of this series established a three-layer provenance architecture: prime quantization tables at the container level, twin prime-gap markers at the pixel level, and a blind spatial variance detector that strengthens under compression. That work answered the question *was this image marked?*

This addendum introduces the fourth layer, which answers a harder question: *was this marked image tampered with, and if so, how?*

---

### The Problem With Detecting What Isn't There

The core difficulty of tamper detection is that absence of evidence is not evidence of absence. An image that has lost its provenance signal through aggressive compression looks identical to an image that had its signal deliberately removed. Layer D — the spatial variance detector — cannot distinguish between these two cases. It detects the presence of a signal. It cannot characterize its absence.

What we needed was a structure that encodes its own integrity invariant: something that, when intact, proves it has not been touched, and when broken, reveals *how* it was broken. The answer came from an unexpected direction.

---

### Mersenne Primes as Structural Markers

Mersenne primes are primes of the form 2ⁿ − 1. In the 8-bit range there are exactly four: **3, 7, 31, 127**. They are distinguished not just by primality but by their binary representation: all ones. A channel difference of exactly 127 (01111111₂) in a natural image is unusual — it requires one channel to sit near the midpoint of the range while the other approaches zero or maximum. This rarity is the signal.

The architecture uses these four values as *sentinels* that bracket sections of prime-gap markers. Each section of `SENTINEL_CANARY_RATIO` markers (currently 8) is wrapped in an entry/exit pair:

```
[Mersenne] [prime] [prime] ... [prime] [prime] [Mersenne]
```

Where `[prime]` is a twin prime-gap marker (two adjacent positions both satisfying the prime-gap constraint) and the `[Mersenne]` is placed immediately adjacent to the first and last marker of the section.

The detection requirement — which is the architectural insight that makes this robust — is that a fuzzy Mersenne value is **not** a canary on its own. It only registers as a sentinel when it is **immediately adjacent to a complete twin prime pair**. The required structure for an entry is:

```
[fuzzy Mersenne] [fuzzy prime] [fuzzy prime]
```

And for an exit:

```
[fuzzy prime] [fuzzy prime] [fuzzy Mersenne]
```

The entry and exit are structural inverses of each other. This is not incidental. The mirroring is the detection mechanism. A natural image does not produce these three-position structures with any regularity because it requires three independent statistical coincidences simultaneously: a channel difference within `CANARY_WIDTH` of a Mersenne prime, followed by two adjacent channel differences both within tolerance of primes above the floor. The joint false positive probability is approximately `P(Mersenne_fuzzy) × P(prime_fuzzy)² ≈ 0.05 × 0.06 × 0.06 ≈ 0.0002` per position.

---

### The Contract and Its Violations

The sentinel architecture defines a formal contract:

**For every entry sentinel in section N, there exists a corresponding exit sentinel.**

This contract is evaluated by a blind scanner that requires no manifest, no receipt, no knowledge of the embedding seed or parameters. It scans every eligible grid position, identifies structural canaries, groups them into sections by spatial proximity, and evaluates well-formedness.

The analogy to XML/SGML is precise and deliberate. A well-formed XML document requires that every opening tag has a corresponding closing tag, that they nest correctly, and that the content between them conforms to the schema. The sentinel contract is the same constraint applied to pixel-space provenance signals. The vocabulary is different; the grammar is identical.

Contract violations fall into six classes, in increasing order of attacker sophistication:

**Class 1 — Missing exit (`exit_missing`)**
The section has an entry but no exit. The tail of the section was removed or overwritten. Detection is immediate and certain. This attacker did not know exits existed, or did not care.

**Class 2 — Missing entry (`entry_missing`)**
The section has an exit but no entry. The head was removed. Same implications as Class 1 from the opposite direction.

**Class 3 — Full wipe (`full_wipe`)**
All sentinels destroyed. The attacker applied a uniform operation — re-encoding at aggressive quality, heavy blurring, or systematic pixel modification — without knowledge of the structure. Also consistent with severe platform transcoding. Indistinguishable from negligence; cannot be attributed to targeted tampering without additional evidence.

**Class 4 — Directional sweep (`tail_sweep`, `head_sweep`)**
Three or more consecutive sections have exits removed (tail sweep) or entries removed (head sweep). This attacker understood that boundary markers exist and removed them from one end of the image systematically. They either scanned for Mersenne values and zeroed them, or applied a spatial crop operation that destroyed markers from one edge inward. The directionality is evidence of intentionality: random degradation does not produce consecutive runs of missing exits.

**Class 5 — Structural inversion (`structural_inversion`)**
Entry and exit positions are present but their types are swapped — an exit pattern appears where an entry should be. This attacker read the specification. They understood that entries and exits are distinct structures, attempted to reconstruct the boundaries, and got the mirroring wrong. This is the mark of a sophisticated adversary who understood enough to try to forge the structure but not enough to replicate it correctly.

**Class 6 — Interior anomaly (`interior_anomaly`)**
The sentinel boundaries are intact and well-formed, but the interior marker count deviates from the expected `SENTINEL_CANARY_RATIO`. The attacker understood the boundary protocol perfectly and did not touch the sentinels. They modified the content *between* the sentinels — injecting additional markers or deleting existing ones — in an attempt to either inflate the apparent provenance signal or reduce it below detection threshold while leaving the structural frame intact. This is the hardest attack to execute correctly and the most informative to detect: it implies the attacker had access to the specification *and* the tooling to implement it. It is also the easiest to counter: the expected interior count is a protocol constant. Any deviation is anomalous by definition.

---

### The `SENTINEL_CANARY_RATIO` Is Not a Configuration Option

The ratio of interior markers to sentinel pairs is a protocol constant, not a user parameter. This distinction has governance implications that extend beyond implementation convenience.

The matching service — the external infrastructure that receives a file, scans its sentinel structure, and compares against a registry of known embeddings — depends on this constant being uniform across all images it has ever ingested. If a user were permitted to change the ratio per-image, they would be creating a private namespace that the matching service could never index into confidently. Worse, they would be generating false negatives at scale: the scanner would look for sections of size 8 and find sections of size 11, and conclude no signal was present.

This is the same reason cryptographic protocol version numbers are not user-configurable: the security property of the system depends on all participants agreeing on the same primitives. The ratio is a version-controlled constant. If empirical testing reveals that 8 is the wrong number — too sparse for small images, too dense for large ones — the correct response is to bump the protocol version and update the scanner to handle both, not to expose the number as a dial.

The user is in charge of many things in this system. The sentinel ratio is not one of them.

---

### Compliance and Governance Implications

The four-layer architecture establishes a hierarchy of evidentiary claims that maps cleanly onto compliance frameworks concerned with provenance, attribution, and chain of custody.

**Layer A (DQT prime tables):** Proves that the file was created by a tool that implements this protocol. Survives only lossless passthrough. Its death at first re-encode is not a failure — it is evidence that the container was modified, which is itself a meaningful claim.

**Layers B/C (compound twin markers):** Proves that specific pixel positions were deliberately modified according to a known algorithm. Requires the manifest (embed receipt) for verification. Establishes *participation*: the image was processed by a system that embeds provenance signals.

**Layer D (blind spatial variance):** Proves that the signal is present even after aggressive compression, without any manifest. The signal amplifies under the very compression an adversary would use to destroy it. This is the primary evidentiary contribution.

**Layer E (sentinel contract):** Proves not just presence but *integrity*. An intact sentinel structure establishes that the signal has not been surgically modified since embedding. A broken sentinel structure characterizes *how* it was modified, which carries evidential weight about the sophistication and intent of the modification.

Together, these layers support the following chain of claims:

1. This image was processed by a provenance-aware system (Layer A, gen0 only)
2. This image contains provenance markers that survive normal distribution pipelines (Layer D)
3. These markers have not been selectively removed or modified (Layer E, intact contract)
4. The specific embedding parameters match a registry entry (Layer B/C with manifest)

No single layer is sufficient for a strong provenance claim. All four together constitute what this series has called "Participation Over Permission": the signal does not require the platform's cooperation to survive, does not require the viewer's knowledge to be present, and does not require the attacker's consent to document their interference.

---

### What This Does Not Claim

This architecture does not identify attackers. It characterizes operations. The difference matters for both technical accuracy and legal defensibility.

A Class 6 interior anomaly tells you that someone with protocol knowledge modified the content between sentinels. It does not tell you *who*. If that actor has registered their tooling with a matching service and the operation signature matches a known fingerprint, the service may return a high-confidence attribution. But that attribution comes from the matching service's registry, not from the signal itself.

The signal proves participation. The matching service proves identity, conditionally, given registration. These are two different claims and they should not be conflated in any compliance documentation, legal proceeding, or policy framework that relies on this work.

The canonical phrase from this series applies: **Participation Over Permission**. We detect participation. We do not compel disclosure.

---

### Implementation Status (March 2026)

The sentinel architecture described above is implemented in `compound_markers.py` as of this writing. The blind scanner (`detect_sentinels_blind`) and manifest scanner (`detect_sentinels`) both produce the full tamper classification taxonomy described here. Testing scripts (`canary_detection_test.py`, `tamper_simulation_test.py`) exercise all nine tamper classes against the DIV2K corpus.

The `SENTINEL_CANARY_RATIO = 8` and `CANARY_WIDTH = 2` are protocol constants documented in source with explicit notes explaining why they are not exposed as user configuration. Empirical validation of these values against the full corpus is ongoing.

Version 2 work — robust pixel-value spanning to improve embedding efficiency at high floor values — is deferred pending completion of the current test suite.

---

*Licensed under Creative Commons Attribution 4.0 International.*
*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*
