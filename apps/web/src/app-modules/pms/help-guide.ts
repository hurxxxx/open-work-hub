import { BookOpen } from 'lucide-react';

import { pmsManifest } from './manifest';

const appId = pmsManifest.appBarItem.id;
const guideSrc = `/help/${appId}/user-guide.html`;

export function getPmsHelpGuideSrc(locale: string | undefined): string {
  return locale?.toLowerCase().startsWith('en')
    ? `${guideSrc}#english`
    : guideSrc;
}

export const pmsHelpGuideRegistration = {
  descriptionKey: 'shell:helpCenter.pmsGuideDescription',
  icon: BookOpen,
  key: appId,
  routePath: `/help/${appId}`,
  src: guideSrc,
  titleKey: 'shell:helpCenter.pmsGuideTitle',
} as const;
