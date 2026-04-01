'use client';

import { useState, useEffect, useCallback } from 'react';

interface Position {
  ticker: string;
  name: string;
  security_type: string;
  shares: number;
  avg_cost: number;
  total_cost: number;
  bought_at: string;
}

interface PortfolioState {
  cash: number;
  positions: Position[];
  transactions: unknown[];
  started_at: string;
}

const STORAGE_KEY = 'alidade_portfolio_sim';

/**
 * Returns the user's virtual portfolio positions from localStorage.
 * Auto-fetches live prices for held positions.
 * Provides a glow class calculator based on position P&L vs current price.
 *
 * Glow rules:
 *  - Within ±1% of avg cost → warm yellow
 *  - Down >1% → red
 *  - Up >1% → calm blue
 */
export function usePortfolio() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [livePrices, setLivePrices] = useState<Record<string, number>>({});

  useEffect(() => {
    function load() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const state: PortfolioState = JSON.parse(raw);
          setPositions(state.positions ?? []);
        }
      } catch {}
    }
    load();
    window.addEventListener('storage', load);
    const interval = setInterval(load, 5000);
    return () => { window.removeEventListener('storage', load); clearInterval(interval); };
  }, []);

  // Fetch live prices for all held tickers
  useEffect(() => {
    if (positions.length === 0) return;
    let cancelled = false;

    async function fetchPrices() {
      const prices: Record<string, number> = {};
      await Promise.all(
        positions.map(async (p) => {
          try {
            const res = await fetch(`/api/security-detail?ticker=${p.ticker}`);
            if (res.ok) {
              const data = await res.json();
              const price = data.snapshot?.price ? Number(data.snapshot.price) : null;
              if (!cancelled && price) prices[p.ticker] = price;
            }
          } catch {}
        })
      );
      if (!cancelled) setLivePrices(prices);
    }

    fetchPrices();
    const interval = setInterval(fetchPrices, 120000); // refresh every 2 min
    return () => { cancelled = true; clearInterval(interval); };
  }, [positions]);

  const getPosition = useCallback((ticker: string): Position | undefined => {
    return positions.find(p => p.ticker === ticker);
  }, [positions]);

  /**
   * Returns a Tailwind box-shadow class for the portfolio glow effect.
   * Uses auto-fetched live prices. Pass currentPrice to override.
   * Returns empty string if the user doesn't hold that security.
   */
  const glowClass = useCallback((ticker: string, currentPrice?: number | null): string => {
    const pos = positions.find(p => p.ticker === ticker);
    if (!pos) return '';

    const price = currentPrice ?? livePrices[ticker];
    if (!price || price <= 0) return '';

    const pctChange = ((price - pos.avg_cost) / pos.avg_cost) * 100;

    if (Math.abs(pctChange) <= 1) {
      return 'glow-held-neutral';
    } else if (pctChange < -1) {
      return 'glow-held-down';
    } else {
      return 'glow-held-up';
    }
  }, [positions, livePrices]);

  return { positions, getPosition, glowClass, livePrices };
}
