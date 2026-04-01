'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';

// ─── Types ───────────────────────────────────────────────────────────────────

interface Filing {
  filing_type: string;
  filing_date: string;
  description: string;
  filing_url: string;
  accession_number: string;
}

interface CorporateRecord {
  record_type: string;
  description: string;
  source_filing: string;
  filing_date: string;
  amount: number | null;
  collected_at: string;
}

interface RelatedEntity {
  entity_name: string;
  entity_type: string;
  relationship: string;
  first_seen: string;
  last_seen: string;
}

interface Executive {
  name: string;
  title: string;
  role_type: string;
  age: number | null;
  since: number | null;
  compensation: number | null;
  headshot_url: string | null;
}

interface BackgroundFinding {
  executive_name: string;
  check_type: string;
  finding: string;
  severity: string;
  source: string;
  source_url: string | null;
  case_date: string | null;
}

interface FilingAnalysis {
  green_flags: string[];
  red_flags: string[];
  suspect_sections: string[];
  weasel_words: string[];
  overall_risk: string;
  summary: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function severityColor(severity: string): string {
  if (severity === 'critical') return 'text-ald-red bg-ald-red/15';
  if (severity === 'high') return 'text-ald-amber bg-ald-amber/15';
  if (severity === 'medium') return 'text-ald-blue bg-ald-blue/15';
  return 'text-ald-text-dim bg-ald-surface-2';
}

function recordTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    loan: 'Loan / Credit',
    lien: 'Lien / UCC',
    judgment: 'Judgment',
    bankruptcy: 'Bankruptcy',
    sec_enforcement: 'SEC Enforcement',
    litigation: 'Litigation',
    personal_bankruptcy: 'Personal Bankruptcy',
    financial_judgment: 'Financial Judgment',
    regulatory_bar: 'Regulatory Bar',
  };
  return labels[type] || type;
}

function HeadshotImg({ src, name }: { src: string | null; name: string }) {
  const [err, setErr] = useState(false);
  if (!src || err) {
    const initials = name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
    return (
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ald-surface-2 font-mono text-xs text-ald-text-dim">
        {initials}
      </div>
    );
  }
  return (
    <Image
      src={src}
      alt={name}
      width={40}
      height={40}
      className="h-10 w-10 shrink-0 rounded-full object-cover"
      onError={() => setErr(true)}
    />
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function FilingsClient({ ticker }: { ticker: string }) {
  const { getIdToken } = useAuth();

  const [companyName, setCompanyName] = useState('');
  const [filings, setFilings] = useState<Filing[]>([]);
  const [records, setRecords] = useState<CorporateRecord[]>([]);
  const [entities, setEntities] = useState<RelatedEntity[]>([]);
  const [executives, setExecutives] = useState<Executive[]>([]);
  const [backgrounds, setBackgrounds] = useState<BackgroundFinding[]>([]);
  const [loading, setLoading] = useState(true);

  const [tab, setTab] = useState<'executives' | 'filings' | 'records' | 'entities' | 'background'>('executives');

  // Analysis state
  const [analysis, setAnalysis] = useState<FilingAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzedFiling, setAnalyzedFiling] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`/api/filings?ticker=${ticker}`);
        if (res.ok) {
          const data = await res.json();
          setCompanyName(data.company_name);
          setFilings(data.filings ?? []);
          setRecords(data.records ?? []);
          setEntities(data.entities ?? []);
          setExecutives(data.executives ?? []);
          setBackgrounds(data.backgrounds ?? []);
        }
      } catch {}
      setLoading(false);
    }
    load();
  }, [ticker]);

  async function analyzeFiling(filing: Filing) {
    const token = await getIdToken();
    if (!token) return;
    setAnalyzing(true);
    setAnalyzedFiling(filing.accession_number);
    setAnalysis(null);

    try {
      // Fetch filing text from SEC
      let filingText = `${filing.filing_type} filed ${filing.filing_date}: ${filing.description}`;

      if (filing.filing_url) {
        try {
          const textRes = await fetch(filing.filing_url);
          if (textRes.ok) {
            const text = await textRes.text();
            filingText = text.slice(0, 20000);
          }
        } catch {}
      }

      const res = await fetch('/api/filings/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ticker,
          filing_text: filingText,
          filing_type: filing.filing_type,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setAnalysis(data.analysis);
      }
    } catch {}
    setAnalyzing(false);
  }

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href={`/alidade/research/${ticker}`}
          className="font-mono text-xs text-ald-blue hover:text-ald-ivory transition-colors"
        >
          &larr; Back to {ticker}
        </Link>
        <h1 className="mt-2 text-2xl font-light tracking-tight text-ald-ivory">
          {companyName || ticker} — Deep Dive
        </h1>
        <p className="text-sm text-ald-text-muted">
          Executives, filings, corporate records, and background checks
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-ald-border overflow-x-auto">
        {([
          ['executives', `Executives (${executives.length})`],
          ['filings', `Filings (${filings.length})`],
          ['records', `Records (${records.length})`],
          ['entities', `Entities (${entities.length})`],
          ['background', `Background (${backgrounds.length})`],
        ] as const).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`whitespace-nowrap px-4 py-2 font-mono text-xs uppercase tracking-wider transition-colors border-b-2 -mb-px ${
              tab === t
                ? 'text-ald-ivory border-ald-blue'
                : 'text-ald-text-dim border-transparent hover:text-ald-text'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ─── Executives Tab ──────────────────────────────────────────── */}
      {tab === 'executives' && (
        <div>
          {executives.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">No executive data available yet.</p>
              <p className="font-mono text-xs text-ald-text-dim mt-1">Run the executive_profiles collector to populate.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {executives.map((ex, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-ald-border bg-ald-surface p-4">
                  <div className="flex items-center gap-4">
                    <HeadshotImg src={ex.headshot_url} name={ex.name} />
                    <div>
                      <span className="block font-mono text-sm text-ald-ivory">{ex.name}</span>
                      <span className="block text-xs text-ald-text-dim">{ex.title}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-right">
                    <span className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                      ex.role_type === 'c-suite' ? 'bg-ald-amber/15 text-ald-amber' :
                      ex.role_type === 'director' ? 'bg-ald-blue/15 text-ald-blue' :
                      'bg-ald-surface-2 text-ald-text-dim'
                    }`}>
                      {ex.role_type}
                    </span>
                    {ex.since && (
                      <span className="font-mono text-xs text-ald-text-dim">Since {ex.since}</span>
                    )}
                    {ex.compensation && (
                      <span className="font-mono text-xs text-ald-text-dim">
                        ${(ex.compensation / 1000000).toFixed(1)}M
                      </span>
                    )}
                    {/* Check if there are background findings for this person */}
                    {backgrounds.some(b => b.executive_name === ex.name) && (
                      <button
                        onClick={() => setTab('background')}
                        className="rounded bg-ald-red/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ald-red"
                      >
                        Flags
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Filings Tab ─────────────────────────────────────────────── */}
      {tab === 'filings' && (
        <div>
          {filings.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">No filings in database yet.</p>
              <p className="font-mono text-xs text-ald-text-dim mt-1">
                Filings are collected from SEC EDGAR automatically.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filings.map((f, i) => (
                <div key={i} className="rounded-lg border border-ald-border bg-ald-surface p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-ald-text-dim">
                        {f.filing_type}
                      </span>
                      <span className="font-mono text-xs text-ald-text-dim">
                        {new Date(f.filing_date).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {f.filing_url && (
                        <a
                          href={f.filing_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-xs text-ald-blue hover:text-ald-ivory transition-colors"
                        >
                          View &rarr;
                        </a>
                      )}
                      <button
                        onClick={() => analyzeFiling(f)}
                        disabled={analyzing}
                        className="rounded border border-ald-blue/40 bg-ald-blue/10 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-ald-blue hover:bg-ald-blue/20 transition-colors disabled:opacity-30"
                      >
                        {analyzing && analyzedFiling === f.accession_number ? 'Analyzing...' : 'Analyze'}
                      </button>
                    </div>
                  </div>
                  <p className="text-sm text-ald-text-dim">{f.description}</p>

                  {/* Analysis results */}
                  {analysis && analyzedFiling === f.accession_number && (
                    <div className="mt-4 space-y-3 border-t border-ald-border pt-4">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">AI Analysis</span>
                        <span className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                          analysis.overall_risk === 'critical' ? 'bg-ald-red/20 text-ald-red' :
                          analysis.overall_risk === 'high' ? 'bg-ald-amber/15 text-ald-amber' :
                          analysis.overall_risk === 'medium' ? 'bg-ald-blue/15 text-ald-blue' :
                          'bg-ald-surface-2 text-ald-text-dim'
                        }`}>
                          {analysis.overall_risk} risk
                        </span>
                      </div>

                      <p className="text-sm text-ald-text-dim">{analysis.summary}</p>

                      {analysis.green_flags.length > 0 && (
                        <div>
                          <span className="block font-mono text-[10px] uppercase tracking-wider text-ald-green mb-1">Green Flags</span>
                          <ul className="space-y-1">
                            {analysis.green_flags.map((f, j) => (
                              <li key={j} className="text-xs text-ald-text-dim pl-3 border-l-2 border-ald-green/30">{f}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {analysis.red_flags.length > 0 && (
                        <div>
                          <span className="block font-mono text-[10px] uppercase tracking-wider text-ald-red mb-1">Red Flags</span>
                          <ul className="space-y-1">
                            {analysis.red_flags.map((f, j) => (
                              <li key={j} className="text-xs text-ald-text-dim pl-3 border-l-2 border-ald-red/30">{f}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {analysis.suspect_sections.length > 0 && (
                        <div>
                          <span className="block font-mono text-[10px] uppercase tracking-wider text-ald-amber mb-1">Suspect Sections</span>
                          <ul className="space-y-1">
                            {analysis.suspect_sections.map((s, j) => (
                              <li key={j} className="text-xs text-ald-text-dim pl-3 border-l-2 border-ald-amber/30">{s}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {analysis.weasel_words.length > 0 && (
                        <div>
                          <span className="block font-mono text-[10px] uppercase tracking-wider text-ald-amber mb-1">Weasel Words</span>
                          <ul className="space-y-1">
                            {analysis.weasel_words.map((w, j) => (
                              <li key={j} className="text-xs text-ald-text-dim italic pl-3 border-l-2 border-ald-amber/30">&ldquo;{w}&rdquo;</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Corporate Records Tab ───────────────────────────────────── */}
      {tab === 'records' && (
        <div>
          {records.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">No corporate records found yet.</p>
              <p className="font-mono text-xs text-ald-text-dim mt-1">Run the corporate_records collector to scan filings.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {records.map((r, i) => (
                <div key={i} className="rounded-lg border border-ald-border bg-ald-surface p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <span className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                      r.record_type === 'bankruptcy' ? 'bg-ald-red/15 text-ald-red' :
                      r.record_type === 'judgment' ? 'bg-ald-amber/15 text-ald-amber' :
                      r.record_type === 'lien' ? 'bg-ald-amber/15 text-ald-amber' :
                      'bg-ald-surface-2 text-ald-text-dim'
                    }`}>
                      {recordTypeLabel(r.record_type)}
                    </span>
                    {r.filing_date && (
                      <span className="font-mono text-xs text-ald-text-dim">
                        {new Date(r.filing_date).toLocaleDateString()}
                      </span>
                    )}
                    {r.amount && (
                      <span className="font-mono text-xs text-ald-ivory">
                        ${r.amount.toLocaleString()}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-ald-text-dim">{r.description}</p>
                  {r.source_filing && (
                    <span className="mt-1 block font-mono text-[10px] text-ald-text-dim">
                      Source: {r.source_filing}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Related Entities Tab ────────────────────────────────────── */}
      {tab === 'entities' && (
        <div>
          {entities.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">No related entities found yet.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {entities.map((e, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-ald-border bg-ald-surface p-4">
                  <div>
                    <span className="block font-mono text-sm text-ald-ivory">{e.entity_name}</span>
                    {e.relationship && (
                      <span className="block text-xs text-ald-text-dim">{e.relationship}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">
                      {e.entity_type}
                    </span>
                    <span className="font-mono text-[10px] text-ald-text-dim">
                      {new Date(e.first_seen).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Background Checks Tab ───────────────────────────────────── */}
      {tab === 'background' && (
        <div>
          {backgrounds.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">No background findings.</p>
              <p className="font-mono text-xs text-ald-text-dim mt-1">
                Run the executive_background collector after executive_profiles has data.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {backgrounds.map((b, i) => (
                <div key={i} className="rounded-lg border border-ald-border bg-ald-surface p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-ald-ivory">{b.executive_name}</span>
                      <span className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${severityColor(b.severity)}`}>
                        {b.severity}
                      </span>
                      <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">
                        {recordTypeLabel(b.check_type)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      {b.case_date && (
                        <span className="font-mono text-xs text-ald-text-dim">
                          {new Date(b.case_date).toLocaleDateString()}
                        </span>
                      )}
                      {b.source_url && (
                        <a
                          href={b.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-xs text-ald-blue hover:text-ald-ivory transition-colors"
                        >
                          Source &rarr;
                        </a>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-ald-text-dim">{b.finding}</p>
                  {b.source && (
                    <span className="mt-1 block font-mono text-[10px] text-ald-text-dim">via {b.source}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
