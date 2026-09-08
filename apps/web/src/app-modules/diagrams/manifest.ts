import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Archive, User, Workflow } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const diagramsManifest: AppModuleManifest = {
  appBarItem: { id: 'diagrams', title: 'diagrams', icon: Workflow },
  contract: {
    owner: 'diagrams-platform',
    permissions: [],
    apiDomain: 'diagrams',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_diagrams.py',
      'apps/web/src/app-modules/diagrams/views/drawio-embed-protocol.spec.ts',
      'apps/web/src/app-modules/diagrams/views/diagrams-hub-model.spec.ts',
    ],
  },
  defaultActiveNavItemId: 'diagrams-all',
  navItems: [
    {
      id: 'diagrams-all',
      title: 'diagrams-all',
      icon: Workflow,
      category: 'Library',
      appId: 'diagrams',
    },
    {
      id: 'diagrams-mine',
      title: 'diagrams-mine',
      icon: User,
      category: 'Library',
      appId: 'diagrams',
      pathSuffix: '?view=mine',
    },
    {
      id: 'diagrams-archived',
      title: 'diagrams-archived',
      icon: Archive,
      category: 'Library',
      appId: 'diagrams',
      pathSuffix: '?view=archived',
    },
  ],
  appRoutePaths: [
    getAppRoutePattern('diagrams.root'),
    getAppRoutePattern('diagrams.diagram'),
  ],
};
