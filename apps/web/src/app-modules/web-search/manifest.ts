import type { FeatureModuleManifest } from '@/src/app/shell/navigation-types';

export const webSearchManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'web-search',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'web_search',
    workspaceApiPrefixes: ['/api/v1/web-search'],
    aiCapabilities: ['web-search'],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_web_search_service.py'],
  },
};
