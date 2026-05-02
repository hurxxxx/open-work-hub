import { Activity, Calendar } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const plannerManifest: AppModuleManifest = {
  appBarItem: { id: 'planner', title: 'planner', icon: Calendar },
  defaultActiveNavItemId: '',
  navItems: [
    { id: 'planner-calendar', title: 'planner-calendar', icon: Calendar, category: 'Schedule', appId: 'planner' },
    { id: 'planner-timeline', title: 'planner-timeline', icon: Activity, category: 'Schedule', appId: 'planner' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/planner'],
};
