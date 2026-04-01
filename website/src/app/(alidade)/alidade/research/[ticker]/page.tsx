import type { Metadata } from 'next';
import ResearchClient from './ResearchClient';

interface PageProps {
  params: Promise<{ ticker: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { ticker } = await params;
  return { title: `${ticker.toUpperCase()} Research — Alidade` };
}

export default async function ResearchPage({ params }: PageProps) {
  const { ticker } = await params;
  return <ResearchClient ticker={ticker.toUpperCase()} />;
}
