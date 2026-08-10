import { Scale } from 'lucide-react';

import { lawSearchToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const lawSearchManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'law-search',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'lawsearch',
    workspaceApiPrefixes: ['/api/v1/lawsearch'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_lawsearch_service.py'],
  },
  surfaces: { aiToolEntry: true },
});

export const lawSearchModule = defineFeatureModuleRegistration({
  manifest: lawSearchManifest,
  shell: {
    navItem: {
      id: 'law-search',
      title: 'law-search',
      icon: Scale,
      category: 'Product Analysis',
    },
    tool: {
      element: lawSearchToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
