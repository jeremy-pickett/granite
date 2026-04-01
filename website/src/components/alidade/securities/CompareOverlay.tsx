'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import IALDScoreGauge from './IALDScoreGauge';
import Sparkline from './Sparkline';

interface SparklinePoint { d: string; s: number; }

export interface CompareSecurity {
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

interface CompareOverlayProps {
  left: CompareSecurity;
  right: CompareSecurity;
  onClose: () => void;
}

/* eslint-disable @typescript-eslint/no-explicit-any */

function scoreColor(score: number | null): string {
  if (score === null) return 'text-ald-text-dim';
  if (score >= 0.75) return 'text-ald-red';
  if (score >= 0.50) return 'text-ald-amber';
  if (score >= 0.25) return 'text-ald-blue';
  return 'text-ald-text-dim';
}

function fmtNum(n: any, prefix = '', decimals = 2): string {
  if (n == null) return '--';
  const v = Number(n);
  if (Math.abs(v) >= 1e12) return `${prefix}${(v/1e12).toFixed(decimals)}T`;
  if (Math.abs(v) >= 1e9) return `${prefix}${(v/1e9).toFixed(decimals)}B`;
  if (Math.abs(v) >= 1e6) return `${prefix}${(v/1e6).toFixed(decimals)}M`;
  return `${prefix}${v.toLocaleString(undefined, {minimumFractionDigits: decimals, maximumFractionDigits: decimals})}`;
}

function WinnerDot({ leftWins }: { leftWins: boolean | null }) {
  if (leftWins === null) return <span className="w-3" />;
  return <span className={`inline-block h-2 w-2 rounded-full ${leftWins ? 'bg-ald-blue' : 'bg-ald-amber'}`} />;
}

function StatRow({ label, leftVal, rightVal, leftColor, rightColor, leftWins }: {
  label: string;
  leftVal: string;
  rightVal: string;
  leftColor?: string;
  rightColor?: string;
  leftWins?: boolean | null;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 py-1.5 border-b border-ald-border/20">
      <div className="flex items-center justify-end gap-2">
        {leftWins === true && <WinnerDot leftWins={true} />}
        <span className={`font-mono text-sm ${leftColor ?? 'text-ald-text'}`}>{leftVal}</span>
      </div>
      <span className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim w-28 text-center">{label}</span>
      <div className="flex items-center gap-2">
        <span className={`font-mono text-sm ${rightColor ?? 'text-ald-text'}`}>{rightVal}</span>
        {leftWins === false && <WinnerDot leftWins={false} />}
      </div>
    </div>
  );
}

export default function CompareOverlay({ left, right, onClose }: CompareOverlayProps) {
  const { isAuthenticated, getIdToken } = useAuth();
  const [detail, setDetail] = useState<any>(null);
  const [opinion, setOpinion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [askingHaiku, setAskingHaiku] = useState(false);
  const [noteSaved, setNoteSaved] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [savingNote, setSavingNote] = useState(false);

  // Fetch enriched comparison data
  useEffect(() => {
    fetch(`/api/compare?left=${left.ticker}&right=${right.ticker}`)
      .then(r => r.json())
      .then(d => { setDetail(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [left.ticker, right.ticker]);

  const askHaiku = async () => {
    setAskingHaiku(true);
    try {
      const resp = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ left: left.ticker, right: right.ticker }),
      });
      const data = await resp.json();
      if (data.haiku_opinion) {
        setOpinion(data.haiku_opinion);
      } else {
        setOpinion('The bartender is thinking... try again in a moment.');
      }
    } catch {
      setOpinion('Could not reach the bartender. Try again.');
    }
    setAskingHaiku(false);
  };

  const L = detail?.left;
  const R = detail?.right;
  const Ls = L?.snapshot;
  const Rs = R?.snapshot;
  const Lc = L?.consensus;
  const Rc = R?.consensus;
  const Ld = L?.debt;
  const Rd = R?.debt;
  const La = L?.aggregates;
  const Ra = R?.aggregates;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ald-void/80 backdrop-blur-sm overflow-y-auto py-6" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-lg border border-ald-border bg-ald-surface p-5 shadow-2xl mx-4 my-auto" onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-mono text-sm uppercase tracking-wider text-ald-ivory">Head to Head</h2>
          <button onClick={onClose} className="font-mono text-sm text-ald-text-dim hover:text-ald-text transition-colors">ESC</button>
        </div>

        {/* Tickers + Gauges */}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 mb-6">
          <div className="text-right">
            <span className="block font-mono text-xl text-ald-ivory">{left.ticker}</span>
            <span className="block text-xs text-ald-text-dim truncate">{left.name}</span>
            <div className="flex justify-end mt-2"><IALDScoreGauge score={left.iald !== null ? Number(left.iald) : null} verdict={left.verdict} size="md" /></div>
          </div>
          <span className="font-mono text-lg text-ald-text-dim">vs</span>
          <div>
            <span className="block font-mono text-xl text-ald-ivory">{right.ticker}</span>
            <span className="block text-xs text-ald-text-dim truncate">{right.name}</span>
            <div className="mt-2"><IALDScoreGauge score={right.iald !== null ? Number(right.iald) : null} verdict={right.verdict} size="md" /></div>
          </div>
        </div>

        {/* Sparklines */}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 mb-4">
          <div className="flex justify-end"><Sparkline points={left.sparkline ?? []} width={140} height={32} /></div>
          <span className="font-mono text-[10px] uppercase text-ald-text-dim w-28 text-center">14d IALD</span>
          <div><Sparkline points={right.sparkline ?? []} width={140} height={32} /></div>
        </div>

        {loading ? (
          <div className="py-8 text-center font-mono text-sm text-ald-text-dim">Loading comparison data...</div>
        ) : (
          <>
            {/* ── Price & Fundamentals ── */}
            {(Ls || Rs) && (
              <div className="mb-2">
                <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim mb-1 text-center">Price & Fundamentals</div>
                {Ls?.price || Rs?.price ? (
                  <StatRow label="Price" leftVal={fmtNum(Ls?.price, '$')} rightVal={fmtNum(Rs?.price, '$')} />
                ) : null}
                {(Ls?.change_pct != null || Rs?.change_pct != null) && (
                  <StatRow label="Day Change"
                    leftVal={Ls?.change_pct != null ? `${Number(Ls.change_pct) >= 0 ? '+' : ''}${Number(Ls.change_pct).toFixed(2)}%` : '--'}
                    rightVal={Rs?.change_pct != null ? `${Number(Rs.change_pct) >= 0 ? '+' : ''}${Number(Rs.change_pct).toFixed(2)}%` : '--'}
                    leftColor={Ls?.change_pct != null ? (Number(Ls.change_pct) >= 0 ? 'text-ald-green' : 'text-ald-red') : undefined}
                    rightColor={Rs?.change_pct != null ? (Number(Rs.change_pct) >= 0 ? 'text-ald-green' : 'text-ald-red') : undefined}
                  />
                )}
                {(Ls?.pe_ratio || Rs?.pe_ratio) && (
                  <StatRow label="P/E (trailing)" leftVal={Ls?.pe_ratio ? Number(Ls.pe_ratio).toFixed(1) : '--'} rightVal={Rs?.pe_ratio ? Number(Rs.pe_ratio).toFixed(1) : '--'} />
                )}
                {(Ls?.market_cap || Rs?.market_cap) && (
                  <StatRow label="Market Cap" leftVal={fmtNum(Ls?.market_cap, '$')} rightVal={fmtNum(Rs?.market_cap, '$')} />
                )}
                {(Ls?.volume_velocity || Rs?.volume_velocity) && (
                  <StatRow label="Vol Velocity"
                    leftVal={Ls?.volume_velocity ? `${Number(Ls.volume_velocity).toFixed(2)}x` : '--'}
                    rightVal={Rs?.volume_velocity ? `${Number(Rs.volume_velocity).toFixed(2)}x` : '--'}
                    leftColor={Number(Ls?.volume_velocity) > 1.5 ? 'text-ald-amber' : undefined}
                    rightColor={Number(Rs?.volume_velocity) > 1.5 ? 'text-ald-amber' : undefined}
                  />
                )}
              </div>
            )}

            {/* ── Signal Strength ── */}
            <div className="mb-2">
              <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim mb-1 text-center">Signal Strength</div>
              <StatRow label="IALD Score"
                leftVal={left.iald != null ? Number(left.iald).toFixed(4) : '--'}
                rightVal={right.iald != null ? Number(right.iald).toFixed(4) : '--'}
                leftColor={scoreColor(left.iald != null ? Number(left.iald) : null)}
                rightColor={scoreColor(right.iald != null ? Number(right.iald) : null)}
                leftWins={left.iald != null && right.iald != null ? Number(left.iald) < Number(right.iald) : null}
              />
              <StatRow label="Active Signals"
                leftVal={String(left.active_signals ?? 0)}
                rightVal={String(right.active_signals ?? 0)}
              />
              {L?.signal_summary && R?.signal_summary && (
                <>
                  <StatRow label="Bullish Signals"
                    leftVal={String(L.signal_summary.bullish)}
                    rightVal={String(R.signal_summary.bullish)}
                    leftColor="text-ald-green" rightColor="text-ald-green"
                    leftWins={L.signal_summary.bullish > R.signal_summary.bullish}
                  />
                  <StatRow label="Bearish Signals"
                    leftVal={String(L.signal_summary.bearish)}
                    rightVal={String(R.signal_summary.bearish)}
                    leftColor="text-ald-red" rightColor="text-ald-red"
                    leftWins={L.signal_summary.bearish < R.signal_summary.bearish}
                  />
                </>
              )}
              <StatRow label="30d Avg"
                leftVal={La?.avg_score_30d != null ? Number(La.avg_score_30d).toFixed(2) : '--'}
                rightVal={Ra?.avg_score_30d != null ? Number(Ra.avg_score_30d).toFixed(2) : '--'}
                leftColor={scoreColor(La?.avg_score_30d ?? null)}
                rightColor={scoreColor(Ra?.avg_score_30d ?? null)}
              />
              <StatRow label="Volatility"
                leftVal={La?.volatility_30d != null ? Number(La.volatility_30d).toFixed(3) : '--'}
                rightVal={Ra?.volatility_30d != null ? Number(Ra.volatility_30d).toFixed(3) : '--'}
              />
              <StatRow label="Trend"
                leftVal={La?.score_trend ?? left.score_trend ?? 'stable'}
                rightVal={Ra?.score_trend ?? right.score_trend ?? 'stable'}
                leftColor={La?.score_trend === 'improving' ? 'text-ald-red' : La?.score_trend === 'declining' ? 'text-ald-green' : 'text-ald-text-dim'}
                rightColor={Ra?.score_trend === 'improving' ? 'text-ald-red' : Ra?.score_trend === 'declining' ? 'text-ald-green' : 'text-ald-text-dim'}
              />
            </div>

            {/* ── Analyst Coverage ── */}
            {(Lc || Rc) && (
              <div className="mb-2">
                <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim mb-1 text-center">Analyst Coverage</div>
                <StatRow label="Consensus"
                  leftVal={Lc ? `${Number(Lc.mean_rating).toFixed(1)} (${Lc.mode_label})` : '--'}
                  rightVal={Rc ? `${Number(Rc.mean_rating).toFixed(1)} (${Rc.mode_label})` : '--'}
                  leftWins={Lc && Rc ? Number(Lc.mean_rating) > Number(Rc.mean_rating) : null}
                />
                <StatRow label="Analysts"
                  leftVal={Lc ? String(Lc.total_analysts) : '--'}
                  rightVal={Rc ? String(Rc.total_analysts) : '--'}
                />
                {(Lc?.mean_price_target || Rc?.mean_price_target) && (
                  <StatRow label="Price Target"
                    leftVal={Lc?.mean_price_target ? fmtNum(Lc.mean_price_target, '$') : '--'}
                    rightVal={Rc?.mean_price_target ? fmtNum(Rc.mean_price_target, '$') : '--'}
                  />
                )}
              </div>
            )}

            {/* ── Financial Health ── */}
            {(Ld || Rd) && (
              <div className="mb-2">
                <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim mb-1 text-center">Financial Health</div>
                <StatRow label="Debt/Equity"
                  leftVal={Ld?.debt_to_equity != null ? Number(Ld.debt_to_equity).toFixed(2) : '--'}
                  rightVal={Rd?.debt_to_equity != null ? Number(Rd.debt_to_equity).toFixed(2) : '--'}
                  leftColor={Number(Ld?.debt_to_equity) > 3 ? 'text-ald-red' : undefined}
                  rightColor={Number(Rd?.debt_to_equity) > 3 ? 'text-ald-red' : undefined}
                  leftWins={Ld && Rd ? Number(Ld.debt_to_equity) < Number(Rd.debt_to_equity) : null}
                />
                {(Ld?.free_cash_flow || Rd?.free_cash_flow) && (
                  <StatRow label="Free Cash Flow"
                    leftVal={fmtNum(Ld?.free_cash_flow, '$')}
                    rightVal={fmtNum(Rd?.free_cash_flow, '$')}
                    leftColor={Number(Ld?.free_cash_flow) < 0 ? 'text-ald-red' : 'text-ald-green'}
                    rightColor={Number(Rd?.free_cash_flow) < 0 ? 'text-ald-red' : 'text-ald-green'}
                  />
                )}
              </div>
            )}

            {/* ── AI Existing Outlooks ── */}
            {(L?.llm_outlook || R?.llm_outlook) && (
              <div className="mb-4">
                <div className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim mb-1 text-center">AI Individual Outlooks</div>
                <div className="grid grid-cols-2 gap-3">
                  {[L?.llm_outlook, R?.llm_outlook].map((llm, i) => (
                    <div key={i} className="rounded border border-ald-border/30 bg-ald-deep p-2">
                      {llm ? (
                        <>
                          <span className={`font-mono text-xs font-bold ${
                            llm.direction === 'bullish' ? 'text-ald-green' :
                            llm.direction === 'bearish' ? 'text-ald-red' : 'text-ald-text-dim'
                          }`}>
                            {llm.direction === 'bullish' ? '▲' : llm.direction === 'bearish' ? '▼' : '●'} {llm.direction}
                          </span>
                          <p className="mt-1 text-[11px] leading-snug text-ald-text-muted line-clamp-4">{llm.analysis}</p>
                        </>
                      ) : <span className="text-xs text-ald-text-dim">No AI outlook</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── The Bartender's Opinion ── */}
            <div className="rounded-lg border border-ald-blue/20 bg-ald-deep p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs uppercase tracking-wider text-ald-blue">If I had $1,000...</span>
                {!opinion && (
                  <button
                    onClick={askHaiku}
                    disabled={askingHaiku}
                    className="rounded border border-ald-blue/30 px-3 py-1 font-mono text-xs text-ald-blue hover:bg-ald-blue/10 transition-colors disabled:opacity-50"
                  >
                    {askingHaiku ? 'Thinking...' : 'Ask the bartender'}
                  </button>
                )}
              </div>
              {opinion ? (
                <p className="text-sm leading-relaxed text-ald-text">{opinion}</p>
              ) : !askingHaiku ? (
                <p className="text-xs text-ald-text-dim">
                  Click to ask Claude for a direct comparison: which security has the edge,
                  in absolute and percentage terms, based on all available data points.
                </p>
              ) : (
                <div className="flex items-center gap-2 py-2">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-ald-blue" />
                  <span className="text-xs text-ald-text-dim">Analyzing both securities...</span>
                </div>
              )}
            </div>
          </>
        )}

        {/* Save to Notes */}
        <div className="mt-4 flex items-center justify-between">
          <p className="font-mono text-[10px] text-ald-text-dim">
            Drag any two cards together to compare
          </p>
          <div className="flex items-center gap-2">
            {noteError && <span className="font-mono text-[10px] text-ald-red">{noteError}</span>}
            <button
              onClick={async () => {
                if (!isAuthenticated) {
                  setNoteError('Sign in to save notes');
                  return;
                }
                setSavingNote(true);
                setNoteError(null);
                try {
                  const token = await getIdToken();
                  if (!token) { setSavingNote(false); setNoteError('Sign in required'); return; }

                  const noteBody = [
                    `${left.ticker} vs ${right.ticker}`,
                    `IALD: ${left.iald != null ? Number(left.iald).toFixed(2) : '--'} vs ${right.iald != null ? Number(right.iald).toFixed(2) : '--'}`,
                    opinion ? `Bartender: ${opinion}` : '',
                  ].filter(Boolean).join('\n');

                  const res = await fetch('/api/notes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                    body: JSON.stringify({
                      title: `Compare: ${left.ticker} vs ${right.ticker}`,
                      body: noteBody,
                      source: 'compare',
                      tickers: [left.ticker, right.ticker],
                    }),
                  });
                  if (res.ok) {
                    setNoteSaved(true);
                  } else if (res.status === 409) {
                    setNoteError('Already saved');
                  } else {
                    const data = await res.json();
                    setNoteError(data.error || 'Failed to save');
                  }
                } catch {
                  setNoteError('Network error');
                }
                setSavingNote(false);
              }}
              disabled={savingNote || noteSaved}
              className="rounded border border-ald-blue/30 px-3 py-1 font-mono text-xs text-ald-blue hover:bg-ald-blue/10 transition-colors disabled:opacity-50"
            >
              {noteSaved ? 'Saved' : savingNote ? '...' : 'Save to Notes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
