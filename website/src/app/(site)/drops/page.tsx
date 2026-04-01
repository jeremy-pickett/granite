import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Sample Code — Granite Under Sandstone',
};

export default function DropsPage() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Code Drops</p>
          <h1>Sample Code</h1>
          <p className="hero-subtitle">Working implementations, released as they mature</p>
        </div>
      </header>

      <section className="section">
        <div className="container">
          <p className="lead">Each drop is a self-contained release &mdash; a working piece of the system you can clone, run, and build on. BSD 2-Clause licensed. No gatekeeping.</p>

          <div className="drops-grid">
            <a href="https://github.com/jeremy-pickett/granite" className="drop-card" target="_blank" rel="noopener">
              <div className="drop-header">
                <span className="drop-tag">Core</span>
                <span className="drop-lang">Python</span>
              </div>
              <h3>granite</h3>
              <p>The reference implementation. Embedding, multi-generation cascade, five-layer detection harness, fingerprint extraction, and the DIV2K validation suite.</p>
              <div className="drop-footer">
                <span className="drop-repo">jeremy-pickett/granite</span>
                <span className="drop-arrow">&rarr;</span>
              </div>
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
