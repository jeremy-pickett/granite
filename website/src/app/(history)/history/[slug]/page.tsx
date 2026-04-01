import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import Part1DiscoveryContent from './content/part-1-discovery';
import Part2ValidationContent from './content/part-2-validation';
import AnAfternoonWellSpentContent from './content/an-afternoon-well-spent';
import OneOfThoseDaysContent from './content/one-of-those-days';

const pages: Record<string, { title: string; component: React.ComponentType }> = {
  'part-1-discovery': {
    title: 'Part I: Discovery — History',
    component: Part1DiscoveryContent,
  },
  'part-2-validation': {
    title: 'Part II: Validation — History',
    component: Part2ValidationContent,
  },
  'an-afternoon-well-spent': {
    title: 'An Afternoon Well Spent — History',
    component: AnAfternoonWellSpentContent,
  },
  'one-of-those-days': {
    title: 'One of Those Days — History',
    component: OneOfThoseDaysContent,
  },
};

const allSlugs = Object.keys(pages);

export function generateStaticParams() {
  return allSlugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const page = pages[slug];
  if (!page) {
    return { title: 'Not Found — Granite Under Sandstone' };
  }
  return {
    title: `${page.title} — Granite Under Sandstone`,
  };
}

export default async function HistorySubPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page = pages[slug];
  if (!page) {
    notFound();
  }

  const Content = page.component;
  return <Content />;
}
