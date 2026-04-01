**GRANITE**

**IMAGE PROVENANCE SYSTEM**

*Technical Reference  —  Layer Specification*

Jeremy Pickett  |  March 2026

*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*

Licensed BSD-2. Open research.

## **About This Document**

This reference documents the GRANITE image provenance system layer by layer. Each layer section uses a consistent structure:

* Purpose and role in the detection stack

* What the layer detects and proves

* What the layer cannot do (explicit constraints)

* Encoding surface — how data is embedded in the image

* Protocol constants with derivations

* Detection algorithm

* Survivability profile across transforms and attacks

* Integration: inputs consumed and outputs provided to the stack

* API reference

* Known limitations and open items

The document begins with a cross-layer competency matrix showing which attacks each layer handles independently versus cooperatively. Read this matrix first.

*This document covers Layer H (Spatial Ruler) in full. Additional layers will be added in subsequent editions using the same section structure.*

# **Cross-Layer Competency Matrix**

The table below maps each attack or image transform against the seven layers of the GRANITE stack. Cells show whether a layer handles the condition independently, cooperatively with peer layers, or not at all.

**Legend:**    ✓ Handles independently    ◑ Partial / cooperative    ✗ Cannot handle    — Not applicable

| Attack / Transform | A | BC | D | E | F | G | H |
| :---- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **JPEG Q85 survival** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **JPEG Q40 survival** | **✓** | **◑** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **JPEG Q30 survival** | **◑** | **✗** | **◑** | **◑** | **◑** | **◑** | **✓** |
| **Arbitrary rotation** | — | — | — | — | **◑** | **✓** | — |
| **Horizontal crop (left/right)** | — | — | — | — | — | — | **✓** |
| **Vertical crop (top/bottom)** | — | — | — | — | — | — | **✓** |
| **Both-axis crop** | — | — | — | — | — | — | **◑** |
| **Image stitch detection** | — | — | — | — | — | — | **✓** |
| **Dimension recovery** | — | — | — | — | — | — | **✓** |
| **Sentinel removal (VOID)** | — | — | **✓** | — | — | **✓** | — |
| **Format-level tampering** | **✓** | — | — | — | — | — | — |
| **Pixel-layer tampering** | — | — | **✓** | — | — | — | — |
| **Participation proof** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **Payload recovery** | — | — | — | — | **✓** | **◑** | **◑** |

Column headers A through H correspond to: A \= Container (DQT), BC \= Frequency (twin prime compound), D \= Spatial (KS variance), E \= Sentinel (spanning relational), F \= Payload (position-offset vote), G \= Halo (radial lensing), H \= Ruler (spatial reference frame).

*No single layer is complete. The stack is designed so that each layer's weaknesses are covered by a peer. Layer G handles rotation, which Layer F cannot. Layer H handles cropping, which all other layers ignore. Layer D provides corroborating State D evidence that Layers E and G use.*

# **Layer Integration Overview**

The following table describes the dependency structure of the stack. Layers are listed in signal-processing order, from the outermost container layer inward to the spatial forensics layer.

| Layer | Provides To Stack | Depends On |
| :---- | :---- | :---- |
| **A  Container** | Format tamper detection, M=31 sentinel anchor | None — operates on raw JPEG tables |
| **BC Frequency** | Twin prime gap markers, cascade-resilient compound signal | Layer A (floor constant, M=31 exclusion) |
| **D  Spatial** | KS variance anomaly signal, corroborating State D | Layer BC (pixel field to measure) |
| **E  Sentinel** | State B/C/D classification, spanning relational proof | Layers A–D (composite signal) |
| **F  Payload** | 24-bit session payload recovery at Q40 | Layer E (sentinel positions for offset encoding) |
| **G  Halo** | Rotation-resilient detection, VOID state after removal | Layer F (sentinel centers as halo origins) |
| **H  Ruler** | Crop/stitch forensics, original dimension recovery | None — operates independently on image geometry |

Layer H is architecturally isolated. It consumes no outputs from other layers and produces no inputs to them. It operates on image geometry and pixel-band statistics, not on the sentinel or halo structures. This independence means it can be applied to an image even if all other layers are absent, and it cannot be confused by signals from other layers. The orthogonal channel design (|R-G| for vertical rulers, |G-B| for horizontal rulers) prevents pixel-level cross-contamination at band intersections.

# **Layer H — Spatial Ruler**

**Role:** *Crop and stitch forensics. Embeds a spatial reference frame into the image as column and row bands, allowing a detector to recover the original image dimensions and detect geometric manipulation even without a manifest.*

## **3.1  Purpose and Role in the Stack**

All other GRANITE layers are designed to survive lossy compression, format conversion, and pixel manipulation. They do not address spatial transforms: a crop that removes 20% of an image from the left, a stitch that joins two images side by side, or a resize that changes the image dimensions. Layer H is the spatial layer.

The architectural motivation is this: an adversary who crops a provenance-marked image does not defeat the other layers — the surviving pixels still carry their signals — but they do destroy spatial relationships. The image no longer represents the same scene extent it was marked as. Layer H detects this and recovers the original geometry.

Layer H embeds ruler bands at deterministic fractions of the image dimensions. Each ruler band is a 16-pixel-wide column (or row) whose pixels have been adjusted to have a specific channel difference value. The ruler's position, combined with the fraction encoded in its payload, allows the detector to determine whether the image has been cropped and — if so — how much was removed and from which edge.

## **3.2  What This Layer Detects and Proves**

### **Detects**

* Horizontal crop: left edge removed, right edge removed, or both

* Vertical crop: top edge removed, bottom edge removed, or both

* Both-axis crop: any rectangular crop that removes edges on two or more sides

* Image stitch: two separately-marked images joined along a vertical or horizontal seam

* Dimension mismatch: image dimensions differ from those encoded in ruler payload

### **Proves**

* 

* 

* 

* 

## **3.3  What This Layer Cannot Do**

*Every layer has explicit constraints. This section is not a deficiency list — it is the boundary definition that tells the reader which peer layer covers what this one does not.*

* 

* 

* 

* 

* 

* 

## **3.4  Encoding Surface**

### **Band Structure**

Each ruler is a BAND\_WIDTH \= 16 pixel-wide column (vertical ruler) or row (horizontal ruler). Every pixel in the band has its channel difference adjusted to RULER\_TARGET \= 198 (= 197+1, 197 prime) for marked segments. Unmarked segments are left at their natural values.

A 16-pixel band width was chosen specifically because it spans exactly two 8-pixel JPEG DCT blocks. When an entire 8-pixel block column has elevated chroma, JPEG preserves it — the quantizer averages within the block, but cannot average away a signal that fills the entire block. Single-pixel embeddings are destroyed by JPEG. Full-column-band embeddings survive at any tested quality level.

### **Segment Encoding**

The band column (or row) is divided into SEGMENT\_HEIGHT \= 32 pixel segments. Each segment encodes one payload bit:

* 

* 

Detection reads the mean |R-G| (or |G-B|) per segment across the band width. If the mean exceeds SEGMENT\_THRESHOLD \= 80, the segment is classified as bit \= 1\. The gap between natural content mean (\~15 counts) and embedded mean (\~195 counts) provides approximately 115 counts of margin, far exceeding the JPEG-induced degradation of 2-5 counts at Q85.

### **Orthogonal Channel Design**

Vertical ruler bands (columns) embed |R-G| \= 198\. Horizontal ruler bands (rows) embed |G-B| \= 198\. These use different channel pairs from the same target value.

The orthogonal design solves the intersection problem: wherever a vertical and horizontal band cross (a 16x16 pixel intersection zone), the horizontal ruler's embedding would overwrite the G channel that the vertical ruler set, corrupting the vertical ruler's signal. By assigning each axis a different channel pair, the detector reads |R-G| for vertical rulers and |G-B| for horizontal rulers, and each is immune to modifications made by the other.

Additionally, horizontal rulers skip the column positions occupied by vertical bands during embedding, preventing the horizontal ruler's G-channel adjustment from corrupting the vertical ruler's R-G relationship.

### **Payload Structure**

The payload is packed MSB-first in priority order. Critical identification data occupies the first bits, ensuring that even a heavily cropped image with only a few surviving segments can identify which ruler it is.

STANDARD MODE (dimension \>= 1024):                           51 bits  
  bit  0      : mode flag (0 \= standard)  
  bits 1-3    : fraction index  (3 bits)  e.g. 001 \= 1/4  
  bit  4      : axis (0 \= vertical/column, 1 \= horizontal/row)  
  bits 5-17   : dim\_orig (13 bits)  W for col rulers, H for row rulers  
  bits 18-34  : timestamp\_hours (17 bits, hour precision, 50-year range)  
  bits 35-50  : session\_hash truncated (16 bits)  
   
SMALL MODE (dimension \< 1024):                               28 bits  
  bit  0      : mode flag (1 \= small)  
  bit  1      : axis  
  bits 2-14   : absolute pixel position (13 bits)  
  bits 15-27  : dim\_orig (13 bits)

The mode flag in bit 0 means any surviving ruler fragment can identify the decoding path. Four surviving segments (4 bits) yield mode \+ partial fraction — enough to prove the image carries a ruler even if the full payload is lost.

## **3.5  Ruler Geometry**

| Image Width / Height | Mode | Ruler Count | Positions | Payload Bits Available |
| :---- | :---- | :---- | :---- | :---- |
| **\< 1024 px (small)** | SMALL | 3 | dim × \[1/4, 1/2, 3/4\] | 16–23  (fraction+pos+dim) |
| **≥ 1024 px (standard)** | STANDARD | 5 | dim × \[1/8, 1/4, 1/2, 3/4, 7/8\] | 32–64  (full payload) |
| **4096 px (very large)** | STANDARD | 5 | same fractions | 105   (full \+ redundancy) |

The 5-ruler geometry at width/height ≥ 1024 provides better stitch localization and more redundancy for crop recovery. With 4 surviving rulers after a 10% crop, the least-squares solver produces exact dimension recovery. With fewer than 2 rulers in either axis, dimension recovery falls back to current dimensions.

Ruler positions are symmetric about the center (e.g., 1/4 and 3/4, 1/8 and 7/8). This symmetry means a right-edge crop and a left-edge crop are equally detectable — the displaced ruler is always close to an expected position for the other edge.

## **3.6  Protocol Constants**

| Constant | Value | Derivation / Rationale |
| :---- | :---- | :---- |
| **RULER\_TARGET** | 198 | \= 197+1  (197 prime, above FLOOR=43). Used for |R-G| in vertical rulers |
| **RULER\_H\_TARGET** | 198 | \= 197+1  same prime, but |G-B| channel — orthogonal to vertical rulers |
| **BAND\_WIDTH** | 16 px | Two 8-pixel JPEG chroma blocks wide — fills entire DCT block per column |
| **SEGMENT\_HEIGHT** | 32 px | One payload bit per 32-pixel segment; balances capacity vs spatial resolution |
| **SEGMENT\_THRESHOLD** | 80 counts | Midpoint between natural |R-G| mean (\~15) and embedded mean (\~195) |
| **SMALL\_THRESH** | 1024 px | Below this dimension: absolute position encoding (small mode) |
| **FLOOR** | 43 | GRANITE protocol minimum prime (sentinel entry constant M=31 \+ margin) |

The separation between RULER\_TARGET \= 198 and the Layer G targets (INNER\_TARGET \= 168, OUTER\_TARGET \= 140) is 30 counts (inner) and 58 counts (outer). This is sufficient to prevent crosstalk under JPEG at any tested quality level, since JPEG-induced target drift is typically ±5–9 counts.

## **3.7  Detection Algorithm**

### **Manifest-Mode Detection**

When the embedding manifest is available, ruler positions are known. The detector scans each expected column and row position, reads segment means, and decodes the payload. This is fast (O(N\_rulers × H × BAND\_WIDTH × N\_segments)) and produces exact results.

1\. Compute expected ruler positions from current image dimensions.  
2\. For each expected column c:  
   a. For each 32px segment s:  
      mean\_rg \= mean(|R-G|) over pixels rows\[32s..32s+32\], cols\[c-8..c+8\]  
      bit\[s\] \= 1 if mean\_rg \>= 80, else 0  
   b. payload \= unpack(bits)  
   c. Report: position, fraction, dim\_orig, timestamp, session\_hash  
3\. Repeat for rows using |G-B| channel.  
4\. Compare decoded dim\_orig to current dimensions.  
   If mismatch: crop detected.

### **Blind-Mode Detection (Forensic)**

When no manifest is available — typical in forensic analysis of potentially-cropped images — the detector scans every column for elevated band means.

1\. Compute per-column mean |R-G| across full image height.  
2\. Apply 16px uniform filter to find band centers.  
3\. Non-maximum suppression within BAND\_WIDTH to get candidates.  
4\. At each candidate column: read segment means, decode payload.  
5\. Classify as genuine if band\_mean \>= 62 AND dim\_orig \> 0\.  
6\. Repeat for rows using |G-B|.  
7\. Run recover\_original\_dimensions() on all genuine detections.

### **Dimension Recovery (Least Squares)**

For each axis, surviving rulers give the linear system:

new\_pos\_i \= W\_orig \* frac\_i \- crop\_offset  
   
Matrix form:  \[frac\_i, \-1\] \* \[W\_orig, crop\_offset\]^T \= new\_pos\_i  
   
With 2+ rulers: np.linalg.lstsq(A, b) gives exact solution.  
With 4+ rulers: overdetermined system, least squares minimizes residual.  
   
Cross-check: dim\_orig in payload must match W\_orig estimate.  
Confidence \+= 1 for each matching payload confirmation.

Three recovery paths handle the cases where least squares cannot be applied (e.g., top crop corrupts column ruler payload segments):

* 

* 

* 

## **3.8  Survivability Profile**

| Transform | Detection | W Recover | H Recover | Notes |
| :---- | :---- | :---- | :---- | :---- |
| **JPEG Q95–Q30** | 100% | ✓ | ✓ | Zero bit errors across all tested quality levels |
| **Left crop** | ✓ | ✓ exact | ✓ exact | LS from 4+ col rulers; row rulers intact |
| **Right crop** | ✓ | ✓ exact | \=H\_cur | Row rulers intact; H\_orig fallback \= H\_cur |
| **Top crop** | ✓ | \=W\_cur | ✓ exact | Col rulers present; small-mode row displacement |
| **Bottom crop** | ✓ | \=W\_cur | ✓ approx | Col rulers present; row blind scan |
| **Both-axis crop** | ✓ | limited | limited | Detection solid; dimension recovery partial |
| **Horizontal stitch** | ✓ | — | — | Inconsistent W\_orig across ruler sets |
| **PNG (lossless)** | ✓ | ✓ | ✓ | Zero degradation |
| **Rotation (any)** | ✗ | — | — | Use Layer G for rotation forensics |
| **Format conversion** | ◑ | ◑ | ◑ | Depends on codec; RAW pipeline: TBD |

The JPEG survival result deserves emphasis: zero bit errors at Q30 through Q95. This is because the 16-pixel band fills the entire DCT chroma block, so JPEG quantization preserves the mean even as it smears individual pixel values. The band mean after Q85 compression measures 195.5 counts against a target of 198 — a drift of 2.5 counts, well within the detection threshold margin of 80 counts.

*Positions survive JPEG. Values do not. Density survives everything. This principle, first articulated for Layer G, applies equally here: the ruler is not a single pixel but a statistical property of a 16-pixel band, and statistical properties survive any compression that preserves spatial structure.*

## **3.9  Integration: Inputs and Outputs**

### **Inputs Consumed**

* A PIL RGB image (any dimensions, any content)

* 

* 

Layer H requires no information from other GRANITE layers. It can be applied independently to any image.

### **Outputs Provided**

* Marked PIL RGB image with all ruler bands embedded

* 

* Per-ruler decoded payload: fraction, axis, dim\_orig, timestamp, session\_hash, bits\_read

### **Interaction with Other Layers**

Layer H is applied after all other layers in the embedding pipeline, since it operates on final pixel values. Applying it before Layer G would cause the Halo embedding to modify ruler band pixels and potentially corrupt ruler segments.

In the detection pipeline, Layer H is run independently of other layers. Its output (original dimensions) can be used to validate Layer G halo positions: after recovering W\_orig and H\_orig from the ruler, Layer G can re-evaluate halo center positions against the original coordinate frame.

## **3.10  API Reference**

Module: layer\_h\_ruler.py  |  License: BSD-2  |  Dependencies: numpy, PIL, scipy, sympy

| Function | Signature (simplified) | Returns |
| :---- | :---- | :---- |
| **embed\_all\_rulers()** | image, timestamp\_hrs=None, session\_hash=0 | PIL Image with all rulers embedded |
| **embed\_ruler()** | image, cr, is\_col, bits, skip\_positions=None | PIL Image with single ruler embedded |
| **detect\_all\_rulers()** | image | List\[RulerDetection\] at expected positions |
| **detect\_ruler()** | image, cr, is\_col | RulerDetection with decoded payload |
| **blind\_scan\_rulers()** | image, band\_col\_threshold=62, band\_row\_threshold=62 | List\[RulerDetection\] found by scan |
| **analyze\_crop()** | image | CropForensicReport |
| **recover\_original\_dimensions()** | detections, W\_cur, H\_cur | dict: W\_orig, H\_orig, crop\_left, crop\_top |
| **pack\_standard()** | frac\_idx, axis, dim\_orig, ts=0, sh=0 | List\[int\] (51-bit payload) |
| **pack\_small()** | axis, position, dim\_orig | List\[int\] (28-bit payload) |
| **unpack()** | bits: List\[int\] | RulerPayload |
| **get\_ruler\_positions()** | W, H | (col\_rulers, row\_rulers) as (pos, fi, mode) |

All functions that return PIL Images return new copies — the input image is never modified in place. Detection functions that take a PIL Image call np.array() internally; no preprocessing is required.

### **Quickstart**

from layer\_h\_ruler import embed\_all\_rulers, detect\_all\_rulers, analyze\_crop  
   
\# Embed — production use  
marked \= embed\_all\_rulers(image, timestamp\_hrs=ts, session\_hash=receipt\_id)  
   
\# Detect — manifest mode (fast)  
rulers \= detect\_all\_rulers(marked)  
for r in rulers:  
    print(r.payload.dim\_orig, r.payload.fraction)  
   
\# Forensic analysis — no manifest needed  
report \= analyze\_crop(suspect\_image)  
if report.crop\_detected:  
    print(f'W\_orig={report.original\_W\_estimate}  crop\_left={report.evidence}')

## **3.11  Known Limitations and Open Items**

### **Confirmed Limitations**

* 

* 

* 

### **Open Items (Future Work)**

* 

* 

* 

* 

* 

## **Canonical Phrases**

*"Positions survive JPEG. Values do not. Density survives everything."*

*"The ruler's position is its testimony. The fraction is its alibi. Together they prove what the image was."*

*"A single surviving rung names the ruler. Four surviving rungs recover the original width to within 8 pixels."*

*"The adversary who crops the image shifts the ruler but cannot erase what the ruler remembers."*

# **Appendix A — Validation Results Summary**

All results from Layer H validation against the DIV2K training corpus (100 images, 2K resolution photographs). Test environment: Windows 11, Python 3.12, PIL 10.x.

| Test | Result | N Tested | Notes |
| :---- | :---- | :---- | :---- |
| **Roundtrip 1024x768** | 8/8 PASS | 8 rulers | W and H decode exactly |
| **Small mode 800x600** | 6/6 PASS | 6 rulers | Absolute positions decode exactly |
| **JPEG Q95** | 8/8 PASS | 8 rulers | Zero bit errors |
| **JPEG Q85** | 8/8 PASS | 8 rulers | Band mean: 195.5 vs target 198 |
| **JPEG Q70** | 8/8 PASS | 8 rulers |  |
| **JPEG Q60** | 8/8 PASS | 8 rulers |  |
| **JPEG Q50** | 8/8 PASS | 8 rulers |  |
| **JPEG Q40** | 8/8 PASS | 8 rulers | Band mean: 199.3 |
| **JPEG Q30** | 8/8 PASS | 8 rulers | Band mean: 195.7 |
| **Left crop detection** | PASS | 100 images | W\_orig \= 1024 recovered exactly |
| **Top crop detection** | PASS | 100 images | H\_orig \= 768 via Path B |
| **Right crop detection** | PASS | 100 images | W\_orig exact, H\_orig \= H\_cur |
| **Both-axis crop** | detect PASS | 100 images | Dimension recovery: limited |
| **Clean no false alarm** | PASS | 100 images | crop\_detected \= False |
| **Stitch detection** | PASS | 50 pairs | Inconsistent W\_orig triggers flag |

*Document version: 1.0  |  March 2026  |  Layer H specification complete.*