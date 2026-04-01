import Link from 'next/link';

export default function OneOfThoseDaysContent() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Daily History &middot; March 27, 2026</p>
          <h1>One of Those Days</h1>
          <p className="hero-subtitle">Prime decomposition topology, gravitational lensing for provenance, and a disk that is still not fixed</p>
        </div>
      </header>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">I</span>
            <h2>Today Was One of Those Days</h2>
            <p className="chapter-subtitle">Started by running out of hard drive space. Ended somewhere else entirely.</p>
          </div>

          <p>Started by running out of hard drive space on my AWS instance. Routine. While digging through the filesystem I somehow ended up deriving a novel steganographic encoding scheme based on prime decomposition topology, writing a formal paper about it, implementing a full Python library, and then building a rotation-resilient gravitational lensing layer for an image provenance system.</p>

          <p>The disk is still not fixed.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">II</span>
            <h2>Information Lives in Structure</h2>
            <p className="chapter-subtitle">Non-contiguous number lines and prime decomposition topology</p>
          </div>

          <p>The through-line, if there is one: <strong>information doesn&rsquo;t have to live in values. It can live in structure.</strong></p>

          <p>We found that the number 733373 has 9 valid prime-tiling decompositions. The same four digits mean nine different things depending on which resolution you apply. An observer who sees it as a prime sees nothing. An observer who knows which split was chosen reads a message.</p>

          <p>The carrier sequence is just a list of primes. The message channel doesn&rsquo;t exist on the integer number line at all &mdash; proximity in that space tells you nothing about proximity in the encoding space.</p>

          <p>We called these <em>non-contiguous number lines</em>. Then we wrote an encoder. Then we encoded &ldquo;HI.&rdquo;</p>

          <p>It worked.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">III</span>
            <h2>The Rotation Gap</h2>
            <p className="chapter-subtitle">The one weakness in five validated layers</p>
          </div>

          <p>Separately, and I want to be precise here: the GRANITE provenance work picked up a real architectural gap today.</p>

          <p>The existing system &mdash; five validated layers, 0.9988 gap between marked and clean, 800/800 payload recovery at Q40 &mdash; has one weakness. <strong>Rotation.</strong> Rotate an image by 30 degrees and the position-offset payload encoding breaks. The sentinels move. The field grammar that encodes the data is disrupted.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">IV</span>
            <h2>The Halo</h2>
            <p className="chapter-subtitle">The fix came from thinking about gravitational lensing</p>
          </div>

          <p>A lens doesn&rsquo;t destroy what&rsquo;s behind it. It distorts the <em>space around it</em> in a way that points back at the mass. If you see the distortion pattern, you know the mass exists &mdash; even if you can&rsquo;t see the mass directly. Even if the mass has been removed.</p>

          <p>So: embed a structured field <em>around</em> each sentinel. Two concentric rings, each encoding a specific prime+1 target value in the channel differences. The inner disk encodes 98 (= 97+1). The outer ring encodes 60 (= 59+1). Natural images produce these values at 3.8% and 9.2% background rate respectively. An embedded halo produces them at near 100%.</p>

          <p>After bilinear rotation, individual pixel values are destroyed by interpolation &mdash; we measured 5% survival at 5&deg;. But the <strong>density</strong> of the field survives. Annular means drift by only 2&ndash;4 counts. The statistical structure is rotation-invariant even when the individual values are not.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">V</span>
            <h2>Validation</h2>
            <p className="chapter-subtitle">4/4 detections. 0 false positives. And one result that keeps me up.</p>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Test</th><th>Result</th></tr>
              </thead>
              <tbody>
                <tr><td>Detection (no rotation)</td><td className="yes">4/4 &mdash; 0 false positives</td></tr>
                <tr><td>Rotation 0&deg;</td><td className="yes">4/4</td></tr>
                <tr><td>Rotation 30&deg;</td><td className="yes">4/4</td></tr>
                <tr><td>Rotation 90&deg;</td><td className="yes">4/4</td></tr>
                <tr><td>Force arrow (sentinel removed)</td><td className="yes">4/4 VOID</td></tr>
                <tr><td>Full wipe</td><td>0 detections</td></tr>
                <tr><td>JPEG Q85</td><td className="yes">4/4</td></tr>
                <tr><td>JPEG Q40</td><td className="yes">4/4 (2 PRESENT, 2 VOID)</td></tr>
              </tbody>
            </table>
          </div>

          <p>The Q40 VOID result is the one I keep thinking about. At aggressive compression, the inner disk density drops below threshold. The outer ring survives. The system classifies the center as VOID &mdash; not ABSENT. <em>Something was here.</em> The force arrows are still pointing at the void.</p>

          <blockquote>
            <p>The adversary who compresses hard enough to kill the inner signal is constructing the VOID signal that documents the destruction.</p>
          </blockquote>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">VI</span>
            <h2>Three New Canonical Phrases</h2>
          </div>

          <div className="dead-ends">
            <div className="dead-end" style={{ borderLeftColor: 'var(--teal)' }}>
              <p style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: '1.15rem', color: 'var(--cream)', margin: 0 }}>&ldquo;Density survives everything.&rdquo;</p>
            </div>
            <div className="dead-end" style={{ borderLeftColor: 'var(--teal)' }}>
              <p style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: '1.15rem', color: 'var(--cream)', margin: 0 }}>&ldquo;The adversary who removes the sentinel leaves the field intact.&rdquo;</p>
            </div>
            <div className="dead-end" style={{ borderLeftColor: 'var(--amber)' }}>
              <p style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: '1.15rem', color: 'var(--cream)', margin: 0 }}>&ldquo;The disk is still not fixed.&rdquo;</p>
            </div>
          </div>

          <p style={{ marginTop: '3rem' }}>All of this is open research. Papers in progress. Code on GitHub. The provenance work is licensed BSD-2. The PSE library is documented.</p>

          <p>If you&rsquo;re working on related problems &mdash; image authenticity, covert channels, compression-domain signal theory &mdash; reach out.</p>

          <p className="closing-line">That&rsquo;s a day.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow" style={{ textAlign: 'center' }}>
          <Link href="/history" style={{ fontFamily: 'var(--mono)', fontSize: '.75rem', letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>&larr; Back to History</Link>
        </div>
      </section>
    </>
  );
}
