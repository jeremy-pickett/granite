'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import WatchlistButton from '@/components/alidade/WatchlistButton';
import IALDScoreGauge from '@/components/alidade/securities/IALDScoreGauge';
import Sparkline from '@/components/alidade/securities/Sparkline';
import CompareOverlay, { type CompareSecurity } from '@/components/alidade/securities/CompareOverlay';
import { usePortfolio } from '@/hooks/usePortfolio';

interface SparklinePoint {
  d: string;
  s: number;
}

interface Security {
  security_id: number;
  ticker: string;
  name: string;
  security_type: string;
  iald: number | null;
  verdict: string | null;
  active_signals: number | null;
  score_trend: string | null;
  volatility_30d: number | null;
  avg_score_30d: number | null;
  sparkline: SparklinePoint[];
}

interface ApiResponse {
  securities: Security[];
  page: number;
  total: number;
  totalPages: number;
}

interface Cohort {
  cohort_id: number;
  cohort_type: string;
  cohort_name: string;
  member_count: number;
}

function scoreBg(score: number | null): string {
  if (score === null) return 'bg-ald-surface border-ald-border';
  if (score >= 0.75) return 'bg-ald-red/20 border-ald-red/40';
  if (score >= 0.50) return 'bg-ald-amber/15 border-ald-amber/35';
  if (score >= 0.25) return 'bg-ald-blue/15 border-ald-blue/30';
  return 'bg-ald-surface border-ald-border';
}

function trendLabel(trend: string | null) {
  if (trend === 'improving') return { arrow: '\u2191', cls: 'text-ald-red' };
  if (trend === 'declining') return { arrow: '\u2193', cls: 'text-ald-green' };
  return { arrow: '\u2192', cls: 'text-ald-text-dim' };
}

function LogoImg({ ticker }: { ticker: string }) {
  const [err, setErr] = useState(false);
  if (err) {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-ald-surface-2 font-mono text-xs text-ald-text-dim">
        {ticker.slice(0, 2)}
      </div>
    );
  }
  return (
    <Image
      src={`/logos/${ticker}.png`}
      alt={ticker}
      width={32}
      height={32}
      className="h-8 w-8 shrink-0 rounded"
      onError={() => setErr(true)}
    />
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [type, setType] = useState('all');
  const [sort, setSort] = useState('ticker');
  const [cohort, setCohort] = useState('');
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [loading, setLoading] = useState(true);
  const [skipPage, setSkipPage] = useState('');
  const limit = 24;
  const { glowClass } = usePortfolio();

  // Drag-to-compare state
  const [dragSource, setDragSource] = useState<Security | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [compareLeft, setCompareLeft] = useState<CompareSecurity | null>(null);
  const [compareRight, setCompareRight] = useState<CompareSecurity | null>(null);
  const dragGhostRef = useRef<HTMLDivElement>(null);

  // Fetch cohorts once
  useEffect(() => {
    fetch('/api/cohorts').then(r => r.json()).then(d => setCohorts(d.cohorts ?? [])).catch(() => {});
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      limit: String(limit),
      sort,
      type,
    });
    if (search) params.set('q', search);
    if (cohort) params.set('cohort', cohort);

    const res = await fetch(`/api/securities?${params}`);
    if (res.ok) {
      setData(await res.json());
    }
    setLoading(false);
  }, [page, search, type, sort, cohort]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Reset to page 1 on filter change
  useEffect(() => { setPage(1); }, [search, type, sort, cohort]);

  // Close compare on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setCompareLeft(null);
        setCompareRight(null);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Drag handlers
  function onDragStart(e: React.DragEvent, s: Security) {
    setDragSource(s);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', s.ticker);
    // Custom ghost
    if (dragGhostRef.current) {
      dragGhostRef.current.textContent = s.ticker;
      e.dataTransfer.setDragImage(dragGhostRef.current, 30, 16);
    }
  }

  function onDragOver(e: React.DragEvent, securityId: number) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTarget(securityId);
  }

  function onDragLeave() {
    setDropTarget(null);
  }

  function onDrop(e: React.DragEvent, target: Security) {
    e.preventDefault();
    setDropTarget(null);
    if (dragSource && dragSource.security_id !== target.security_id) {
      setCompareLeft(dragSource as CompareSecurity);
      setCompareRight(target as CompareSecurity);
    }
    setDragSource(null);
  }

  function onDragEnd() {
    setDragSource(null);
    setDropTarget(null);
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Invisible drag ghost */}
      <div
        ref={dragGhostRef}
        className="fixed -left-[9999px] rounded bg-ald-blue px-3 py-1 font-mono text-sm text-ald-void"
      />

      <div className="mb-8">
        <h1 className="mb-1 text-2xl font-light tracking-tight text-ald-ivory">Securities Dashboard</h1>
        <p className="text-sm text-ald-text-muted">
          {data ? `${data.total} securities` : 'Loading...'}
          <span className="ml-3 text-ald-text-dim">Drag two cards to compare</span>
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search ticker or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border border-ald-border bg-ald-surface px-4 py-2 font-mono text-sm text-ald-text placeholder:text-ald-text-dim focus:border-ald-blue/40 focus:outline-none w-64"
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="rounded border border-ald-border bg-ald-surface px-3 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none appearance-none"
        >
          <option value="all">All Types</option>
          <option value="equity">Equities</option>
          <option value="crypto">Crypto</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="rounded border border-ald-border bg-ald-surface px-3 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none appearance-none"
        >
          <option value="ticker">Ticker A-Z</option>
          <option value="name">Name A-Z</option>
          <option value="iald_desc">IALD Score &#8595;</option>
          <option value="iald_asc">IALD Score &#8593;</option>
        </select>
      </div>

      {/* Cohort chips */}
      {cohorts.length > 0 && (
        <div className="mb-6">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setCohort('')}
              className={`rounded-full px-3 py-1 font-mono text-xs uppercase tracking-wider transition-colors ${
                !cohort
                  ? 'bg-ald-blue text-ald-void'
                  : 'border border-ald-border text-ald-text-dim hover:text-ald-text hover:border-ald-blue/30'
              }`}
            >
              All
            </button>
            {cohorts.map((c) => (
              <button
                key={c.cohort_id}
                onClick={() => setCohort(String(c.cohort_id))}
                className={`rounded-full px-3 py-1 font-mono text-xs uppercase tracking-wider transition-colors ${
                  cohort === String(c.cohort_id)
                    ? 'bg-ald-blue text-ald-void'
                    : 'border border-ald-border text-ald-text-dim hover:text-ald-text hover:border-ald-blue/30'
                }`}
              >
                {c.cohort_name} <span className="opacity-50">{c.member_count}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Securities Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {data?.securities.map((s) => {
            const isDragOver = dropTarget === s.security_id;
            const isDragging = dragSource?.security_id === s.security_id;
            const trend = trendLabel(s.score_trend);
            const glow = glowClass(s.ticker);

            return (
              <div
                key={s.security_id}
                draggable
                onDragStart={(e) => onDragStart(e, s)}
                onDragOver={(e) => onDragOver(e, s.security_id)}
                onDragLeave={onDragLeave}
                onDrop={(e) => onDrop(e, s)}
                onDragEnd={onDragEnd}
                className={`group relative rounded border p-3 transition-all cursor-grab active:cursor-grabbing ${scoreBg(s.iald)} ${glow} ${
                  isDragOver
                    ? 'ring-2 ring-ald-blue scale-[1.01]'
                    : isDragging
                      ? 'opacity-50 scale-[0.97]'
                      : 'hover:border-ald-blue/40'
                }`}
              >
                <Link
                  href={`/alidade/research/${s.ticker}`}
                  className="absolute inset-0 z-10"
                  draggable={false}
                  onClick={(e) => { if (dragSource) e.preventDefault(); }}
                />

                {/* Row 1: Logo + ticker/name | type badge */}
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <LogoImg ticker={s.ticker} />
                    <div className="min-w-0">
                      <span className="block font-mono text-xs font-medium text-ald-ivory group-hover:text-ald-blue transition-colors leading-tight">
                        {s.ticker}
                      </span>
                      <span className="block text-[11px] text-ald-text-dim truncate max-w-[100px] leading-tight">{s.name}</span>
                    </div>
                  </div>
                  <div className="relative z-20 flex items-center gap-1.5 shrink-0">
                    <WatchlistButton ticker={s.ticker} />
                    <span className="rounded bg-ald-surface-2 px-1.5 py-px font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">
                      {s.security_type}
                    </span>
                  </div>
                </div>

                {/* Row 2: Score + sparkline, compact */}
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <IALDScoreGauge score={s.iald !== null ? Number(s.iald) : null} size="sm" showVerdict={false} />
                  <Sparkline points={s.sparkline ?? []} width={80} height={24} />
                </div>

                {/* Row 3: verdict + trend — tight bottom */}
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">
                    {s.verdict ?? ''}
                  </span>
                  <span className={`font-mono text-[10px] ${trend.cls}`}>
                    {trend.arrow} {s.score_trend ?? 'stable'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {data && data.totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-4">
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="rounded border border-ald-border px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            &larr; Previous
          </button>
          <span className="font-mono text-sm text-ald-text-dim">
            Page {data.page} of {data.totalPages}
          </span>
          <button
            disabled={page >= data.totalPages}
            onClick={() => setPage(page + 1)}
            className="rounded border border-ald-border px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Next &rarr;
          </button>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const p = parseInt(skipPage, 10);
              if (p >= 1 && p <= data.totalPages) setPage(p);
              setSkipPage('');
            }}
            className="flex items-center gap-1 ml-4"
          >
            <span className="font-mono text-xs text-ald-text-dim">Go to</span>
            <input
              type="number"
              min={1}
              max={data.totalPages}
              value={skipPage}
              onChange={(e) => setSkipPage(e.target.value)}
              placeholder="#"
              className="w-14 rounded border border-ald-border bg-ald-surface px-2 py-1.5 font-mono text-xs text-ald-text text-center focus:border-ald-blue/40 focus:outline-none"
            />
          </form>
        </div>
      )}

      {/* Compare Overlay */}
      {compareLeft && compareRight && (
        <CompareOverlay
          left={compareLeft}
          right={compareRight}
          onClose={() => {
            setCompareLeft(null);
            setCompareRight(null);
          }}
        />
      )}
    </div>
  );
}
