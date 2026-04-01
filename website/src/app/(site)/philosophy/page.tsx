import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Philosophy — Granite Under Sandstone',
};

export default function PhilosophyPage() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Axiomatic Fictions Series</p>
          <h1>Participation Over Permission</h1>
          <p className="hero-subtitle">The philosophy of provenance without authority</p>
        </div>
      </header>

      <section className="section" id="core">
        <div className="container content-narrow">
          <h2>The Core Argument</h2>
          <p className="lead">Provenance should not require anyone&rsquo;s permission to embed or detect. It proves that someone <em>participated</em> in marking content, rather than requiring institutional gatekeeping.</p>

          <p>Every existing approach to media provenance &mdash; watermarking, DRM, certificate authorities, blockchain registries &mdash; requires infrastructure. Someone must run the servers. Someone must issue the certificates. Someone must maintain the ledger. And whoever controls that infrastructure controls who gets to prove what.</p>

          <p>Granite Under Sandstone takes a different path. The provenance signal lives in the statistical properties of the file itself. No servers. No certificates. No ledger. No permission required.</p>

          <blockquote>
            <p>The signal is not the perturbation. The signal is the system&rsquo;s response to the perturbation over time.</p>
          </blockquote>

          <p>The default is always <em>no provenance</em>. The user or operator must explicitly choose to inject. The system never forces behavior. It creates measurements, not mandates.</p>
        </div>
      </section>

      <section className="section section-alt" id="identity">
        <div className="container content-narrow">
          <h2>What This Is. What This Is Not.</h2>

          <div className="two-col-compare">
            <div className="col-is">
              <h3>This IS</h3>
              <ul>
                <li>Statistical provenance signal</li>
                <li>Transformation-resilient</li>
                <li>Population-scale detection mechanism</li>
                <li>Weak chain-of-custody indicator</li>
                <li>A thermodynamic fact about compression</li>
              </ul>
            </div>
            <div className="col-isnt">
              <h3>This is NOT</h3>
              <ul>
                <li>DRM</li>
                <li>Cryptographic proof of ownership</li>
                <li>An identity system</li>
                <li>A tamper-proof watermark</li>
                <li>An enforcement mechanism</li>
              </ul>
            </div>
          </div>

          <p>The system creates four observable states for any piece of media:</p>

          <div className="states-grid">
            <div className="state">
              <div className="state-label">State A</div>
              <p>No signal, no claim. Safe default. The vast majority of media.</p>
            </div>
            <div className="state">
              <div className="state-label">State B</div>
              <p>Signal present, coherent. Provenance intent exists, preserved through handling.</p>
            </div>
            <div className="state">
              <div className="state-label">State C</div>
              <p>Signal degraded. Consistent with benign transforms &mdash; resizing, format conversion, normal platform processing.</p>
            </div>
            <div className="state state-d">
              <div className="state-label">State D</div>
              <p>Signal interfered. Inconsistent degradation, selective removal, replacement artifacts. Someone tried to remove it.</p>
            </div>
          </div>

          <blockquote>
            <p>Today: &ldquo;We don&rsquo;t know where this came from.&rdquo;<br />
            With this system: &ldquo;We detected a provenance signal and classified its handling behavior.&rdquo;<br />
            That&rsquo;s enough to change decisions.</p>
          </blockquote>
        </div>
      </section>

      <section className="section" id="economics">
        <div className="container content-narrow">
          <h2>The Economics of Provenance</h2>
          <p className="lead">A self-described Keynesian accidentally built something Milton Friedman would love.</p>

          <p>The uncomfortable realization at the heart of this project: the scheme protects creators by making it <em>profitable</em> for third parties to protect creators. Not through regulation. Not through mandate. Through incentive alignment.</p>

          <p>Detection is cheap. Embedding is cheap. The code is open. The method is published. Anyone can build on it. This creates a market:</p>

          <div className="econ-cards">
            <div className="card">
              <h3>The Creator</h3>
              <p>Embeds a provenance signal at save time. Cost: negligible. No subscription, no service, no account required. The signal rides with the file forever.</p>
            </div>
            <div className="card">
              <h3>The Third Party</h3>
              <p>Builds detection, matching, and attribution services. The open standard creates a market for these services. Competition drives quality up and cost down. The average broke creator doesn&rsquo;t need to pay &mdash; but has the choice.</p>
            </div>
            <div className="card">
              <h3>The Adversary</h3>
              <p>Must perform pipeline-level reconstruction of the perturbation field to remove the signal. Cost explodes. Artifacts accumulate. General-purpose transforms no longer suffice. And the attempt itself is forensically detectable.</p>
            </div>
          </div>

          <blockquote>
            <p>The scheme protects creators by making it profitable for third parties to protect creators. Do you understand how profound that is?</p>
          </blockquote>

          <p>This is the &ldquo;Someone Else&rsquo;s Problem&rdquo; rule turned on its head. By making detection cheap and open, third parties have economic incentive to build matching and attribution services. The system never handles identity. It creates the conditions where identity services become profitable.</p>

          <p>It&rsquo;s free to pass through. It&rsquo;s expensive to strip out. And attempting removal opens the adversary to both criminal and civil liability. The economics are self-reinforcing.</p>
        </div>
      </section>

      <section className="section section-alt" id="matching">
        <div className="container content-narrow">
          <h2>The Matching Service Ecosystem</h2>
          <p className="lead">Without matching services, provenance is a message in a bottle. With them, it&rsquo;s a market.</p>

          <p>The provenance signal solves half the problem: it proves that someone participated in marking a piece of media. But without active monitoring, the creator embeds their signal and then&hellip; waits. Hopes someone uses their file. Hopes they discover it. Hopes they can prove the match. That&rsquo;s not scalable. That&rsquo;s a message in a bottle.</p>

          <p>Matching services close the loop. And because the detection method is open, <em>anyone</em> can build one.</p>

          <div className="econ-cards">
            <div className="card">
              <h3>Probabilistic Triage, Not Deterministic Cert</h3>
              <p>A matching service doesn&rsquo;t issue certificates. It performs probabilistic triage &mdash; scanning at corpus scale, ranking by Jaccard similarity, flagging likely matches. The service triages. The human decides.</p>
            </div>
            <div className="card">
              <h3>Rotation-Invariant Search</h3>
              <p>Platforms don&rsquo;t usually rotate images 15 degrees. Scrapers and &ldquo;laundry services&rdquo; do. A matching service needs to search not just for the fingerprint map, but for the map at every possible angle and scale. The compute cost is the service&rsquo;s problem, not the creator&rsquo;s.</p>
            </div>
            <div className="card">
              <h3>Temporal Stratigraphy</h3>
              <p>When multiple provenance layers exist in the same file &mdash; Alice embeds, Bob re-embeds &mdash; the differential match quality proves chronological order. Like geological strata, the oldest layer is deepest. First-in has priority.</p>
            </div>
          </div>

          <p>This is the &ldquo;Someone Else&rsquo;s Problem&rdquo; rule, named with full awareness of the irony. The system doesn&rsquo;t manage identities. It doesn&rsquo;t run matching infrastructure. It doesn&rsquo;t handle disputes. It creates the economic conditions where all of those services become <em>profitable for someone else to build</em>.</p>

          <blockquote>
            <p>It&rsquo;s not prime gap&rsquo;s job to manage identities. But you <em>can</em> use timestamps, and First In is probably a good recommendation.</p>
          </blockquote>

          <p>The average broke creator doesn&rsquo;t need to pay for a matching service. But they have the choice. And because detection is cheap and the standard is open, competition between services drives quality up and cost down. The creator&rsquo;s only cost is embedding &mdash; which is functionally free.</p>
        </div>
      </section>

      <section className="section" id="thermodynamics">
        <div className="container content-narrow">
          <h2>The Thermodynamic Tax</h2>
          <p className="lead">Adversarial resistance is not a cryptographic problem. It&rsquo;s an economic one.</p>

          <p>Removing the provenance signal requires more computational energy &mdash; more joules, more heat &mdash; than embedding or passing it through. This creates a thermal limit analogous to proof-of-work costs in cryptocurrency mining:</p>

          <ul className="principle-list">
            <li><strong>Embedding</strong> costs ~0.01 joules. A rounding error.</li>
            <li><strong>Passing through</strong> costs nothing extra. Normal compression, normal transcoding. The signal rides for free.</li>
            <li><strong>Removing</strong> requires reconstructing the perturbation field across every block, every channel, every quantization boundary. The cost scales with image complexity.</li>
          </ul>

          <p>The system incentivizes serving authentic, unaltered provenance files. And disincentivizes rewriting provenance. It&rsquo;s free to pass, it&rsquo;s expensive to strip, and the attempt leaves scars.</p>

          <blockquote>
            <p>Any system that compresses reality must assume a model of reality. Anything that violates that model becomes detectable under that system&rsquo;s optimization pressure.</p>
          </blockquote>

          <p>This is not unique to JPEG. Any codec that uses a <strong>partition &rarr; transform &rarr; quantize</strong> pipeline creates the same asymmetry. MP3, H.264, HEIF, AV1 &mdash; the mechanism is universal because the physics is universal.</p>
        </div>
      </section>

      <section className="section section-alt" id="trust">
        <div className="container content-narrow">
          <h2>Trust Without Authority</h2>

          <p>The system makes no claims about truth. It produces measurements. What those measurements mean is a human decision, made in context, with uncertainty acknowledged.</p>

          <div className="principles">
            <div className="principle">
              <h3>No forced behavior</h3>
              <p>The system warns, never blocks. If a user wants to do something inadvisable, they pass an explicit flag. This is not the Saw franchise &mdash; we don&rsquo;t force anyone&rsquo;s hand.</p>
            </div>
            <div className="principle">
              <h3>Full adversary knowledge assumed</h3>
              <p>Every piece of information except the exact seed and the exact basket must be assumed compromised. The code is open. The method is published. Security through obscurity is not security.</p>
            </div>
            <div className="principle">
              <h3>Failures must not be silent</h3>
              <p>When things go wrong, the system says so. Loudly. Clearly. With enough context to understand why.</p>
            </div>
            <div className="principle">
              <h3>The image is its own control group</h3>
              <p>Detection compares marker positions against control positions in the same image. No reference image. No database lookup. No phone home. The evidence travels with the file.</p>
            </div>
          </div>

          <blockquote>
            <p>The two most important statements in human history are: &ldquo;I don&rsquo;t know,&rdquo; and &ldquo;That&rsquo;s odd.&rdquo;</p>
          </blockquote>
        </div>
      </section>

      <section className="section" id="giants">
        <div className="container content-narrow">
          <h2>Shoulders of Giants</h2>

          <p>None of the individual components here are new. Prime number theory is ancient. DCT-based compression is well-understood. Statistical hypothesis testing is textbook. Quantization artifacts have been studied for decades.</p>

          <p>The contribution is the <em>system</em> &mdash; the recognition that these pieces fit together in a way that creates emergent behavior no individual piece exhibits alone.</p>

          <blockquote>
            <p>I am going to assume that each individual piece is probably known to someone at some time, but they may not have grokked how it can work as a cog to solve a larger problem. Like teeth in a gear. The idea of teeth isn&rsquo;t new at all. Variable gears with differential teeth strategies are though.</p>
          </blockquote>

          <blockquote>
            <p>Shoulders of giants, man. Shoulders of giants.</p>
          </blockquote>

          <p className="closing-line">I want Whitfield Diffie to be proud of me.</p>
        </div>
      </section>
    </>
  );
}
