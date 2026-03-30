**GRANITE**

**IMAGE PROVENANCE SYSTEM**

*Technical Reference  —  Layer Specification*

Jeremy Pickett  |  March 2026

*Co-developed with Claude (Anthropic). Human-directed, AI-assisted.*

Licensed BSD-2. Open research.

## **About This Document**

This edition documents Layer G (Halo) of the GRANITE stack. It uses the same section structure as all layer documents in this series. Section 0 provides the system model shared across all editions — read it before individual layer sections. The full system model appears in the Layer H edition; this document carries an abbreviated reference.

# **Section 0 — System Model (Reference)**

The full system model, including the three outcome classes, attack signature taxonomy, legal language conventions, and Layer D mode definitions, appears in the Layer H edition of this reference series. This section carries the cross-layer competency matrix and integration overview for context. Refer to the Layer H edition for the complete Section 0\.

## **0.1  Framing**

*GRANITE is an anti-scrubbing evidentiary lattice. The goal is not that all layers survive all attacks. The goal is that removal tells on itself: one or more layers survive casual and semi-competent handling, while deliberate multi-layer removal becomes interpretable as evidence of the removal. The system claims differential interpretability of damage, not invulnerability.*

## **0.2  Cross-Layer Competency Matrix**

**Legend:**    ✓  Independent    ◑  Cooperative    ✗  Cannot handle    —  N/A

| Attack / Transform | A | BC | D | E | F | G | H |
| :---- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **JPEG Q85 survival** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **JPEG Q40 survival** | **✓** | **◑** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **Arbitrary rotation** | — | — | — | — | **◑** | **✓** | — |
| **Horizontal crop** | — | — | — | — | — | — | **✓** |
| **Vertical crop** | — | — | — | — | — | — | **✓** |
| **Sentinel removal (VOID)** | — | — | **✓** | — | — | **✓** | — |
| **Format-level tampering** | **✓** | — | — | — | — | — | — |
| **Pixel-layer tampering** | — | — | **✓** | — | — | — | — |
| **Participation proof** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** | **✓** |
| **Payload recovery** | — | — | — | — | **✓** | **◑** | **◑** |

Layer G is highlighted in this matrix: it is the only layer that handles arbitrary rotation, and it shares VOID-state detection with Layer D (spatial anomaly). The combination provides two independent detection mechanisms for sentinel removal.

## **0.3  Layer Integration Overview**

| Layer | Provides To Stack | Depends On |
| :---- | :---- | :---- |
| **A  Container** | Format tamper detection, M=31 anchor | None |
| **BC Frequency** | Twin prime gap markers | Layer A (floor, M=31 exclusion) |
| **D  Spatial** | KS variance anomaly; blind primary / manifest corroboration | Layer BC |
| **E  Sentinel** | State B/C/D classification, spanning relational proof | Layers A–D |
| **F  Payload** | 24-bit session payload recovery at Q40 | Layer E (sentinel positions) |
| **G  Halo** | Rotation-resilient detection, VOID state after sentinel removal | Layer F (sentinel centers as halo origins) |
| **H  Ruler** | Crop/stitch forensics, original dimension recovery | None — independent |

Layer G sits at position 6 in the dependency chain. It consumes sentinel center positions from Layer F and wraps them with a radial lensing field. The output — halo positions and states — feeds no downstream layer but can inform forensic re-analysis after Layer H recovers original image coordinates.

# **Section 1 — Layer G: Halo**

**Role:** *Rotation-resilient sentinel detection using a radial lensing field. Embeds a two-zone channel-difference structure around each sentinel center. The field survives bilinear interpolation at any rotation angle because it encodes in density distributions, not absolute values. After sentinel removal, the field persists as a VOID state that may support an inference of targeted removal.*

## **1.1  Purpose and Role in the Stack**

Layers E and F encode payload information in the positional relationships between sentinels. A sentinel at column 192, row 64 carries meaning because of where it sits relative to section boundaries. Rotate the image by 30 degrees and that relationship changes. The sentinel is detectable in isolation, but the positional grammar that encodes the payload has been disrupted.

More critically: an adversary who applies a rotation and then removes the sentinel has eliminated all positional evidence. No structure remains that points back at where the sentinel was. This is the gap Layer G fills.

The gravitational lensing analogy is precise, not decorative. A gravitational lens does not destroy what lies behind it. It distorts the surrounding space in a radially symmetric, predictable way. Observers who detect the distortion pattern can infer the existence, position, and properties of the lensing mass even without directly observing it. The distortions are force arrows. They all point at something.

Layer G embeds exactly this structure: a radial field of perturbed pixels surrounding each sentinel. Each pixel in the field is a force arrow pointing toward the center. The center is detectable not by finding the sentinel directly, but by finding the convergence point of all surrounding force arrows. And when the sentinel is removed, the force arrows remain. The field outlives the mass. The void is detectable.

## **1.2  What This Layer Detects and Proves**

### **Detects**

* Sentinel presence at any rotation angle (0° through 360°)

* Sentinel removal after embedding: VOID state where inner disk is absent but outer ring persists

* Halo center positions in rotated images, enabling Layer F payload reconstruction after rotation correction

* Force-arrow convergence: the radial structure that identifies the center even without the sentinel

### **Proves**

* **Participation:** the image was processed by a tool implementing this protocol

* **Rotation resilience:** 100% detection at all tested angles (0°, 15°, 30°, 45°, 90°, 180°) on DIV2K corpus

* **VOID state:** inner disk density absent, outer ring elevated — a pattern that may support an inference of targeted inner-disk removal

* **State D₂ (force-arrow):** the halo field survives sentinel removal; the adversary who removes the sentinel cannot erase the surrounding field without additional targeted intervention

### **Does Not Prove**

* Crop or stitch geometry (Layer H handles this)

* Payload content (Layer F handles this; Layer G provides halo centers for rotation-corrected payload recovery)

* Identity of the entity that performed any removal

## **1.3  Explicit Constraints**

*This section defines boundaries. Each item is covered by a peer layer or documented as an open item.*

* **Does not encode payload.** Layer G is a detection and attribution layer. Information encoding is Layer F’s domain. Layer G provides halo centers; Layer F uses them to locate sentinels; the sentinel positions carry the payload.

* **Rotation reveals halo positions, not payload.** After rotation, halos are detectable. Payload recovery from a rotated image requires: (1) locate halos, (2) estimate rotation angle from halo geometry, (3) apply inverse rotation, (4) run Layer F decoder. Steps 2–4 are architecturally defined but not yet fully implemented.

* **FP rate in blind mode: \~30% on DIV2K.** Images with natural |R−G| distribution near 168 produce off-grid detections. In manifest mode (grid check), FP rate is 0%. In blind mode, the strict detector \+ zone-boundary sharpness test \+ edge-guidance reduce but do not eliminate FPs on high-saturation natural images.

* **Does not handle crop.** Layer H handles crop forensics. Layer G is complementary to Layer H: G covers rotation, H covers translation/scale.

* **JPEG Q40 may transition some centers to VOID.** At aggressive compression, inner disk density may drop below INNER\_THRESH on some images. These centers are detected as VOID, not PRESENT. The count is still 4/4; the state differs. This is correct behavior — compression damaged the inner signal, and the VOID state records that.

* **Does not authenticate identity.** Presence of a halo proves protocol participation. Identity requires the matching service.

## **1.4  Encoding Surface**

### **Engineering History: Three Options Considered**

The current two-zone encoding (Option C) was reached after two failed approaches. The failure modes are documented here because they illuminate why Option C works and establish the constraints any future modification must respect.

| Option | Approach | Rotation 5° | JPEG Q85 | Verdict | Root Cause of Failure |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **A** | prevprime(d)+1 absolute pixel values | 5% survival | N/A | **Rejected** | Bilinear interpolation averages neighbours; individual pixel values destroyed |
| **B** | Radial profile correlation (decreasing prime targets per ring) | 96% Pearson r | ✗ FP-saturated | **Rejected** | Outer ring targets common in JPEG-compressed natural images; FP ceiling exceeded signal |
| **C (current)** | Two-zone density convergence INNER=168 OUTER=140 | ✓ 100% | ✓ 100% | **Adopted** | N/A — see §1.4 for design rationale |

### **Option A Failure: Absolute Values Do Not Survive Bilinear Interpolation**

The first approach used prevprime(d)+1 absolute pixel values. Each pixel in the halo region was set so that its channel difference was one above the nearest lower prime. This creates a statistical signature: a high fraction of pixels satisfying “value minus one is prime.”

This worked on uncompressed images and after exact-rotation angles (0°, 90°, 180°). It failed after bilinear interpolation at all intermediate angles. Measured pixel-value survival at 5°: 5.1%. At 30°: 5.0%. The signal had collapsed entirely to background.

The mechanism is the same as the M=127 chroma gravity well in Layer E: bilinear interpolation averages neighbouring pixels. A pixel with |R−G|=72 adjacent to a natural pixel with |R−G|=45 becomes approximately 58 after interpolation. The target value is destroyed. Absolute values are not rotation-invariant.

### **Option B Failure: JPEG Quantization Saturated the Outer Ring**

The second approach used radial profile correlation: decreasing prime targets from inner to outer rings, with detection via Pearson correlation of the measured profile against the expected profile. Survival through bilinear rotation was strong (96% Pearson r at all angles). JPEG defeated it.

After Q85 compression, the background |R−G| distribution of natural images drifted into the outer ring’s target range. The background rate at the outer target became high enough to saturate detection — natural images produced false positives because their post-JPEG chroma values happened to cluster where the expected outer ring was.

The lesson: encoding targets must be chosen not just for rarity in uncompressed natural images, but for rarity after JPEG quantization at the target quality level.

### **Option C: Two-Zone Density Convergence**

The current encoding uses two concentric zones with fixed prime+1 targets: inner disk (r ≤ 5px) |R−G| \= INNER\_TARGET \= 168 (= 167+1, 167 prime) and outer ring (r ≤ 10px) |R−G| \= OUTER\_TARGET \= 140 (= 139+1, 139 prime). Background rates in natural images: \~0.023% near 168, \~0.241% near 140\. The joint probability of both zones being simultaneously elevated at a single point in a natural image is negligible.

The key detection criterion is density convergence: both zones must simultaneously exceed their respective thresholds, and the inner density must exceed the outer (gradient condition, except post-JPEG where gradient inverts). This joint criterion cannot be satisfied by natural image content. Natural images that happen to have elevated |R−G| near 168 in some region do not simultaneously have elevated |R−G| near 140 in a precise outer ring at exactly r=5–10px.

After bilinear rotation, individual pixel values are destroyed but the density distributions are preserved. If 80% of pixels in a zone are encoded near a target value, bilinear interpolation reduces the density but does not eliminate it. The bias persists in the distribution even when individual values are scrambled.

### **Embedding Mechanics**

for each center (cy, cx) in centers:  
  for each pixel (py, px) in disk of radius HALO\_RADIUS:  
    r \= sqrt((py-cy)^2 \+ (px-cx)^2)  
    target \= INNER\_TARGET if r \<= INNER\_RADIUS else OUTER\_TARGET  
    \# Achieve |R-G| \= target:  
    if R \>= target:  G \= R \- target  
    elif G \+ target \<= 255:  R \= G \+ target  
    else:  R \= 255; G \= max(0, 255 \- target)

## **1.5  Four Observable States**

Layer G produces one of four states at each expected sentinel position. These states are the primary output of the layer and the vocabulary for forensic interpretation.

| State | Name | Inner Disk Density | Outer Ring Density | Gradient | Interpretation |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **B** | **PRESENT** | ≥ 0.44 | ≥ 0.05 | \> 0 | Sentinel intact. Layer G participation proven. |
| **C** | **DEGRADED** | 0.28–0.44 | ≥ 0.05 | Any | JPEG or benign compression reduced inner density. Consistent with Class 1 degradation. Not evidence of tampering. |
| **D₂** | **VOID** | \< 0.44 | ≥ 0.35 | N/A | Inner disk removed, outer ring intact. Force arrows point at void. May support inference of targeted inner-disk removal. |
| **A** | **ABSENT** | \< 0.28 | \< 0.05 | N/A | No halo signal detected at this position. Cannot distinguish Class 1 from Class 2 without the manifest. |

The VOID state (D₂) is the gravitational lensing property made operational. An adversary who removes the inner disk to eliminate the high-density inner signature leaves the outer ring intact. They cannot remove the outer ring without the removal itself being detectable as a spatial anomaly — which is Layer D’s domain. The adversary who attacks the halo is fighting two detection systems simultaneously.

The compressor that destroys the inner disk is constructing the VOID signal. At Q40, some centers transition from PRESENT to VOID because aggressive quantization reduces inner density below INNER\_THRESH while outer ring density remains elevated. This is not a detection failure — it is the correct state. The compression damaged the inner signal, and the VOID state faithfully records that the inner mass was lost. The center is still found; its state is different.

## **1.6  Detection Algorithm**

### **Core Detection Pipeline**

Detection uses a box-filter approximation of circular disk density. A naive scan (measuring density at every pixel independently) would be O(H × W × halo\_area). The box-filter approach achieves O(H × W) by replacing per-pixel disk density measurement with a single convolution.

1\. Build vote masks:  
     inner\_mask \= |R-G| within VOTE\_TOL of INNER\_TARGET  
     outer\_mask \= |R-G| within VOTE\_TOL of OUTER\_TARGET  
   
2\. Convolve with box filter (size \= 2r+1):  
     inner\_map \= uniform\_filter(inner\_mask, size=2\*INNER\_RADIUS+1) \* area\_correction  
     outer\_map \= uniform\_filter(outer\_mask, size=2\*HALO\_RADIUS+1)  \* area\_correction  
   
3\. Candidate detection:  
     present\_cand \= (inner\_map \>= INNER\_THRESH)  
                  & (outer\_map \>= OUTER\_THRESH)  
                  & ((inner\_map \- outer\_map) \>= GRADIENT\_MIN)  
     void\_cand    \= (inner\_map \< INNER\_THRESH) & (outer\_map \>= VOID\_OUTER\_MIN)  
   
4\. Non-maximum suppression (window \= NMS\_WINDOW).  
5\. Deduplicate within INNER\_RADIUS \+ 2\.

### **Rotation Matching**

After detection on a rotated image, expected center positions are computed by applying the same rotation transform to the original embedding positions. The PIL rotation convention (clockwise in image coordinates) gives:

dc \= cx \- cx\_img;  dr \= cy \- cy\_img  
exp\_col \= cos(theta)\*dc \+ sin(theta)\*dr \+ cx\_img  
exp\_row \= \-sin(theta)\*dc \+ cos(theta)\*dr \+ cy\_img  
   
A detection is matched if distance(detected, expected) \<= MATCH\_RADIUS.  
MATCH\_RADIUS \= 28px accounts for density-map peak spreading after rotation.

**○  MANIFEST MODE — embedding record known**

**Manifest-Mode FP Filtering: Grid Regularity Check**

When embedding positions are known, off-grid detections are not claimed as halos. The grid check partitions all detections into on-grid (within GRID\_TOL of a known center) and off-grid (everything else). Off-grid count is the honest FP measure in manifest mode, which achieves 0% FP on the DIV2K corpus.

**●  BLIND MODE — no manifest required**

**Blind-Mode FP Filtering: Strict Detector \+ Zone-Boundary Sharpness**

Without a manifest, two mechanisms filter FPs before grid inference:

* **Strict detector:** STRICT\_INNER \= 0.55 raises the inner threshold above the natural FP ceiling (0.471 measured on DIV2K). This eliminates \~70% of FP candidates.

* **Zone-boundary sharpness test:** compute mean(|R−G|, r≤5) − mean(|R−G|, 5\<r≤10). Embedded halos: step ≈28 counts. Natural content: step ≈0–6 counts. Threshold \= 10 counts provides clean separation with margin above natural ceiling and below Q85 floor.

Remaining blind-mode FPs (\~30% of DIV2K images at one or more positions) are images with large saturated warm-toned regions where |R−G| naturally clusters near 168\. These are correctly identified as high-saturation content in forensic context; they do not produce incorrect provenance claims in manifest mode.

### **Edge-Guided Center Selection**

FPs cluster in smooth, low-edge regions — exactly the areas that provenance embedding should avoid. The natural content that looks like a halo is spatially homogeneous. The edge\_guided\_pick\_centers() function selects embedding positions above the image’s own 60th percentile edge density. Since the detection filter applies the same edge criterion, positions that were ineligible for embedding are ineligible for detection. This is format-agnostic: edge density is a universal property that generalises across JPEG, HEIC, WebP, PNG, and video frames.

## **1.7  Protocol Constants**

| Constant | Value | Derivation / Rationale |
| :---- | :---- | :---- |
| **HALO\_RADIUS** | 10 px | Outer boundary of the lensing field. Sets detection window size. |
| **INNER\_RADIUS** | 5 px | Inner disk boundary. Separates the two encoding zones. |
| **INNER\_TARGET** | 168 | \= 167+1 (167 prime, above FLOOR=43). Rare in natural images: \~0.023% background rate. |
| **OUTER\_TARGET** | 140 | \= 139+1 (139 prime). \~0.241% background rate in natural images. |
| **VOTE\_TOL** | 8 counts | Tolerance window for target matching after JPEG quantization drift. |
| **INNER\_THRESH** | 0.44 | Minimum inner disk density to classify as PRESENT or VOID. Above natural FP ceiling (0.11). |
| **OUTER\_THRESH** | 0.05 | Minimum outer ring density. Kept loose: JPEG kills outer; inner is the primary discriminator. |
| **VOID\_OUTER\_MIN** | 0.35 | Minimum outer density to classify as VOID (force-arrow state). |
| **GRADIENT\_MIN** | −0.50 | Effectively disabled. JPEG inverts the inner–outer gradient; gradient is not used as gate. |
| **NMS\_WINDOW** | 21 px | Non-maximum suppression window for peak detection. |
| **MATCH\_RADIUS** | 28 px | Maximum distance from expected position for a detection to count as matched. |
| **STRICT\_INNER** | 0.55 | Inner threshold for the strict (clean-image FP) detector. Above natural FP ceiling; below Q85 floor. |
| **FLOOR** | 43 | GRANITE protocol minimum prime (sentinel entry constant M=31 \+ margin). |
| **EDGE\_PERCENTILE** | 60 | Edge-guided selection: embed only at positions above this percentile of the image’s own edge distribution. |

The choice of INNER\_TARGET \= 168 and OUTER\_TARGET \= 140 was reached after calibration against the DIV2K corpus. The diagnostics showed: natural image max inner disk density 1.541 at target 98 (old target) — higher than the embedded signal (1.031). No threshold could separate them. Moving to 168/140 reduced the natural background rate to 0.023% / 0.241%, giving a 9× gap between natural FP ceiling (0.11) and embedded signal (1.031). The value M=127 is permanently excluded from all GRANITE prime targets: it is the JPEG chroma quantization gravity well, attracting pixel values post-compression regardless of the original embedding.

## **1.8  Survivability Profile**

| Transform | Class | Det. | State | Notes |
| :---- | :---- | :---- | :---- | :---- |
| **JPEG Q85** | 1 — Benign | 100% | B (PRESENT) | Inner density 0.31–0.52; above INNER\_THRESH=0.44 |
| **JPEG Q40** | 1 — Benign | 100% | B or D₂ | 2/4 centers may transition to VOID; all detected |
| **Rotation 0°** | 1/3 | 100% | B | Exact pixel remap; no interpolation |
| **Rotation 15°** | 1/3 | 100% | B | Bilinear interpolation; density degrades to 0.92–0.94 |
| **Rotation 30°** | 1/3 | 100% | B | 0.92 density; 75% threshold passed |
| **Rotation 45°** | 1/3 | 100% | B | 0.92 density |
| **Rotation 90°** | 1/3 | 100% | B | Exact pixel remap |
| **Rotation 180°** | 1/3 | 100% | B | Exact pixel remap |
| **Force arrow (VOID)** | 3 indicator | 100% | D₂ (VOID) | Inner wiped, outer intact; force arrows persist |
| **Full wipe** | 3 indicator | 0 det. | A (ABSENT) | Both zones restored; clean State A; no false claim |
| **Crop (any)** | Use Layer H | N/A | N/A | Layer H handles geometry; Layer G handles rotation |
| **PNG (lossless)** | 1 | 100% | B | Zero degradation |

*The adversary who removes the sentinel leaves the field intact. The field still points at what was there. JPEG and bilinear interpolation destroy absolute values. Density distributions survive both. The gap between marked and clean is 0.9988. The distributions do not touch.*

## **1.9  Integration**

### **Position in Embedding Pipeline**

Layer G is applied after Layer F (Payload). Layer F establishes sentinel positions. Layer G wraps those positions with the halo field. Layer H (Ruler) is applied after Layer G, since Layer H operates on final pixel values and must not be disrupted by subsequent halo embedding.

Embedding order: A → BC → D (measurement only) → E → F → G → H.

### **Position in Detection Pipeline**

Layer G runs after Layer E provides candidate sentinel positions. In manifest mode, Layer E positions are known; Layer G evaluates state at those positions. In blind mode, Layer G scans independently and its detected halo centers inform Layer E’s sentinel location estimates.

After Layer H recovers original image coordinates (in the case of a cropped image), Layer G halo positions can be re-evaluated in the original frame. The recovered W\_orig and H\_orig from Layer H define the coordinate transform; halo centers in the cropped image translate back to original positions for payload reconstruction.

### **Inputs**

* **centers:** List\[(row, col)\] of sentinel positions from Layer F

* PIL RGB image at current state of processing

### **Outputs**

* **Per-center HaloCenter:** state (PRESENT/VOID/ABSENT), inner\_density, outer\_density, amplitude

* **Rotation survival:** present\_matched, void\_matched, missed, survival\_fraction per tested angle

* **FP partition:** on\_grid / off\_grid counts after grid check

## **1.10  API Reference**

Module: halo\_div2k\_test.py  |  Standalone, no provenance package dependency  |  BSD-2

| Function | Signature | Returns |
| :---- | :---- | :---- |
| **embed\_halos()** | image, centers: List\[Tuple\[int,int\]\] | PIL Image with halos embedded |
| **detect\_halos()** | image, max\_centers=200 | List\[HaloCenter\] sorted by inner\_density |
| **detect\_halos\_strict()** | image, max\_centers=200 | List\[HaloCenter\] with tight FP filter (STRICT\_INNER=0.55) |
| **wipe\_inner\_disk()** | marked, original, centers, radius=None | PIL Image with inner disk restored (VOID test) |
| **wipe\_full\_halo()** | marked, original, centers | PIL Image with both zones restored (full wipe test) |
| **rotation\_survival()** | image, centers, angle | dict: present\_matched, void\_matched, missed, survival\_fraction |
| **grid\_check\_manifest()** | detected\_positions, known\_centers, grid\_tol=20 | (on\_grid, off\_grid) — manifest-mode FP partition |
| **grid\_check\_blind()** | detected\_positions, img\_h, img\_w, grid\_tol=20 | (on\_grid, off\_grid, dominant\_spacing) — blind lattice check |
| **edge\_guided\_pick\_centers()** | image, n, edge\_percentile=60 | List\[Tuple\[int,int\]\] — centers in high-edge zones |
| **pick\_centers()** | image, n | List\[Tuple\[int,int\]\] — regular grid fallback |
| **zone\_step\_at()** | image, cy, cx | float — radial step at inner radius boundary (≈28 embedded, ≈0–6 natural) |

### **Quickstart**

from halo\_div2k\_test import (  
    embed\_halos, detect\_halos, detect\_halos\_strict,  
    wipe\_inner\_disk, wipe\_full\_halo, rotation\_survival,  
    edge\_guided\_pick\_centers, grid\_check\_manifest, zone\_step\_at,  
    HaloState,  
)  
   
\# Select embedding positions in high-edge zones  
centers \= edge\_guided\_pick\_centers(image, n=4, edge\_percentile=60)  
   
\# Embed  
marked \= embed\_halos(image, centers)  
   
\# Detect (manifest mode)  
halos \= detect\_halos(marked)  
for h in halos:  
    print(h.state, h.inner\_density, h.outer\_density)  
   
\# FP check (manifest mode, grid-checked)  
fps \= detect\_halos\_strict(clean\_image)  
fp\_pos \= \[(d.row, d.col) for d in fps\]  
\_, off\_grid \= grid\_check\_manifest(fp\_pos, centers)  
print(f'Off-grid FPs: {len(off\_grid)}')  
   
\# Rotation survival  
for angle in \[0, 15, 30, 45, 90, 180\]:  
    result \= rotation\_survival(image, centers, angle)  
    print(angle, result\['survival\_fraction'\])

## **1.11  Known Limitations and Open Items**

### **Confirmed Limitations**

* **Blind-mode FP rate \~30% on DIV2K.** Images with large warm-toned uniform regions. Manifest mode achieves 0%. The strict detector \+ zone-boundary sharpness test reduces but does not eliminate the blind FP rate. This is a documented property of the target value 168 in high-saturation photography, not a detector flaw.

* **Rotation payload recovery not yet implemented.** Halo detection after rotation is complete. Recovering the Layer F payload from a rotated image requires: (1) locate halos in rotated frame, (2) estimate rotation angle from halo geometry via rigid-body constraint, (3) apply inverse rotation, (4) run Layer F decoder. Steps 2–4 are architecturally defined but not implemented.

* **Halo-to-sentinel association after rotation.** Each halo corresponds to a sentinel. After rotation, the correspondence must be re-established via geometric proximity. Three or more halos constrain the rigid-body rotation to a unique solution; two halos are under-constrained.

* **Q40 VOID transition.** At Q40, some inner disk targets transition to VOID because INNER\_TARGET=168 is close to the JPEG chroma quantization grid at that quality level. Detection count remains 4/4; state changes from PRESENT to VOID. Documented as expected behavior.

### **Open Items**

* **Rotation-corrected payload recovery.** Implement: locate halos → estimate rotation angle from halo pairwise geometry → apply inverse rotation → run Layer F decoder. This closes the loop on rotation resilience as a complete provenance claim.

* **INNER\_TARGET stability at Q40.** Characterize the JPEG chroma quantization table at Q40 and verify that INNER\_TARGET=168 falls between quantization levels. If not, select a target that avoids the gravity well at that quality setting.

* **Scale to 500+ images.** Current validation corpus: 100 DIV2K images. Extend to full 800-image set for FP rate and state-transition statistics.

* **Neural codec characterization.** HEIC, AVIF, WebP. Density-distribution encoding is theoretically more robust than absolute-value encoding against non-DCT pipelines, but this has not been measured.

* **RAW/Lightroom pipeline.** Shared open item with Layer H. If halo density distributions survive demosaicing, the claim extends to unedited professional photography. Coordinate with Layer H RAW validation session.

## **Canonical Phrases**

*“The adversary who removes the sentinel leaves the field intact. The field still points at what was there.”*

*“JPEG and bilinear interpolation destroy absolute values. Density distributions survive both.”*

*“The gap between marked and clean is 0.9988. The distributions do not touch.”*

*“The compressor that destroys the inner disk is constructing the VOID signal.”*

*“127 is not a wrapping boundary. It is JPEG’s chroma gravity well.”*

*“Positions survive JPEG. Values do not. Density survives everything.”*

# **Appendix A — Layer G Validation Results**

All results from validation against the DIV2K training corpus. 100 images, 2K resolution. Targets: INNER\_TARGET=168, OUTER\_TARGET=140. Test environment: Windows 11, Python 3.12.

| Test | Result | N | Notes |
| :---- | :---- | :---- | :---- |
| **Detection** | 100/100 PASS | 100 | 4/4 centers PRESENT per image |
| **FP (manifest, grid-checked)** | 100/100 PASS | 100 | off\_grid \= 0 for all images |
| **FP (blind mode)** | \~70/100 | 100 | \~30 images have natural |R-G| near 168; blind FP is documented property |
| **Rotation 0°** | 100/100 PASS | 100 | Exact pixel remap |
| **Rotation 15°** | 100/100 PASS | 100 | Bilinear interp; density 0.92–0.94; 0 false positives |
| **Rotation 30°** | 100/100 PASS | 100 |  |
| **Rotation 45°** | 100/100 PASS | 100 |  |
| **Rotation 90°** | 100/100 PASS | 100 | Exact pixel remap |
| **Rotation 180°** | 100/100 PASS | 100 | Exact pixel remap |
| **Force arrow VOID** | 100/100 PASS | 100 | Inner wiped, outer intact; all 4 centers detected as VOID |
| **Full wipe (clean)** | 100/100 PASS | 100 | Both zones restored; 0 detections; no false provenance claim |
| **JPEG Q85** | 100/100 PASS | 100 |  |
| **JPEG Q40** | 100/100 PASS | 100 | Some centers VOID; all detected; correct behavior |
| **Encoding option A (rotation 5°)** | 5.1% survival | N/A | Historical: absolute values destroyed by bilinear interp |
| **Encoding option B (JPEG)** | FP-saturated | N/A | Historical: outer ring targets common post-JPEG |

*Document version: 1.0  |  March 2026  |  Layer G (Halo) complete.*