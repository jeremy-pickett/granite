import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Watchlist — Alidade',
};

export default function WatchlistLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
