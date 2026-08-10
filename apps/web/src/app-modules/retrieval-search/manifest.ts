import { Search } from 'lucide-react';

import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';
import { retrievalSearchElement } from './routes';

export const retrievalSearchManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'retrieval-search',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'retrieval',
    resourceScope: 'hybrid',
    workspaceApiPrefixes: ['/api/v1/retrieval'],
    aiCapabilities: ['retrieval.search', 'retrieval.list_sources'],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_retrieval.py'],
  },
});

export const retrievalSearchModule = defineFeatureModuleRegistration({
  manifest: retrievalSearchManifest,
  shell: {
    navItem: {
      id: 'retrieval-search',
      title: 'retrieval-search',
      icon: Search,
      category: 'Business AI',
    },
    tool: { element: retrievalSearchElement, subSidebar: 'hidden' },
  },
});
