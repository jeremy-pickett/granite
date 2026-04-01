import type { Metadata } from 'next';
import Link from 'next/link';
import Countdown from '@/components/Countdown';

export const metadata: Metadata = {
  title: 'Signal Delta — Projects',
  description: 'Research projects by Jeremy Pickett',
};

export default function ProjectsPage() {
  return (
    <>
      <style>{`
        body {
          background: #07090F;
          color: #C8C4B8;
          font-family: 'Courier New', monospace;
          min-height: 100vh;
          overflow-x: hidden;
        }
        .projects-page {
          max-width: 64rem;
          margin: 0 auto;
          padding: 6rem 2rem 4rem;
        }
        .projects-header {
          text-align: center;
          margin-bottom: 5rem;
        }
        .delta {
          font-size: 3rem;
          color: #333;
          letter-spacing: 0.5rem;
          margin-bottom: 1.5rem;
          animation: pulse 4s ease-in-out infinite;
        }
        .site-title {
          font-size: 23px;
          font-family: var(--font-mono, 'IBM Plex Mono', 'Courier New', monospace);
          letter-spacing: 0.3em;
          text-transform: uppercase;
          color: #5A5650;
          margin-bottom: 0.5rem;
        }
        .site-subtitle {
          font-family: var(--font-serif, 'Cormorant Garamond', Georgia, serif);
          font-size: 23px;
          font-weight: 300;
          color: #5A5650;
          line-height: 1.8;
        }
        .countdown {
          margin-top: 2rem;
        }
        .countdown-segments {
          display: flex;
          align-items: baseline;
          justify-content: center;
          gap: 0.25rem;
        }
        .countdown-segment {
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .countdown-value {
          font-family: 'Courier New', monospace;
          font-size: 1.8rem;
          letter-spacing: 0.1em;
          color: #333;
        }
        .countdown-label {
          font-size: 0.55rem;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          color: #2a2820;
          margin-top: 0.2rem;
        }
        .countdown-sep {
          font-size: 1.4rem;
          color: #222;
          margin: 0 0.15rem;
          align-self: flex-start;
          padding-top: 0.2rem;
        }
        .projects-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
          gap: 1.5rem;
        }
        .project-card {
          display: block;
          padding: 2.5rem 2rem;
          background: #0C0F1A;
          border: 1px solid rgba(255,255,255,0.07);
          border-radius: 8px;
          text-decoration: none;
          transition: border-color 0.3s, box-shadow 0.3s, transform 0.2s;
        }
        .project-card:hover {
          transform: translateY(-2px);
        }
        .project-card.project-granite:hover {
          border-color: #C8972A;
          box-shadow: 0 0 30px rgba(200,151,42,.12);
        }
        .project-card.project-alidade:hover {
          border-color: #6A8FD8;
          box-shadow: 0 0 30px rgba(106,143,216,.12);
        }
        .project-card.project-coming:hover {
          border-color: #5A5650;
        }
        .project-status {
          display: inline-block;
          font-size: 18px;
          font-family: var(--font-mono, 'IBM Plex Mono', 'Courier New', monospace);
          letter-spacing: 0.15em;
          text-transform: uppercase;
          padding: 0.2rem 0.6rem;
          border-radius: 3px;
          margin-bottom: 1.25rem;
        }
        .status-active {
          background: rgba(200,151,42,.12);
          color: #C8972A;
        }
        .status-dev {
          background: rgba(106,143,216,.12);
          color: #6A8FD8;
        }
        .status-planned {
          background: rgba(255,255,255,0.04);
          color: #5A5650;
        }
        .project-name {
          font-family: var(--font-display, 'Bebas Neue', sans-serif);
          font-size: 32px;
          font-weight: 400;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          margin-bottom: 0.5rem;
          line-height: 1.1;
        }
        .project-name em {
          font-style: italic;
        }
        .project-card.project-granite .project-name { color: #C8972A; }
        .project-card.project-alidade .project-name { color: #6A8FD8; }
        .project-card.project-coming .project-name { color: #5A5650; }
        .project-tagline {
          font-family: var(--font-serif, 'Cormorant Garamond', Georgia, serif);
          font-size: 23px;
          font-weight: 300;
          color: #8a8890;
          line-height: 1.7;
          margin-bottom: 0;
        }
        .projects-footer {
          text-align: center;
          margin-top: 5rem;
          padding-top: 2rem;
          border-top: 1px solid rgba(255,255,255,0.04);
        }
        .projects-footer p {
          font-size: 18px;
          font-family: var(--font-mono, 'IBM Plex Mono', 'Courier New', monospace);
          color: #3a3830;
          letter-spacing: 0.1em;
        }
        .projects-footer a {
          color: #5A5650;
          text-decoration: none;
          transition: color 0.2s;
        }
        .projects-footer a:hover { color: #C8C4B8; }
        @keyframes pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.7; }
        }
      `}</style>
      <div className="projects-page">
        <header className="projects-header">
          <div className="delta">&#916;</div>
          <p className="site-title">Signal Delta</p>
          <p className="site-subtitle">Jeremy Pickett &mdash; Axiomatic Fictions Series</p>
          <Countdown />
        </header>

        <div className="projects-grid">
          <Link href="/home" className="project-card project-granite">
            <span className="project-status status-active">Active</span>
            <h2 className="project-name">Granite Under <em>Sandstone</em></h2>
            <p className="project-tagline">
              Compression-amplified provenance signal detection for digital media.
              The signal survives JPEG &mdash; and strengthens under it.
            </p>
          </Link>

          <Link href="/alidade" className="project-card project-alidade">
            <span className="project-status status-dev">In Development</span>
            <h2 className="project-name">Alidade</h2>
            <p className="project-tagline">
              Information asymmetry detection across 993+ securities.
              66 signals. 4 tiers. One score.
            </p>
          </Link>
        </div>

        <footer className="projects-footer">
          <p>
            <a href="https://github.com/jeremy-pickett" target="_blank" rel="noopener">GitHub</a>
            &nbsp;&middot;&nbsp;
            BSD 2-Clause License
          </p>
        </footer>
      </div>
    </>
  );
}
