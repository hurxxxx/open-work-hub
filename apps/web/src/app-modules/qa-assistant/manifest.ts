import type { FeatureModuleManifest } from '@/src/app/shell/navigation-types';

export const qaAssistantManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'qa-assistant',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'qna',
    resourceScope: 'company',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_qna_service.py'],
  },
  surfaces: {
    launcher: { defaultPinOrder: 3, globalPath: '/qa-assistant' },
  },
};
