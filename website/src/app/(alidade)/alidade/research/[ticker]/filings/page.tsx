import FilingsClient from './FilingsClient';

export default async function FilingsPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return <FilingsClient ticker={ticker.toUpperCase()} />;
}
