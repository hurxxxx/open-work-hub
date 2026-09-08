import type { FeatureModuleManifest } from '@/src/app/shell/navigation-types';

export const announcementsManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'announcements',
  contract: {
    owner: 'platform-shell',
    permissions: [],
    apiDomain: 'announcements',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/home/views/HomeView/useHomeController.spec.ts',
      'apps/web/src/app-modules/home/views/HomeView/home-model.spec.ts',
      'apps/api/tests/test_announcements.py',
    ],
  },
};
