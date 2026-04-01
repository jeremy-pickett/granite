'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import IALDScoreGauge from '@/components/alidade/securities/IALDScoreGauge';
import Sparkline from '@/components/alidade/securities/Sparkline';
import CompareOverlay, { type CompareSecurity } from '@/components/alidade/securities/CompareOverlay';
import { usePortfolio } from '@/hooks/usePortfolio';

// ─── Types ───────────────────────────────────────────────────────────────────

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

interface Position {
  ticker: string;
  name: string;
  security_type: string;
  shares: number;
  avg_cost: number;
  total_cost: number;
  bought_at: string;
}

interface Transaction {
  id: string;
  type: 'buy' | 'sell';
  ticker: string;
  shares: number;
  price: number;
  total: number;
  date: string;
  pnl?: number;
}

interface PortfolioState {
  cash: number;
  positions: Position[];
  transactions: Transaction[];
  started_at: string;
}

interface SnapshotData {
  price: number | null;
  change_pct: number | null;
  price_sparkline: { d: string; p: number }[];
}

// ─── LocalStorage helpers ────────────────────────────────────────────────────

const STORAGE_KEY = 'alidade_portfolio_sim';
const INITIAL_CASH = 10000;

function loadPortfolio(): PortfolioState {
  if (typeof window === 'undefined') {
    return { cash: INITIAL_CASH, positions: [], transactions: [], started_at: new Date().toISOString() };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return { cash: INITIAL_CASH, positions: [], transactions: [], started_at: new Date().toISOString() };
}

function savePortfolio(state: PortfolioState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

// ─── Small components ────────────────────────────────────────────────────────

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

function formatMoney(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function pnlColor(pnl: number): string {
  if (pnl > 0) return 'text-ald-green';
  if (pnl < 0) return 'text-ald-red';
  return 'text-ald-text-dim';
}

function pnlSign(pnl: number): string {
  return pnl > 0 ? '+' : '';
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

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function SimulatorPage() {
  const { isAuthenticated, isLoading: authLoading, getIdToken } = useAuth();
  const router = useRouter();

  // Portfolio state
  const [portfolio, setPortfolio] = useState<PortfolioState>(loadPortfolio);

  const { glowClass: portfolioGlow } = usePortfolio();

  // Securities browser
  const [securities, setSecurities] = useState<Security[]>([]);
  const [secLoading, setSecLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [type, setType] = useState('all');
  const [sort, setSort] = useState('iald_desc');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [skipPage, setSkipPage] = useState('');

  // IALD filter
  const [ialdMin, setIaldMin] = useState(0.01);

  // Buy modal
  const [buyTarget, setBuyTarget] = useState<Security | null>(null);
  const [buyPrice, setBuyPrice] = useState<number | null>(null);
  const [buyShares, setBuyShares] = useState(1);
  const [buyLoading, setBuyLoading] = useState(false);

  // Sell modal
  const [sellTarget, setSellTarget] = useState<Position | null>(null);
  const [sellPrice, setSellPrice] = useState<number | null>(null);
  const [sellShares, setSellShares] = useState(1);
  const [sellLoading, setSellLoading] = useState(false);

  // Live prices for positions
  const [livePrices, setLivePrices] = useState<Record<string, SnapshotData>>({});

  // Tab
  const [tab, setTab] = useState<'browse' | 'positions' | 'history'>('browse');

  // Drag-to-compare state
  const [dragSource, setDragSource] = useState<Security | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [compareLeft, setCompareLeft] = useState<CompareSecurity | null>(null);
  const [compareRight, setCompareRight] = useState<CompareSecurity | null>(null);
  const dragGhostRef = useRef<HTMLDivElement>(null);

  // Persist on change
  useEffect(() => { savePortfolio(portfolio); }, [portfolio]);

  // Auth guard
  useEffect(() => {
    if (!authLoading && !isAuthenticated) router.push('/alidade/login');
  }, [isAuthenticated, authLoading, router]);

  // Close compare on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { setCompareLeft(null); setCompareRight(null); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Fetch securities
  const fetchSecurities = useCallback(async () => {
    setSecLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      limit: '24',
      sort,
      type,
    });
    if (search) params.set('q', search);

    const res = await fetch(`/api/securities?${params}`);
    if (res.ok) {
      const data = await res.json();
      const filtered = data.securities.filter((s: Security) =>
        s.iald !== null && s.iald >= ialdMin
      );
      setSecurities(filtered);
      setTotalPages(data.totalPages);
    }
    setSecLoading(false);
  }, [page, search, type, sort, ialdMin]);

  useEffect(() => { if (isAuthenticated) fetchSecurities(); }, [fetchSecurities, isAuthenticated]);
  useEffect(() => { setPage(1); }, [search, type, sort, ialdMin]);

  // Fetch live price for a ticker
  const fetchPrice = useCallback(async (ticker: string): Promise<number | null> => {
    try {
      const res = await fetch(`/api/security-detail?ticker=${ticker}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data.snapshot?.price ? Number(data.snapshot.price) : null;
    } catch {
      return null;
    }
  }, []);

  // Fetch live prices for all positions
  useEffect(() => {
    if (portfolio.positions.length === 0) return;
    let cancelled = false;
    async function fetchAll() {
      const prices: Record<string, SnapshotData> = {};
      await Promise.all(
        portfolio.positions.map(async (p) => {
          try {
            const res = await fetch(`/api/security-detail?ticker=${p.ticker}`);
            if (res.ok) {
              const data = await res.json();
              if (!cancelled && data.snapshot) {
                prices[p.ticker] = {
                  price: data.snapshot.price ? Number(data.snapshot.price) : null,
                  change_pct: data.snapshot.change_pct ? Number(data.snapshot.change_pct) : null,
                  price_sparkline: (data.price_sparkline ?? []).map((pt: { d: string; p: string | number }) => ({ d: pt.d, p: Number(pt.p) })),
                };
              }
            }
          } catch {}
        })
      );
      if (!cancelled) setLivePrices(prices);
    }
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [portfolio.positions]);

  // ─── Drag handlers ──────────────────────────────────────────────────────

  function onDragStart(e: React.DragEvent, s: Security) {
    setDragSource(s);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', s.ticker);
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

  function onDragLeave() { setDropTarget(null); }

  function onDrop(e: React.DragEvent, target: Security) {
    e.preventDefault();
    setDropTarget(null);
    if (dragSource && dragSource.security_id !== target.security_id) {
      setCompareLeft(dragSource as CompareSecurity);
      setCompareRight(target as CompareSecurity);
    }
    setDragSource(null);
  }

  function onDragEnd() { setDragSource(null); setDropTarget(null); }

  // ─── Buy / Sell ─────────────────────────────────────────────────────────

  async function openBuyModal(e: React.MouseEvent, sec: Security) {
    e.preventDefault();
    e.stopPropagation();
    setBuyTarget(sec);
    setBuyShares(1);
    setBuyLoading(true);
    const price = await fetchPrice(sec.ticker);
    setBuyPrice(price);
    setBuyLoading(false);
  }

  function executeBuy() {
    if (!buyTarget || !buyPrice || buyShares < 1) return;
    const total = buyShares * buyPrice;
    if (total > portfolio.cash) return;

    const existing = portfolio.positions.find(p => p.ticker === buyTarget.ticker);
    let newPositions: Position[];

    if (existing) {
      const newShares = existing.shares + buyShares;
      const newTotalCost = existing.total_cost + total;
      newPositions = portfolio.positions.map(p =>
        p.ticker === buyTarget.ticker
          ? { ...p, shares: newShares, avg_cost: newTotalCost / newShares, total_cost: newTotalCost }
          : p
      );
    } else {
      newPositions = [
        ...portfolio.positions,
        {
          ticker: buyTarget.ticker,
          name: buyTarget.name,
          security_type: buyTarget.security_type,
          shares: buyShares,
          avg_cost: buyPrice,
          total_cost: total,
          bought_at: new Date().toISOString(),
        },
      ];
    }

    const tx: Transaction = {
      id: crypto.randomUUID(),
      type: 'buy',
      ticker: buyTarget.ticker,
      shares: buyShares,
      price: buyPrice,
      total,
      date: new Date().toISOString(),
    };

    setPortfolio({
      ...portfolio,
      cash: portfolio.cash - total,
      positions: newPositions,
      transactions: [tx, ...portfolio.transactions],
    });
    setBuyTarget(null);
  }

  async function openSellModal(pos: Position) {
    setSellTarget(pos);
    setSellShares(pos.shares);
    setSellLoading(true);
    const price = await fetchPrice(pos.ticker);
    setSellPrice(price);
    setSellLoading(false);
  }

  function executeSell() {
    if (!sellTarget || !sellPrice || sellShares < 1 || sellShares > sellTarget.shares) return;

    const total = sellShares * sellPrice;
    const costBasis = sellShares * sellTarget.avg_cost;
    const pnl = total - costBasis;

    let newPositions: Position[];
    if (sellShares === sellTarget.shares) {
      newPositions = portfolio.positions.filter(p => p.ticker !== sellTarget.ticker);
    } else {
      newPositions = portfolio.positions.map(p =>
        p.ticker === sellTarget.ticker
          ? { ...p, shares: p.shares - sellShares, total_cost: (p.shares - sellShares) * p.avg_cost }
          : p
      );
    }

    const tx: Transaction = {
      id: crypto.randomUUID(),
      type: 'sell',
      ticker: sellTarget.ticker,
      shares: sellShares,
      price: sellPrice,
      total,
      date: new Date().toISOString(),
      pnl,
    };

    setPortfolio({
      ...portfolio,
      cash: portfolio.cash + total,
      positions: newPositions,
      transactions: [tx, ...portfolio.transactions],
    });
    setSellTarget(null);
  }

  function resetPortfolio() {
    if (!confirm('Reset portfolio? This will wipe all positions and history.')) return;
    setPortfolio({ cash: INITIAL_CASH, positions: [], transactions: [], started_at: new Date().toISOString() });
    setLivePrices({});
  }

  // ─── Computed values ──────────────────────────────────────────────────

  const totalMarketValue = portfolio.positions.reduce((sum, p) => {
    const lp = livePrices[p.ticker]?.price;
    return sum + (lp ? lp * p.shares : p.total_cost);
  }, 0);

  const totalCostBasis = portfolio.positions.reduce((sum, p) => sum + p.total_cost, 0);
  const unrealizedPnl = totalMarketValue - totalCostBasis;
  const realizedPnl = portfolio.transactions
    .filter(t => t.type === 'sell' && t.pnl !== undefined)
    .reduce((sum, t) => sum + (t.pnl ?? 0), 0);
  const totalPnl = unrealizedPnl + realizedPnl;
  const portfolioValue = portfolio.cash + totalMarketValue;
  const totalReturn = ((portfolioValue - INITIAL_CASH) / INITIAL_CASH) * 100;

  // ─── Render ───────────────────────────────────────────────────────────

  if (authLoading || (!isAuthenticated && !authLoading)) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Invisible drag ghost */}
      <div
        ref={dragGhostRef}
        className="fixed -left-[9999px] rounded bg-ald-blue px-3 py-1 font-mono text-sm text-ald-void"
      />

      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-light tracking-tight text-ald-ivory">
            Portfolio Simulator
          </h1>
          <p className="text-sm text-ald-text-muted">
            Paper trading with IALD conviction filtering
            {securities.length > 1 && tab === 'browse' && (
              <span className="ml-3 text-ald-text-dim">Drag two cards to compare</span>
            )}
          </p>
        </div>
        <button
          onClick={resetPortfolio}
          className="rounded border border-ald-border px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-text-dim hover:text-ald-red hover:border-ald-red/30 transition-colors"
        >
          Reset
        </button>
      </div>

      {/* Portfolio Summary Cards */}
      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-ald-border bg-ald-surface p-4">
          <div className="text-xs font-mono uppercase tracking-wider text-ald-text-dim mb-1">Portfolio Value</div>
          <div className="font-mono text-lg text-ald-ivory">{formatMoney(portfolioValue)}</div>
        </div>
        <div className="rounded-lg border border-ald-border bg-ald-surface p-4">
          <div className="text-xs font-mono uppercase tracking-wider text-ald-text-dim mb-1">Cash</div>
          <div className="font-mono text-lg text-ald-blue">{formatMoney(portfolio.cash)}</div>
        </div>
        <div className="rounded-lg border border-ald-border bg-ald-surface p-4">
          <div className="text-xs font-mono uppercase tracking-wider text-ald-text-dim mb-1">Total P&L</div>
          <div className={`font-mono text-lg ${pnlColor(totalPnl)}`}>
            {pnlSign(totalPnl)}{formatMoney(totalPnl)}
          </div>
        </div>
        <div className="rounded-lg border border-ald-border bg-ald-surface p-4">
          <div className="text-xs font-mono uppercase tracking-wider text-ald-text-dim mb-1">Return</div>
          <div className={`font-mono text-lg ${pnlColor(totalReturn)}`}>
            {pnlSign(totalReturn)}{totalReturn.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* IALD Slider */}
      <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">
            IALD Minimum Conviction
          </span>
          <span className="font-mono text-sm text-ald-blue">{ialdMin.toFixed(2)}</span>
        </div>
        <input
          type="range"
          min="0.01"
          max="1.0"
          step="0.01"
          value={ialdMin}
          onChange={(e) => setIaldMin(parseFloat(e.target.value))}
          className="w-full accent-ald-blue"
        />
        <div className="flex justify-between mt-1">
          <span className="font-mono text-[10px] text-ald-text-dim">0.01 — show everything</span>
          <span className="font-mono text-[10px] text-ald-text-dim">1.00 — critical only</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-ald-border">
        {(['browse', 'positions', 'history'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 font-mono text-sm uppercase tracking-wider transition-colors border-b-2 -mb-px ${
              tab === t
                ? 'text-ald-ivory border-ald-blue'
                : 'text-ald-text-dim border-transparent hover:text-ald-text'
            }`}
          >
            {t === 'browse' ? 'Browse' : t === 'positions' ? `Positions (${portfolio.positions.length})` : `History (${portfolio.transactions.length})`}
          </button>
        ))}
      </div>

      {/* ─── Browse Tab ──────────────────────────────────────────────────── */}
      {tab === 'browse' && (
        <div>
          {/* Filters */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
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
              <option value="all">All Sectors</option>
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
            <span className="font-mono text-xs text-ald-text-dim">
              Showing IALD &ge; {ialdMin.toFixed(2)}
            </span>
          </div>

          {secLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
            </div>
          ) : securities.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted mb-1">No securities match your filters.</p>
              <p className="font-mono text-xs text-ald-text-dim">Try lowering the IALD threshold or broadening your search.</p>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {securities.map((s) => {
                const isDragOver = dropTarget === s.security_id;
                const isDragging = dragSource?.security_id === s.security_id;
                const trend = trendLabel(s.score_trend);
                const held = portfolio.positions.find(p => p.ticker === s.ticker);
                const glow = portfolioGlow(s.ticker);

                return (
                  <div
                    key={s.security_id}
                    draggable
                    onDragStart={(e) => onDragStart(e, s)}
                    onDragOver={(e) => onDragOver(e, s.security_id)}
                    onDragLeave={onDragLeave}
                    onDrop={(e) => onDrop(e, s)}
                    onDragEnd={onDragEnd}
                    className={`group relative rounded-lg border p-4 transition-all cursor-grab active:cursor-grabbing ${scoreBg(s.iald)} ${glow} ${
                      isDragOver
                        ? 'ring-2 ring-ald-blue scale-[1.02]'
                        : isDragging
                          ? 'opacity-50 scale-95'
                          : 'hover:border-ald-blue/40 hover:shadow-[0_0_20px_rgba(106,143,216,0.06)]'
                    }`}
                  >
                    <Link
                      href={`/alidade/research/${s.ticker}`}
                      className="absolute inset-0 z-10"
                      draggable={false}
                      onClick={(e) => { if (dragSource) e.preventDefault(); }}
                    />

                    {/* Top: Logo, ticker, name | type + held badge */}
                    <div className="mb-3 flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <LogoImg ticker={s.ticker} />
                        <div>
                          <span className="block font-mono text-sm font-medium text-ald-ivory group-hover:text-ald-blue transition-colors">
                            {s.ticker}
                          </span>
                          <span className="block text-xs text-ald-text-dim truncate max-w-[120px]">{s.name}</span>
                        </div>
                      </div>
                      <div className="relative z-20 flex items-center gap-2">
                        {held && (
                          <span className="rounded bg-ald-blue/20 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ald-blue">
                            {held.shares} held
                          </span>
                        )}
                        <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-ald-text-dim">
                          {s.security_type}
                        </span>
                      </div>
                    </div>

                    {/* Middle: Score gauge + Sparkline */}
                    <div className="mb-2 flex items-center justify-between">
                      <IALDScoreGauge
                        score={s.iald !== null ? Number(s.iald) : null}
                        size="sm"
                        showVerdict={false}
                      />
                      <Sparkline points={s.sparkline ?? []} />
                    </div>

                    {/* Bottom: verdict + trend + buy */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {s.verdict ? (
                          <span className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">
                            {s.verdict}
                          </span>
                        ) : (
                          <span />
                        )}
                        <span className={`font-mono text-xs ${trend.cls}`}>
                          {trend.arrow} {s.score_trend ?? 'stable'}
                        </span>
                      </div>
                      <button
                        onClick={(e) => openBuyModal(e, s)}
                        className="relative z-20 rounded border border-ald-green/40 bg-ald-green/10 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-ald-green hover:bg-ald-green/20 transition-colors"
                      >
                        Buy
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-4">
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="rounded border border-ald-border px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors disabled:opacity-30"
              >
                &larr; Prev
              </button>
              <span className="font-mono text-sm text-ald-text-dim">
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                className="rounded border border-ald-border px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors disabled:opacity-30"
              >
                Next &rarr;
              </button>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const p = parseInt(skipPage, 10);
                  if (p >= 1 && p <= totalPages) setPage(p);
                  setSkipPage('');
                }}
                className="flex items-center gap-1 ml-4"
              >
                <span className="font-mono text-xs text-ald-text-dim">Go to</span>
                <input
                  type="number"
                  min={1}
                  max={totalPages}
                  value={skipPage}
                  onChange={(e) => setSkipPage(e.target.value)}
                  placeholder="#"
                  className="w-14 rounded border border-ald-border bg-ald-surface px-2 py-1.5 font-mono text-xs text-ald-text text-center focus:border-ald-blue/40 focus:outline-none"
                />
              </form>
            </div>
          )}
        </div>
      )}

      {/* ─── Positions Tab ───────────────────────────────────────────────── */}
      {tab === 'positions' && (
        <div>
          {portfolio.positions.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted mb-2">No positions yet.</p>
              <button
                onClick={() => setTab('browse')}
                className="font-mono text-sm text-ald-blue hover:text-ald-ivory transition-colors"
              >
                Browse securities to buy &rarr;
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {/* Column header */}
              <div className="grid grid-cols-14 gap-2 px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-ald-text-dim" style={{ gridTemplateColumns: '3fr 1fr 2fr 2fr 1.5fr 2fr 2fr' }}>
                <div>Security</div>
                <div className="text-right">Shares</div>
                <div className="text-right">Avg Cost</div>
                <div className="text-right">Mkt Price</div>
                <div className="text-center">14d Price</div>
                <div className="text-right">P&L</div>
                <div className="text-right">Action</div>
              </div>

              {portfolio.positions.map((pos) => {
                const snap = livePrices[pos.ticker];
                const lp = snap?.price;
                const mktValue = lp ? lp * pos.shares : null;
                const positionPnl = mktValue ? mktValue - pos.total_cost : null;
                const positionPnlPct = positionPnl !== null ? (positionPnl / pos.total_cost) * 100 : null;
                const sparkData = (snap?.price_sparkline ?? []).map((pt: { d: string; p: number }) => ({ d: pt.d, s: pt.p }));
                const sparkColor = positionPnl !== null ? (positionPnl >= 0 ? '#1A7D42' : '#C53030') : '#6A8FD8';

                return (
                  <div
                    key={pos.ticker}
                    className="grid items-center rounded-lg border border-ald-border bg-ald-surface p-4 hover:border-ald-blue/30 transition-all"
                    style={{ gridTemplateColumns: '3fr 1fr 2fr 2fr 1.5fr 2fr 2fr' }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <LogoImg ticker={pos.ticker} />
                      <div className="min-w-0">
                        <Link
                          href={`/alidade/research/${pos.ticker}`}
                          className="block font-mono text-sm text-ald-ivory hover:text-ald-blue transition-colors"
                        >
                          {pos.ticker}
                        </Link>
                        <span className="block text-xs text-ald-text-dim truncate">{pos.name}</span>
                      </div>
                    </div>
                    <div className="text-right font-mono text-sm text-ald-ivory">
                      {pos.shares}
                    </div>
                    <div className="text-right font-mono text-sm text-ald-text-dim">
                      {formatMoney(pos.avg_cost)}
                    </div>
                    <div className="text-right font-mono text-sm text-ald-ivory">
                      {lp ? formatMoney(lp) : '...'}
                    </div>
                    <div className="flex justify-center">
                      <Sparkline points={sparkData} width={80} height={24} color={sparkColor} />
                    </div>
                    <div className="text-right">
                      {positionPnl !== null ? (
                        <div>
                          <div className={`font-mono text-sm ${pnlColor(positionPnl)}`}>
                            {pnlSign(positionPnl)}{formatMoney(positionPnl)}
                          </div>
                          <div className={`font-mono text-[10px] ${pnlColor(positionPnl)}`}>
                            {pnlSign(positionPnlPct!)}{positionPnlPct!.toFixed(2)}%
                          </div>
                        </div>
                      ) : (
                        <span className="font-mono text-sm text-ald-text-dim">...</span>
                      )}
                    </div>
                    <div className="text-right">
                      <button
                        onClick={() => openSellModal(pos)}
                        className="rounded border border-ald-red/40 bg-ald-red/10 px-4 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-red hover:bg-ald-red/20 transition-colors"
                      >
                        Sell
                      </button>
                    </div>
                  </div>
                );
              })}

              {/* P&L summary */}
              <div className="mt-4 flex items-center justify-between rounded-lg border border-ald-border bg-ald-surface-2 p-4">
                <div className="flex gap-8">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">Unrealized</div>
                    <div className={`font-mono text-sm ${pnlColor(unrealizedPnl)}`}>
                      {pnlSign(unrealizedPnl)}{formatMoney(unrealizedPnl)}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">Realized</div>
                    <div className={`font-mono text-sm ${pnlColor(realizedPnl)}`}>
                      {pnlSign(realizedPnl)}{formatMoney(realizedPnl)}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">Market Value</div>
                  <div className="font-mono text-sm text-ald-ivory">{formatMoney(totalMarketValue)}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── History Tab ─────────────────────────────────────────────────── */}
      {tab === 'history' && (
        <div>
          {portfolio.transactions.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">No transactions yet.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {portfolio.transactions.map((tx) => (
                <div
                  key={tx.id}
                  className="flex items-center justify-between rounded-lg border border-ald-border bg-ald-surface p-4"
                >
                  <div className="flex items-center gap-4">
                    <span className={`rounded px-2 py-0.5 font-mono text-xs uppercase tracking-wider ${
                      tx.type === 'buy'
                        ? 'bg-ald-green/15 text-ald-green'
                        : 'bg-ald-red/15 text-ald-red'
                    }`}>
                      {tx.type}
                    </span>
                    <LogoImg ticker={tx.ticker} />
                    <div>
                      <span className="font-mono text-sm text-ald-ivory">{tx.ticker}</span>
                      <span className="ml-2 font-mono text-xs text-ald-text-dim">
                        {tx.shares} shares @ {formatMoney(tx.price)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    {tx.pnl !== undefined && (
                      <span className={`font-mono text-sm ${pnlColor(tx.pnl)}`}>
                        {pnlSign(tx.pnl)}{formatMoney(tx.pnl)}
                      </span>
                    )}
                    <span className={`font-mono text-sm ${tx.type === 'buy' ? 'text-ald-red' : 'text-ald-green'}`}>
                      {tx.type === 'buy' ? '-' : '+'}{formatMoney(tx.total)}
                    </span>
                    <span className="font-mono text-xs text-ald-text-dim">
                      {new Date(tx.date).toLocaleDateString()} {new Date(tx.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── Buy Modal ───────────────────────────────────────────────────── */}
      {buyTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-ald-border bg-ald-void p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-mono text-lg text-ald-ivory">Buy {buyTarget.ticker}</h2>
              <button onClick={() => setBuyTarget(null)} className="font-mono text-sm text-ald-text-dim hover:text-ald-text">&times;</button>
            </div>

            {buyLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
                <span className="ml-3 font-mono text-sm text-ald-text-dim">Fetching price...</span>
              </div>
            ) : buyPrice === null ? (
              <div className="py-8 text-center">
                <p className="text-sm text-ald-red">Price unavailable for {buyTarget.ticker}.</p>
                <button onClick={() => setBuyTarget(null)} className="mt-4 font-mono text-sm text-ald-text-dim hover:text-ald-text">Close</button>
              </div>
            ) : (
              <>
                <div className="mb-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-ald-text-dim">{buyTarget.name}</span>
                    {buyTarget.iald !== null && (
                      <IALDScoreGauge score={Number(buyTarget.iald)} size="sm" showVerdict={false} />
                    )}
                  </div>
                  <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                    <span className="font-mono text-xs uppercase text-ald-text-dim">Market Price</span>
                    <span className="font-mono text-lg text-ald-ivory">{formatMoney(buyPrice)}</span>
                  </div>
                  <div>
                    <label className="block font-mono text-xs uppercase tracking-wider text-ald-text-dim mb-1">Shares</label>
                    <input
                      type="number"
                      min={1}
                      max={Math.floor(portfolio.cash / buyPrice)}
                      value={buyShares}
                      onChange={(e) => setBuyShares(Math.max(1, parseInt(e.target.value) || 1))}
                      className="w-full rounded border border-ald-border bg-ald-surface px-4 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                    <span className="font-mono text-xs uppercase text-ald-text-dim">Total Cost</span>
                    <span className={`font-mono text-lg ${buyShares * buyPrice > portfolio.cash ? 'text-ald-red' : 'text-ald-ivory'}`}>
                      {formatMoney(buyShares * buyPrice)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-ald-text-dim">
                    <span>Available: {formatMoney(portfolio.cash)}</span>
                    <button
                      onClick={() => setBuyShares(Math.floor(portfolio.cash / buyPrice))}
                      className="font-mono text-ald-blue hover:text-ald-ivory transition-colors"
                    >
                      Max
                    </button>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button onClick={() => setBuyTarget(null)} className="flex-1 rounded border border-ald-border py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors">Cancel</button>
                  <button
                    onClick={executeBuy}
                    disabled={buyShares * buyPrice > portfolio.cash || buyShares < 1}
                    className="flex-1 rounded bg-ald-green/20 border border-ald-green/40 py-2 font-mono text-sm uppercase tracking-wider text-ald-green hover:bg-ald-green/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    Execute Buy
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ─── Sell Modal ──────────────────────────────────────────────────── */}
      {sellTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-ald-border bg-ald-void p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-mono text-lg text-ald-ivory">Sell {sellTarget.ticker}</h2>
              <button onClick={() => setSellTarget(null)} className="font-mono text-sm text-ald-text-dim hover:text-ald-text">&times;</button>
            </div>

            {sellLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
                <span className="ml-3 font-mono text-sm text-ald-text-dim">Fetching price...</span>
              </div>
            ) : sellPrice === null ? (
              <div className="py-8 text-center">
                <p className="text-sm text-ald-red">Price unavailable for {sellTarget.ticker}.</p>
                <button onClick={() => setSellTarget(null)} className="mt-4 font-mono text-sm text-ald-text-dim hover:text-ald-text">Close</button>
              </div>
            ) : (
              <>
                <div className="mb-4 space-y-3">
                  <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                    <span className="font-mono text-xs uppercase text-ald-text-dim">Market Price</span>
                    <span className="font-mono text-lg text-ald-ivory">{formatMoney(sellPrice)}</span>
                  </div>
                  <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                    <span className="font-mono text-xs uppercase text-ald-text-dim">Your Avg Cost</span>
                    <span className="font-mono text-sm text-ald-text-dim">{formatMoney(sellTarget.avg_cost)}</span>
                  </div>
                  <div>
                    <label className="block font-mono text-xs uppercase tracking-wider text-ald-text-dim mb-1">
                      Shares to Sell (holding {sellTarget.shares})
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={sellTarget.shares}
                      value={sellShares}
                      onChange={(e) => setSellShares(Math.max(1, Math.min(sellTarget.shares, parseInt(e.target.value) || 1)))}
                      className="w-full rounded border border-ald-border bg-ald-surface px-4 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                    <span className="font-mono text-xs uppercase text-ald-text-dim">Proceeds</span>
                    <span className="font-mono text-lg text-ald-ivory">{formatMoney(sellShares * sellPrice)}</span>
                  </div>
                  {(() => {
                    const pnl = (sellPrice - sellTarget.avg_cost) * sellShares;
                    const pnlPct = ((sellPrice - sellTarget.avg_cost) / sellTarget.avg_cost) * 100;
                    return (
                      <div className={`flex items-center justify-between rounded p-3 ${
                        pnl >= 0 ? 'bg-ald-green/10 border border-ald-green/20' : 'bg-ald-red/10 border border-ald-red/20'
                      }`}>
                        <span className="font-mono text-xs uppercase text-ald-text-dim">P&L</span>
                        <div className="text-right">
                          <span className={`font-mono text-lg ${pnlColor(pnl)}`}>
                            {pnlSign(pnl)}{formatMoney(pnl)}
                          </span>
                          <span className={`ml-2 font-mono text-xs ${pnlColor(pnl)}`}>
                            ({pnlSign(pnlPct)}{pnlPct.toFixed(2)}%)
                          </span>
                        </div>
                      </div>
                    );
                  })()}
                  <div className="flex items-center justify-end text-xs">
                    <button onClick={() => setSellShares(sellTarget.shares)} className="font-mono text-ald-blue hover:text-ald-ivory transition-colors">Sell All</button>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button onClick={() => setSellTarget(null)} className="flex-1 rounded border border-ald-border py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors">Cancel</button>
                  <button
                    onClick={executeSell}
                    disabled={sellShares < 1 || sellShares > sellTarget.shares}
                    className="flex-1 rounded bg-ald-red/20 border border-ald-red/40 py-2 font-mono text-sm uppercase tracking-wider text-ald-red hover:bg-ald-red/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    Execute Sell
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Compare Overlay */}
      {compareLeft && compareRight && (
        <CompareOverlay
          left={compareLeft}
          right={compareRight}
          onClose={() => { setCompareLeft(null); setCompareRight(null); }}
        />
      )}
    </div>
  );
}
