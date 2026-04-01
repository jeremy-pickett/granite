'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';

/* eslint-disable @typescript-eslint/no-explicit-any */

function Stat({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded border border-ald-border bg-ald-deep p-3">
      <span className="block font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">{label}</span>
      <span className={`block font-mono text-lg ${color ?? 'text-ald-ivory'}`}>{value}</span>
      {sub && <span className="block font-mono text-[10px] text-ald-text-dim">{sub}</span>}
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`} />;
}

function ago(hours: number | null): string {
  if (hours == null) return 'never';
  if (hours < 1) return `${Math.round(hours * 60)}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function AdminPage() {
  const { dbUser, isAuthenticated, isLoading } = useAuth();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchStatus = useCallback(async () => {
    setRefreshing(true);
    try {
      const resp = await fetch('/api/admin/status');
      if (resp.ok) {
        setData(await resp.json());
        setError(null);
      } else {
        setError(`API returned ${resp.status}`);
      }
    } catch (e) {
      setError(String(e));
    }
    setRefreshing(false);
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(fetchStatus, 30000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchStatus]);

  if (isLoading) return <div className="p-8 text-ald-text-dim">Loading...</div>;
  if (!isAuthenticated || dbUser?.role !== 'admin') {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <span className="block text-4xl mb-2">🔒</span>
          <span className="block font-mono text-sm text-ald-text-dim">Admin access required</span>
          <Link href="/alidade/dashboard" className="mt-4 block font-mono text-xs text-ald-blue hover:underline">← Dashboard</Link>
        </div>
      </div>
    );
  }

  const s = data;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-light tracking-tight text-ald-ivory">System Status</h1>
          <span className="font-mono text-xs text-ald-text-dim">
            {s ? `Updated ${new Date(s.timestamp).toLocaleTimeString()}` : 'Loading...'}
            {refreshing && ' · refreshing...'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 font-mono text-xs text-ald-text-dim cursor-pointer">
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} className="rounded" />
            Auto-refresh 30s
          </label>
          <button onClick={fetchStatus} disabled={refreshing}
            className="rounded border border-ald-border px-3 py-1 font-mono text-xs text-ald-text-dim hover:text-ald-text disabled:opacity-50">
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="mb-4 rounded border border-red-500/30 bg-red-500/10 p-3 font-mono text-sm text-red-400">{error}</div>}

      {s && (
        <>
          {/* ── System Overview ── */}
          <section className="mb-6">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">System</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="Uptime" value={s.system.uptime || '--'} />
              <Stat label="Load Avg" value={s.system.load_avg || '--'} sub={`${s.system.cpu_cores} cores`} />
              <Stat label="Memory" value={s.system.memory || '--'} />
              <Stat label="Disk" value={s.system.disk || '--'} />
              <Stat label="Node.js" value={s.system.node_version || '--'} />
              <Stat label="Python" value={s.system.python_version || '--'} />
            </div>
          </section>

          {/* ── Next.js ── */}
          <section className="mb-6">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">Next.js Server</h2>
            <div className="rounded border border-ald-border bg-ald-deep p-4 font-mono text-sm text-ald-text">
              {s.next_js.process || 'Not detected'}
            </div>
          </section>

          {/* ── Database ── */}
          <section className="mb-6">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">Database</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="DB Size" value={s.database.db_size || '--'} />
              <Stat label="Securities" value={String(s.database.total_securities ?? '--')} sub={`${s.database.equities} eq · ${s.database.crypto} crypto`} />
              <Stat label="Tables" value={String(s.database.table_sizes?.length ?? '--')} />
              <Stat label="Rate Limits" value={s.rate_limits?.finnhub_remaining ? `${s.rate_limits.finnhub_remaining} finnhub` : '--'} />
            </div>
            {s.database.table_sizes?.length > 0 && (
              <details className="mt-3">
                <summary className="cursor-pointer font-mono text-xs text-ald-text-dim hover:text-ald-text">Table sizes ({s.database.table_sizes.length} tables)</summary>
                <div className="mt-2 max-h-48 overflow-y-auto rounded border border-ald-border bg-ald-deep p-3">
                  {s.database.table_sizes.map((t: any) => (
                    <div key={t.table_name} className="flex justify-between py-0.5 font-mono text-xs">
                      <span className="text-ald-text">{t.table_name}</span>
                      <span className="text-ald-text-dim">{Number(t.row_count).toLocaleString()} rows · {t.size}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </section>

          {/* ── IALD Scoring ── */}
          <section className="mb-6">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">IALD Scoring</h2>
            {s.scoring ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Stat label="Last Scored" value={s.scoring.last_scored || 'never'} />
                <Stat label="Securities Scored" value={String(s.scoring.securities_scored ?? 0)} />
                <Stat label="Avg Score" value={s.scoring.avg_score != null ? Number(s.scoring.avg_score).toFixed(3) : '--'} />
                <Stat label="Very High / High" value={`${s.scoring.very_high ?? 0} / ${s.scoring.high ?? 0}`} color="text-ald-amber" />
                <Stat label="Medium / Low" value={`${s.scoring.medium ?? 0} / ${s.scoring.low ?? 0}`} />
              </div>
            ) : (
              <div className="text-sm text-ald-text-dim">No scores recorded today</div>
            )}
          </section>

          {/* ── Signals ── */}
          <section className="mb-6">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">Signals (7-day)</h2>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <Stat label="Total Signals" value={String(s.signals.total_7d ?? 0)} />
              <Stat label="Securities w/ Signals" value={String(s.signals.securities_with_signals ?? 0)} />
              <Stat label="Signal Types Active" value={String(s.signals.signal_types_active ?? 0)} />
            </div>
            {s.signals.by_type?.length > 0 && (
              <div className="max-h-64 overflow-y-auto rounded border border-ald-border bg-ald-deep p-3">
                {s.signals.by_type.map((sig: any) => (
                  <div key={sig.signal_type} className="flex items-center justify-between py-1 border-b border-ald-border/20 last:border-0">
                    <span className="font-mono text-xs text-ald-text">{sig.signal_type}</span>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs text-ald-text-dim">{sig.total} signals</span>
                      <span className="font-mono text-[10px] text-ald-text-dim">{ago(Number(sig.hours_since_latest))}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Collectors ── */}
          <section className="mb-6">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">
              Collectors ({s.collectors.registered} registered, {s.collectors.running_python} running now)
            </h2>
            <div className="max-h-96 overflow-y-auto rounded border border-ald-border bg-ald-deep">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ald-border text-left">
                    <th className="px-3 py-2 font-mono text-[10px] uppercase text-ald-text-dim">Status</th>
                    <th className="px-3 py-2 font-mono text-[10px] uppercase text-ald-text-dim">Collector</th>
                    <th className="px-3 py-2 font-mono text-[10px] uppercase text-ald-text-dim">Type</th>
                    <th className="px-3 py-2 font-mono text-[10px] uppercase text-ald-text-dim text-right">Records</th>
                    <th className="px-3 py-2 font-mono text-[10px] uppercase text-ald-text-dim text-right">Coverage</th>
                    <th className="px-3 py-2 font-mono text-[10px] uppercase text-ald-text-dim text-right">Last Success</th>
                  </tr>
                </thead>
                <tbody>
                  {s.collectors.items.map((c: any) => {
                    const hoursAgo = Number(c.hours_since_success);
                    const healthy = hoursAgo < 30;
                    const stale = hoursAgo >= 30 && hoursAgo < 120;
                    return (
                      <tr key={c.collector_id} className="border-b border-ald-border/20 hover:bg-ald-surface">
                        <td className="px-3 py-1.5"><StatusDot ok={healthy} /></td>
                        <td className="px-3 py-1.5 font-mono text-xs text-ald-text">{c.collector_name}</td>
                        <td className="px-3 py-1.5 font-mono text-[10px] text-ald-text-dim">{c.collector_type}</td>
                        <td className="px-3 py-1.5 font-mono text-xs text-ald-text-dim text-right">{c.records_total?.toLocaleString() ?? '--'}</td>
                        <td className="px-3 py-1.5 font-mono text-xs text-ald-text-dim text-right">
                          {c.securities_covered ?? 0}/{c.total_securities ?? 0}
                        </td>
                        <td className={`px-3 py-1.5 font-mono text-xs text-right ${healthy ? 'text-emerald-400' : stale ? 'text-ald-amber' : 'text-red-400'}`}>
                          {ago(hoursAgo)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* ── Recent Errors ── */}
          {s.errors?.length > 0 && (
            <section className="mb-6">
              <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-red-400">Errors (24h)</h2>
              <div className="space-y-2">
                {s.errors.map((e: any, i: number) => (
                  <div key={i} className="rounded border border-red-500/20 bg-red-500/5 p-3">
                    <div className="flex justify-between">
                      <span className="font-mono text-xs font-bold text-red-400">{e.collector_name}</span>
                      <span className="font-mono text-[10px] text-ald-text-dim">{e.last_error_at}</span>
                    </div>
                    <p className="mt-1 font-mono text-xs text-red-300/70 break-all">{e.last_error?.substring(0, 200)}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Cron & Logs ── */}
          <section className="mb-6">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">Cron ({s.cron.total_jobs} jobs)</h2>
                <pre className="max-h-32 overflow-y-auto rounded border border-ald-border bg-ald-deep p-3 font-mono text-[10px] text-ald-text-dim whitespace-pre-wrap">{s.cron.sample || 'No cron jobs'}</pre>
              </div>
              <div>
                <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-ald-text-dim">Log Files</h2>
                <pre className="max-h-32 overflow-y-auto rounded border border-ald-border bg-ald-deep p-3 font-mono text-[10px] text-ald-text-dim whitespace-pre-wrap">{s.logs || 'No logs'}</pre>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
