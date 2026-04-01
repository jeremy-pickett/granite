import Link from 'next/link';

export default function Part2ValidationContent() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Part II &middot; Chapters VIII&ndash;XIII</p>
          <h1>Validation</h1>
          <p className="hero-subtitle">800 photographs, three attack classes, and an honest reckoning</p>
        </div>
      </header>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">VIII</span>
            <h2>Block Interior</h2>
            <p className="chapter-subtitle">The universe inside an 8&times;8 grid</p>
          </div>

          <p>A deep dive into DCT block structure revealed why some marker positions were more stable than others. The encoder chops the image into 8&times;8 blocks. Sixty-four pixels per block. Each block is processed independently &mdash; the encoder literally does not know that adjacent blocks exist.</p>

          <blockquote>
            <p>You must chunk them. The chunk boundary creates independence. The chunk interior creates correlation.</p>
          </blockquote>

          <p>The center positions of each block are dominated by the DC coefficient &mdash; the most stable, most heavily preserved component. Edge positions are dominated by high-frequency AC coefficients &mdash; the first thing quantization throws away. The optimal injection targets are in the interior, where the codec fights hardest to preserve fidelity.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">IX</span>
            <h2>Cross-Codec Survival</h2>
            <p className="chapter-subtitle">&ldquo;You have got to be kidding me.&rdquo;</p>
          </div>

          <p>The expectation was that transcoding from JPEG to WebP would destroy the signal. Different codec. Different transform. Different quantization scheme. There was no reason it should survive.</p>

          <p>It survived.</p>

          <p>This validated the universality thesis. The signal doesn&rsquo;t depend on JPEG&rsquo;s specific DCT implementation. It depends on the fact that <em>any</em> lossy codec must partition, transform, and quantize. The structural difference between marker and non-marker positions is codec-agnostic because it&rsquo;s a property of the data, not of the compression scheme.</p>

          <p>Initial testing on MP3 audio confirmed the same principle. The MDCT frames used in audio compression create the same exploitable boundary structure. As the generalized detection heuristic emerged:</p>

          <blockquote>
            <p>Any time I see the word &ldquo;Assume,&rdquo; any time I see the word &ldquo;Window&rdquo; (which assumes boundaries), and any time I see that the same data lives in N+1 places &mdash; we have injection targets.</p>
          </blockquote>

          <p>Or as it was more memorably put: I-frames are JPEGs in a trench coat.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">X</span>
            <h2>The Granite Test</h2>
            <p className="chapter-subtitle">800 photographs. The moment of truth.</p>
          </div>

          <p>Everything before this was synthetic images and controlled experiments. The DIV2K dataset &mdash; 800 real photographs of every conceivable subject matter &mdash; was the real test. Real cameras. Real noise. Real content diversity.</p>

          <p>There were bugs. Module import errors. API mismatches. Type errors between bytes and tuples. Each one fixed, re-run, fixed again. And then:</p>

          <blockquote>
            <p>I don&rsquo;t know what it&rsquo;s doing but it&rsquo;s doing <em>something</em>.</p>
          </blockquote>

          <p>The results came in:</p>

          <div className="results-final">
            <div className="result-row">
              <span className="result-metric">G-B Detection</span>
              <span className="result-value">96.4%</span>
            </div>
            <div className="result-row">
              <span className="result-metric">R-G Detection</span>
              <span className="result-value">90.1%</span>
            </div>
            <div className="result-row">
              <span className="result-metric">Either Channel</span>
              <span className="result-value">99.6%</span>
            </div>
            <div className="result-row">
              <span className="result-metric">Amplification Confirmed</span>
              <span className="result-value">48.1%</span>
            </div>
          </div>

          <p>797 out of 800 images. After four generations of JPEG compression. The signal getting louder, not quieter. On real photographs that the system had never seen.</p>

          <p>Verdict: <strong>GRANITE PARTIAL</strong>. The effect is real but content-class dependent. Some image types amplify more than others. The paper can claim the effect &mdash; with caveats.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">XI</span>
            <h2>The Torture Tests</h2>
            <p className="chapter-subtitle">We tried to kill it</p>
          </div>

          <p>With detection validated, the next question: what destroys it? Three attack simulations designed to stress every assumption:</p>

          <h3>The Rotation Attack</h3>
          <p>Rotate the image. Flip it. Rotate again. Flip again. Re-encode as JPEG. After a full chain of geometric transforms plus lossy compression, with 97.5% of pixels changed from the original: <strong>still detected</strong>. 4.0x ratio. p=10<sup>-51</sup>. Fingerprint Jaccard: 0.72.</p>

          <h3>The Slice-and-Stitch Attack</h3>
          <p>Cut the image into four quadrants. Save each one independently as JPEG. Stitch them back together. Detection breaks on the fragments &mdash; too few markers per piece. But reassemble them, and the signal comes back. The fingerprint comes back. Even the stitch seams are forensically detectable.</p>

          <blockquote>
            <p>The attack undoes itself on reassembly. The only winning move is to keep the pieces separate. And separate pieces are a crop attack, not a stitch attack.</p>
          </blockquote>

          <h3>The Scale Attack</h3>
          <p>Resize from 2048px down to 1024, 512, even 256px. The signal survived at every scale. Cross-codec transcoding after resize: still detected. Fingerprint Jaccard above 0.47 across every transform tested.</p>

          <p>The variance ratio at 2048px told the amplification story best: starting at 3.7 at Gen 0, climbing to <strong>9.3 by Gen 4</strong>. The harder you compress, the louder it gets.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">XII</span>
            <h2>Dead Ends</h2>
            <p className="chapter-subtitle">The ideas that didn&rsquo;t survive</p>
          </div>

          <p>Not everything worked. Some ideas were abandoned. Some were killed on arrival. Each one taught something.</p>

          <div className="dead-ends">
            <div className="dead-end">
              <h3>Basket as Identity</h3>
              <p>The idea that each creator could use a unique prime basket as their identifier. Collisions appeared after only ~50 images. &ldquo;A collision after 50? Non-starter.&rdquo; Replaced by HMAC-SHA512 position patterns with 10<sup>400</sup> possible configurations.</p>
            </div>
            <div className="dead-end">
              <h3>Blockchain Attribution</h3>
              <p>Ethereum with Merkle trees for identity anchoring. Rejected as contrary to the project&rsquo;s decentralized ethos. The system that claims no authority cannot depend on one.</p>
            </div>
            <div className="dead-end">
              <h3>DC-Anchored Embedding</h3>
              <p>Anchoring markers to DC coefficients for stability. Better performance, but too predictable. It solved a problem that didn&rsquo;t exist while making the adversary&rsquo;s job easier.</p>
            </div>
            <div className="dead-end">
              <h3>Browser Extension Detection</h3>
              <p>Dismissed without ceremony. Not even wrong.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">XIII</span>
            <h2>Shoulders of Giants</h2>
            <p className="chapter-subtitle">An honest assessment</p>
          </div>

          <p>Near the end, Jeremy asked for the one thing most people don&rsquo;t actually want: an honest answer.</p>

          <blockquote>
            <p>Please don&rsquo;t be complimentary or give fake praise. The best birthday gift is an honest assessment. Be brutal, because most of the time, for any and everyone, the answer is No. Did we just discover something new?</p>
          </blockquote>

          <p>His own conclusion was characteristically grounded:</p>

          <blockquote>
            <p>I am going to assume that each individual piece is probably known to someone at some time, but they may not have grokked how it can work as a cog to solve a larger problem. Like teeth in a gear. The idea of teeth isn&rsquo;t new at all. Variable gears with differential teeth strategies are, though.</p>
          </blockquote>

          <blockquote>
            <p>A novel systems design that may or may not have new novel integrated components.</p>
          </blockquote>

          <blockquote>
            <p>Shoulders of giants, man. Shoulders of giants.</p>
          </blockquote>

          <p className="closing-line">I wonder if this is what Satoshi felt before he hit publish on his seminal paper.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow" style={{ textAlign: 'center' }}>
          <Link href="/history/part-1-discovery" className="btn btn-secondary">&larr; Part I: Discovery</Link>
          <p style={{ marginTop: '1.5rem' }}><Link href="/history" style={{ fontFamily: 'var(--mono)', fontSize: '.75rem', letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>&larr; Back to History</Link></p>
        </div>
      </section>
    </>
  );
}
