import Link from 'next/link';

export default function AnAfternoonWellSpentContent() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Daily History &middot; March 26, 2026</p>
          <h1>An Afternoon Well Spent</h1>
          <p className="hero-subtitle">AWS Instance ip-172-31-32-45</p>
        </div>
      </header>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">I</span>
            <h2>Disk Forensics</h2>
            <p className="chapter-subtitle">Ran out of hard drive space in an afternoon. Investigated systematically.</p>
          </div>

          <p><strong>Root volume:</strong> 7.8G total &mdash; healthy for an OS, irrelevant to the problem.</p>

          <p><strong>Actual culprits found:</strong></p>
          <ul className="principle-list">
            <li><code>~/.local/share/claude/versions</code> &mdash; <strong>450M</strong> of Claude Code installer versions accumulating across self-updates. Prunable.</li>
            <li><code>~/.local/lib/python3.12/site-packages</code> &mdash; <strong>311M</strong> of provenance paper dependencies: scipy (111M), numpy (42M), matplotlib (31M), PIL, lxml. Earned, not waste.</li>
            <li><code>~/.cache/pip</code> &mdash; <strong>96M</strong>. Safe to purge with <code>pip cache purge</code>.</li>
            <li><code>bootes-env</code> virtualenv (82M) potentially double-carrying packages already in <code>~/.local</code>. Worth auditing.</li>
          </ul>

          <p><strong>Key commands developed:</strong></p>
          <div className="table-wrap">
            <table>
              <tbody>
                <tr><td><code>du -h --max-depth=2 . | sort -rh</code></td><td>the workhorse</td></tr>
                <tr><td><code>ls -lh ~/.local/share/claude/versions/</code></td><td>find the dead weight</td></tr>
                <tr><td><code>ls -d ~/.local/share/claude/versions/*/ | sort -V | head -n -1 | xargs rm -rf</code></td><td>prune old versions</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">II</span>
            <h2>Cosmological Constants and Why They&rsquo;re Suspicious</h2>
            <p className="chapter-subtitle">The most confounding fundamental constants &mdash; the ones that fall out of physics with no derivable origin</p>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Constant</th><th>Problem</th></tr>
              </thead>
              <tbody>
                <tr><td>&Lambda; (Cosmological Constant)</td><td>Off by 10<sup>120</sup> from QFT prediction</td></tr>
                <tr><td>&alpha; (Fine Structure, ~1/137)</td><td>Dimensionless, underivable, Feynman called it a mystery</td></tr>
                <tr><td>Hierarchy Problem</td><td>Higgs mass requires cancellation to ~34 decimal places</td></tr>
                <tr><td>Strong CP Problem</td><td>&theta; &lt; 10<sup>&minus;10</sup> for no known reason</td></tr>
                <tr><td>Baryon Asymmetry</td><td>1 extra baryon per 10<sup>9</sup> pairs. We are that baryon.</td></tr>
                <tr><td>Three Generations</td><td>Why exactly three? Mass ratios: unknown</td></tr>
                <tr><td>Coincidence Problem</td><td>Matter and dark energy equal <em>right now</em>, briefly</td></tr>
                <tr><td>G (Gravitational Constant)</td><td>Least precisely measured constant. Resists.</td></tr>
              </tbody>
            </table>
          </div>

          <p><strong>Standard Model free parameters: 19.</strong> With neutrino masses: 26.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">III</span>
            <h2>Structural Pairings</h2>
            <p className="chapter-subtitle">Not thematic groupings &mdash; structural ones. Constants that are probably the same mystery.</p>
          </div>

          <div className="dead-ends">
            <div className="dead-end" style={{ borderLeftColor: 'var(--amber)' }}>
              <h3 style={{ color: 'var(--amber)' }}>&Lambda; &harr; Hierarchy Problem</h3>
              <p>Catastrophic cancellation in two sectors. One solution solves both.</p>
            </div>
            <div className="dead-end" style={{ borderLeftColor: 'var(--amber)' }}>
              <h3 style={{ color: 'var(--amber)' }}>Strong CP &harr; Baryon Asymmetry</h3>
              <p>Inverse twins of the same broken symmetry.</p>
            </div>
            <div className="dead-end" style={{ borderLeftColor: 'var(--amber)' }}>
              <h3 style={{ color: 'var(--amber)' }}>G &harr; &Lambda;</h3>
              <p>Gravity specifically refuses both precision measurement and correct prediction. Probably the same failure.</p>
            </div>
            <div className="dead-end" style={{ borderLeftColor: 'var(--teal)' }}>
              <h3 style={{ color: 'var(--teal)' }}>&alpha;</h3>
              <p>Stands alone. The isolation is the clue.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">IV</span>
            <h2>The Pachinko Universe</h2>
            <p className="chapter-subtitle">The constants aren&rsquo;t ordered by a higher power &mdash; they settled</p>
          </div>

          <p>The constants aren&rsquo;t ordered by a higher power &mdash; they settle where they are because some transformation was applied to the initial conditions dataset. A higher-order constraint, possibly infinite in variety, acts like a guided pachinko board. The universe clicked into <em>this</em> attractor.</p>

          <p>This makes 19 free parameters feel prime-like: irreducible only because we haven&rsquo;t found the right coordinate system. Mendeleev had the same problem with elements until quantum numbers arrived.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">V</span>
            <h2>Base Suspicion and Number Fields</h2>
            <p className="chapter-subtitle">Base-10 is suspicious. But primes are base-independent.</p>
          </div>

          <p>The <em>right</em> question: change the number system, not just the base.</p>

          <ul className="principle-list">
            <li><strong>Gaussian integers</strong> have a genuinely different prime structure. 2 is not a Gaussian prime. 3 is.</li>
            <li><strong>Eisenstein integers</strong>, <strong>p-adic numbers</strong> &mdash; different prime landscapes, partial overlaps.</li>
            <li><strong>Langlands Program</strong> &mdash; the largest open project in mathematics, connecting prime structure in different number fields to symmetry groups in geometry. Smells like the pachinko board.</li>
            <li><strong>Monstrous Moonshine</strong> &mdash; Monster group dimensions appear in string theory j-function coefficients. Nobody fully understands why.</li>
          </ul>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <div className="chapter-header">
            <span className="chapter-num">VI</span>
            <h2>Primes in the Constants</h2>
            <p className="chapter-subtitle">Significant figures of fundamental constants, checked for primality</p>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Constant</th><th>Value</th><th>First 3 Sig Figs</th><th>Prime?</th></tr>
              </thead>
              <tbody>
                <tr><td>&alpha;<sup>&minus;1</sup></td><td>137.036</td><td>137</td><td className="yes">PRIME</td></tr>
                <tr><td>Electron mass</td><td>9.109 &times; 10<sup>&minus;31</sup> kg</td><td>911</td><td className="yes">PRIME</td></tr>
                <tr><td>Z boson mass</td><td>91.1876 GeV</td><td>911</td><td className="yes">PRIME</td></tr>
                <tr><td>Proton mass</td><td>1.6726 &times; 10<sup>&minus;27</sup> kg</td><td>167</td><td className="yes">PRIME</td></tr>
                <tr><td>SM free parameters</td><td>19</td><td>19</td><td className="yes">PRIME</td></tr>
              </tbody>
            </table>
          </div>

          <blockquote>
            <p>911 appears at two completely different energy scales &mdash; the electron (a fermion) and the Z boson (a weak force carrier). They are not obviously intimately related. Both prime. Same digits.</p>
          </blockquote>

          <p>This analysis is base-10 dependent. Which remains suspicious.</p>

          <p className="closing-line">All of this happened on an AWS instance with a full hard drive.</p>
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
