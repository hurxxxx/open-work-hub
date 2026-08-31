import { Globe2 } from 'lucide-react';
import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const webSearchManifest: AppModuleManifest = {
  appBarItem: { id: 'web-search', title: 'web-search', icon: Globe2 },
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'web_search',
    workspaceApiPrefixes: ['/api/v1/web-search'],
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
  workspaceRoutePaths: [getAppRoutePattern('web-search.root')],
};
