import { Activity, Calendar } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const plannerManifest: AppModuleManifest = {
  appBarItem: { id: 'planner', title: 'planner', icon: Calendar },
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
  workspaceRoutePaths: ['/w/:workspaceSlug/planner'],
};
