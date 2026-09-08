import { Users } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { buildAppPath } from '@/src/platform/apps/app-links';

export const meetingSidebarConfig: AppSidebarConfig = {
  createActions: ({ currentPathname, navigate }) => [
    {
      id: 'meeting-create',
      label: 'meeting-create',
      labelKey: 'sidebarActions.meeting-create',
      icon: Users,
      run: () => {
        const currentMeetingPath = buildAppPath('meeting');
        if (
          currentMeetingPath &&
          (currentPathname === currentMeetingPath ||
            currentPathname.startsWith(`${currentMeetingPath}/`))
        ) {
          window.dispatchEvent(new CustomEvent('meeting:create-event'));
          return;
        }

        navigate(buildAppPath('meeting'));

        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('meeting:create-event'));
        }, 50);
      },
    },
  ],
};
