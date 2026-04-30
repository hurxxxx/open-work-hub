import { Calendar, Users } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';

export const plannerSidebarConfig: AppSidebarConfig = {
  createActions: () => [
    {
      id: 'planner-create-event',
      label: 'Event',
      icon: Calendar,
      run: () => {
        window.dispatchEvent(new CustomEvent('planner:create-event'));
      },
    },
    {
      id: 'planner-create-meeting',
      label: 'Meeting',
      icon: Users,
      run: () => {
        window.dispatchEvent(new CustomEvent('planner:create-meeting'));
      },
    },
  ],
};
