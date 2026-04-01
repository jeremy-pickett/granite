import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import LayerGContent from './content/layer-g';
import LayerHContent from './content/layer-h';

const pages: Record<string, { title: string; component: React.ComponentType }> = {
  'layer-g': {
    title: 'Layer G: Halo',
    component: LayerGContent,
  },
  'layer-h': {
    title: 'Layer H: Spatial Ruler',
    component: LayerHContent,
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

export default async function StackSubPage({
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
