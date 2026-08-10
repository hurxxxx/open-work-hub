import { ScanSearch } from 'lucide-react';

import { patentAnalysisToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const patentAnalysisManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'patent-analysis',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'patent',
    workspaceApiPrefixes: ['/api/v1/patent'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_patent.py'],
  },
  surfaces: { aiToolEntry: true },
});

export const patentAnalysisModule = defineFeatureModuleRegistration({
  manifest: patentAnalysisManifest,
  shell: {
    navItem: {
      id: 'patent-apply',
      title: 'patent-apply',
      icon: ScanSearch,
      category: 'Patent',
    },
    tool: {
      element: patentAnalysisToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
