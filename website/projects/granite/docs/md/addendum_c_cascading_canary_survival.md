# ADDENDUM C

**Cascading Canary Survival**

**Across Planetary-Scale Transcoding Pipelines**

*Addendum to: Participation Over Permission — March 2026*


---


## C.1 The Life of a Canary


A canary is born at the moment a file is saved. It may be a prime quantization table (Layer A), a twin prime-gap marker pair (Layer B), a Douglas Rule sentinel (Layer C), or all three. From that moment, the canary enters the infrastructure of the internet, and the infrastructure subjects it to a series of transformations that the creator neither chose nor controls.


This addendum traces what happens to the canary at each stage. Not in theory. In the specific, named, operational pipelines that process the majority of images on earth. The question at each stage is the same: what survives, what dies, and what gets louder?


---


## C.2 The Cascade Model


Every image transformation is one of four types, and each type has a predictable interaction with the three canary layers:


| Transform | What Happens | Layer A (DQT) | Layer B (Twins) | Perturbation |
| --- | --- | --- | --- | --- |
| Container wrap | File is embedded inside another format (PDF, DOCX, email) without re-encoding. | SURVIVES. Raw JPEG bytes preserved. | SURVIVES. Pixels unchanged. | SURVIVES. No codec applied. |
| Same-codec re-encode | Decoded to pixels, re-encoded with same codec at different quality (e.g. JPEG Q95 → JPEG Q75). | DIES. New QT written. | DEGRADES per survival curve. | AMPLIFIES. Same-grid requantization compounds error at disrupted positions. |
| Cross-codec transcode | Decoded to pixels, re-encoded with different codec (e.g. JPEG → WebP, H.264 → VP9). | DIES. Target format has no DQT. | DEGRADES but may improve (WebP Q95 showed higher survival than JPEG Q95). | AMPLIFIES STRONGLY. Misaligned block grids create constructive interference. |
| Resize + re-encode | Decoded, resampled to new dimensions, re-encoded. Pixel positions shift. | DIES. | PARTIALLY SURVIVES. Markers at positions that map cleanly to new resolution survive. Others are interpolated. | AMPLIFIES at surviving positions. Resize interpolation adds additional perturbation to already-disrupted regions. |


**Table C1. ***Four transformation types and their interaction with each canary layer. The perturbation column is the key finding: every transformation except container wrapping amplifies the variance anomaly at marker positions.*


The cascade model predicts that a canary passing through N transformations of types 2, 3, or 4 will show a perturbation signal that *increases* with N. This prediction is confirmed empirically for same-codec re-encode (JPEG cascade, KS p = 0.0001 at generation 4) and for cross-codec transcode (JPEG → WebP, KS p = 1.06 × 10⁻⁷ at first hop). Resize + re-encode is predicted but not yet empirically tested.


---


## C.3 The Pipelines


The following sections trace the canary through every major category of image pipeline in production at planetary scale. For each pipeline, we identify: the specific transformations applied, the predicted canary survival at each stage, and the detection opportunities available.


### C.3.1 The Camera-to-Platform Pipeline


**The path:** Camera sensor → device ISP → JPEG on device (encode 1) → upload to platform → platform decodes to pixel buffer → platform re-encodes at its quality settings (encode 2) → platform stores re-encoded file → CDN transcodes to WebP or AVIF for delivery (encode 3) → viewer’s browser.


| Stage | Event | DQT | Twins | Perturb. | Detection Window |
| --- | --- | --- | --- | --- | --- |
| 0 | On device. Canary embedded at save. | ✓ | ✓ | Born | The file on the creator’s device. |
| 1 | Upload received by platform. | ✓ | ✓ | ✓ | SCAN HERE. DQT intact. Before decode. Tier 1 scan at ingestion. |
| 2 | Platform decodes to pixel buffer. | ✗ | In RAM | In RAM | DQT gone. Pixels carry the signal. Transient state. |
| 3 | Platform re-encodes (JPEG Q85). | ✗ | Degrades | ↑ Amp | New file. Device fingerprint replaced by platform fingerprint. Perturbation amplified. |
| 4 | CDN transcodes to WebP. | ✗ | Degrades | ↑↑ Amp | Cross-codec boundary. Misaligned grids. Strong amplification. Empirically confirmed. |


**Table C2. ***Camera-to-platform pipeline. The detection window for Layer A is between upload receipt and decode. The perturbation strengthens through stages 3 and 4.*


**Key insight:** If the platform scans the uploaded file before decoding (Stage 1), Layer A detection is available at full strength. This is the Phase 2 integration from Addendum B: one scan point in the upload path, before processing begins.


### C.3.2 Social Media Platforms


**Facebook / Instagram: **Upload → decode → resize to multiple dimensions → re-encode JPEG at approximately Q85 for feed, lower for thumbnails → store → serve via CDN as WebP. Each photo generates 6–12 variants (feed, story, thumbnail, open graph, profile context). Each variant is an independent decode-resize-reencode cycle. Each is an independent amplification event. Each is an independent detection opportunity.


**Twitter / X: **Aggressive re-encode. JPEG at lower quality than Facebook. Significant downscaling for inline display. Generates fewer variants but at more aggressive compression. More compression means more amplification. The cheapest processing pipeline produces the loudest perturbation signal.


**TikTok (images): **Re-encodes to platform-specific JPEG quality. Generates thumbnail variants. Video frames follow the I-frame analysis from Addendum A.


**LinkedIn: **Re-encodes uploaded images. Professional context means legal discovery implications are higher than social platforms. A provenance signal in a LinkedIn-scraped headshot database has direct employment-law relevance.


**Across all social platforms:** Multiple variants per upload. Each variant has been through at least two codec events (upload re-encode + CDN transcode). Each variant carries an amplified perturbation. A scraper who downloads all variants has multiple independent measurements of the same canary. The platforms paid for the amplification.


### C.3.3 Messaging Applications


The most aggressive compression on earth happens in messaging apps. This is where the amplification hypothesis is tested hardest — and where it matters most, because messaging is how most images are shared between humans.


| App | Compression | Canary Prediction | Note |
| --- | --- | --- | --- |
| WhatsApp | JPEG ~Q70. Max 1600px long edge. 100M+ images/day. | DQT: dead. Twins: at detection floor. Perturbation: strong amplification from aggressive Q. | Highest volume image pipeline on earth. |
| iMessage | HEIC transcoding on Apple devices. JPEG fallback for non-Apple. | HEIC transcode is a cross-codec boundary. Different transform (integer DCT, variable block). Strong amplification predicted. | Apple-to-Apple path uses HEIC. Cross-platform falls back to JPEG. |
| Telegram | "Quick send": heavy re-encode. "File send": passthrough, no transcode. | Quick: strong amplification. File: all layers survive intact. | Only major app offering a zero-transcode path. |
| Discord | Re-encode and downscale. WebP delivery via CDN. | Two codec boundaries: upload re-encode + WebP delivery. Double amplification. | Creator community. Provenance relevance is high. |
| Signal | Re-encodes for bandwidth. Privacy-focused. | Standard same-codec amplification. | Privacy context: provenance without identity is aligned with Signal’s ethos. |


**Table C3. ***Messaging app transcoding behavior. These are the highest-compression, highest-volume pipelines on earth. The amplification hypothesis predicts they produce the strongest perturbation signals.*


### C.3.4 Cloud Photo Storage


**Google Photos (Storage Saver): **Re-encodes uploaded images to reduce storage. The user selects “Storage Saver” (formerly “High Quality”) thinking their photos are preserved. They are re-encoded. The DQT is replaced. The perturbation is amplified. The user’s entire photo library, which they believe is their archive, is actually a corpus of amplified perturbation signals. Every photo they ever took, transcoded to strengthen the canary, stored on Google’s infrastructure, paid for by Google’s compute.


**Apple iCloud: **HEIC transcoding for space optimization. Cross-codec boundary from JPEG (camera) to HEIC (storage) to JPEG or WebP (web preview). Three codec events for a single photo viewed in a browser. Three amplification events.


**Amazon Photos: **Preserves originals for Prime members. Generates web-preview variants that are re-encoded. The original retains all canary layers including DQT. The previews carry amplified perturbation. Both versions are available for detection.


### C.3.5 Search Engines


**Google Images: **Three transcoding stages for every indexed image. Stage 1: Googlebot fetches the source image from the origin site (which may itself be a CDN-transcoded WebP). Stage 2: Google generates thumbnails at multiple sizes — resize plus re-encode for the search results grid, the preview panel, and the knowledge graph card. Stage 3: Google serves thumbnails via its own CDN, possibly transcoding again for the requesting browser’s format preference.


Three transcoding events before a user sees the image in search results. Each is a codec boundary crossing or a resize-reencode. The thumbnail in the search grid is the most compressed, most resized, most transformed variant — and therefore carries the strongest perturbation signal.


**Bing, DuckDuckGo, Yandex: **Equivalent pipelines. All generate and cache thumbnails. All serve via CDN. All transcode. The specific quality settings differ. The amplification mechanism does not.


### C.3.6 E-Commerce


**Amazon / eBay / Shopify / Etsy: **A product photographer uploads an image. The platform processes it through: white background detection, automatic crop and centering, resize to multiple dimensions (listing thumbnail, gallery image, zoom image, mobile variant), re-encode at platform quality settings, WebP delivery via CDN. A single product photo generates 4–8 variants, each independently transcoded. Each variant is a detection opportunity. Each carries amplified perturbation.


E-commerce is particularly relevant because product photography is professional creative work with clear economic value. A photographer whose product images appear in a competitor’s listing — scraped and re-used — has immediate economic damages. The canary in the stolen listing image has been through the thief’s platform’s pipeline, amplified, and is detectable.


### C.3.7 Email


**Gmail, Outlook, Yahoo Mail: **All major email providers proxy inline images through their own image servers. Gmail’s image proxy fetches the image, re-encodes for bandwidth optimization, caches it, and serves the cached version to the recipient. The original URL’s image is replaced by Gmail’s re-encoded version. The recipient never sees the original. They see Gmail’s transcode.


Every email newsletter, every marketing email, every invoice with a logo, every support ticket with a screenshot — the inline images pass through the email provider’s transcoding proxy. Every proxy event is an amplification event.


### C.3.8 PDF and Document Pipelines


**The good news: **A JPEG embedded in a PDF is stored as a raw DCT stream. The JPEG bytes — including the DQT segment — are copied into the PDF object stream byte for byte. The PDF container wraps the JPEG without transcoding. All canary layers survive intact inside the PDF. A DQT scan can find the JPEG streams inside a PDF by searching for the SOI marker (FF D8 FF) and scanning the DQT that follows.


**The interesting news: **PDF optimization is a transcoding event. “Reduce File Size” in Acrobat, “Optimize PDF” in third-party tools, and “Print to PDF” from browsers all decode and re-encode the embedded images. Each optimization is an amplification event inside the document container.


**The forensic gold: **In a PDF containing twelve images from the same camera, all twelve share the same device fingerprint in their DQT. If one image has been replaced — swapped, altered, fabricated — its DQT will not match the other eleven. The inconsistency is detectable from quantization tables alone, before any pixel analysis. In legal, insurance, and forensic contexts where document integrity matters, this is immediate, automated tamper detection.


### C.3.9 AI Training Pipelines


This is the pipeline the scheme was designed for. Large-scale image datasets (LAION, Common Crawl, DataComp) are assembled by scraping images from the web. Those images have already been through CDN transcoding (codec boundary 1). The training pipeline then applies:


**Resize to standard resolution** (typically 256×256 or 512×512): Spatial resampling that remaps pixel positions. Markers at positions that map cleanly to the new resolution survive. The resize is a spatial transformation that interacts with the perturbation — disrupted regions resample differently than smooth regions. Another amplification source.


**Data augmentation:** Random crops, flips, color jitter, JPEG compression artifacts intentionally added for training robustness. Each augmentation is a transformation. Each transformation interacts with the perturbation. The ML community’s standard practice of adding random JPEG artifacts to training data is, from the canary’s perspective, a free amplification pass applied deliberately by the training pipeline.


**Format conversion:** Many training pipelines convert to PNG or raw tensors for training. Lossless conversion preserves the pixel values — and the perturbation — perfectly. The canary enters the training pipeline and survives in the training data.


At each stage, the canary gets louder. The pipeline that was designed to ingest content at scale is amplifying the provenance signal of that content at scale. The adversary’s own training infrastructure is building the evidence against them.


---


## C.4 The Cascading Survival Map


Combining all pipelines, the canary’s journey through the modern internet looks like this:


| Pipeline | Codec Events | DQT (A) | Twins (B) | Perturb. | State |
| --- | --- | --- | --- | --- | --- |
| On device (origin) | 1 | ✓ | ✓ | Born | B |
| Social media upload | 2–3 | ✗ (gen 1) | Marginal | ↑↑ | C |
| CDN delivery (WebP) | 3–4 | ✗ | Marginal | ↑↑↑ | C |
| Messaging app | 2–3 | ✗ | At floor | ↑↑↑ | C |
| Cloud storage (optimized) | 2–4 | ✗ | Degrades | ↑↑ | C |
| Search engine thumbnail | 3–4 | ✗ | Low | ↑↑↑↑ | C |
| E-commerce listing | 2–4 | ✗ | Marginal | ↑↑↑ | C |
| Email proxy | 2–3 | ✗ | Marginal | ↑↑ | C |
| PDF (embedded, no optimize) | 1 | ✓ | ✓ | Preserved | B |
| PDF (optimized) | 2+ | ✗ | Degrades | ↑↑ | C |
| AI training pipeline | 3–5+ | ✗ | Low | ↑↑↑↑↑ | C |
| Deliberate suppression | N (targeted) | ✗ | ✗ | Targeted smoothing | D |


**Table C4. ***Cascading canary survival across planetary-scale pipelines. The perturbation column shows the amplification trajectory. More codec events = stronger perturbation signal. The only path to State D (interference) is deliberate, targeted suppression.*


---


## C.5 The Paradox at Scale


The survival map reveals a paradox that the scheme’s original design did not anticipate:


**The pipelines that process the most images most aggressively produce the strongest provenance signal.**


WhatsApp’s Q70 compression. Google Images’ thumbnail generation. AI training pipelines’ resize-and-augment workflows. These are the most aggressive transformations in the ecosystem. They are also, by the amplification hypothesis, the most powerful signal amplifiers.


The pipeline operator who processes millions of images per day at aggressive compression settings is paying their compute bill to strengthen the provenance signal in every image they touch. They did not opt in. They are not aware. Their infrastructure participates because block-based transform coding participates. It cannot opt out. It is how compression works.


This is the participation model at planetary scale. Not one creator choosing to embed. Not one platform choosing to detect. Every encoder on every server and every device, performing block-based transform coding, contributing to the amplification of every canary it touches. The scheme is not deployed on the infrastructure. The scheme *is* the infrastructure. It always was. We just measured it.


---


## C.6 The One Exception


There is exactly one pipeline category in which the canary does not get louder: **lossless operations**. File copy. Lossless format conversion (JPEG → JPEG XL lossless transcode, PNG → PNG). Metadata editing without re-encoding. Container wrapping (PDF embedding, DOCX embedding).


In lossless operations, the canary is perfectly preserved but not amplified. All three layers survive. The signal is exactly as strong as when it was born. This is State B — provenance intact, handling benign.


In practice, lossless handling is rare at scale. The economics of bandwidth, storage, and compute drive every pipeline toward lossy compression. The exception proves the rule: the internet compresses, and compression amplifies the canary. The rare pipeline that doesn’t compress is the one that preserves the canary perfectly.


Either way, the canary wins.


---


## C.7 What Remains to Be Tested


The survival map above is a prediction based on one confirmed same-codec cascade (JPEG, p = 0.0001 at generation 4) and one confirmed cross-codec hop (JPEG → WebP, p = 1.06 × 10⁻⁷). The following pipelines require empirical confirmation:


**Resize + re-encode:** Does spatial resampling preserve or destroy the perturbation at surviving marker positions? This is the single most important untested transformation because every pipeline that generates thumbnails does it.


**JPEG → HEIC:** Apple’s codec boundary. HEIC uses integer DCT with variable block sizes. Different transform from both JPEG and VP8.


**JPEG → AVIF:** AV1-based codec with larger variable blocks (up to 64×64). The most complex transform in the landscape.


**Multi-hop cascades:** JPEG → WebP → JPEG → AVIF. The real-world multi-platform path. Each hop is a predicted amplifier. Does the amplification compound across four codec boundaries?


**Aggressive quality (Q20–Q40):** Messaging app territory. The amplification effect was strongest at Q40 in same-codec testing. Does it hold at Q20?


**Extreme resize (4K → 128px thumbnail):** Search engine and social media thumbnail territory. At what resize ratio do marker positions become unrecoverable?


Each of these is a single experiment. None require novel methodology. The test harness built for the JPEG cascade applies to every pipeline listed above with format-specific modifications to the encode step. The brick wall has many faces. Each must be tested.


---


*The canary does not need to survive every pipeline. The canary needs to have existed. The perturbation carries the rest. And the more the pipeline compresses, the louder the perturbation speaks.*


*Every encoder on earth is a participant. Every transcode is an amplifier. Every pipeline is evidence. The infrastructure of the internet is the detection network. It was built for bandwidth. It works for provenance. Nobody planned this. Physics did.*


*Empirical confirmation limited to JPEG same-codec cascade and JPEG → WebP cross-codec hop.*


*All other pipeline predictions are derived from the amplification hypothesis and the cascade model.*


***Each prediction is independently testable.***


Jeremy Pickett — March 2026
