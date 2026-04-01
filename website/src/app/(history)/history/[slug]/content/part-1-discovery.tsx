import Link from 'next/link';

export default function Part1DiscoveryContent() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Part I &middot; Chapters I&ndash;VII</p>
          <h1>Discovery</h1>
          <p className="hero-subtitle">From a hand on a keyboard to the central breakthrough</p>
        </div>
      </header>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">I</span>
            <h2>The Detector</h2>
            <p className="chapter-subtitle">It started with a hand on a keyboard</p>
          </div>

          <p>Jeremy was about to open vim and start hand-coding a prime-gap artifact detector. A tool to sniff out statistical fingerprints in compressed media and start gathering data on false positive rates. &ldquo;We assume it&rsquo;s low, but we don&rsquo;t know.&rdquo;</p>

          <p>He took his hands off the keyboard. Not because the idea was wrong, but because the implementation would be faster with a collaborator who was, by his own admission, a better Python coder.</p>

          <p>The initial concept: embed primes into digital media files and detect their statistical fingerprint after compression. Simple in statement. The devil was in every detail that followed.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">II</span>
            <h2>The False Positive Problem</h2>
            <p className="chapter-subtitle">JPEG was tripping the detector. On purpose.</p>
          </div>

          <p>The first major obstacle: JPEG&rsquo;s own structure was generating prime-gap patterns that looked like embedded signals. The detector couldn&rsquo;t tell the difference between a planted canary and a structural coincidence.</p>

          <p>The fix came from an analogy to cryptography. Small primes are dangerous &mdash; Diffie-Hellman with tiny key spaces is catastrophically weak. The same principle applied here.</p>

          <blockquote>
            <p>Drop every prime in the basket under 256. The simplest will absolutely get us in trouble. See Diffie-Hellman and how problematic it is with tiny key spaces.</p>
          </blockquote>

          <p>This wasn&rsquo;t just a parameter tweak. It was the first instance of a pattern that would repeat throughout the project: the answer was always in making the <em>injector</em> smarter, not the detector.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">III</span>
            <h2>The Smart Embedder</h2>
            <p className="chapter-subtitle">&ldquo;The injector does the homework so the detector doesn&rsquo;t have to.&rdquo;</p>
          </div>

          <p>Rather than building an ever-more-sophisticated detector that could distinguish real signals from structural artifacts, the approach inverted: make the embedding process so well-informed that it only places markers where they&rsquo;ll survive and where they can&rsquo;t be confused with natural patterns.</p>

          <p>This led to file-type profiles &mdash; JPEG, PNG, WebP, Audio &mdash; each with its own understanding of where injection targets live, what survives compression, and what the entropy landscape looks like. The embedder started doing reconnaissance before placing a single marker.</p>

          <p>The &ldquo;Douglas Rule&rdquo; emerged here: a prime value only counts as a marker if it&rsquo;s adjacent to a magic byte (42). If it&rsquo;s not next to that sentinel, it&rsquo;s not ours. Named, naturally, after the answer to life, the universe, and everything.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">IV</span>
            <h2>Strategy 4: The Quantization Tables</h2>
            <p className="chapter-subtitle">What if the table itself is the signal?</p>
          </div>

          <p>A question that changed the architecture: what sections of a JPEG file <em>must</em> be retained during compression? The answer: the DQT &mdash; the quantization table. Without it, the decoder can&rsquo;t reconstruct the image.</p>

          <blockquote>
            <p>Oh okay then let&rsquo;s shift that section to its closest large prime. That&rsquo;s Strategy 4.</p>
          </blockquote>

          <p>This became Layer 1. Replace quantization table entries with nearest primes. The table itself carries the provenance signal. It <em>must</em> survive re-encoding because the codec depends on it. Double-quantization artifacts reveal its history.</p>

          <p>A signal that the codec is contractually obligated to preserve.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">V</span>
            <h2>The Fuse and the Fire</h2>
            <p className="chapter-subtitle">The moment everything changed</p>
          </div>

          <p>Testing multi-generation JPEG cascades &mdash; Q95 down to Q85 down to Q75 down to Q60 down to Q40 &mdash; Jeremy noticed something that shouldn&rsquo;t have been possible:</p>

          <blockquote>
            <p>Wait wait wait, the more you try to hide through compression the more the canaries stick out?</p>
          </blockquote>

          <p>The prime values themselves &mdash; the <em>fuse</em> &mdash; were destroyed by the first compression pass. That was expected. But the variance anomaly they created &mdash; the <em>fire</em> &mdash; didn&rsquo;t just survive. It <em>amplified</em>.</p>

          <p>The explanation: the markers were placed by a process that doesn&rsquo;t respect spatial coherence. The natural pixels were placed by a camera that does. Compression doesn&rsquo;t care about the values. It finds the structural difference and <em>reveals it</em>. Each quantization pass is another round of the same optimization pressure, and each round makes the anomaly more pronounced.</p>

          <blockquote>
            <p>It is a granite block under sandstone that the ocean keeps hitting it and hitting it and hitting it. And what does it leave? The granite, not the sandstone.</p>
          </blockquote>

          <p>This was the central breakthrough of the entire project. The perturbation is the fuse &mdash; engineering, format-specific, replaceable. The variance anomaly is the fire &mdash; physics, universal to any partition-transform-quantize system. The fuse starts the fire. The fire is self-sustaining.</p>

          <div className="discovery-box">
            <p>The fuse is engineering. The fire is physics.</p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">VI</span>
            <h2>The Interference Pattern</h2>
            <p className="chapter-subtitle">Why amplification is non-monotonic</p>
          </div>

          <p>The amplification wasn&rsquo;t smooth. Some compression steps made the signal louder. Others seemed to dampen it. The pattern looked random until Jeremy&rsquo;s mental model shifted:</p>

          <blockquote>
            <p>It&rsquo;s not that more compression amplifies the signal. It&rsquo;s that passing over quantization boundaries is the mechanism. Like hitting nodes or antinodes when combining harmonic overtones. It&rsquo;s an interference pattern, isn&rsquo;t it?</p>
          </blockquote>

          <p>Each quantization step creates a sawtooth error landscape. Marker positions cross quantization boundaries that smooth background coefficients don&rsquo;t. The result is a standing wave of amplification &mdash; sometimes constructive, sometimes destructive, but on average always growing.</p>

          <blockquote>
            <p>The moment my mental model went from &ldquo;8&times;8 block&rdquo; to &ldquo;these are just specific kinds of changes over time, and each cycle is bounded, and each bounded edge behaves like a node or antinode in a wave&rdquo; &mdash; it just made sense.</p>
          </blockquote>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">VII</span>
            <h2>Channel Pairs</h2>
            <p className="chapter-subtitle">Three channels, eight states, a diagnostic</p>
          </div>

          <p>Testing whether RGB channels behaved independently revealed a structural insight. They don&rsquo;t &mdash; JPEG converts to YCbCr color space, coupling the channels. But this coupling creates <em>exploitable diagnostic information</em>.</p>

          <p>The G-B pair turned out to be the strongest detector because it lives where chroma quantization is harshest &mdash; exactly where the granite effect thrives. R-G provided independent confirmation. The failure pattern across channel pairs became diagnostic: not just &ldquo;was the signal suppressed?&rdquo; but &ldquo;what class of operation was applied?&rdquo;</p>

          <p>Three binary channels. Eight possible states. Each state corresponding to a distinct handling history.</p>

          <blockquote>
            <p>Neither of us would have discovered that independently. Not a chance.</p>
          </blockquote>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow" style={{ textAlign: 'center' }}>
          <p className="section-eyebrow">Continue reading</p>
          <Link href="/history/part-2-validation" className="btn btn-primary">Part II: Validation &rarr;</Link>
          <p style={{ marginTop: '1.5rem' }}><Link href="/history" style={{ fontFamily: 'var(--mono)', fontSize: '.75rem', letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>&larr; Back to History</Link></p>
        </div>
      </section>
    </>
  );
}
