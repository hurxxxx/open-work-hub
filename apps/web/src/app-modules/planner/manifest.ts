import { Activity, Calendar } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const plannerManifest: AppModuleManifest = {
  appBarItem: { id: 'planner', title: 'Planner', icon: Calendar },
  defaultActiveNavItemId: '',
  navItems: [
    { id: 'planner-calendar', title: '캘린더', icon: Calendar, category: 'Schedule', appId: 'planner' },
    { id: 'planner-timeline', title: '타임라인', icon: Activity, category: 'Schedule', appId: 'planner' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/planner'],
};
