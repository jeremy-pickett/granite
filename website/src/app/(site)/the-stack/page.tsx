import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'The Stack — Granite Under Sandstone',
};

export default function TheStackPage() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Layer-by-Layer</p>
          <h1>The Stack</h1>
          <p className="hero-subtitle">Seven detection layers. Each one tested, characterized, and documented with honest results.</p>
        </div>
      </header>

      <section className="section">
        <div className="container">
          <h2>Cross-Layer Competency Matrix</h2>
          <p className="lead">Which attacks each layer handles independently, cooperatively, or not at all.</p>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Attack / Transform</th>
                  <th>A</th><th>BC</th><th>D</th><th>E</th><th>F</th><th>G</th><th>H</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>JPEG Q85 survival</td>        <td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td></tr>
                <tr><td>JPEG Q40 survival</td>        <td className="yes">✓</td><td>○</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td></tr>
                <tr><td>JPEG Q30 survival</td>        <td>○</td><td>✗</td><td>○</td><td>○</td><td>○</td><td>○</td><td className="yes">✓</td></tr>
                <tr><td>Arbitrary rotation</td>        <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>○</td><td className="yes">✓</td><td>&mdash;</td></tr>
                <tr><td>Horizontal crop</td>           <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td></tr>
                <tr><td>Vertical crop</td>             <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td></tr>
                <tr><td>Both-axis crop</td>            <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>○</td></tr>
                <tr><td>Image stitch detection</td>    <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td></tr>
                <tr><td>Dimension recovery</td>        <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td></tr>
                <tr><td>Sentinel removal (VOID)</td>   <td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td><td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td><td>&mdash;</td></tr>
                <tr><td>Format-level tampering</td>    <td className="yes">✓</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td></tr>
                <tr><td>Pixel-layer tampering</td>     <td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td></tr>
                <tr><td>Participation proof</td>       <td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td><td className="yes">✓</td></tr>
                <tr><td>Payload recovery</td>          <td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td className="yes">✓</td><td>○</td><td>○</td></tr>
              </tbody>
            </table>
          </div>
          <p style={{ marginTop: '1rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            <span className="yes">✓</span> Handles independently &nbsp;&nbsp;
            ○ Partial / cooperative &nbsp;&nbsp;
            ✗ Cannot handle &nbsp;&nbsp;
            &mdash; Not applicable
          </p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container">
          <h2>The Layers</h2>
          <p className="lead">Select a layer for its full specification, detection algorithm, test results, and known limitations.</p>

          <div className="grid-3" style={{ marginTop: '2rem' }}>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Layer A &mdash; DQT Prime Tables</h3>
              <p>Container-level provenance. Replace quantization table entries with nearest primes. O(1) detection &mdash; scan 128 bytes. Dies on re-encode by design.</p>
            </div>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Layer BC &mdash; Compound Frequency</h3>
              <p>Twin-prime gap markers at known positions with AND logic. Near-field detector: operational G0&ndash;G2, near zero at G4.</p>
            </div>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Layer D &mdash; Spatial Variance</h3>
              <p>KS test on local variance distributions. Blind &mdash; no reference needed. Cannot stand alone: enters combined score only when Layer E or F fires.</p>
            </div>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Layer E &mdash; Spanning Sentinel</h3>
              <p>Mersenne-prime anchors with relational encoding. 98.6% at Q40, tiered degradation, zero false State D. The breakthrough layer.</p>
            </div>
            <div className="doc-card">
              <span className="doc-tag coming">Coming</span>
              <h3>Layer F &mdash; Position Payload</h3>
              <p>24-bit payload in positional offsets. 800/800 recovery at Q40, mean bit margin 1.000. Not robustness &mdash; invariance.</p>
            </div>
            <Link href="/the-stack/layer-g" className="doc-card" style={{ textDecoration: 'none' }}>
              <span className="doc-tag guide">Spec</span>
              <h3>Layer G &mdash; Halo</h3>
              <p>Radial lensing around sentinel centers. Rotation-resilient detection and VOID state after deliberate removal. 100% survival at all tested angles.</p>
            </Link>
            <Link href="/the-stack/layer-h" className="doc-card" style={{ textDecoration: 'none' }}>
              <span className="doc-tag guide">Spec</span>
              <h3>Layer H &mdash; Spatial Ruler</h3>
              <p>Crop and stitch forensics. Embeds a spatial reference frame that recovers original dimensions even after aggressive cropping. Zero bit errors Q30&ndash;Q95.</p>
            </Link>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">

          <h2>System Model and Evidentiary Claims</h2>

          <p className="lead">GRANITE is an anti-scrubbing evidentiary lattice for image provenance. That phrase is precise and each word is load-bearing.</p>

          <div className="table-wrap" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr><th>Term</th><th>What It Means Here</th></tr>
              </thead>
              <tbody>
                <tr><td><strong>Anti-scrubbing</strong></td><td>The system is not designed to survive all possible attacks. It is designed so that the act of removing it produces interpretable evidence of the removal. The goal is not invulnerability. The goal is that removal tells on itself.</td></tr>
                <tr><td><strong>Evidentiary</strong></td><td>The system produces signals that may support an inference of deliberate suppression. It does not prove intent. It produces a record from which inferences may be drawn, subject to further analysis and appropriate legal caution.</td></tr>
                <tr><td><strong>Lattice</strong></td><td>Multiple independent layers, each covering different attack surfaces, each providing evidence even when peers fail. No single layer is authoritative. The lattice as a whole is more than any individual layer.</td></tr>
              </tbody>
            </table>
          </div>

          <blockquote style={{ marginTop: '2rem' }}>
            <p><em>The security community scores provenance systems like DRM: &ldquo;Can I strip it?&rdquo; The honest answer is yes &mdash; a sufficiently motivated adversary with sufficient knowledge can strip any steganographic system. That is the wrong battleground. GRANITE&rsquo;s battleground is this: &ldquo;Can you strip it without the stripping being interpretable?&rdquo; That is a harder problem, and it is the problem this system actually solves.</em></p>
          </blockquote>

        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">

          <h2>Positioning Within the Literature</h2>
          <p>This system belongs to an established research category. The construction is novel; the category is not. Claiming otherwise would be imprecise and unhelpful.</p>

          <div className="grid-2" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark">
              <h3>What Has Prior Art</h3>
              <p><strong>Response-based signal detection.</strong> Using what a compressor does to a signal as the detection surface is explicit in Bianchi and Piva&rsquo;s double-JPEG detection work.</p>
              <p><strong>PRNU and forensic fingerprinting.</strong> Statistical signals embedded in image content that survive pipeline transforms and produce forensic evidence of modification.</p>
              <p><strong>Steganalysis-aware embedding.</strong> Any competent reviewer will evaluate this system against cover-model divergence, chi-squared attacks, and ensemble classifiers. This is expected.</p>
            </div>
            <div className="card card-dark">
              <h3>What Is Novel in Construction</h3>
              <p><strong>Twin prime gap markers</strong> whose divergence is amplified rather than suppressed by JPEG quantization (&ldquo;granite under sandstone&rdquo;).</p>
              <p><strong>Four observable states</strong> (A/B/C/D) as a formal response taxonomy, distinguishing benign degradation from targeted suppression.</p>
              <p><strong>Two-zone radial lensing</strong> (Layer G) providing rotation-resilient detection with a void state that outlives the embedded sentinel.</p>
              <p><strong>Spatial ruler</strong> (Layer H) providing crop and stitch forensics independently of all other layers.</p>
            </div>
          </div>

          <p style={{ marginTop: '1.5rem' }}><em>The correct category claim: this system applies response-based, multi-layer forensic provenance methods with novel construction choices designed to make the damage pattern interpretable across a range of adversarial transforms. It does not claim to invent the category.</em></p>

        </div>
      </section>

      <section className="section">
        <div className="container">

          <h2>Three Outcome Classes</h2>
          <p className="lead">Every marked image, after any transform or handling, produces a signal pattern classifiable into one of three outcome classes. These classes are the fundamental vocabulary of GRANITE forensics.</p>

          <div className="grid-3" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--pass)' }}>
              <h3 style={{ color: 'var(--pass)' }}>Class 1 &mdash; Benign Degradation</h3>
              <p><strong>Mechanism:</strong> Lossy compression, format conversion, legitimate processing pipeline.</p>
              <p><strong>Interpretation:</strong> Participation proven. Signal degraded uniformly and consistently with known codec behavior. Chain-of-custody intact. No inference of deliberate intervention is supported.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--amber)' }}>
              <h3 style={{ color: 'var(--amber)' }}>Class 2 &mdash; Opaque Destruction</h3>
              <p><strong>Mechanism:</strong> Unknown catastrophic transform, severe corruption, total format conversion.</p>
              <p><strong>Interpretation:</strong> Indeterminate. Total absence of all layers is consistent with extreme benign degradation. Cannot be reliably distinguished from Class 1 at the extreme without additional context.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--tamper)' }}>
              <h3 style={{ color: 'var(--tamper)' }}>Class 3 &mdash; Targeted Suppression</h3>
              <p><strong>Mechanism:</strong> Selective removal of specific layers while others are preserved or degraded differently.</p>
              <p><strong>Interpretation:</strong> Incoherent collapse pattern. Inconsistent with any single known transform. May support an inference of deliberate suppression. Requires further analysis; does not independently establish intent.</p>
            </div>
          </div>

          <p style={{ marginTop: '1.5rem' }}>The middle class is the most legally and forensically important. Class 3 is structurally different: random damage does not produce selectively absent layers. Randomness produces coherent collapse. Incoherent collapse &mdash; where some layers are intact and others are absent in a pattern inconsistent with any single known transform &mdash; is not a natural artifact.</p>

          <blockquote>
            <p><em>The goal of the system is not that individual layers survive. The goal is that one or more layers survive casual and semi-competent handling, while deliberate multi-layer removal becomes interpretable as evidence of the removal itself.</em></p>
          </blockquote>

        </div>
      </section>

      <section className="section section-alt">
        <div className="container">

          <h2>Attack Signature Taxonomy</h2>
          <p className="lead">Per-layer signatures across the three outcome classes. The composite row is the key forensic discriminator.</p>

          <div className="table-wrap" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr><th>Layer</th><th style={{ color: 'var(--pass)' }}>Class 1 &mdash; Benign</th><th style={{ color: 'var(--amber)' }}>Class 2 &mdash; Opaque</th><th style={{ color: 'var(--tamper)' }}>Class 3 &mdash; Targeted</th></tr>
              </thead>
              <tbody>
                <tr><td><strong>A &nbsp;Container</strong></td><td>DQT tables present, degraded</td><td>DQT absent or corrupt</td><td>DQT selectively zeroed; other tables intact</td></tr>
                <tr><td><strong>BC Frequency</strong></td><td>Twin prime density reduced</td><td>Uniform noise floor</td><td>Prime-gap markers inverted; DC intact</td></tr>
                <tr><td><strong>D &nbsp;Spatial</strong></td><td>KS statistic elevated uniformly</td><td>Indeterminate</td><td>Localized anomaly near embedding sites</td></tr>
                <tr><td><strong>E &nbsp;Sentinel</strong></td><td>State C: values drifted</td><td>State A: total absence</td><td>State D: positions scrambled; values removed</td></tr>
                <tr><td><strong>F &nbsp;Payload</strong></td><td>Partial bit recovery; no fault</td><td>Zero recovery; no fault</td><td>Zero recovery + E/D inconsistency</td></tr>
                <tr><td><strong>G &nbsp;Halo</strong></td><td>VOID state from compression</td><td>ABSENT state</td><td>ABSENT inner, elevated outer (force arrow)</td></tr>
                <tr><td><strong>H &nbsp;Ruler</strong></td><td>Band survives; dim recovers</td><td>No band signal detected</td><td>Bands selectively absent; others intact</td></tr>
                <tr style={{ borderTop: '2px solid var(--amber)' }}><td><strong>Composite</strong></td><td>Coherent collapse across layers</td><td>Total absence; indeterminate</td><td style={{ color: 'var(--tamper)' }}>Incoherent collapse; layer-specific residue</td></tr>
              </tbody>
            </table>
          </div>

          <p style={{ marginTop: '1.5rem' }}>Global recompression produces a coherent signal: all layers degrade together in a pattern consistent with a single quantization pass. Targeted suppression produces an incoherent signal: Layer A absent while Layer H intact, or Layer E in State D while Layer G reports ABSENT (not VOID). These combinations have no innocent explanation.</p>

        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">

          <h2>Layer D Operating Modes</h2>
          <p>Layer D (Spatial KS Variance) operates differently depending on whether the embedding manifest is available. This is explicitly distinct from all other layers.</p>

          <div className="grid-2" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark" style={{ borderLeft: '3px solid var(--teal)' }}>
              <h3><span style={{ color: 'var(--teal)' }}>&bull;</span> Blind Mode &mdash; No Manifest</h3>
              <p>Layer D is the <strong>primary signal</strong>. The KS variance anomaly is detectable without knowing where markers were placed, what payload was used, or what session produced the image. This is the most important property of Layer D: it functions as a forensic scanner without any prior knowledge of the marked image.</p>
            </div>
            <div className="card card-dark" style={{ borderLeft: '3px solid var(--amber)' }}>
              <h3><span style={{ color: 'var(--amber)' }}>○</span> Manifest Mode &mdash; Record Known</h3>
              <p>Layer D is <strong>corroborating evidence</strong>. When the manifest is known, Layer D confirms the spatial anomaly at expected positions, with expected magnitude and direction. The sentinel contract (Layer E) is primary. Layer D adds weight but does not independently establish the claim.</p>
            </div>
          </div>

          <p style={{ marginTop: '1.5rem' }}><em>These two roles cannot both be primary simultaneously. Any analysis that presents Layer D must specify which mode it is describing.</em></p>

        </div>
      </section>

      <section className="section section-alt">
        <div className="container">

          <h2>Legal Language Conventions</h2>
          <p className="lead">The system produces statistical signals from which inferences may be drawn. It does not establish intent. It does not independently prove deliberate suppression.</p>

          <div className="table-wrap" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr><th>Context</th><th style={{ color: 'var(--pass)' }}>Use This</th><th style={{ color: 'var(--tamper)' }}>Not This</th></tr>
              </thead>
              <tbody>
                <tr><td>Selective layer removal</td><td><em>may support an inference of deliberate suppression</em></td><td><em>proves tampering / shows intent</em></td></tr>
                <tr><td>Incoherent collapse pattern</td><td><em>is inconsistent with benign degradation</em></td><td><em>proves targeted removal</em></td></tr>
                <tr><td>Anti-forensic signature</td><td><em>the pattern is consistent with coordinated suppression</em></td><td><em>demonstrates malicious intent</em></td></tr>
                <tr><td>Zero payload recovery</td><td><em>the payload was not recovered; this may indicate removal</em></td><td><em>the payload was destroyed deliberately</em></td></tr>
                <tr><td>Force-arrow VOID state</td><td><em>the halo field remains, consistent with localized removal</em></td><td><em>the adversary removed the sentinel</em></td></tr>
                <tr><td>Corroborating Layer D</td><td><em>Layer D provides additional support for this inference</em></td><td><em>Layer D confirms the attack</em></td></tr>
              </tbody>
            </table>
          </div>

          <blockquote style={{ marginTop: '1.5rem' }}>
            <p><em>Use &ldquo;may support an inference of deliberate suppression&rdquo; far more often than &ldquo;shows intent&rdquo; or &ldquo;proves tampering.&rdquo; An overreach that a reviewer can refute damages the entire paper. A careful inferential claim is difficult to attack.</em></p>
          </blockquote>

        </div>
      </section>

      <section className="section">
        <div className="container">
          <h2>Layer Integration</h2>
          <p className="lead">Each layer provides outputs to and consumes inputs from the stack. The dependency flows from the outermost container layer inward.</p>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Layer</th><th>Provides To Stack</th><th>Depends On</th></tr>
              </thead>
              <tbody>
                <tr><td><strong>A &nbsp;Container</strong></td><td>Format tamper detection, M=31 sentinel anchor</td><td>None &mdash; operates on raw JPEG tables</td></tr>
                <tr><td><strong>BC Frequency</strong></td><td>Twin prime gap markers, cascade-resilient compound signal</td><td>Layer A (floor constant, M=31 exclusion)</td></tr>
                <tr><td><strong>D &nbsp;Spatial</strong></td><td>KS variance anomaly; blind-mode primary signal; manifest-mode corroboration</td><td>Layer BC (pixel field to measure)</td></tr>
                <tr><td><strong>E &nbsp;Sentinel</strong></td><td>State B/C/D classification, spanning relational proof</td><td>Layers A&ndash;D (composite signal)</td></tr>
                <tr><td><strong>F &nbsp;Payload</strong></td><td>24-bit session payload recovery at Q40</td><td>Layer E (sentinel positions for offset encoding)</td></tr>
                <tr><td><strong>G &nbsp;Halo</strong></td><td>Rotation-resilient detection, VOID state after removal</td><td>Layer F (sentinel centers as halo origins)</td></tr>
                <tr><td><strong>H &nbsp;Ruler</strong></td><td>Crop/stitch forensics, original dimension recovery</td><td>None &mdash; operates independently on image geometry</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </>
  );
}
