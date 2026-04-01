import type { Metadata } from 'next';
import HistoryClient from './HistoryClient';

export const metadata: Metadata = {
  title: 'History — Signal Delta',
  description: 'The development history of Granite Under Sandstone, as it happened',
};

export default function HistoryPage() {
  return <HistoryClient />;
}
