import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import DesignHistoryContent from './content/design-history';
import RawIntegrationContent from './content/raw-integration';
import PrimeSplitEncodingContent from './content/prime-split-encoding';
import AddendumAVideoExtensionContent from './content/addendum-a-video-extension';
import AddendumBIntegrationLandscapeContent from './content/addendum-b-integration-landscape';
import AddendumCCascadingCanarySurvivalContent from './content/addendum-c-cascading-canary-survival';
import AddendumDAttributionArchitectureContent from './content/addendum-d-attribution-architecture';
import AddendumFMultilayerProvenanceContent from './content/addendum-f-multilayer-provenance';
import AddendumGKnownAttacksContent from './content/addendum-g-known-attacks';
import AddendumHTharBeDragonsContent from './content/addendum-h-thar-be-dragons';
import AddendumIColorOfSurvivalContent from './content/addendum-i-color-of-survival';
import AddendumJThermodynamicTaxContent from './content/addendum-j-thermodynamic-tax';
import AddendumKFuseAndFireContent from './content/addendum-k-fuse-and-fire';
import AddendumLSpanningSentinelContent from './content/addendum-l-spanning-sentinel';

const docs: Record<string, { title: string; component: React.ComponentType }> = {
  'design-history': {
    title: 'Design History',
    component: DesignHistoryContent,
  },
  'raw-integration': {
    title: 'Raw Integration Guide',
    component: RawIntegrationContent,
  },
  'prime-split-encoding': {
    title: 'Prime Split Encoding',
    component: PrimeSplitEncodingContent,
  },
  'addendum-a-video-extension': {
    title: 'Addendum A: Extension to Video',
    component: AddendumAVideoExtensionContent,
  },
  'addendum-b-integration-landscape': {
    title: 'Addendum B: Integration Landscape',
    component: AddendumBIntegrationLandscapeContent,
  },
  'addendum-c-cascading-canary-survival': {
    title: 'Addendum C: Cascading Canary Survival',
    component: AddendumCCascadingCanarySurvivalContent,
  },
  'addendum-d-attribution-architecture': {
    title: 'Addendum D: Attribution Architecture',
    component: AddendumDAttributionArchitectureContent,
  },
  'addendum-f-multilayer-provenance': {
    title: 'Addendum F: Multilayer Provenance',
    component: AddendumFMultilayerProvenanceContent,
  },
  'addendum-g-known-attacks': {
    title: 'Addendum G: Known Attacks',
    component: AddendumGKnownAttacksContent,
  },
  'addendum-h-thar-be-dragons': {
    title: 'Addendum H: Thar Be Dragons',
    component: AddendumHTharBeDragonsContent,
  },
  'addendum-i-color-of-survival': {
    title: 'Addendum I: The Color of Survival',
    component: AddendumIColorOfSurvivalContent,
  },
  'addendum-j-thermodynamic-tax': {
    title: 'Addendum J: The Thermodynamic Tax',
    component: AddendumJThermodynamicTaxContent,
  },
  'addendum-k-fuse-and-fire': {
    title: 'Addendum K: Fuse and Fire',
    component: AddendumKFuseAndFireContent,
  },
  'addendum-l-spanning-sentinel': {
    title: 'Addendum L: The Spanning Sentinel',
    component: AddendumLSpanningSentinelContent,
  },
};

const allSlugs = Object.keys(docs);

export function generateStaticParams() {
  return allSlugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const doc = docs[slug];
  if (!doc) {
    return { title: 'Not Found — Granite Under Sandstone' };
  }
  return {
    title: `${doc.title} — Granite Under Sandstone`,
  };
}

export default async function DocSubPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const doc = docs[slug];
  if (!doc) {
    notFound();
  }

  const Content = doc.component;
  return <Content />;
}
