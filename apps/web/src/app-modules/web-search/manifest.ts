import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Globe2 } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const webSearchManifest: AppModuleManifest = {
  appBarItem: { id: 'web-search', title: 'web-search', icon: Globe2 },
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'web_search',
    aiCapabilities: ['web-search'],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_web_search_service.py'],
  },
  defaultActiveNavItemId: 'web-search',
  navItems: [
    {
      id: 'web-search',
      title: 'web-search',
      icon: Globe2,
      category: 'AI',
      appId: 'web-search',
    },
  ],
  appRoutePaths: [getAppRoutePattern('web-search.root')],
};
