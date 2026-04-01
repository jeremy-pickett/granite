'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import WatchlistButton from '@/components/alidade/WatchlistButton';

interface Alert {
  alert_id: number;
  ticker: string;
  name: string;
  alert_type: string;
  condition_value: number | null;
  status: string;
  triggered_count: number;
  created_at: string;
  last_triggered: string | null;
}

const typeLabels: Record<string, string> = {
  score_threshold: 'Score Threshold',
  score_change: 'Score Change',
  verdict_change: 'Verdict Change',
  price_change: 'Price Change',
};

function conditionText(alert: Alert): string {
  switch (alert.alert_type) {
    case 'score_threshold':
      return alert.condition_value !== null ? `IALD > ${Number(alert.condition_value).toFixed(2)}` : 'IALD threshold';
    case 'score_change':
      return alert.condition_value !== null ? `IALD Δ > ${Number(alert.condition_value).toFixed(2)} in 7d` : 'IALD change';
    case 'verdict_change':
      return 'Verdict changes';
    case 'price_change':
      return alert.condition_value !== null ? `Price ±${Number(alert.condition_value).toFixed(0)}% in 24h` : 'Price change';
    default:
      return alert.alert_type;
  }
}

function LogoImg({ ticker }: { ticker: string }) {
  const [err, setErr] = useState(false);
  if (err) {
    return (
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-ald-surface-2 font-mono text-xs text-ald-text-dim">
        {ticker.slice(0, 2)}
      </div>
    );
  }
  return (
    <Image
      src={`/logos/${ticker}.png`}
      alt={ticker}
      width={24}
      height={24}
      className="h-6 w-6 shrink-0 rounded"
      onError={() => setErr(true)}
    />
  );
}

export default function AlertsPage() {
  const { isAuthenticated, isLoading: authLoading, getIdToken } = useAuth();
  const router = useRouter();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newTicker, setNewTicker] = useState('');
  const [newType, setNewType] = useState('score_threshold');
  const [newValue, setNewValue] = useState('0.80');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAlerts = useCallback(async () => {
    const token = await getIdToken();
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch('/api/alerts', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts);
      }
    } catch {}
    setLoading(false);
  }, [getIdToken]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/alidade/login');
    } else if (isAuthenticated) {
      fetchAlerts();
    }
  }, [isAuthenticated, authLoading, router, fetchAlerts]);

  const handleToggle = async (alertId: number, currentStatus: string) => {
    const token = await getIdToken();
    if (!token) return;
    const newStatus = currentStatus === 'active' ? 'paused' : 'active';
    const res = await fetch('/api/alerts', {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_id: alertId, status: newStatus }),
    });
    if (res.ok) {
      setAlerts(alerts.map(a => a.alert_id === alertId ? { ...a, status: newStatus } : a));
    }
  };

  const handleDelete = async (alertId: number) => {
    const token = await getIdToken();
    if (!token) return;
    const res = await fetch('/api/alerts', {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_id: alertId }),
    });
    if (res.ok) {
      setAlerts(alerts.filter(a => a.alert_id !== alertId));
    }
  };

  const handleCreate = async () => {
    const token = await getIdToken();
    if (!token || !newTicker.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch('/api/alerts', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: newTicker.toUpperCase(),
          alert_type: newType,
          condition_value: newType !== 'verdict_change' ? parseFloat(newValue) : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || 'Failed to create alert');
      } else {
        setShowCreate(false);
        setNewTicker('');
        setNewValue('0.80');
        setError(null);
        await fetchAlerts();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create alert');
    }
    setCreating(false);
  };

  if (authLoading || (!isAuthenticated && !authLoading)) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  const activeCount = alerts.filter(a => a.status === 'active').length;

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-light tracking-tight text-ald-ivory">Alerts</h1>
          <p className="text-sm text-ald-text-muted">
            {loading ? 'Loading...' : `${activeCount} active`}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="rounded border border-ald-blue bg-ald-blue/10 px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue hover:text-ald-void transition-colors"
        >
          + New Alert
        </button>
      </div>

      {/* Create Alert Form */}
      {showCreate && (
        <div className="mb-6 rounded-lg border border-ald-blue/30 bg-ald-surface p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block font-mono text-sm text-ald-text-dim mb-1">Ticker</label>
              <input
                type="text"
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
                placeholder="NVDA"
                className="rounded border border-ald-border bg-ald-deep px-3 py-2 font-mono text-sm text-ald-text w-28 focus:border-ald-blue/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-mono text-sm text-ald-text-dim mb-1">Type</label>
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="rounded border border-ald-border bg-ald-deep px-3 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none appearance-none"
              >
                <option value="score_threshold">Score Threshold</option>
                <option value="score_change">Score Change</option>
                <option value="verdict_change">Verdict Change</option>
                <option value="price_change">Price Change</option>
              </select>
            </div>
            {newType !== 'verdict_change' && (
              <div>
                <label className="block font-mono text-sm text-ald-text-dim mb-1">Value</label>
                <input
                  type="number"
                  step="0.01"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  className="rounded border border-ald-border bg-ald-deep px-3 py-2 font-mono text-sm text-ald-text w-24 focus:border-ald-blue/40 focus:outline-none"
                />
              </div>
            )}
            <button
              onClick={handleCreate}
              disabled={creating || !newTicker.trim()}
              className="rounded bg-ald-blue px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-void hover:bg-ald-blue/80 transition-colors disabled:opacity-50"
            >
              {creating ? '...' : 'Create'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="rounded border border-ald-border px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded border border-ald-red/30 bg-ald-red/5 p-3 font-mono text-sm text-ald-red">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
          <p className="mb-2 text-sm text-ald-text-muted">No alerts configured.</p>
          <p className="font-mono text-sm text-ald-text-dim">Create alerts to monitor score thresholds, verdict changes, and price movements.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <div
              key={alert.alert_id}
              className={`flex items-center justify-between rounded-lg border p-4 transition-all ${
                alert.status === 'active'
                  ? 'border-ald-border bg-ald-surface'
                  : 'border-ald-border/50 bg-ald-void/50 opacity-60'
              }`}
            >
              <div className="flex items-center gap-4">
                <span className={`inline-block h-2 w-2 rounded-full ${
                  alert.status === 'active' ? 'bg-ald-blue animate-pulse' : 'bg-ald-text-dim'
                }`} />
                <LogoImg ticker={alert.ticker} />
                <WatchlistButton ticker={alert.ticker} />
                <div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/alidade/research/${alert.ticker}`}
                      className="font-mono text-sm text-ald-ivory hover:text-ald-blue transition-colors"
                    >
                      {alert.ticker}
                    </Link>
                    <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-sm uppercase tracking-wider text-ald-text-dim">
                      {typeLabels[alert.alert_type] ?? alert.alert_type}
                    </span>
                  </div>
                  <span className="block font-mono text-sm text-ald-text-dim">{conditionText(alert)}</span>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <span className="block font-mono text-sm text-ald-text-dim">
                    {alert.triggered_count}x triggered
                  </span>
                  {alert.last_triggered && (
                    <span className="block font-mono text-xs text-ald-text-dim">
                      last {new Date(alert.last_triggered).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleToggle(alert.alert_id, alert.status)}
                  className="rounded border border-ald-border px-3 py-1.5 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text hover:border-ald-blue/30 transition-colors"
                >
                  {alert.status === 'active' ? 'Pause' : 'Resume'}
                </button>
                <button
                  onClick={() => handleDelete(alert.alert_id)}
                  className="rounded border border-ald-border px-3 py-1.5 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-red hover:border-ald-red/30 transition-colors"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
