import { Database, Table2, TerminalSquare } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const plmManifest: AppModuleManifest = {
  appBarItem: { id: 'plm', title: 'plm', icon: Database },
  contract: {
    owner: 'plm-platform',
    permissions: [],
    apiDomain: 'plm',
    workspaceApiPrefixes: ['/api/v1/plm'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_plm_query_policy.py',
      'apps/api/tests/test_plm_raw_oracle.py',
    ],
  },
  defaultActiveNavItemId: 'plm-raw-tables',
  navItems: [
    {
      id: 'plm-raw-tables',
      title: 'plm-raw-tables',
      icon: Table2,
      category: 'PLM',
      appId: 'plm',
    },
    {
      id: 'plm-raw-sql',
      title: 'plm-raw-sql',
      icon: TerminalSquare,
      category: 'PLM',
      appId: 'plm',
      pathSuffix: '?tab=sql',
    },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/plm'],
};
