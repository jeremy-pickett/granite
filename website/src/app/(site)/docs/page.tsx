import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Documentation — Granite Under Sandstone',
};

export default function DocsPage() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Documentation</p>
          <h1>Granite Docs</h1>
          <p className="hero-subtitle">Integration guides, API reference, and field notes.</p>
        </div>
      </header>

      <section className="section">
        <div className="container">

          <h2>Integration</h2>
          <div className="grid-3">
            <Link href="/docs/raw-integration" className="doc-card">
              <span className="doc-tag guide">Guide</span>
              <h3>Raw Integration</h3>
              <p>Embed and detect provenance signals by importing the source modules directly. No library, no build step.</p>
            </Link>
            <Link href="/docs/design-history" className="doc-card">
              <span className="doc-tag guide">Guide</span>
              <h3>Design History</h3>
              <p>How we got here &mdash; every wrong assumption, why it failed, and what the correct architecture is.</p>
            </Link>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Library Integration</h3>
              <p>Install via pip, import, and go. Clean API surface for production use.</p>
            </div>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Architecture Overview</h3>
              <p>The three detection layers, signal pipeline, and how they compose.</p>
            </div>
            <Link href="/docs/prime-split-encoding" className="doc-card">
              <span className="doc-tag guide">Paper</span>
              <h3>Prime Split Encoding</h3>
              <p>Steganographic information channels in prime decomposition space. Layer 2 payload encoding via split selection.</p>
            </Link>
          </div>

        </div>
      </section>

      <section className="section section-alt">
        <div className="container">

          <h2>Addendums</h2>
          <p className="lead">Field notes, extensions, and deep dives from the research series.</p>
          <div className="grid-3">
            <Link href="/docs/addendum-a-video-extension" className="doc-card">
              <span className="doc-tag addendum">Addendum A</span>
              <h3>Extension to Video</h3>
              <p>I-frames are JPEGs in a trench coat. The same granite hypothesis applies to H.264, H.265, VP9, and AV1.</p>
            </Link>
            <Link href="/docs/addendum-b-integration-landscape" className="doc-card">
              <span className="doc-tag addendum">Addendum B</span>
              <h3>Integration Landscape</h3>
              <p>Where Granite sits in the provenance ecosystem &mdash; C2PA, watermarking, fingerprinting, and the gaps between them.</p>
            </Link>
            <Link href="/docs/addendum-c-cascading-canary-survival" className="doc-card">
              <span className="doc-tag addendum">Addendum C</span>
              <h3>Cascading Canary Survival</h3>
              <p>What happens to the signal across 5+ generations of lossy compression. The canary in the cascade.</p>
            </Link>
            <Link href="/docs/addendum-d-attribution-architecture" className="doc-card">
              <span className="doc-tag addendum">Addendum D</span>
              <h3>Attribution Architecture</h3>
              <p>From detection to attribution &mdash; how the rare basket layer enables corpus-scale provenance at O(1) lookup.</p>
            </Link>
            <Link href="/docs/addendum-f-multilayer-provenance" className="doc-card">
              <span className="doc-tag addendum">Addendum F</span>
              <h3>Multilayer Provenance</h3>
              <p>How the three detection layers compose into a defense-in-depth provenance architecture.</p>
            </Link>
            <Link href="/docs/addendum-g-known-attacks" className="doc-card">
              <span className="doc-tag addendum">Addendum G</span>
              <h3>Known Attacks</h3>
              <p>Every attack we tested &mdash; rotation, slicing, rescaling, cross-codec transcoding &mdash; and what survived.</p>
            </Link>
            <Link href="/docs/addendum-h-thar-be-dragons" className="doc-card">
              <span className="doc-tag addendum">Addendum H</span>
              <h3>Thar Be Dragons</h3>
              <p>The failure modes, edge cases, and open problems we know about. Honest accounting of what doesn&rsquo;t work yet.</p>
            </Link>
            <Link href="/docs/addendum-i-color-of-survival" className="doc-card">
              <span className="doc-tag addendum">Addendum I</span>
              <h3>The Color of Survival</h3>
              <p>Why G-B outperforms R-G, and what chroma subsampling teaches us about channel pair selection.</p>
            </Link>
            <Link href="/docs/addendum-j-thermodynamic-tax" className="doc-card">
              <span className="doc-tag addendum">Addendum J</span>
              <h3>The Thermodynamic Tax</h3>
              <p>The information-theoretic cost of embedding. What the signal costs in PSNR, file size, and perceptual quality.</p>
            </Link>
            <Link href="/docs/addendum-k-fuse-and-fire" className="doc-card">
              <span className="doc-tag addendum">Addendum K</span>
              <h3>Fuse and Fire</h3>
              <p>The decision framework &mdash; when to declare detection, when to escalate, and the doctrine of compound evidence.</p>
            </Link>
            <Link href="/docs/addendum-l-spanning-sentinel" className="doc-card">
              <span className="doc-tag addendum">Addendum L</span>
              <h3>The Spanning Sentinel</h3>
              <p>When the compressor becomes the custodian &mdash; relational encoding, tiered detection, and the 0.9988 gap.</p>
            </Link>
          </div>

        </div>
      </section>
    </>
  );
}
