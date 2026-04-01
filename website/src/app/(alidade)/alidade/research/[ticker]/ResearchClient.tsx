'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';
import IALDScoreGauge from '@/components/alidade/securities/IALDScoreGauge';
import TradingLinks from '@/components/alidade/securities/TradingLinks';
import WatchlistButton from '@/components/alidade/WatchlistButton';
import CommentsSection from '@/components/CommentsSection';
import Tooltip, { TipTitle, TipBody, TipScale } from '@/components/alidade/Tooltip';
import { usePortfolio } from '@/hooks/usePortfolio';

interface Collector {
  collector_id: number;
  collector_name: string;
  collector_type: string;
  description: string;
  is_active: boolean;
  last_run_at: string | null;
  last_success_at: string | null;
  run_interval_minutes: number;
  records_count: number | null;
  last_data_at: string | null;
}

interface ScoreAggregates {
  avg_score_30d: number | null;
  min_score_30d: number | null;
  max_score_30d: number | null;
  volatility_30d: number | null;
  score_trend: string | null;
  data_points: number;
  last_score: number | null;
  last_verdict: string | null;
}

interface ScorePoint {
  score_date: string;
  score: number;
  verdict: string;
  active_signals: number;
}

const TYPE_COLORS: Record<string, string> = {
  sec_filing: 'text-ald-amber',
  market_data: 'text-ald-blue',
  analytics: 'text-ald-cyan',
  political: 'text-ald-red',
  social: 'text-fuchsia-400',
  blockchain: 'text-emerald-400',
};

function scoreColor(score: number | null): string {
  if (score === null) return 'text-ald-text-dim';
  if (score >= 0.75) return 'text-ald-red';
  if (score >= 0.50) return 'text-ald-amber';
  if (score >= 0.25) return 'text-ald-blue';
  return 'text-ald-text-dim';
}


function LogoImg({ ticker, size = 32 }: { ticker: string; size?: number }) {
  const [err, setErr] = useState(false);
  if (err) {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded bg-ald-surface-2 font-mono text-sm text-ald-text-dim"
        style={{ width: size, height: size }}
      >
        {ticker.slice(0, 2)}
      </div>
    );
  }
  return (
    <Image
      src={`/logos/${ticker}.png`}
      alt={ticker}
      width={size}
      height={size}
      className="shrink-0 rounded"
      onError={() => setErr(true)}
    />
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function ResearchClient({ ticker }: { ticker: string }) {
  const { isAuthenticated, getIdToken } = useAuth();
  const [onWatchlist, setOnWatchlist] = useState(false);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [security, setSecurity] = useState<{ name: string; security_type: string } | null>(null);
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [aggregates, setAggregates] = useState<ScoreAggregates | null>(null);
  const [history, setHistory] = useState<ScorePoint[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const { getPosition, glowClass } = usePortfolio();

  // Virtual buy state
  const [showBuyModal, setShowBuyModal] = useState(false);
  const [buyShares, setBuyShares] = useState(1);
  const [buyConfirm, setBuyConfirm] = useState<string | null>(null);

  // Check if on watchlist
  const checkWatchlist = useCallback(async () => {
    if (!isAuthenticated) return;
    const token = await getIdToken();
    if (!token) return;
    const res = await fetch('/api/watchlist', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setOnWatchlist(data.watchlist.some((w: { ticker: string }) => w.ticker === ticker));
    }
  }, [isAuthenticated, getIdToken, ticker]);

  // Fetch security info
  useEffect(() => {
    fetch(`/api/securities?q=${ticker}&limit=1`)
      .then(r => r.json())
      .then(data => {
        const match = data.securities?.find((s: { ticker: string }) => s.ticker === ticker);
        if (match) setSecurity({ name: match.name, security_type: match.security_type });
      })
      .catch(() => {});
  }, [ticker]);

  // Fetch collectors for this ticker
  useEffect(() => {
    fetch(`/api/collectors?ticker=${ticker}`)
      .then(r => r.json())
      .then(data => setCollectors(data.collectors ?? []))
      .catch(() => {});
  }, [ticker]);

  // Fetch score history + aggregates
  useEffect(() => {
    fetch(`/api/scores?ticker=${ticker}&days=30`)
      .then(r => r.json())
      .then(data => {
        setHistory(data.history ?? []);
        setAggregates(data.aggregates ?? null);
      })
      .catch(() => {});
  }, [ticker]);

  // Fetch enriched detail (price, analyst, signals, institutional, press, LLM)
  useEffect(() => {
    fetch(`/api/security-detail?ticker=${ticker}`)
      .then(r => r.json())
      .then(d => setDetail(d))
      .catch(() => {});
  }, [ticker]);

  useEffect(() => { checkWatchlist(); }, [checkWatchlist]);

  const toggleWatchlist = async () => {
    const token = await getIdToken();
    if (!token) return;
    setWatchlistLoading(true);
    const method = onWatchlist ? 'DELETE' : 'POST';
    const res = await fetch('/api/watchlist', {
      method,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker }),
    });
    if (res.ok) setOnWatchlist(!onWatchlist);
    setWatchlistLoading(false);
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Breadcrumb */}
      <div className="mb-6 flex items-center gap-2 font-mono text-sm text-ald-text-dim">
        <Link href="/alidade/dashboard" className="hover:text-ald-text transition-colors">Dashboard</Link>
        <span>/</span>
        <span className="text-ald-text">{ticker}</span>
      </div>

      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div className="flex items-center gap-4">
          <LogoImg ticker={ticker} size={48} />
          <div>
            <div className="flex items-center gap-3">
              <h1 className="mb-1 text-3xl font-light tracking-tight text-ald-ivory">{ticker}</h1>
              <WatchlistButton ticker={ticker} size="md" />
            </div>
            <p className="text-sm text-ald-text-muted">
              {security ? `${security.name} \u00b7 ${security.security_type}` : ticker}
            </p>
          </div>
          <IALDScoreGauge
            score={aggregates?.last_score != null ? Number(aggregates.last_score) : null}
            verdict={aggregates?.last_verdict ?? null}
            size="lg"
            bounce
          />
        </div>
        {isAuthenticated && (
          <div className="flex gap-2">
            <button
              onClick={toggleWatchlist}
              disabled={watchlistLoading}
              className={`rounded border px-4 py-2 font-mono text-sm uppercase tracking-wider transition-colors disabled:opacity-50 ${
                onWatchlist
                  ? 'border-ald-green/30 text-ald-green hover:border-ald-red/30 hover:text-ald-red'
                  : 'border-ald-border text-ald-text-dim hover:text-ald-text hover:border-ald-blue/30'
              }`}
            >
              {onWatchlist ? 'On Watchlist' : '+ Watchlist'}
            </button>
            <Link
              href="/alidade/alerts"
              className="rounded border border-ald-border px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text hover:border-ald-blue/30 transition-colors"
            >
              + Alert
            </Link>
            {detail?.snapshot?.price && (
              <button
                onClick={() => { setBuyShares(1); setShowBuyModal(true); }}
                className="rounded border border-ald-green/40 bg-ald-green/10 px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-green hover:bg-ald-green/20 transition-colors"
              >
                Buy (Virtual)
              </button>
            )}
          </div>
        )}
        {/* Buy confirmation flash */}
        {buyConfirm && (
          <div className="animate-[fadeFlash_1.5s_ease-in-out] font-mono text-sm font-bold text-ald-green">
            {buyConfirm}
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-6">
          {/* IALD Score Card */}
          <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
            <div className="mb-6">
                <Tooltip content={<><TipTitle>IALD Score</TipTitle><TipBody>Integrated Anomaly &amp; Liquidity Detection. Scores the platform&apos;s confidence that something significant is happening with this security. Higher score = more signals converging from independent sources. The score measures signal intensity, not price direction — check the individual signal arrows for directional bias.</TipBody><TipScale items={[{color:'#ef4444',label:'0.75+',description:'CRITICAL — multiple strong signals converging'},{color:'#f59e0b',label:'0.50–0.74',description:'ELEVATED — notable signal activity'},{color:'#3b82f6',label:'0.25–0.49',description:'MODERATE — some signals present'},{color:'#6b7280',label:'<0.25',description:'LOW — minimal or background noise'}]} /></>}>
                  <span className="block font-mono text-sm uppercase tracking-wider text-ald-text-dim mb-1">IALD Score &#9432;</span>
                </Tooltip>
                {!aggregates && history.length === 0 && (
                  <p className="mt-2 text-sm text-ald-text-dim">
                    Score data will appear once the scoring engine is active.
                  </p>
                )}
            </div>

            {/* Score Stats — 2x2 grid in the space below IALD label */}
            {aggregates && aggregates.data_points > 0 && (
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <Tooltip position="bottom" content={<><TipTitle>30-Day Average</TipTitle><TipBody>Average IALD score over the last 30 days. Compare to the current score: if current is higher, anomalous activity is increasing. If lower, signals are fading. A security that consistently averages above 0.50 has persistent issues worth investigating.</TipBody></>}>
                    <span className="block font-mono text-xs uppercase text-ald-text-dim">30d Avg &#9432;</span>
                  </Tooltip>
                  <span className={`block font-mono text-lg ${scoreColor(aggregates.avg_score_30d)}`}>
                    {aggregates.avg_score_30d !== null ? Number(aggregates.avg_score_30d).toFixed(2) : '--'}
                  </span>
                </div>
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <Tooltip position="bottom" content={<><TipTitle>Score Volatility</TipTitle><TipBody>Standard deviation of IALD scores over 30 days. High volatility (0.10+) means the score is swinging — new signals appearing and decaying rapidly. Low volatility near 0 means either consistently clean or consistently flagged. Sudden volatility spikes often precede major events.</TipBody></>}>
                    <span className="block font-mono text-xs uppercase text-ald-text-dim">Volatility &#9432;</span>
                  </Tooltip>
                  <span className="block font-mono text-lg text-ald-text">
                    {aggregates.volatility_30d !== null ? Number(aggregates.volatility_30d).toFixed(3) : '--'}
                  </span>
                </div>
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <Tooltip position="bottom" content={<><TipTitle>30-Day Range</TipTitle><TipBody>The minimum and maximum IALD score over the last 30 days. A wide range (e.g., 0.10–0.80) means the security has oscillated between clean and heavily flagged. A narrow range near 0 = consistently quiet. A narrow range near 1 = persistent anomaly that isn&apos;t going away.</TipBody></>}>
                    <span className="block font-mono text-xs uppercase text-ald-text-dim">Range &#9432;</span>
                  </Tooltip>
                  <span className="block font-mono text-lg text-ald-text">
                    {aggregates.min_score_30d !== null && aggregates.max_score_30d !== null
                      ? `${Number(aggregates.min_score_30d).toFixed(2)}-${Number(aggregates.max_score_30d).toFixed(2)}`
                      : '--'}
                  </span>
                </div>
                <div className={`rounded border bg-ald-deep p-3 flex items-center gap-3 ${
                  aggregates.score_trend === 'improving' ? 'border-ald-red/30' :
                  aggregates.score_trend === 'declining' ? 'border-ald-green/30' : 'border-ald-border'
                }`}>
                  <span className={`text-4xl font-light leading-none ${
                    aggregates.score_trend === 'improving' ? 'text-ald-red' :
                    aggregates.score_trend === 'declining' ? 'text-ald-green' : 'text-ald-text-dim'
                  }`}>
                    {aggregates.score_trend === 'improving' ? '↑' : aggregates.score_trend === 'declining' ? '↓' : '→'}
                  </span>
                  <div className="flex flex-col leading-tight">
                    <span className="text-sm font-bold uppercase tracking-wide text-ald-text" style={{ fontFamily: 'system-ui, -apple-system, sans-serif' }}>Trend</span>
                    <span className={`text-sm font-bold uppercase tracking-wide ${
                      aggregates.score_trend === 'improving' ? 'text-ald-red' :
                      aggregates.score_trend === 'declining' ? 'text-ald-green' : 'text-ald-text-dim'
                    }`} style={{ fontFamily: 'system-ui, -apple-system, sans-serif' }}>
                      {aggregates.score_trend ?? 'stable'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* 30-Day History Chart */}
            <div>
              <h3 className="mb-3 font-mono text-sm uppercase tracking-wider text-ald-text-dim">30-Day History</h3>
              {history.length > 0 ? (
                <div className="flex items-end gap-1 h-16">
                  {history.slice().reverse().map((h) => (
                    <div
                      key={h.score_date}
                      className="flex-1 rounded-t bg-ald-blue/30 hover:bg-ald-blue/50 transition-colors"
                      style={{ height: `${Number(h.score) * 100}%` }}
                      title={`${h.score_date}: ${Number(h.score).toFixed(2)}`}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex items-center justify-center h-16 text-sm text-ald-text-dim">
                  Score history will appear once the scoring engine is active.
                </div>
              )}
            </div>

            {/* Deep Dive link */}
            <div className="mt-6 pt-4 border-t border-ald-border/50">
              <Link
                href={`/alidade/research/${ticker}/filings`}
                className="flex items-center justify-between rounded-lg border border-ald-border bg-ald-surface p-4 hover:border-ald-blue/30 transition-all group"
              >
                <div>
                  <span className="block font-mono text-sm text-ald-ivory group-hover:text-ald-blue transition-colors">Deep Dive</span>
                  <span className="block text-xs text-ald-text-dim">Executives, filings, records, background checks</span>
                </div>
                <span className="font-mono text-sm text-ald-text-dim group-hover:text-ald-blue transition-colors">&rarr;</span>
              </Link>
            </div>

            {/* Held position indicator */}
            {(() => {
              const pos = getPosition(ticker);
              if (!pos) return null;
              const price = detail?.snapshot?.price ? Number(detail.snapshot.price) : null;
              const pnl = price ? ((price - pos.avg_cost) / pos.avg_cost * 100) : null;
              return (
                <div className="mt-6 pt-4 border-t border-ald-border/50">
                  <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                    <span className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">Held</span>
                    <div className="text-right">
                      <span className="font-mono text-sm text-ald-ivory">{pos.shares} shares @ ${pos.avg_cost.toFixed(2)}</span>
                      {pnl !== null && (
                        <span className={`ml-2 font-mono text-xs ${pnl >= 0 ? 'text-ald-green' : 'text-ald-red'}`}>
                          {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Trading Links */}
            {security && (
              <div className="mt-6 pt-4 border-t border-ald-border/50">
                <h3 className="mb-3 font-mono text-sm uppercase tracking-wider text-ald-text-dim">Trade (Real)</h3>
                <TradingLinks ticker={ticker} securityType={security.security_type} />
              </div>
            )}
          </div>

          {/* Live Price & Fundamentals */}
          {detail?.snapshot && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Market Data</h2>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <span className="block font-mono text-xs uppercase text-ald-text-dim">Price</span>
                  <span className="block font-mono text-xl text-ald-ivory">
                    ${Number(detail.snapshot.price).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                  </span>
                  {detail.snapshot.change_pct != null && (
                    <span className={`font-mono text-xs ${Number(detail.snapshot.change_pct) >= 0 ? 'text-ald-green' : 'text-ald-red'}`}>
                      {Number(detail.snapshot.change_pct) >= 0 ? '+' : ''}{Number(detail.snapshot.change_pct).toFixed(2)}%
                    </span>
                  )}
                </div>
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <span className="block font-mono text-xs uppercase text-ald-text-dim">Volume</span>
                  <span className="block font-mono text-lg text-ald-text">
                    {detail.snapshot.volume_at_snap ? fmtLargeNum(detail.snapshot.volume_at_snap) : '--'}
                  </span>
                  {detail.snapshot.volume_velocity != null && (
                    <span className={`font-mono text-xs ${Number(detail.snapshot.volume_velocity) > 1.5 ? 'text-ald-amber' : 'text-ald-text-dim'}`}>
                      {Number(detail.snapshot.volume_velocity).toFixed(2)}x avg
                    </span>
                  )}
                </div>
                {security?.security_type === 'equity' && (
                  <>
                    <div className="rounded border border-ald-border bg-ald-deep p-3">
                      <span className="block font-mono text-xs uppercase text-ald-text-dim">P/E Ratio</span>
                      <span className="block font-mono text-lg text-ald-text">
                        {detail.snapshot.pe_ratio ? Number(detail.snapshot.pe_ratio).toFixed(1) : '--'}
                      </span>
                      <span className="font-mono text-xs text-ald-text-dim">
                        fwd: {detail.snapshot.forward_pe ? Number(detail.snapshot.forward_pe).toFixed(1) : '--'}
                      </span>
                    </div>
                    <div className="rounded border border-ald-border bg-ald-deep p-3">
                      <span className="block font-mono text-xs uppercase text-ald-text-dim">Market Cap</span>
                      <span className="block font-mono text-lg text-ald-text">
                        {detail.snapshot.market_cap ? fmtLargeNum(detail.snapshot.market_cap, '$') : '--'}
                      </span>
                    </div>
                  </>
                )}
              </div>
              {detail.snapshot.day_open && (
                <div className="mt-3 font-mono text-xs text-ald-text-dim">
                  Open {fmtPrice(detail.snapshot.day_open)} · High {fmtPrice(detail.snapshot.day_high)} · Low {fmtPrice(detail.snapshot.day_low)} · Prev Close {fmtPrice(detail.snapshot.prev_close)}
                </div>
              )}
              <div className="mt-1 font-mono text-xs text-ald-text-dim/50">
                Snapshot: {detail.snapshot.snapshot_type} · {new Date(detail.snapshot.snapshot_time).toLocaleString()}
              </div>
            </div>
          )}

          {/* Active Signals Breakdown */}
          <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
            <Tooltip content={<><TipTitle>Active Signals</TipTitle><TipBody>Signals are anomalies detected by our 39 collectors across SEC filings, market data, blockchain analytics, news, and prediction markets. Each signal has a direction, strength, and age. They decay over time — older signals contribute less to the IALD score.</TipBody><TipScale items={[{color:'#22c55e',label:'▲ Bullish',description:'Signal expects price to rise'},{color:'#ef4444',label:'▼ Bearish',description:'Signal expects price to fall'},{color:'#6b7280',label:'● Neutral',description:'Anomaly detected, no directional prediction'}]} /></>}>
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">
                Active Signals {detail?.signals?.length ? `(${detail.signals.length})` : ''} &#9432;
              </h2>
            </Tooltip>
            {detail?.signals?.length > 0 ? (
              <div className="space-y-1.5">
                {detail.signals.map((s: any, i: number) => {
                  const tierColor = s.direction === 'bearish' ? 'bg-red-500/20 text-red-400' :
                                    s.direction === 'bullish' ? 'bg-green-500/20 text-green-400' :
                                    'bg-zinc-500/20 text-zinc-400';
                  const dirIcon = s.direction === 'bearish' ? '▼' : s.direction === 'bullish' ? '▲' : '●';
                  const dirLabel = s.direction === 'bearish' ? 'Bearish — this signal suggests downward price pressure' :
                                   s.direction === 'bullish' ? 'Bullish — this signal suggests upward price pressure' :
                                   'Neutral — anomalous activity detected but no directional prediction';
                  const ageH = ((Date.now() - new Date(s.detected_at).getTime()) / 3600000);
                  const ageLabel = ageH < 1 ? '<1h ago' : `${ageH.toFixed(0)}h ago`;
                  const decayNote = ageH < 6 ? 'Very fresh — near full weight' :
                                   ageH < 24 ? 'Recent — still strong' :
                                   ageH < 72 ? 'Aging — reduced weight' :
                                   'Old — significantly decayed';
                  return (
                    <div key={i} className="flex items-center gap-2 rounded border border-ald-border/50 bg-ald-deep px-3 py-2">
                      <Tooltip position="right" content={<><TipTitle>Direction</TipTitle><TipBody>{dirLabel}</TipBody></>}>
                        <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-xs font-bold ${tierColor}`}>{dirIcon}</span>
                      </Tooltip>
                      <Tooltip position="bottom" maxWidth={400} content={<><TipTitle>{s.signal_type}</TipTitle><TipBody>{s.description || 'No description available'}</TipBody></>}>
                        <span className="flex-1 truncate font-mono text-sm text-ald-text">{s.signal_type}</span>
                      </Tooltip>
                      <Tooltip position="left" content={<><TipTitle>Contribution</TipTitle><TipBody>How strong this signal is on a 0–1 scale. 1.0 = maximum strength. This value is multiplied by the signal&apos;s tier weight and time decay to compute its actual impact on the IALD score.</TipBody></>}>
                        <span className="shrink-0 font-mono text-xs text-ald-text-dim">c={Number(s.contribution).toFixed(2)}</span>
                      </Tooltip>
                      <Tooltip position="left" content={<><TipTitle>Signal Age</TipTitle><TipBody>Detected {ageLabel}. {decayNote}. Each signal type has a half-life — at one half-life old, it contributes 50% of its original weight. Governance signals (720h half-life) stay relevant for weeks. Market signals (24-48h) fade within days.</TipBody></>}>
                        <span className="shrink-0 font-mono text-xs text-ald-text-dim">{ageH.toFixed(0)}h</span>
                      </Tooltip>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center justify-center py-8">
                <div className="text-center">
                  <span className="block font-mono text-3xl font-light text-ald-text-dim">{collectors.length}</span>
                  <span className="block font-mono text-sm text-ald-text-dim mt-1">collectors monitoring</span>
                </div>
              </div>
            )}
          </div>

          {/* Analyst Consensus */}
          {detail?.consensus && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Analyst Consensus</h2>
              <div className="flex items-baseline gap-3 mb-3">
                <span className="font-mono text-3xl font-light text-ald-ivory">
                  {Number(detail.consensus.mean_rating).toFixed(2)}
                </span>
                <span className="font-mono text-lg text-ald-text-dim">/ 5.00</span>
                <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-xs text-ald-text-dim">
                  {detail.consensus.mode_label}
                </span>
                <span className="font-mono text-xs text-ald-text-dim ml-auto">
                  {detail.consensus.total_analysts} analysts
                </span>
              </div>
              {/* Distribution bar */}
              <div className="flex h-4 overflow-hidden rounded mb-2">
                <div className="bg-green-700" style={{width: `${detail.consensus.strong_buy_pct}%`}} title={`Strong Buy ${Number(detail.consensus.strong_buy_pct).toFixed(1)}%`} />
                <div className="bg-green-500" style={{width: `${detail.consensus.buy_pct}%`}} title={`Buy ${Number(detail.consensus.buy_pct).toFixed(1)}%`} />
                <div className="bg-yellow-500" style={{width: `${detail.consensus.hold_pct}%`}} title={`Hold ${Number(detail.consensus.hold_pct).toFixed(1)}%`} />
                <div className="bg-orange-500" style={{width: `${detail.consensus.sell_pct}%`}} title={`Sell ${Number(detail.consensus.sell_pct).toFixed(1)}%`} />
                <div className="bg-red-600" style={{width: `${detail.consensus.strong_sell_pct}%`}} title={`Strong Sell ${Number(detail.consensus.strong_sell_pct).toFixed(1)}%`} />
              </div>
              <div className="flex justify-between font-mono text-xs text-ald-text-dim mb-4">
                <span>Strong Buy {Number(detail.consensus.strong_buy_pct).toFixed(0)}%</span>
                <span>Buy {Number(detail.consensus.buy_pct).toFixed(0)}%</span>
                <span>Hold {Number(detail.consensus.hold_pct).toFixed(0)}%</span>
                <span>Sell {Number(detail.consensus.sell_pct).toFixed(0)}%</span>
              </div>
              {detail.consensus.mean_price_target && (
                <div className="rounded border border-ald-border bg-ald-deep p-3 font-mono text-sm">
                  <span className="text-ald-text-dim">Price Target: </span>
                  <span className="text-ald-ivory font-bold">${Number(detail.consensus.mean_price_target).toFixed(2)}</span>
                  <span className="text-ald-text-dim"> mean </span>
                  <span className="text-ald-text-dim/60">
                    (${Number(detail.consensus.low_price_target).toFixed(2)} — ${Number(detail.consensus.high_price_target).toFixed(2)})
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Recent Analyst Actions */}
          {detail?.ratings?.length > 0 && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Recent Analyst Actions</h2>
              <div className="space-y-1.5">
                {detail.ratings.map((r: any, i: number) => (
                  <div key={i} className="flex items-center justify-between py-1.5 border-b border-ald-border/30 last:border-0">
                    <div className="min-w-0">
                      <span className="font-mono text-xs text-ald-text-dim">{r.rating_date}</span>
                      <span className="ml-2 text-sm text-ald-text truncate">{r.company}</span>
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-ald-text">{r.action}</span>
                      {r.from_rating && r.to_rating && (
                        <span className="font-mono text-xs text-ald-text-dim">{r.from_rating} → {r.to_rating}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* LLM Outlook */}
          {detail?.llm_outlook && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-mono text-sm uppercase tracking-wider text-ald-ivory">AI Outlook</h2>
                <span className="font-mono text-xs text-ald-text-dim">
                  {detail.llm_outlook.model} · {detail.llm_outlook.outlook_date} · {Number(detail.llm_outlook.query_seconds).toFixed(1)}s
                </span>
              </div>
              <div className="mb-3">
                <span className={`rounded px-2 py-1 font-mono text-sm font-bold uppercase ${
                  detail.llm_outlook.direction === 'bullish' ? 'bg-green-500/15 text-green-400' :
                  detail.llm_outlook.direction === 'bearish' ? 'bg-red-500/15 text-red-400' :
                  'bg-zinc-500/15 text-zinc-400'
                }`}>
                  {detail.llm_outlook.direction === 'bullish' ? '▲ Bullish' :
                   detail.llm_outlook.direction === 'bearish' ? '▼ Bearish' : '● Neutral'}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-ald-text">{detail.llm_outlook.analysis}</p>
            </div>
          )}

          {/* Institutional Moves */}
          {detail?.institutional?.length > 0 && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Institutional Moves</h2>
              <div className="space-y-1.5">
                {detail.institutional.map((m: any, i: number) => (
                  <div key={i} className="flex items-center justify-between py-1.5 border-b border-ald-border/30 last:border-0">
                    <span className="text-sm text-ald-text truncate max-w-[200px]">{m.holder_name}</span>
                    <div className="shrink-0 flex items-center gap-3">
                      <span className={`font-mono text-sm ${Number(m.shares_changed) > 0 ? 'text-ald-green' : 'text-ald-red'}`}>
                        {Number(m.shares_changed) > 0 ? '+' : ''}{Number(m.shares_changed).toLocaleString()}
                      </span>
                      {m.change_pct != null && (
                        <span className="font-mono text-xs text-ald-text-dim">
                          {Number(m.change_pct) > 0 ? '+' : ''}{Number(m.change_pct).toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Press Releases */}
          {detail?.press?.length > 0 && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Press Releases</h2>
              <div className="space-y-2">
                {detail.press.map((p: any, i: number) => (
                  <div key={i} className="py-1.5 border-b border-ald-border/30 last:border-0">
                    <div className="text-sm text-ald-text">{p.headline}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      {p.source && <span className="font-mono text-xs text-ald-text-dim">{p.source}</span>}
                      {p.published_at && <span className="font-mono text-xs text-ald-text-dim/50">{new Date(p.published_at).toLocaleDateString()}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Debt Metrics */}
          {detail?.debt && (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
              <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Debt Metrics</h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <span className="block font-mono text-xs uppercase text-ald-text-dim">D/E Ratio</span>
                  <span className={`block font-mono text-lg ${Number(detail.debt.debt_to_equity) > 3 ? 'text-ald-red' : 'text-ald-text'}`}>
                    {Number(detail.debt.debt_to_equity).toFixed(2)}
                  </span>
                </div>
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <span className="block font-mono text-xs uppercase text-ald-text-dim">Interest/Rev</span>
                  <span className={`block font-mono text-lg ${Number(detail.debt.interest_to_revenue) > 0.3 ? 'text-ald-red' : 'text-ald-text'}`}>
                    {(Number(detail.debt.interest_to_revenue) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <span className="block font-mono text-xs uppercase text-ald-text-dim">Total Debt</span>
                  <span className="block font-mono text-lg text-ald-text">{fmtLargeNum(detail.debt.total_debt, '$')}</span>
                </div>
                <div className="rounded border border-ald-border bg-ald-deep p-3">
                  <span className="block font-mono text-xs uppercase text-ald-text-dim">Free Cash Flow</span>
                  <span className={`block font-mono text-lg ${Number(detail.debt.free_cash_flow) < 0 ? 'text-ald-red' : 'text-ald-text'}`}>
                    {fmtLargeNum(detail.debt.free_cash_flow, '$')}
                  </span>
                </div>
              </div>
              <div className="mt-2 font-mono text-xs text-ald-text-dim/50">Period: {detail.debt.period_date}</div>
            </div>
          )}

          {/* Comments */}
          <CommentsSection
            entityType="security"
            entityId={ticker}
            variant="light"
            prefsKey={`security-${ticker}`}
          />
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Data Sources (Real Collectors) */}
          <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
            <h2 className="mb-1 font-mono text-sm uppercase tracking-wider text-ald-ivory">Data Sources</h2>
            <p className="mb-4 font-mono text-xs text-ald-text-dim">{collectors.length} collectors active</p>
            <div className="space-y-2">
              {collectors.map((c) => {
                const lastHeard = c.last_success_at || c.last_run_at;
                const hoursAgo = lastHeard
                  ? (Date.now() - new Date(lastHeard).getTime()) / 3_600_000
                  : Infinity;

                // Green: <30h (Maintenance), Amber: 30h-5d, Grey: >5d (Redundant Data)
                let dotColor: string;
                let statusLabel: string;
                if (hoursAgo <= 30) {
                  dotColor = 'bg-ald-green';
                  statusLabel = formatFreshness(lastHeard!);
                } else if (hoursAgo <= 120) {
                  dotColor = 'bg-ald-amber';
                  statusLabel = formatFreshness(lastHeard!);
                } else {
                  dotColor = 'bg-zinc-400';
                  statusLabel = lastHeard ? 'Redundant Data' : 'never';
                }

                const freshness = lastHeard ? formatFreshness(lastHeard) : 'never';
                return (
                  <div key={c.collector_id} className="flex items-center justify-between py-1.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2.5">
                        <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${dotColor}`} />
                        <span className="text-sm text-ald-text truncate">{c.collector_name}</span>
                      </div>
                      <span className={`ml-5 font-mono text-xs ${TYPE_COLORS[c.collector_type] ?? 'text-ald-text-dim'}`}>
                        {c.collector_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {c.records_count != null && c.records_count > 0 && (
                        <span className="font-mono text-xs text-ald-text-dim">
                          {c.records_count} rec
                        </span>
                      )}
                      <span className={`font-mono text-xs ${
                        hoursAgo <= 30 ? 'text-ald-green/70' :
                        hoursAgo <= 120 ? 'text-ald-amber/70' :
                        'text-zinc-400'
                      }`}>{statusLabel}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recent Scores */}
          <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
            <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-ivory">Recent Scores</h2>
            {history.length > 0 ? (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ald-border">
                    <th className="pb-2 text-left font-mono text-sm uppercase tracking-wider text-ald-text-dim">Date</th>
                    <th className="pb-2 text-right font-mono text-sm uppercase tracking-wider text-ald-text-dim">IALD</th>
                    <th className="pb-2 text-right font-mono text-sm uppercase tracking-wider text-ald-text-dim">Signals</th>
                  </tr>
                </thead>
                <tbody>
                  {history.slice(0, 10).map((h) => (
                    <tr key={h.score_date} className="border-b border-ald-border/50">
                      <td className="py-1.5 font-mono text-sm text-ald-text-dim">{h.score_date}</td>
                      <td className={`py-1.5 text-right font-mono text-sm ${scoreColor(Number(h.score))}`}>
                        {Number(h.score).toFixed(2)}
                      </td>
                      <td className="py-1.5 text-right font-mono text-sm text-ald-text-dim">{h.active_signals}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="flex items-center justify-center py-4 text-sm text-ald-text-dim">
                No score history available yet.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ─── Virtual Buy Modal ───────────────────────────────────────── */}
      {showBuyModal && detail?.snapshot?.price && (() => {
        const price = Number(detail.snapshot.price);
        const STORAGE_KEY = 'alidade_portfolio_sim';

        function getPortfolio() {
          try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) return JSON.parse(raw);
          } catch {}
          return { cash: 10000, positions: [], transactions: [], started_at: new Date().toISOString() };
        }

        const portfolio = getPortfolio();
        const maxShares = Math.floor(portfolio.cash / price);
        const total = buyShares * price;

        function executeBuy() {
          const p = getPortfolio();
          if (total > p.cash || buyShares < 1) return;

          const existing = p.positions.find((pos: { ticker: string }) => pos.ticker === ticker);
          if (existing) {
            const newShares = existing.shares + buyShares;
            const newCost = existing.total_cost + total;
            p.positions = p.positions.map((pos: { ticker: string; shares: number; total_cost: number }) =>
              pos.ticker === ticker
                ? { ...pos, shares: newShares, avg_cost: newCost / newShares, total_cost: newCost }
                : pos
            );
          } else {
            p.positions.push({
              ticker,
              name: security?.name ?? ticker,
              security_type: security?.security_type ?? 'equity',
              shares: buyShares,
              avg_cost: price,
              total_cost: total,
              bought_at: new Date().toISOString(),
            });
          }

          p.cash -= total;
          p.transactions.unshift({
            id: crypto.randomUUID(),
            type: 'buy',
            ticker,
            shares: buyShares,
            price,
            total,
            date: new Date().toISOString(),
          });

          localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
          setShowBuyModal(false);
          setBuyConfirm(`Bought ${buyShares} ${ticker} @ $${price.toFixed(2)}`);
          setTimeout(() => setBuyConfirm(null), 2000);
        }

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="w-full max-w-md rounded-lg border border-ald-border bg-ald-void p-6 shadow-2xl">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-mono text-lg text-ald-ivory">Buy {ticker} (Virtual)</h2>
                <button onClick={() => setShowBuyModal(false)} className="font-mono text-sm text-ald-text-dim hover:text-ald-text">&times;</button>
              </div>

              <div className="mb-4 space-y-3">
                <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                  <span className="font-mono text-xs uppercase text-ald-text-dim">Market Price</span>
                  <span className="font-mono text-lg text-ald-ivory">${price.toFixed(2)}</span>
                </div>

                <div>
                  <label className="block font-mono text-xs uppercase tracking-wider text-ald-text-dim mb-1">Shares</label>
                  <input
                    type="number"
                    min={1}
                    max={maxShares}
                    value={buyShares}
                    onChange={(e) => setBuyShares(Math.max(1, parseInt(e.target.value) || 1))}
                    className="w-full rounded border border-ald-border bg-ald-surface px-4 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none"
                  />
                </div>

                <div className="flex items-center justify-between rounded bg-ald-surface p-3">
                  <span className="font-mono text-xs uppercase text-ald-text-dim">Total Cost</span>
                  <span className={`font-mono text-lg ${total > portfolio.cash ? 'text-ald-red' : 'text-ald-ivory'}`}>
                    ${total.toFixed(2)}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs text-ald-text-dim">
                  <span>Available: ${portfolio.cash.toFixed(2)}</span>
                  <button
                    onClick={() => setBuyShares(maxShares)}
                    className="font-mono text-ald-blue hover:text-ald-ivory transition-colors"
                  >
                    Max
                  </button>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowBuyModal(false)}
                  className="flex-1 rounded border border-ald-border py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={executeBuy}
                  disabled={total > portfolio.cash || buyShares < 1}
                  className="flex-1 rounded bg-ald-green/20 border border-ald-green/40 py-2 font-mono text-sm uppercase tracking-wider text-ald-green hover:bg-ald-green/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Execute Buy
                </button>
              </div>
            </div>
          </div>
        );
      })()}

    </div>
  );
}

function fmtLargeNum(n: number | string | null, prefix = ''): string {
  if (n == null) return '--';
  const v = Number(n);
  if (Math.abs(v) >= 1e12) return `${prefix}${(v/1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `${prefix}${(v/1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `${prefix}${(v/1e6).toFixed(2)}M`;
  if (Math.abs(v) >= 1e3) return `${prefix}${(v/1e3).toFixed(1)}K`;
  return `${prefix}${v.toFixed(2)}`;
}

function fmtPrice(n: number | string | null): string {
  if (n == null) return '--';
  return `$${Number(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

function formatFreshness(isoDate: string): string {
  const ms = Date.now() - new Date(isoDate).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const d = Math.floor(hr / 24);
  return `${d}d ago`;
}
