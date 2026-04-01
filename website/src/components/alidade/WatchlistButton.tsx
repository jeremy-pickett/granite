'use client';

import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';

interface WatchlistButtonProps {
  ticker: string;
  size?: 'sm' | 'md';
}

export default function WatchlistButton({ ticker, size = 'sm' }: WatchlistButtonProps) {
  const { getIdToken, isAuthenticated } = useAuth();
  const [added, setAdded] = useState(false);
  const [loading, setLoading] = useState(false);

  if (!isAuthenticated) return null;

  async function handleAdd() {
    if (added || loading) return;
    setLoading(true);
    try {
      const token = await getIdToken();
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: ticker.toUpperCase() }),
      });
      if (res.ok) setAdded(true);
    } catch {}
    setLoading(false);
  }

  const cls = size === 'sm'
    ? 'h-5 w-5 text-xs'
    : 'h-6 w-6 text-sm';

  if (added) {
    return (
      <span className={`inline-flex items-center justify-center rounded-full bg-ald-green/20 text-ald-green ${cls}`} title="Added to watchlist">
        ✓
      </span>
    );
  }

  return (
    <button
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleAdd(); }}
      disabled={loading}
      className={`inline-flex items-center justify-center rounded-full border border-ald-border bg-ald-deep text-ald-text-dim hover:border-ald-blue hover:text-ald-blue transition-colors disabled:opacity-50 ${cls}`}
      title={`Add ${ticker} to watchlist`}
    >
      +
    </button>
  );
}
