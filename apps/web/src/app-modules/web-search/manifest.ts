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

export const researchTrendsManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'research-trends',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'research_trends',
    workspaceApiPrefixes: ['/api/v1/research-trends'],
    aiCapabilities: ['research-trends'],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_web_search_service.py'],
  },
};

export const standardsMonitorManifest: FeatureModuleManifest = {
  moduleKind: 'feature',
  moduleId: 'standards-monitor',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'standards_monitor',
    workspaceApiPrefixes: ['/api/v1/standards-monitor'],
    aiCapabilities: ['standards-monitor'],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_web_search_service.py'],
  },
};
