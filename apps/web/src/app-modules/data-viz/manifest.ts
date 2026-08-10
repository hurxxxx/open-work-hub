import { BarChart3 } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const dataVizManifest: AppModuleManifest = {
  appBarItem: { id: 'data-viz', title: 'data-viz', icon: BarChart3 },
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: 'dataviz',
    workspaceApiPrefixes: ['/api/v1/dataviz'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/data-viz/views/compressor-perf-table-model.spec.ts',
      'apps/web/src/app-modules/data-viz/views/sysperf-graph-model.spec.ts',
    ],
  },
  defaultActiveNavItemId: 'data-viz',
  navItems: [
    {
      id: 'data-viz',
      title: 'data-viz',
      icon: BarChart3,
      category: 'business-apps',
      appId: 'data-viz',
      description: 'data-viz',
    },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/data-viz'],
};
