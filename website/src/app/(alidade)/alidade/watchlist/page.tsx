'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import IALDScoreGauge from '@/components/alidade/securities/IALDScoreGauge';
import { usePortfolio } from '@/hooks/usePortfolio';
import Sparkline from '@/components/alidade/securities/Sparkline';
import CompareOverlay, { type CompareSecurity } from '@/components/alidade/securities/CompareOverlay';

interface SparklinePoint {
  d: string;
  s: number;
}

interface WatchlistItem {
  watchlist_id: number;
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
  added_at: string;
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

export default function WatchlistPage() {
  const { isAuthenticated, isLoading: authLoading, getIdToken } = useAuth();
  const { glowClass } = usePortfolio();
  const router = useRouter();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState<string | null>(null);

  // Drag-to-compare state
  const [dragSource, setDragSource] = useState<WatchlistItem | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [compareLeft, setCompareLeft] = useState<CompareSecurity | null>(null);
  const [compareRight, setCompareRight] = useState<CompareSecurity | null>(null);
  const dragGhostRef = useRef<HTMLDivElement>(null);

  const fetchWatchlist = useCallback(async () => {
    const token = await getIdToken();
    if (!token) return;
    setLoading(true);
    const res = await fetch('/api/watchlist', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setItems(data.watchlist);
    }
    setLoading(false);
  }, [getIdToken]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/alidade/login');
    } else if (isAuthenticated) {
      fetchWatchlist();
    }
  }, [isAuthenticated, authLoading, router, fetchWatchlist]);

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

  const handleRemove = async (ticker: string) => {
    const token = await getIdToken();
    if (!token) return;
    setRemoving(ticker);
    const res = await fetch('/api/watchlist', {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ticker }),
    });
    if (res.ok) {
      setItems(items.filter(i => i.ticker !== ticker));
    }
    setRemoving(null);
  };

  // Drag handlers
  function onDragStart(e: React.DragEvent, s: WatchlistItem) {
    setDragSource(s);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', s.ticker);
    if (dragGhostRef.current) {
      dragGhostRef.current.textContent = s.ticker;
      e.dataTransfer.setDragImage(dragGhostRef.current, 30, 16);
    }
  }

  function onDragOver(e: React.DragEvent, watchlistId: number) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTarget(watchlistId);
  }

  function onDragLeave() {
    setDropTarget(null);
  }

  function onDrop(e: React.DragEvent, target: WatchlistItem) {
    e.preventDefault();
    setDropTarget(null);
    if (dragSource && dragSource.watchlist_id !== target.watchlist_id) {
      setCompareLeft(dragSource as unknown as CompareSecurity);
      setCompareRight(target as unknown as CompareSecurity);
    }
    setDragSource(null);
  }

  function onDragEnd() {
    setDragSource(null);
    setDropTarget(null);
  }

  if (authLoading || (!isAuthenticated && !authLoading)) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      {/* Invisible drag ghost */}
      <div
        ref={dragGhostRef}
        className="fixed -left-[9999px] rounded bg-ald-blue px-3 py-1 font-mono text-sm text-ald-void"
      />

      <div className="mb-8">
        <h1 className="mb-1 text-2xl font-light tracking-tight text-ald-ivory">Watchlist</h1>
        <p className="text-sm text-ald-text-muted">
          {loading ? 'Loading...' : `${items.length} securities monitored`}
          {items.length > 1 && (
            <span className="ml-3 text-ald-text-dim">Drag two rows to compare</span>
          )}
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
          <p className="mb-2 text-sm text-ald-text-muted">No securities in your watchlist.</p>
          <Link href="/alidade/dashboard" className="font-mono text-sm text-ald-blue hover:text-ald-ivory transition-colors">
            Browse Dashboard &rarr;
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((s) => {
            const isDragOver = dropTarget === s.watchlist_id;
            const isDragging = dragSource?.watchlist_id === s.watchlist_id;
            const trend = trendLabel(s.score_trend);
            const glow = glowClass(s.ticker);

            return (
              <div
                key={s.watchlist_id}
                draggable
                onDragStart={(e) => onDragStart(e, s)}
                onDragOver={(e) => onDragOver(e, s.watchlist_id)}
                onDragLeave={onDragLeave}
                onDrop={(e) => onDrop(e, s)}
                onDragEnd={onDragEnd}
                className={`group relative flex items-center justify-between rounded-lg border bg-ald-surface p-4 transition-all cursor-grab active:cursor-grabbing ${glow} ${
                  isDragOver
                    ? 'ring-2 ring-ald-blue scale-[1.01] border-ald-blue/40'
                    : isDragging
                      ? 'opacity-50 scale-[0.98] border-ald-border'
                      : 'border-ald-border hover:border-ald-blue/30'
                }`}
              >
                <Link
                  href={`/alidade/research/${s.ticker}`}
                  className="flex items-center gap-4 flex-1 min-w-0"
                  draggable={false}
                  onClick={(e) => { if (dragSource) e.preventDefault(); }}
                >
                  <LogoImg ticker={s.ticker} />
                  <IALDScoreGauge
                    score={s.iald !== null ? Number(s.iald) : null}
                    size="sm"
                    showVerdict={false}
                  />
                  <div className="min-w-0">
                    <span className="block font-mono text-sm text-ald-ivory group-hover:text-ald-blue transition-colors">
                      {s.ticker}
                    </span>
                    <span className="block text-sm text-ald-text-dim truncate">{s.name}</span>
                  </div>
                  <Sparkline points={s.sparkline ?? []} width={100} height={28} />
                </Link>
                <div className="flex items-center gap-4 shrink-0 ml-4">
                  {s.verdict && (
                    <span className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">{s.verdict}</span>
                  )}
                  <span className={`font-mono text-xs ${trend.cls}`}>
                    {trend.arrow} {s.score_trend ?? 'stable'}
                  </span>
                  <span className="font-mono text-xs text-ald-text-dim">
                    {new Date(s.added_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={() => handleRemove(s.ticker)}
                    disabled={removing === s.ticker}
                    className="relative z-10 rounded border border-ald-border px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-text-dim hover:text-ald-red hover:border-ald-red/30 transition-colors disabled:opacity-50"
                  >
                    {removing === s.ticker ? '...' : 'Remove'}
                  </button>
                </div>
              </div>
            );
          })}
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
