import { BookOpen } from 'lucide-react';

import { pmsManifest } from './manifest';

const appId = pmsManifest.appBarItem.id;

export const pmsHelpGuideRegistration = {
  descriptionKey: 'shell:helpCenter.pmsGuideDescription',
  icon: BookOpen,
  key: appId,
  routePath: `/help/${appId}`,
  src: `/help/${appId}/user-guide.html`,
  titleKey: 'shell:helpCenter.pmsGuideTitle',
} as const;
