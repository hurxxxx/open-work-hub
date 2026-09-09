import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Search } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const retrievalSearchManifest: AppModuleManifest = {
  appBarItem: {
    id: 'retrieval-search',
    title: 'retrieval-search',
    icon: Search,
  },
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'retrieval',
    aiCapabilities: ['retrieval.search', 'retrieval.list_sources'],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_retrieval.py'],
  },
  defaultActiveNavItemId: 'retrieval-search',
  navItems: [
    {
      id: 'retrieval-search',
      title: 'retrieval-search',
      icon: Search,
      category: 'Business AI',
      appId: 'retrieval-search',
    },
  ],
  appRoutePaths: [getAppRoutePattern('retrieval-search.root')],
};
