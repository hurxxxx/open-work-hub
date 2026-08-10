import type { FeatureModuleManifest } from '@/src/app/shell/navigation-types';

export const dmManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'dm',
  contract: {
    owner: 'communications-platform',
    permissions: [],
    apiDomain: 'dm',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/dm/api/dm-api.spec.ts',
      'apps/api/tests/test_dm.py',
    ],
  },
};
