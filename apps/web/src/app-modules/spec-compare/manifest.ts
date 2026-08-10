import { FileSearch } from 'lucide-react';

import { specCompareToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const specCompareManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'spec-compare',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'spec_compare',
    workspaceApiPrefixes: ['/api/v1/spec-compare'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/ai/views/spec-compare-view-model.spec.ts',
      'apps/api/tests/test_spec_compare_service.py',
    ],
  },
  surfaces: { aiToolEntry: true },
});

export const specCompareModule = defineFeatureModuleRegistration({
  manifest: specCompareManifest,
  shell: {
    navItem: {
      id: 'spec-compare',
      title: 'spec-compare',
      icon: FileSearch,
      category: 'Business AI',
    },
    tool: {
      element: specCompareToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
