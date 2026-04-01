'use client';

import Link from 'next/link';

export default function HistoryClient() {
  return (
    <>
      {/* ── Nav (minimal) ── */}
      <header className="h-header">
        <nav className="h-nav">
          <Link href="/home" className="h-brand">Signal Delta</Link>
          <span className="h-title">History</span>
          <Link href="/home" className="h-back">Back</Link>
        </nav>
      </header>

      <main className="h-main">
        {/* ── Preamble ── */}
        <div className="h-preamble">
          <h1>How We Got Here</h1>
          <p>The development history of Granite Under Sandstone, as it happened. Every breakthrough, dead end, and moment of discovery.</p>
          <p style={{ marginTop: '0.75rem' }}>
            <Link href="/log" style={{ fontFamily: 'var(--mono)', fontSize: '.8rem', letterSpacing: '.1em', color: 'var(--amber)' }}>
              Read the .plan &rarr;
            </Link>
          </p>
        </div>

        {/* ── Founding story (static) ── */}
        <section className="h-founding">
          <h2 className="h-section-label">The Founding Story</h2>
          <div className="h-story-grid">
            <Link href="/history/part-1-discovery" className="h-story-card">
              <span className="h-card-label">Part I</span>
              <h3>Discovery</h3>
              <p>Chapters I&ndash;VII &mdash; From a hand on a keyboard to &ldquo;the fuse is engineering, the fire is physics.&rdquo;</p>
              <span className="h-card-count">7 chapters</span>
            </Link>
            <Link href="/history/part-2-validation" className="h-story-card">
              <span className="h-card-label">Part II</span>
              <h3>Validation</h3>
              <p>Chapters VIII&ndash;XIII &mdash; Block interior physics, cross-codec survival, the 800-image Granite Test, and an honest reckoning.</p>
              <span className="h-card-count">6 chapters</span>
            </Link>
          </div>
        </section>

        {/* ── Daily history (static) ── */}
        <section className="h-daily">
          <h2 className="h-section-label">Daily</h2>
          <div className="h-story-grid">
            <Link href="/history/one-of-those-days" className="h-story-card">
              <span className="h-card-label">March 27, 2026</span>
              <h3>One of Those Days</h3>
              <p>Prime decomposition topology. The rotation gap. A gravitational lensing fix. Density survives everything.</p>
              <span className="h-card-count">6 parts</span>
            </Link>
            <Link href="/history/an-afternoon-well-spent" className="h-story-card">
              <span className="h-card-label">March 26, 2026</span>
              <h3>An Afternoon Well Spent</h3>
              <p>Disk forensics, cosmological constants, structural pairings, the Pachinko Universe hypothesis.</p>
              <span className="h-card-count">6 parts</span>
            </Link>
          </div>
        </section>
      </main>

      <footer className="h-footer">
        <p>&copy; {new Date().getFullYear()} Signal Delta</p>
      </footer>
    </>
  );
}
