import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Archive, Presentation, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const bentoManifest: AppModuleManifest = {
  appBarItem: { id: 'bento', title: 'bento', icon: Presentation },
  contract: {
    owner: 'collaboration-platform',
    permissions: [],
    apiDomain: 'bento',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_bento_documents.py',
      'apps/web/src/app-modules/bento/bento-route-paths.spec.ts',
      'apps/web/src/app-modules/bento/views/bento-embed-protocol.spec.ts',
    ],
  },
  defaultActiveNavItemId: 'bento-all',
  navItems: [
    {
      id: 'bento-all',
      title: 'bento-all',
      icon: Presentation,
      category: 'Library',
      appId: 'bento',
    },
    {
      id: 'bento-mine',
      title: 'bento-mine',
      icon: User,
      category: 'Library',
      appId: 'bento',
      pathSuffix: '?view=mine',
    },
    {
      id: 'bento-archived',
      title: 'bento-archived',
      icon: Archive,
      category: 'Library',
      appId: 'bento',
      pathSuffix: '?view=archived',
    },
  ],
  appRoutePaths: [
    getAppRoutePattern('bento.root'),
    getAppRoutePattern('bento.presentation'),
  ],
};
