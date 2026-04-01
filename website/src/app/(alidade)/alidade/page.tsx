import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Alidade — Information Asymmetry Detection',
};

export default function AlidadeLanding() {
  return (
    <>
      {/* Hero */}
      <header className="relative py-24 px-6 text-center">
        <div className="mx-auto max-w-3xl">
          <p className="mb-6 font-mono text-sm font-light uppercase tracking-[0.28em] text-ald-blue">
            <span className="mr-3 inline-block h-px w-8 bg-ald-blue-dim align-middle" />
            Intelligence Platform
          </p>
          <h1 className="mb-4 text-5xl font-light tracking-tight text-ald-ivory md:text-7xl">
            See What<br />They See
          </h1>
          <p className="mb-10 text-xl font-light leading-relaxed text-ald-text-muted">
            Information asymmetry detection across 993+ securities.
            66 signals. 4 tiers. One score.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/alidade/dashboard"
              className="inline-block rounded bg-ald-blue px-8 py-3 font-mono text-sm font-medium uppercase tracking-[0.15em] text-ald-void transition-all hover:bg-transparent hover:text-ald-blue hover:shadow-[0_0_30px_rgba(106,143,216,0.12)] border border-ald-blue"
            >
              Open Dashboard
            </Link>
            <Link
              href="/alidade/login"
              className="inline-block rounded border border-ald-border px-8 py-3 font-mono text-sm uppercase tracking-[0.15em] text-ald-text-dim transition-colors hover:text-ald-text hover:border-ald-text-dim"
            >
              Sign In
            </Link>
          </div>
        </div>
      </header>

      {/* Signal Architecture */}
      <section className="border-t border-ald-border bg-ald-deep py-20 px-6">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-3 text-3xl font-light tracking-tight text-ald-ivory">Four Tiers of Evidence</h2>
          <p className="mb-10 max-w-2xl text-base font-light leading-relaxed text-ald-text-muted">
            Each signal is weighted by reliability. Tier 1 signals alone can move a verdict. Tier 4 signals adjust priors. The system rewards convergence.
          </p>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {[
              {
                tier: '1',
                label: 'Strongest Evidence',
                weight: '1.4–1.5x',
                count: 8,
                color: 'text-ald-red',
                border: 'border-ald-red/20',
                examples: 'Form 4 Insider Clustering, Congressional Trading, M&A Leakage, SEC Investigation',
              },
              {
                tier: '2',
                label: 'Strong Indicators',
                weight: '1.2–1.3x',
                count: 18,
                color: 'text-ald-amber',
                border: 'border-ald-amber/20',
                examples: 'Options Anomaly, Dark Pool Divergence, Short Interest Spike, Institutional Exit',
              },
              {
                tier: '3',
                label: 'Supporting Signals',
                weight: '1.0–1.1x',
                count: 18,
                color: 'text-ald-blue',
                border: 'border-ald-border',
                examples: 'Earnings Date Shift, C-Suite Departure, Material Weakness, Sector Divergence',
              },
              {
                tier: '4',
                label: 'Context',
                weight: '0.7–0.9x',
                count: 6,
                color: 'text-ald-text-dim',
                border: 'border-ald-border',
                examples: 'Social Sentiment, News Velocity, Analyst Revision, Wikipedia Edit Velocity',
              },
            ].map((t) => (
              <div
                key={t.tier}
                className={`rounded-lg border ${t.border} bg-ald-surface p-5 transition-colors hover:border-ald-blue/30`}
              >
                <div className="mb-3 flex items-baseline gap-2">
                  <span className={`font-mono text-2xl font-light ${t.color}`}>T{t.tier}</span>
                  <span className="font-mono text-sm uppercase tracking-wider text-ald-text-dim">{t.weight}</span>
                </div>
                <h3 className="mb-1 font-mono text-base font-medium uppercase tracking-wider text-ald-ivory">{t.label}</h3>
                <p className="mb-3 font-mono text-sm text-ald-text-dim">{t.count} signals</p>
                <p className="text-base leading-relaxed text-ald-text-muted">{t.examples}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* IALD Score */}
      <section className="border-t border-ald-border py-20 px-6">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-12 md:grid-cols-2 items-center">
            <div>
              <h2 className="mb-3 text-3xl font-light tracking-tight text-ald-ivory">The IALD Score</h2>
              <p className="mb-4 text-base font-light leading-relaxed text-ald-text-muted">
                Information Asymmetry &amp; Leakage Detection. A single composite metric
                that aggregates all active signals, weighted by tier, into a normalized score.
              </p>
              <p className="text-base font-light leading-relaxed text-ald-text-muted">
                30-day history. Trend detection. Volatility tracking. The score tells you
                where to look. The research page tells you why.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              {[
                { value: '993+', label: 'Securities', sub: 'Equities & Crypto' },
                { value: '66', label: 'Signals', sub: '4-tier weighted' },
                { value: '30d', label: 'History', sub: 'Per security' },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-ald-border bg-ald-surface p-5">
                  <span className="block font-mono text-2xl font-light text-ald-blue">{s.value}</span>
                  <span className="mt-1 block font-mono text-sm uppercase tracking-wider text-ald-ivory">{s.label}</span>
                  <span className="block text-sm text-ald-text-dim">{s.sub}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section className="border-t border-ald-border bg-ald-deep py-20 px-6">
        <div className="mx-auto max-w-6xl">
          <h2 className="mb-10 text-3xl font-light tracking-tight text-ald-ivory">What You Get</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[
              { title: 'Research Dashboard', desc: 'Browse, filter, and sort securities by IALD score, type, market cap, or name. Real-time scoring.' },
              { title: 'Deep Research', desc: 'Per-security pages with signal breakdown, 30-day history, collector stats, and data freshness metrics.' },
              { title: 'Watchlist', desc: 'Track securities you care about. IALD scores and price changes at a glance.' },
              { title: 'Alerts', desc: 'Score thresholds, verdict changes, price movements. Get notified when something moves.' },
              { title: 'Signal Transparency', desc: 'Every signal documented. Thresholds published. Resolution windows tracked. No black boxes.' },
              { title: 'Cross-Asset', desc: 'Equities and crypto in the same system. Same signals where applicable. Same scoring.' },
            ].map((f) => (
              <div key={f.title} className="rounded-lg border border-ald-border bg-ald-surface p-5 transition-colors hover:border-ald-blue/30">
                <h3 className="mb-2 font-mono text-base text-ald-ivory">{f.title}</h3>
                <p className="text-base leading-relaxed text-ald-text-muted">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-ald-border py-8 px-6 text-center">
        <p className="font-mono text-sm text-ald-text-dim">
          Alidade &mdash; Jeremy Pickett
        </p>
      </footer>
    </>
  );
}
