import { Calendar, Users } from 'lucide-react';

import type {
  AppSidebarConfig,
  AppSidebarCreateAction,
} from '@/src/app/shell/sidebar-types';

export const plannerSidebarConfig: AppSidebarConfig = {
  createActions: ({ enabledWorkspaceAppIds }) => {
    const actions: AppSidebarCreateAction[] = [
      {
        id: 'planner-create-event',
        label: 'planner-create-event',
        labelKey: 'sidebarActions.planner-create-event',
        icon: Calendar,
        run: () => {
          window.dispatchEvent(new CustomEvent('planner:create-event'));
        },
      },
    ];

    if (enabledWorkspaceAppIds.includes('meeting')) {
      actions.push({
        id: 'planner-create-meeting',
        label: 'planner-create-meeting',
        labelKey: 'sidebarActions.planner-create-meeting',
        icon: Users,
        run: () => {
          window.dispatchEvent(new CustomEvent('planner:create-meeting'));
        },
      });
    }

    return actions;
  },
};
