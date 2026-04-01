import type { Metadata } from 'next';
import Link from 'next/link';
import HeroIllustration from '@/components/HeroIllustration';
import SectionIllustration from '@/components/SectionIllustration';
import LayerBar from '@/components/LayerBar';

export const metadata: Metadata = {
  title: 'Granite Under Sandstone — Provenance Signal Detection',
};

export default function HomePage() {
  return (
    <>
      {/* SCREEN 1 — HERO */}
      <header className="hero">
        {/* LEFT: COPY */}
        <div className="hero-copy">
          <p className="eyebrow">Participation Over Permission</p>

          <h1>Granite<br />Under<br /><em>Sandstone</em></h1>

          <p className="hero-subtitle">
            Compression-amplified provenance signal detection<br />for digital media.
          </p>

          <blockquote className="quote-block">
            <span className="quote-line-1">The signal is not the perturbation.</span>
            <span className="quote-line-2">
              The signal is the system&apos;s response<br />to the perturbation over time.
            </span>
          </blockquote>

          <div className="hero-cta">
            <a href="#architecture" className="btn btn-primary">The Architecture</a>
            <a href="https://github.com/jeremy-pickett/granite" className="btn btn-secondary" target="_blank" rel="noopener">View on GitHub</a>
          </div>
        </div>

        {/* RIGHT: SEMPÉ ILLUSTRATION WINDOW */}
        <div className="illustration-column">
          <div className="scene-window">
            <div className="scene-paper">
              <HeroIllustration />
              <div className="scan-line" />
            </div>
            <div className="scene-frame" />
            <LayerBar />
          </div>
          <p className="scene-caption">courier over the city</p>
        </div>

        {/* SCORE STRIP */}
        <div className="score-strip">
          <div className="score-item">
            <span className="score-value">0.9988</span>
            <span className="score-label">marked mean</span>
          </div>
          <div className="score-divider" />
          <div className="score-item">
            <span className="score-value muted">0.0000</span>
            <span className="score-label">clean mean</span>
          </div>
          <div className="score-divider" />
          <div className="score-item">
            <span className="score-value amber">0.9988</span>
            <span className="score-label">gap</span>
          </div>
          <div className="score-divider" />
          <div className="score-item">
            <span className="score-value" style={{ fontSize: '1rem' }}>50 / 50 State B</span>
            <span className="score-label">combined harness &middot; 0 false positives</span>
          </div>
        </div>
      </header>

      {/* SCREEN 2 — WHAT IT IS + HOW IT WORKS */}
      <section className="section-what">
        <div className="section-figure">
          <SectionIllustration />
        </div>

        <div className="section-copy">
          <p className="section-eyebrow">What this is</p>
          <h2 className="section-heading">Proves<br />Participation</h2>
          <p className="section-body">
            A statistical perturbation scheme that embeds provenance signal into digital
            media. The signal survives aggressive JPEG compression &mdash; and strengthens under it.
            Marked corpus mean: 0.9988. Clean baseline mean: 0.0000. The distributions do
            not touch.
          </p>
          <p className="section-body">
            Not a watermark. Not steganography. Not DRM. Not a certificate authority.
            The signal proves participation. A matching service proves identity.
            These are different claims, and the difference matters.
          </p>
        </div>
      </section>

      <section className="section section-alt" id="how">
        <div className="container">
          <h2>How It Works</h2>

          <div className="pipeline">
            <div className="pipeline-step">
              <div className="step-number">1</div>
              <h3>Embed</h3>
              <p>At save time, force inter-channel distances at selected pixel positions to prime-valued gaps. Cost: ~0.01 joules. Imperceptible to the human eye.</p>
            </div>
            <div className="pipeline-arrow" aria-hidden="true" />
            <div className="pipeline-step">
              <div className="step-number">2</div>
              <h3>Compress</h3>
              <p>The codec&apos;s block-based quantization penalizes the perturbation&apos;s local complexity. Each generation <em>amplifies</em> the variance anomaly at marker positions.</p>
            </div>
            <div className="pipeline-arrow" aria-hidden="true" />
            <div className="pipeline-step">
              <div className="step-number">3</div>
              <h3>Detect</h3>
              <p>Measure statistical distributions at candidate vs. control positions. The image is its own control group. No reference image needed.</p>
            </div>
            <div className="pipeline-arrow" aria-hidden="true" />
            <div className="pipeline-step">
              <div className="step-number">4</div>
              <h3>Attribute</h3>
              <p>Positions derived from a 256-bit key via HMAC-SHA512. The position pattern is the fingerprint. C(4000,200) &asymp; 10<sup>400</sup> possible patterns.</p>
            </div>
          </div>

          <div className="fuse-fire">
            <div className="fuse">
              <h3>The Fuse</h3>
              <p>The prime values. Destroyed by the first compression. Engineering: format-specific, replaceable.</p>
            </div>
            <div className="fire">
              <h3>The Fire</h3>
              <p>The variance anomaly. Persists and amplifies. Physics: universal to any partition-transform-quantize system.</p>
            </div>
          </div>
        </div>
      </section>

      {/* SCREEN 3 — THE ARCHITECTURE */}
      <section className="section" id="architecture">
        <div className="container">
          <h2>Five Detection Layers</h2>
          <p className="lead">Defense in depth. Each layer operates independently in a different domain, with a validated operational range and honestly documented failure modes.</p>

          <div className="results-headline">
            <div className="stat">
              <span className="stat-number">98.6%</span>
              <span className="stat-label">Sentinel Survival</span>
              <span className="stat-detail">Layer E at Q40 &mdash; 500 images, &gt;99% any tier</span>
            </div>
            <div className="stat">
              <span className="stat-number">100%</span>
              <span className="stat-label">Payload Recovery</span>
              <span className="stat-detail">Layer F at Q40 &mdash; 800 images, margin 1.000</span>
            </div>
            <div className="stat">
              <span className="stat-number">0.998</span>
              <span className="stat-label">Combined Gap</span>
              <span className="stat-detail">Marked vs. clean &mdash; distributions do not touch</span>
            </div>
          </div>

          <div className="layers">
            <div className="layer">
              <div className="layer-num">A</div>
              <div className="layer-body">
                <h3>DQT Prime Tables</h3>
                <p>Replace JPEG quantization table entries with nearest primes. The table itself is the provenance signal. O(1) detection &mdash; scan 128 bytes without decoding. <strong>Operational: G0 only.</strong> Dies on any re-encode, which is expected: the absence of Layer A after processing is evidence of processing, not failure.</p>
              </div>
            </div>
            <div className="layer">
              <div className="layer-num">BC</div>
              <div className="layer-body">
                <h3>Compound Frequency Markers</h3>
                <p>Twin-prime markers at known positions with AND logic. <strong>Operational: G0&ndash;G2.</strong> Frequency signal degrades under aggressive compression &mdash; at G4 detection is near zero. This is an honest result: Layer BC is a near-field detector. OR logic was tested and rejected (raised false positive rate to ~22% on controls).</p>
              </div>
            </div>
            <div className="layer">
              <div className="layer-num">D</div>
              <div className="layer-body">
                <h3>Spatial Variance <span style={{ color: 'var(--amber)', fontSize: '.75rem', verticalAlign: 'middle' }}>&nbsp;CORROBORATING</span></h3>
                <p>KS test on local variance distributions. Blind &mdash; no reference image needed. Two prior versions failed: v1 measured JPEG&apos;s own blocking artifact (0.89 FP rate on clean images); v2 measured natural chromatic asymmetry (0.98 FP rate). <strong>Architectural constraint:</strong> Layer D enters the combined score only when a manifest-mode layer (E or F) has non-zero score. With this constraint, false positive rate collapses to 0%. Without it, Layer D cannot distinguish marked from naturally asymmetric images.</p>
              </div>
            </div>
            <div className="layer">
              <div className="layer-num">E</div>
              <div className="layer-body">
                <h3>Spanning Relational Sentinel</h3>
                <p>Mersenne-prime anchors (M=31 entry, M=7 exit) with correlated flanking pixels within 8&times;8 DCT blocks. The differential between positions survives when absolute values do not (intra-block correlation r=0.96 at Q40). Three detection tiers (T24/T16/T8) degrade gracefully. M=127 permanently excluded &mdash; 97.6% both-catastrophic rate due to JPEG&apos;s chroma gravity well at mid-range values. <strong>Operational: G0&ndash;G4.</strong> 98.6% at Q40, 28.4% tier demotion, &gt;99% effective at any tier. Validated on 500 images. Zero false State D across 250 image-generation combinations.</p>
              </div>
            </div>
            <div className="layer">
              <div className="layer-num">F</div>
              <div className="layer-body">
                <h3>Position-Based Payload</h3>
                <p>24-bit payload (creator ID, hash fragment, protocol version, flags) encoded in positional offsets from natural section boundaries. 2 bits per section, ~108 sections, ~9 votes per bit position via majority vote. Positions survive JPEG. Values do not. <strong>Operational: G0&ndash;G4.</strong> 800/800 images: 100% recovery on all fields, mean bit margin 1.000 (unanimous), zero uncertain bits at Q40. This is not robustness &mdash; it is invariance.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SCREEN 4 — VALIDATED RESULTS + DEEP DIVES */}
      <section className="section section-alt" id="results">
        <div className="container">
          <h2>Validated Results</h2>
          <p className="lead">All numbers from the DIV2K corpus through Q95 &rarr; Q85 &rarr; Q75 &rarr; Q60 &rarr; Q40 cascade. Codec: Pillow&apos;s libjpeg. No other implementations tested.</p>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Metric</th><th>Result</th><th>Corpus</th><th>Layer</th></tr>
              </thead>
              <tbody>
                <tr><td>Combined score &mdash; marked</td><td className="yes">0.9988</td><td>50 images</td><td>All (combined harness)</td></tr>
                <tr><td>Combined score &mdash; clean</td><td>0.0000</td><td>50 images</td><td>All (combined harness)</td></tr>
                <tr><td>False positives</td><td className="yes">0 / 50</td><td>50 images</td><td>All (combined harness)</td></tr>
                <tr><td>State B rate (800-image)</td><td className="yes">99.5% (796/800)</td><td>800 images</td><td>All</td></tr>
                <tr><td>FP rate (800-image)</td><td className="yes">0 / 800</td><td>800 images</td><td>All</td></tr>
                <tr><td>Sentinel T24 intact at Q40</td><td className="yes">98.6%</td><td>500 images</td><td>E</td></tr>
                <tr><td>Effective detection (any tier)</td><td className="yes">&gt;99%</td><td>500 images</td><td>E</td></tr>
                <tr><td>False State D</td><td className="yes">0 / 250 combinations</td><td>500 images</td><td>E</td></tr>
                <tr><td>CID recovery at Q40</td><td className="yes">100% (800/800)</td><td>800 images</td><td>F</td></tr>
                <tr><td>Payload bit margin at Q40</td><td className="yes">1.000 (unanimous)</td><td>800 images</td><td>F</td></tr>
                <tr><td>Uncertain bits</td><td className="yes">0</td><td>800 images</td><td>F</td></tr>
                <tr><td>DQT detection at G0</td><td className="yes">100%</td><td>All</td><td>A</td></tr>
                <tr><td>Layer BC at G4</td><td>~0% (near chance)</td><td>500 images</td><td>BC</td></tr>
              </tbody>
            </table>
          </div>

          <h3>Known Limitations</h3>
          <div className="grid-2" style={{ marginTop: '1rem' }}>
            <div className="card card-dark">
              <h3>Not Yet Characterized</h3>
              <p>Geometric transforms (rotation, non-integer scaling, affine). Neural codecs (HEIC, AVIF). Quality below Q10. Codec implementations beyond Pillow&apos;s libjpeg (MozJPEG, libjpeg-turbo, hardware encoders).</p>
            </div>
            <div className="card card-dark">
              <h3>Honest Scope</h3>
              <p>50-image FP confidence interval upper bound: 5.8%. 800-image bound: 0.36%. Neither sufficient for production at scale without further validation. Layer D cannot stand alone. Layer BC is not effective past Q75.</p>
            </div>
          </div>

          {/* Deep Dives */}
          <h3 style={{ marginTop: '4rem' }}>Deep Dives</h3>
          <p>The full technical documentation, design history, and proofs behind every claim on this page.</p>

          <div className="grid-3" style={{ marginTop: '1.5rem' }}>
            <Link href="/docs/design-history" className="card card-dark" style={{ textDecoration: 'none' }}>
              <h3>Design History</h3>
              <p>Six wrong assumptions, the M=127 gravity well, relational encoding, and how every failure became a feature.</p>
            </Link>
            <Link href="/docs/addendum-l-spanning-sentinel" className="card card-dark" style={{ textDecoration: 'none' }}>
              <h3>The Spanning Sentinel</h3>
              <p>Layer E: from flat-line failure to 98.6% survival. The relational encoding breakthrough.</p>
            </Link>
            <Link href="/docs/addendum-k-fuse-and-fire" className="card card-dark" style={{ textDecoration: 'none' }}>
              <h3>Fuse &amp; Fire</h3>
              <p>Formal definitions, novelty assessment, and why compression is the amplifier, not the enemy.</p>
            </Link>
            <Link href="/docs/addendum-g-known-attacks" className="card card-dark" style={{ textDecoration: 'none' }}>
              <h3>Known Attacks</h3>
              <p>Rotation, slice-and-stitch, scale, Ship of Theseus. What survived, what broke, and the economics of suppression.</p>
            </Link>
            <Link href="/docs/addendum-h-thar-be-dragons" className="card card-dark" style={{ textDecoration: 'none' }}>
              <h3>Thar Be Dragons</h3>
              <p>Seven failure modes and open problems. Seed compromise, no revocation, no forward secrecy &mdash; by design.</p>
            </Link>
            <Link href="/history" className="card card-dark" style={{ textDecoration: 'none' }}>
              <h3>The Full Story</h3>
              <p>Part I: Discovery. Part II: Validation. Built in a single sustained conversation between a human and an AI.</p>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
