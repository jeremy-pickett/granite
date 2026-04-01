# ADDENDUM B

**Integration Landscape**

*Addendum to: Participation Over Permission — March 2026*


---


## B.1 The Observation


The provenance signal scheme does not require a new image processing library. It requires a thin layer on top of libraries that already exist on every application server, every CDN edge node, and every creative tool on earth.


The image processing ecosystem has converged on three libraries. Not five. Not ten. Three. Every platform that processes images at scale — from DeviantArt to Mastodon to Cloudflare — uses one of these three libraries or a service built on top of them. This convergence is the integration opportunity.


---


## B.2 The Three Libraries


| Library | Language / Bindings | Install Base | Status |
| --- | --- | --- | --- |
| ImageMagick | C. Bindings: MiniMagick (Ruby), Wand (Python), gm (Node) | Legacy incumbent. Default on Heroku, older Rails, WordPress. Billions of images processed daily. | Declining. 49+ CVEs. Memory-intensive. Being replaced by libvips. |
| libvips | C. Bindings: sharp (Node), ruby-vips (Ruby), pyvips (Python) | Modern default. Rails 7+ default. Mastodon. Fast-growing adoption in Node ecosystem via sharp. | Ascending. 4× faster, 10× less memory than ImageMagick. Active security posture. |
| Pillow | Python. Wraps libjpeg-turbo, libwebp, zlib. | Python ecosystem default. Every Django/Flask site, every ML pipeline, every data science notebook. | Stable. Ubiquitous in Python. Primary path for AI training pipeline integration. |


**Table B1. ***The three image processing libraries. The provenance scheme needs integration points in all three to achieve meaningful coverage.*


Above these libraries sits a CDN layer: Cloudflare Polish, Cloudinary, ImageKit, Imgix, BunnyCDN, and similar services that perform on-the-fly image optimization at the network edge. These services typically build on libvips or custom forks. A provenance-aware CDN integration would operate at this layer, but the underlying mechanism is the same: intercept the encode path, apply prime quantization tables and twin markers, pass through to the existing codec.


---


## B.3 Two Sides: Embedding and Detection


The integration landscape has two distinct sides with different requirements, different deployment contexts, and different complexity profiles.


### B.3.1 The Embedding Side (Creation)


Embedding occurs at the moment a file is saved. The integration point is the codec’s encode path. The provenance layer intercepts the quantization table selection (for Strategy 4 / Layer A), the pixel values before encoding (for twin markers / Layer B), and optionally the container metadata (for the Douglas Rule / Layer C).


The critical requirement: the embedding must happen *inside* the encode operation, not as a pre-processing step. If markers are embedded into pixel values and then the image is encoded normally, the encoder’s own quantization may shift the markers off their prime values before the file is written. The embedding must be integrated with or applied simultaneously with quantization table selection.


The integration model for each library follows the same pattern: wrap or extend the existing JPEG/WebP encode function to apply provenance embedding as part of the encode operation. The application’s API does not change. The save call produces a provenance-bearing file instead of a normal file.


| Library | Integration Model | What Changes | What Doesn’t Change |
| --- | --- | --- | --- |
| Pillow | Custom encoder plugin or wrapper around JpegImagePlugin.save() that applies prime QT and twin markers. | The quantization tables passed to libjpeg. Pixel values at marker positions before handoff to encoder. | The application’s save() call. The file format. The visual output (imperceptible quality delta). |
| sharp / libvips | A custom vips operation (.so/.dll) loaded into the libvips pipeline, or a sharp middleware function in the transform chain. | Same as Pillow: QT entries and pixel values at marker positions during the encode pass. | The sharp API. The pipeline architecture. Existing resize, crop, and format operations. |
| ImageMagick | External delegate registered in delegates.xml, or a custom coder module. Less elegant but functional for the legacy install base. | Same mechanism. ImageMagick’s modular architecture allows custom coders to override the default JPEG encoder. | The convert / mogrify CLI. Existing scripts and automation. |


**Table B2. ***Embedding integration model per library. The pattern is consistent: wrap the encode path, leave the API unchanged.*


### B.3.2 The Detection Side (Ingestion)


Detection has two tiers with very different integration profiles.


**Tier 1: DQT scan (Layer A). **This is 128 bytes of file header reading followed by a prime count. It does not require an image library. It does not require decoding the image. It requires fread() and arithmetic. This can be implemented as: a standalone CLI tool; a shared library callable from any language; an nginx module that scans uploads at the reverse proxy layer; a Cloudflare Worker or Lambda@Edge function that scans at the CDN edge; a filesystem watcher that scans on write. Detection runs at I/O speed, not processing speed. On modern hardware, this is millions of files per hour per core.


**Tier 2: Twin marker and variance anomaly detection (Layers B and B+). **This requires decoding the image to pixel space and measuring distances at known marker positions. It needs an image library (Pillow, libvips, or equivalent) and the marker position metadata (basket seed, window parameter). This is a read-only operation: open, decode, sample, measure, return confidence score. It runs at image decode speed — milliseconds per image. The integration model is a function call that takes a file path and marker parameters and returns a detection result.


| Detection Tier | Requires | Speed | Deployment Options |
| --- | --- | --- | --- |
| Tier 1: DQT scan | File I/O only. No image library. No decoding. | Microseconds per file. Filesystem scan speed. | CLI, .so/.dll, nginx module, CDN Worker, Lambda@Edge, filesystem watcher. |
| Tier 2: Marker detection | Image decoder (Pillow, libvips). Marker position metadata. | Milliseconds per image. Decode speed. | Python function, Node function, libvips operation, batch processing pipeline. |


---


## B.4 The CDN Pipeline Reality


The modern image delivery pipeline is not creator → viewer. It is:


*Creator → JPEG → Platform upload server → CDN edge → WebP (or AVIF) → Browser → Scraper → ??? → next platform → next CDN → next format → ...*


At each arrow, a transcoding step may occur. The CDN layer — Cloudflare, Cloudinary, Fastly, Akamai — automatically transcodes JPEG to WebP for delivery based on the browser’s Accept header. This is invisible to both creator and viewer. It is infrastructure.


Empirical testing shows that the JPEG → WebP codec boundary does not destroy the provenance signal. It amplifies it. The KS distribution separation for twin markers improved from p = 0.044 (JPEG Q95) to p = 1.06 × 10⁻⁷ (WebP Q95) — six orders of magnitude. The misaligned quantization grids (JPEG’s 8×8 vs. VP8’s 4×4) create constructive interference in the variance signal at marker positions.


This means the CDN layer is not hostile to the scheme. It is a *participating amplifier*. The integration opportunity is not to modify CDN behavior. It is to recognize that existing CDN behavior already works in the scheme’s favor. No CDN integration is required for the signal to function. CDN integration is only beneficial for the detection side: a Tier 1 DQT scan at the CDN edge would flag provenance-marked files at ingestion speed before they enter the platform’s processing pipeline.


---


## B.5 Deployment Phases


The scheme does not require simultaneous adoption across the ecosystem. Each phase is independently useful.


### Phase 1 — Creator Tools (Embedding)


A Pillow plugin distributed via PyPI. A creator installs one package. Their existing save calls produce provenance-bearing JPEGs. No workflow change. No account. No subscription. The plugin handles basket generation, marker placement, quantization table priming, and embedding metadata storage. The creator’s file carries the signal from the moment of creation.


This phase requires zero platform cooperation. The signal is embedded unilaterally. This is the “participation over permission” principle in deployment form.


### Phase 2 — Ingestion Pipeline (Detection)


A standalone DQT scanner distributed as a CLI tool and as a shared library. A platform adds one line to its upload processing pipeline: scan the incoming file, log the result. Provenance-marked files are flagged. Non-marked files pass through unchanged. The cost is microseconds per upload. The value is an audit trail that didn’t exist before.


This phase requires minimal platform cooperation — one integration point in the upload path. The platform makes no commitment about what to do with the flag. It simply records whether provenance signal was present. The recording is the value.


### Phase 3 — Platform Embedding


A sharp middleware or libvips operation that allows platforms to become participating systems. The platform embeds its own provenance layer during upload processing, alongside or in addition to the creator’s layer. Multi-entity layered attribution: the creator’s signal identifies the creator; the platform’s signal identifies the platform; both are independently detectable.


This phase requires active platform participation. It is the highest-value integration but the highest-effort deployment. It is not required for the scheme to function. It is additive.


### Phase 4 — CDN-Edge Detection


A Cloudflare Worker, Lambda@Edge, or equivalent edge function that performs Tier 1 DQT scanning on every image passing through the CDN. Provenance state is recorded as a response header or logged to an audit service. The image is delivered unmodified. The CDN becomes a passive detection network without modifying any content.


This phase is aspirational. It requires CDN provider cooperation or customer-configurable edge compute (which Cloudflare Workers and AWS Lambda@Edge already provide). The technical barrier is low. The business case depends on whether platforms and CDN providers see value in provenance metadata as a service.


---


## B.6 The Local Proxy Option


For creators who want provenance embedding without modifying their tools, a local proxy offers a zero-integration path.


The proxy runs as a local service (localhost). The creator configures their image editor to save to a watched directory or to upload through the proxy. The proxy intercepts the file on write, applies provenance embedding, and passes the modified file to its destination. The creator’s tool is unmodified. The proxy handles the embedding.


This model is familiar: it is how local development proxies (Charles, Fiddler, mitmproxy), ad blockers (Pi-hole), and content filters already operate. The technical implementation is a filesystem watcher or an HTTP proxy that intercepts image uploads and applies the embedding pipeline before forwarding.


The local proxy is the least invasive integration option and the most accessible to non-technical creators. It is also the least performant and the most fragile. It is a bridge, not a destination. The destination is native integration at the library level.


---


## B.7 What We Are Not Building


This addendum describes integration *paths*, not integration *products*. The scheme is a method, not a service. The correct outcome is not a company that sells provenance embedding. The correct outcome is:


Every image library ships with a provenance option. Pillow grows a provenance=True parameter on its JPEG encoder. sharp grows a .provenance() method in its pipeline. libvips grows a vips_jpegsave_provenance() function. The embedding becomes infrastructure. Infrastructure does not have a vendor.


Every ingestion pipeline ships with a DQT scan at the front of the queue. The scan is 20 lines of C. It is not a product. It is a function. The function becomes a standard check, like virus scanning or EXIF extraction. Standard checks do not have vendors. They have implementations.


The method is published. The code is open. The economics are self-enforcing. If it works, it works because everyone can implement it. Not because anyone controls it. That is the point. That has always been the point.


---


*The scheme does not need a platform. The scheme needs a library. The libraries already exist. The path is visible. The integration is thin. The barrier is will, not technology.*


*No code has been written for any integration described in this addendum.*


*The path is described because we see it, not because we have walked it.*


Jeremy Pickett — March 2026
