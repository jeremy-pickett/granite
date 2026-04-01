**GRANITE**

**IMAGE PROVENANCE SYSTEM**

*Technical Reference  —  Layer Specification*

Jeremy Pickett  |  March 2026

*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*

Licensed BSD-2. Open research.

## **About This Document**

This reference documents the GRANITE image provenance system layer by layer. Each layer section uses an identical structure: purpose, what the layer detects and proves, explicit constraints, encoding surface, protocol constants, detection algorithm, survivability profile, integration, API reference, and known limitations.

The document opens with Section 0: System Model, which defines the evidentiary framework, the three outcome classes, the attack signature taxonomy, and the legal language conventions. Section 0 is shared across all layer documents. Read it before any individual layer section.

# **Section 0 — System Model and Evidentiary Claims**

## **0.1  What This System Is**

GRANITE is an anti-scrubbing evidentiary lattice for image provenance. That phrase is precise and each word is load-bearing.

| Term | What It Means Here |
| :---- | :---- |
| **Anti-scrubbing** | The system is not designed to survive all possible attacks. It is designed so that the act of removing it produces interpretable evidence of the removal. The goal is not invulnerability. The goal is that removal tells on itself. |
| **Evidentiary** | The system produces signals that may support an inference of deliberate suppression. It does not prove intent. It produces a record from which inferences may be drawn, subject to further analysis and appropriate legal caution. |
| **Lattice** | Multiple independent layers, each covering different attack surfaces, each providing evidence even when peers fail. No single layer is authoritative. The lattice as a whole is more than any individual layer. |

*The security community scores provenance systems like DRM: “Can I strip it?” The honest answer is yes — a sufficiently motivated adversary with sufficient knowledge can strip any steganographic system. That is the wrong battleground. GRANITE’s battleground is this: “Can you strip it without the stripping being interpretable?” That is a harder problem, and it is the problem this system actually solves.*

## **0.2  Positioning Within the Literature**

This system belongs to an established research category. The construction is novel; the category is not. Claiming otherwise would be imprecise and unhelpful.

### **What Has Prior Art**

* Response-based signal detection. The GRANITE approach uses what a compressor does to a signal as the detection surface — JPEG amplifies detectable divergence rather than destroying the signal. This is explicit in Bianchi and Piva’s double-JPEG detection work, which analyzes quantization artifacts as a detection signal rather than an obstacle to one.

* PRNU and forensic fingerprinting. The use of a statistical signal embedded in image content that survives pipeline transforms and produces forensic evidence of modification is the core of PRNU-based camera attribution and related forensic methods.

* Steganalysis-aware embedding. The steganalysis literature extensively studies distributional changes produced by steganographic transforms. Any competent reviewer will evaluate this system against cover-model divergence, chi-squared attacks, and ensemble classifiers. This is expected, not surprising.

### **What Is Novel in Construction**

* The specific encoding surface: twin prime gap markers whose divergence is amplified rather than suppressed by JPEG quantization (“granite under sandstone”).

* The four observable states (A/B/C/D) as a formal response taxonomy, distinguishing benign degradation from targeted suppression at the signal level.

* The two-zone radial lensing field (Layer G) providing rotation-resilient detection with a void state that outlives the embedded sentinel.

* The multi-layer lattice design where each layer’s failure mode is covered by a peer, and the combination of failures is itself evidence.

* The spatial ruler layer (Layer H) providing crop and stitch forensics independently of all other layers.

*The correct category claim is: this system applies response-based, multi-layer forensic provenance methods with novel construction choices designed to make the damage pattern interpretable across a range of adversarial transforms. It does not claim to invent the category.*

## **0.3  Three Outcome Classes**

Every marked image, after any transform or handling, produces a signal pattern classifiable into one of three outcome classes. These classes are the fundamental vocabulary of GRANITE forensics. All layer sections use this vocabulary.

| Class | Name | Mechanism | Evidentiary Interpretation |
| :---- | :---- | :---- | :---- |
| **1** | **Benign Degradation** | Lossy compression, format conversion, legitimate processing pipeline | Participation proven. Signal degraded uniformly and consistently with known codec behavior. Chain-of-custody intact. No inference of deliberate intervention is supported. |
| **2** | **Opaque Destruction** | Unknown catastrophic transform, severe corruption, total format conversion | Indeterminate. Total absence of all layers is consistent with extreme benign degradation. Cannot be reliably distinguished from Class 1 at the extreme without additional context. |
| **3** | **Targeted Suppression** | Selective removal of specific layers while others are preserved or degraded differently | Incoherent collapse pattern. Inconsistent with any single known transform. May support an inference of deliberate suppression. Requires further analysis; does not independently establish intent. |

The middle class is the most legally and forensically important. Class 2 (opaque destruction) is difficult to distinguish from extreme Class 1 (catastrophic benign degradation) without external context. Class 3 is structurally different: random damage does not produce selectively absent layers. Randomness produces coherent collapse. Incoherent collapse — where some layers are intact and others are absent in a pattern inconsistent with any single known transform — is not a natural artifact.

*The goal of the system is not that individual layers survive. The goal is that one or more layers survive casual and semi-competent handling, while deliberate multi-layer removal becomes interpretable as evidence of the removal itself.*

## **0.4  Attack Signature Taxonomy**

The following table maps each outcome class to its per-layer signature. The composite row (bottom) is the key forensic discriminator: a coherent collapse across all layers is consistent with Class 1 or 2\. An incoherent collapse — specific layers absent, others intact or anomalous in layer-specific ways — is the signature of Class 3\.

| Layer | Class 1 Benign Degradation | Class 2 Opaque Destruction | Class 3 Targeted Suppression |
| :---- | :---- | :---- | :---- |
| **A  Container** | DQT tables present, degraded | DQT absent or corrupt | DQT selectively zeroed; other tables intact |
| **BC Frequency** | Twin prime density reduced | Uniform noise floor | Prime-gap markers inverted; DC intact |
| **D  Spatial** | KS statistic elevated uniformly | Indeterminate | Localized anomaly near embedding sites |
| **E  Sentinel** | State C: values drifted | State A: total absence | State D: positions scrambled; values removed |
| **F  Payload** | Partial bit recovery; no fault | Zero recovery; no fault | Zero recovery \+ E/D inconsistency |
| **G  Halo** | VOID state from compression | ABSENT state | ABSENT inner, elevated outer (force arrow) |
| **H  Ruler** | Band survives; dim recovers | No band signal detected | Bands selectively absent; others intact |
| **Composite** | Coherent collapse across layers | Total absence; indeterminate | Incoherent collapse; layer-specific residue |

The composite row is the system-level claim. Global recompression produces a coherent signal: all layers degrade together in a pattern consistent with a single quantization pass. Targeted suppression produces an incoherent signal: Layer A absent while Layer H intact, or Layer E in State D while Layer G reports ABSENT (not VOID). These combinations have no innocent explanation.

Example Class 3 indicator: Layer A absent \+ Layer H selectively erased at ruler positions \+ Layer D localized anomaly at embedding sites \+ Layer F zero recovery. No single codec operation produces this combination. The pattern is consistent with coordinated suppression of individual layers, which **may support an inference of deliberate intervention**.

## **0.5  Layer D Operating Modes**

Layer D (Spatial KS Variance) operates differently depending on whether the embedding manifest is available. This is explicitly distinct from all other layers, which have consistent behavior in both modes. Every Layer D section in this document uses the mode badge system.

**●  BLIND MODE — no manifest required**

Layer D is the primary signal. The KS variance anomaly produced by twin prime gap embeddings is detectable without knowing where markers were placed, what payload was used, or what session produced the image. The KS statistic is elevated across the pixel-value distribution in regions containing Layer BC markers. This is the most important property of Layer D: it functions as a forensic scanner without any prior knowledge of the marked image.

**○  MANIFEST MODE — embedding record known**

Layer D is corroborating evidence. When the embedding manifest is known, Layer D confirms that the spatial anomaly is present at the expected positions, with the expected magnitude, and in the expected direction. In manifest mode, Layer D is not the primary claim — the sentinel contract (Layer E) is. Layer D adds weight to the inference but does not independently establish the primary evidentiary claim.

*These two roles cannot both be primary simultaneously. Any paper section that presents Layer D must specify which mode it is describing. Conflating the modes produces an oscillation between “Layer D is the paper” and “Layer D is corroborating only” that no reviewer should have to resolve.*

## **0.6  Legal Language Conventions**

This section defines the language conventions used throughout this document and all associated papers. These conventions are not stylistic preferences. They reflect the epistemic status of the claims being made and the legal and rhetorical consequences of language choices.

The system produces statistical signals from which inferences may be drawn. It does not establish intent. It does not independently prove deliberate suppression. It produces evidence patterns that, in combination with other evidence and appropriate expert analysis, may support inferences about what was done to an image and whether that was likely deliberate.

| Context | Use This | Not This |
| :---- | :---- | :---- |
| **Selective layer removal** | *may support an inference of deliberate suppression* | *proves tampering / shows intent* |
| **Incoherent collapse pattern** | *is inconsistent with benign degradation* | *proves targeted removal* |
| **Anti-forensic signature** | *the pattern is consistent with coordinated suppression* | *demonstrates malicious intent* |
| **Zero payload recovery** | *the payload was not recovered; this may indicate removal* | *the payload was destroyed deliberately* |
| **Force-arrow VOID state** | *the halo field remains, consistent with localized removal* | *the adversary removed the sentinel* |
| **DQT anomaly absent** | *Layer A signal is absent; this warrants further analysis* | *the format layer was wiped* |
| **Corroborating Layer D** | *Layer D provides additional support for this inference* | *Layer D confirms the attack* |

*Use “may support an inference of deliberate suppression” far more often than “shows intent” or “proves tampering.” Technically and rhetorically, the inferential framing is both more accurate and more credible. An overreach that a reviewer can refute damages the entire paper. A careful inferential claim is difficult to attack.*

## **0.7  Cross-Layer Competency Matrix**

The matrix below maps attacks and transforms against all seven layers. Read across a row to see which layers handle a given attack. Read down a column to see a layer’s coverage profile. The composite view answers the system-level question: which attack patterns leave no surviving evidence, and which produce interpretable residue.

**Legend:**    ✓  Handles independently    ◑  Partial / cooperative    ✗  Cannot handle    —  Not applicable

| Attack / Transform | A | BC | D | E | F | G | H |
| :---- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **JPEG Q85 survival** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **JPEG Q40 survival** | **✓** | **◑** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **JPEG Q30 survival** | **◑** | **✗** | **◑** | **◑** | **◑** | **◑** | **✓** |
| **Arbitrary rotation** | — | — | — | — | **◑** | **✓** | — |
| **Horizontal crop** | — | — | — | — | — | — | **✓** |
| **Vertical crop** | — | — | — | — | — | — | **✓** |
| **Both-axis crop** | — | — | — | — | — | — | **◑** |
| **Image stitch** | — | — | — | — | — | — | **✓** |
| **Original dimension recovery** | — | — | — | — | — | — | **✓** |
| **Sentinel removal (VOID)** | — | — | **✓** | — | — | **✓** | — |
| **Format-level tampering** | **✓** | — | — | — | — | — | — |
| **Pixel-layer tampering** | — | — | **✓** | — | — | — | — |
| **Participation proof** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **Payload recovery** | — | — | — | — | **✓** | **◑** | **◑** |

Columns: A \= Container (DQT), BC \= Frequency (twin prime compound), D \= Spatial (KS variance), E \= Sentinel (spanning relational), F \= Payload (position-offset vote), G \= Halo (radial lensing field), H \= Ruler (spatial reference frame).

Note that no layer handles all attacks. The rotation row has only Layer G. The crop rows have only Layer H. The format-level tampering row has only Layer A. This is intentional: each layer is purpose-built for its attack surface, and the lattice derives its strength from the combination.

## **0.8  Layer Integration Overview**

| Layer | Provides To Stack | Depends On |
| :---- | :---- | :---- |
| **A  Container** | Format tamper detection, M=31 sentinel anchor | None — operates on raw JPEG quantization tables |
| **BC Frequency** | Twin prime gap markers, cascade-resilient compound signal | Layer A (floor constant, M=31 exclusion) |
| **D  Spatial** | KS variance anomaly; blind-mode primary signal; manifest-mode corroboration | Layer BC (pixel field to measure) |
| **E  Sentinel** | State B/C/D classification, spanning relational proof | Layers A–D (composite signal) |
| **F  Payload** | 24-bit session payload recovery at Q40 | Layer E (sentinel positions for offset encoding) |
| **G  Halo** | Rotation-resilient detection, VOID state after removal | Layer F (sentinel centers as halo origins) |
| **H  Ruler** | Crop/stitch forensics, original dimension recovery | None — operates independently on image geometry |

Layer H is architecturally isolated: it produces no outputs to the stack and requires no inputs from peers. All other layers form a dependency chain from A through G. This isolation means Layer H can be evaluated and trusted independently of whether any other layer is present or functioning.

# **Section 1 — Layer H: Spatial Ruler**

**Role:** *Crop and stitch forensics. Embeds a spatial reference frame as column and row bands, allowing a detector to recover original dimensions and detect geometric manipulation without a manifest. Operates independently of all other layers.*

## **1.1  Purpose and Role in the Stack**

All other GRANITE layers are designed to survive lossy compression, format conversion, and pixel manipulation. None of them address spatial transforms. A crop that removes 20% of an image from the left, a stitch that joins two images side by side, or any other operation that changes the image’s spatial extent is invisible to Layers A through G.

Layer H fills this gap. It embeds ruler bands at deterministic fractions of the image dimensions. Each band’s encoded payload includes its canonical fraction and the original image dimensions. After any spatial transform, surviving bands are either at their expected positions (no crop) or displaced (crop, with recoverable offset), absent (that edge was cropped away), or present in inconsistent combinations (stitch).

The crop or stitch may be Class 1 (routine image editing) or Class 3 (targeted manipulation). Layer H does not distinguish these on its own. It records the geometry. The interpretation — whether the crop is consistent with known editorial behavior, whether it is suspiciously precise around evidence, whether the stitch joins images with other provenance anomalies — requires the larger evidentiary context.

## **1.2  What This Layer Detects and Proves**

### **Detects**

* Horizontal crop: left edge removed, right edge removed, or both

* Vertical crop: top edge removed, bottom edge removed, or both

* Both-axis crop: any rectangular crop removing edges on two or more sides

* Image stitch: two separately-marked images joined along a seam

* Dimension mismatch: current dimensions inconsistent with ruler payloads

### **Proves**

* **Participation:** the image was processed by a tool implementing this protocol

* **Original dimensions:** W\_orig and H\_orig recoverable to within 8px via least squares when 2+ rulers survive on an axis

* **Crop offset:** amount removed from left and/or top edge, recoverable from ruler displacement

* **Stitch seam:** approximately identifiable from the column where ruler sets change

* **Geometric integrity:** if rulers are at expected positions and payloads decode consistently, the image has not been spatially manipulated

### **Does Not Prove**

* Why the crop or stitch occurred

* Whether the crop was deliberate or editorial

* Identity of the entity that performed the operation

These inferences require the broader evidentiary context described in Section 0\.

## **1.3  Explicit Constraints**

*This section defines the boundaries of Layer H. Every item listed is covered by a peer layer or is a documented open item. Nothing in this list is a deficiency — it is the specification of what this layer is for and what it delegates.*

* **Rotation destroys ruler alignment.** Use Layer G. These two layers are designed as complements with no overlap in attack surface.

* **Both-axis crop recovers dimensions only partially.** A simultaneous left and top crop corrupts both the column ruler payload (row-segment shift from top crop) and the row ruler payload (column-segment shift from left crop). Detection is solid; dimension recovery degrades. The manifest resolves this.

* **Does not authenticate identity.** Presence of a ruler proves the protocol was applied. It does not establish who applied it. That is the matching service’s domain.

* **RAW/Lightroom pipeline not yet validated.** Whether bands survive demosaicing and Lightroom export is an open item. If they do, this layer extends claims to professional photography workflows. This is the highest-priority open item in the system.

* **Extreme monochromatic content.** Images where the natural |R−G| or |G−B| distribution already clusters near 198 may produce spurious ruler detections. The blind-scan threshold (62) is calibrated against the DIV2K corpus.

* **Not a pixel-integrity layer.** Use Layer D for pixel-level tampering detection. Layer H is a geometric layer.

## **1.4  Encoding Surface**

### **Why Bands, Not Points**

The fundamental challenge for any geometric layer is JPEG resilience. JPEG operates on 8×8 pixel blocks using DCT. A single marked pixel is averaged with 63 neighbors, and any chroma signal is destroyed by the quantization step. This eliminates all single-pixel and small-patch approaches for use with lossy formats.

The solution is to fill the entire 8×8 block with the target chroma. A 16-pixel-wide band column spans exactly two 8-pixel JPEG block columns. When every pixel in both columns has |R−G| \= 198, the entire chroma block is uniformly elevated. JPEG quantizes the block mean, not individual pixels. A uniformly elevated block mean survives at any quality setting — JPEG cannot reduce a consistent chroma signal without reducing the entire block, which would be visible in the luminance.

Empirical result: band mean after Q85 \= 195.5 (target 198, drift 2.5 counts). Band mean after Q30 \= 195.7. Natural column mean \= 15–20 counts. Detection margin \= 175+ counts at all tested quality levels. Zero bit errors across Q30–Q95.

### **Segment Encoding**

The band column is divided into SEGMENT\_HEIGHT \= 32 pixel segments. Each segment carries one payload bit: bit \= 1 means the segment’s band pixels are set to |R−G| \= 198; bit \= 0 leaves them natural. Detection reads the mean |R−G| per segment across the band width. Threshold \= 80 counts.

### **Orthogonal Channel Design**

Vertical rulers embed |R−G| \= 198\. Horizontal rulers embed |G−B| \= 198\. At every intersection of a vertical and horizontal band, both rulers attempt to modify pixels in the same 16×16 zone. Using orthogonal channel pairs ensures that the detector reading |R−G| for vertical rulers is not corrupted by the |G−B| modifications made by horizontal rulers, and vice versa.

Additionally, horizontal rulers skip column positions occupied by vertical band zones during embedding. This prevents the horizontal ruler’s G-channel adjustment from corrupting the G value that the vertical ruler previously set to achieve |R−G| \= 198\.

### **Payload Structure**

STANDARD MODE  (dimension ≥ 1024\)                    51 bits  
  bit  0       mode flag (0 \= standard)  
  bits 1–3     fraction index  (3 bits)  
  bit  4       axis (0 \= col/vertical, 1 \= row/horizontal)  
  bits 5–17    dim\_orig  (13 bits: W for col rulers, H for row rulers)  
  bits 18–34   timestamp\_hours (17 bits, hour precision, 50-year range)  
  bits 35–50   session\_hash truncated (16 bits)  
   
SMALL MODE  (dimension \< 1024\)                         28 bits  
  bit  0       mode flag (1 \= small)  
  bit  1       axis  
  bits 2–14    absolute pixel position (13 bits)  
  bits 15–27   dim\_orig (13 bits)  
   
Priority encoding: identification data occupies first bits.  
4 surviving segments → mode \+ partial fraction (ruler identified).  
18 surviving segments → full position \+ dimension (crop recoverable).

## **1.5  Ruler Geometry**

| Dimension | Mode | Rulers | Positions | Payload Bits |
| :---- | :---- | :---- | :---- | :---- |
| **\< 1024 px (small)** | SMALL | 3 | dim × \[1/4, 1/2, 3/4\] | 16–23  (fraction \+ pos \+ dim) |
| **≥ 1024 px** | STANDARD | 5 | dim × \[1/8, 1/4, 1/2, 3/4, 7/8\] | 32–64  (full payload) |
| **≥ 4096 px** | STANDARD | 5 | same fractions | 105   (full \+ redundancy) |

## **1.6  Protocol Constants**

| Constant | Value | Derivation / Rationale |
| :---- | :---- | :---- |
| **RULER\_TARGET** | 198 | \= 197+1 (197 prime, above FLOOR=43). Target |R-G| for vertical ruler bands |
| **RULER\_H\_TARGET** | 198 | \= 197+1, |G-B| channel only. Orthogonal to RULER\_TARGET; no crosstalk |
| **BAND\_WIDTH** | 16 px | Two 8-pixel JPEG chroma blocks. Fills entire DCT block column — JPEG preserves the mean |
| **SEGMENT\_HEIGHT** | 32 px | One payload bit per segment. Balances capacity vs spatial resolution |
| **SEGMENT\_THRESHOLD** | 80 counts | Midpoint: natural |R-G| mean ≈15, embedded mean ≈195. Margin: 115 counts vs JPEG drift \<5 |
| **SMALL\_THRESH** | 1024 px | Below this dimension: absolute position encoding. Above: fraction-based encoding |
| **FLOOR** | 43 | GRANITE protocol minimum prime (sentinel entry constant M=31 \+ margin) |

## **1.7  Detection Algorithm**

**○  MANIFEST MODE — embedding record known**

**Manifest-Mode Detection**

Scan each expected column and row position given current image dimensions. For each, read segment means, decode payload, compare decoded dim\_orig to current dimensions. Fast and exact.

for each expected col c (from get\_ruler\_positions(W\_cur, H\_cur)):  
  for each segment s in range(H\_cur // 32):  
    mean\_rg \= mean(|R-G|, rows\[32s:32s+32\], cols\[c±8\])  
    bit\[s\]  \= 1 if mean\_rg ≥ 80 else 0  
  payload \= unpack(bits)  
  if payload.dim\_orig \!= W\_cur: crop\_detected \= True

**●  BLIND MODE — no manifest required**

**Blind-Mode Detection (Forensic, No Manifest)**

Scan every column for elevated band mean. Non-maximum suppression to find centers. Decode payload at each candidate. Filter to genuine rulers (band\_mean ≥ 62 AND dim\_orig \> 0). Run least-squares dimension recovery.

col\_means \= mean(|R-G|, axis=0)  \# per-column mean across full height  
smoothed  \= uniform\_filter1d(col\_means, size=16)  \# find band centers  
candidates \= columns where smoothed \> 62  
for each candidate c:  
  payload \= detect\_ruler(image, c, is\_col=True)  
  if payload.dim\_orig \> 0: genuine\_rulers.append((c, payload))  
W\_orig, crop\_left \= least\_squares\_recovery(genuine\_rulers, W\_cur)

**Dimension Recovery: Three Paths**

The recovery algorithm handles the cases where JPEG or crop corrupts one or more payload paths:

* **Path A — Least squares:** 2+ col rulers with valid, diverse fractions. Solves new\_pos\_i \= W\_orig × frac\_i − crop\_offset. Exact when overdetermined.

* **Path B — Small-mode displacement:** crop\_top \= encoded\_pos − current\_row for small-mode row rulers. H\_orig \= H\_cur \+ crop\_top. Robust to left crops that corrupt standard-mode payloads.

* **Path C — Garbled payload detection:** If all col rulers report the same fraction (garbled by top crop shifting segment indices), the horizontal axis was not cropped. W\_orig \= W\_cur.

## **1.8  Survivability Profile**

| Transform | Outcome Class | Detection | W Recover | H Recover | Notes |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **JPEG Q95–Q30** | 1 — Benign | 100% | ✓ | ✓ | Zero bit errors; band mean drift \< 5 counts |
| **Left crop** | 3 (if targeted) | 100% | ✓ exact | ✓ exact | LS from col rulers; row payload intact |
| **Right crop** | 3 (if targeted) | 100% | ✓ exact | \= H\_cur | Row rulers intact; H\_orig unchanged |
| **Top crop** | 3 (if targeted) | 100% | \= W\_cur | ✓ exact | Path B: small-mode row displacement |
| **Bottom crop** | 3 (if targeted) | 100% | \= W\_cur | ✓ approx | Path B: row blind scan |
| **Both-axis crop** | 3 (if targeted) | 100% | limited | limited | Detection solid; dim recovery partial |
| **Horizontal stitch** | 3 (if targeted) | 100% | — | — | Inconsistent W\_orig across ruler sets |
| **PNG (lossless)** | 1 — Benign | 100% | ✓ | ✓ | Zero degradation |
| **Rotation (any)** | N/A | ✗ | — | — | Use Layer G; Layer H is axis-aligned only |
| **RAW/Lightroom** | Open item | TBD | TBD | TBD | Highest-priority open item; see §3.11 |

*Positions survive JPEG. Values do not. Density survives everything. The ruler is not a single pixel. It is a statistical property of a 16-pixel band across the full image height. Statistical properties of filled spatial regions survive any compression that preserves spatial structure.*

## **1.9  Integration**

### **Embedding Position in Pipeline**

Layer H should be applied after all other layers in the embedding pipeline. Layers G (Halo) and F (Payload) modify pixel values near sentinel positions. Applying Layer H before these layers risks ruler segments being overwritten by subsequent embedding. Applying it last ensures the ruler bands reflect the final pixel state.

### **Detection Pipeline Position**

Layer H runs independently in the detection pipeline. Its output — original dimensions and crop geometry — can inform Layer G’s halo detection: after recovering W\_orig and H\_orig, halo center positions can be re-evaluated in the original coordinate frame. This is useful for images that have been both cropped and contain halo markers from Layer G.

### **Inputs**

* A PIL RGB image (any dimensions, any content)

* timestamp\_hrs: hours since Unix epoch for sidecar linkage (optional)

* session\_hash: truncated hash for receipt association (optional)

### **Outputs**

* Marked PIL RGB image with all ruler bands embedded

* CropForensicReport: crop\_detected, stitch\_detected, W\_orig, H\_orig, crop\_left, crop\_top, evidence list

* Per-ruler payload: fraction, axis, dim\_orig, timestamp, session\_hash, bits\_read

## **1.10  API Reference**

Module: layer\_h\_ruler.py  |  License: BSD-2  |  Dependencies: numpy, PIL, scipy, sympy

| Function | Signature | Returns |
| :---- | :---- | :---- |
| **embed\_all\_rulers()** | image, timestamp\_hrs=None, session\_hash=0 | PIL Image, all rulers embedded |
| **embed\_ruler()** | image, cr, is\_col, bits, skip\_positions=None | PIL Image, single ruler |
| **detect\_all\_rulers()** | image | List\[RulerDetection\] at expected positions |
| **detect\_ruler()** | image, cr, is\_col | RulerDetection with decoded payload |
| **blind\_scan\_rulers()** | image, band\_col\_threshold=62, band\_row\_threshold=62 | List\[RulerDetection\] by scan |
| **analyze\_crop()** | image | CropForensicReport |
| **recover\_original\_dimensions()** | detections, W\_cur, H\_cur | dict: W\_orig, H\_orig, crop\_left, crop\_top |
| **pack\_standard()** | frac\_idx, axis, dim\_orig, ts=0, sh=0 | List\[int\] (51 bits) |
| **pack\_small()** | axis, position, dim\_orig | List\[int\] (28 bits) |
| **unpack()** | bits: List\[int\] | RulerPayload |
| **get\_ruler\_positions()** | W, H | (col\_rulers, row\_rulers) |

### **Quickstart**

from layer\_h\_ruler import embed\_all\_rulers, detect\_all\_rulers, analyze\_crop  
   
\# Embed  
marked \= embed\_all\_rulers(image, timestamp\_hrs=ts, session\_hash=receipt\_id)  
   
\# Detect — manifest mode  
rulers \= detect\_all\_rulers(marked)  
for r in rulers:  
    print(r.payload.dim\_orig, r.payload.fraction)  
   
\# Forensic analysis — blind mode, no manifest  
report \= analyze\_crop(suspect\_image)  
if report.crop\_detected:  
    print(f'Crop detected. W\_orig={report.original\_W\_estimate}')  
    for ev in report.evidence:  
        print(f'  {ev}')

## **1.11  Known Limitations and Open Items**

### **Confirmed Limitations**

* **Both-axis crop dimension recovery.** Simultaneous left and top crop corrupts payloads on both axes. Crop is detected; exact dimensions require the manifest or an iterative search over (crop\_left, crop\_top) pairs. The iterative search is O(N\_fracs²) and tractable but not yet implemented.

* **Extreme monochromatic content.** Images whose natural |R−G| distribution clusters near 198 may produce spurious detections above the band threshold. Threshold is calibrated against DIV2K; specialized image types (infrared, extreme-saturation) require threshold adjustment.

* **Rotation destroys axis alignment.** By design. Layer G covers rotation. The two layers are complementary.

### **Open Items**

* **RAW/Lightroom pipeline.** Highest-priority open item. If ruler bands survive RAW demosaicing and Lightroom export (RAW→PNG and RAW→JPEG), this layer extends forensic provenance to professional photography workflows. Test protocol: embed in first lossless output post-demosaic; verify band mean after each Lightroom export quality setting.

* **Both-axis iterative recovery.** Implement candidate search over (crop\_left, crop\_top) pairs by correlating blind-scan positions against all fraction assignments.

* **Stitch seam precision.** Currently detected but not precisely localized. Add seam-column reporting to analyze\_crop().

* **Scale to 500+ images.** Current validation: 100 DIV2K images. Extend to full 800-image training set.

* **Neural codec characterization.** HEIC, AVIF, WebP use non-DCT compression. Band-mean encoding is theoretically more robust than point encoding against these codecs, but survivability has not been measured.

## **Canonical Phrases**

*“Positions survive JPEG. Values do not. Density survives everything.”*

*“The ruler’s position is its testimony. The fraction is its alibi. Together they prove what the image was.”*

*“The adversary who crops the image shifts the ruler but cannot erase what the ruler encodes.”*

*“Can you strip it without the stripping being interpretable? That is the harder problem, and the one this system actually solves.”*

# **Appendix A — Layer H Validation Results**

All results from validation against the DIV2K training corpus. 100 images, 2K resolution professional photographs. Test environment: Windows 11, Python 3.12, PIL 10.x.

| Test | Result | N | Notes |
| :---- | :---- | :---- | :---- |
| **Roundtrip 1024×768 (8 rulers)** | 8/8 PASS | 8 | W and H decode exactly; ts and sh recovered |
| **Small mode 800×600 (6 rulers)** | 6/6 PASS | 6 | Absolute positions decode exactly |
| **JPEG Q95** | 8/8 PASS | 8 | Band mean 195.9; natural mean 15.1; gap 180.9 |
| **JPEG Q85** | 8/8 PASS | 8 | Band mean 195.5; gap 178.6 |
| **JPEG Q70** | 8/8 PASS | 8 | Band mean 195.6 |
| **JPEG Q60** | 8/8 PASS | 8 | Band mean 196.0 |
| **JPEG Q50** | 8/8 PASS | 8 | Band mean 197.9 |
| **JPEG Q40** | 8/8 PASS | 8 | Band mean 199.3; gap 190.4 |
| **JPEG Q30** | 8/8 PASS | 8 | Band mean 195.7; zero bit errors |
| **Left crop (200px)** | PASS | 100 | W\_orig \= 1024 exact via Path A |
| **Top crop (150px)** | PASS | 100 | H\_orig \= 768 exact via Path B; W\_orig \= W\_cur via Path C |
| **Right crop** | PASS | 100 | W\_orig exact; H\_orig \= H\_cur (fallback) |
| **Both-axis crop** | detect PASS dim PARTIAL | 100 | Crop confirmed; W/H recovery limited without manifest |
| **Clean — no false alarm** | PASS | 100 | crop\_detected \= False on all 100 images |
| **Stitch detection** | PASS | 50 pairs | Inconsistent W\_orig triggers stitch flag |

*Document version: 2.0  |  March 2026  |  Section 0 (System Model) \+ Layer H (Spatial Ruler) complete.*