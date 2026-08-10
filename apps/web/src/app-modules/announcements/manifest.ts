import type { FeatureModuleManifest } from '@/src/app/shell/navigation-types';

export const announcementsManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'announcements',
  contract: {
    owner: 'platform-shell',
    permissions: [],
    apiDomain: 'announcements',
    workspaceApiPrefixes: ['/api/v1/announcements'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/home/views/WorkspaceHomeView/useWorkspaceHomeController.spec.ts',
      'apps/web/src/app-modules/home/views/WorkspaceHomeView/workspace-home-model.spec.ts',
      'apps/api/tests/test_announcements.py',
    ],
  },
};
