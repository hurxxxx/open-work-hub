import { Activity, Calendar } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const plannerManifest: AppModuleManifest = {
  appBarItem: { id: 'planner', title: 'planner', icon: Calendar },
  surfaces: { launcher: { globalPath: '/planner' } },
  contract: {
    owner: 'planner-platform',
    permissions: [],
    apiDomain: 'planner',
    resourceScope: 'personal',
    aiCapabilities: [
      'planner.list_events',
      'planner.create_event',
      'planner.update_event',
      'planner.delete_event',
    ],
    writeAuditActions: [
      'planner.create_event',
      'planner.update_event',
      'planner.delete_event',
    ],
    appLocalTests: [
      'apps/web/src/app-modules/planner/views/planner-calendar-session.spec.ts',
      'apps/api/tests/test_planner_events.py',
    ],
  },
  defaultActiveNavItemId: 'planner-calendar',
  navItems: [
    {
      id: 'planner-calendar',
      title: 'planner-calendar',
      icon: Calendar,
      category: 'Schedule',
      appId: 'planner',
    },
    {
      id: 'planner-timeline',
      title: 'planner-timeline',
      icon: Activity,
      category: 'Schedule',
      appId: 'planner',
      pathSuffix: '?view=timeline',
    },
  ],
  workspaceRoutePaths: [],
  globalRoutePaths: ['/planner'],
};
