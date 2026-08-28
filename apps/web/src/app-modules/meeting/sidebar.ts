import { Users } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import {
  buildWorkspaceAppPath,
  buildWorkspaceAppEntryPath,
} from '@/src/platform/workspaces/workspace-utils';

export const meetingSidebarConfig: AppSidebarConfig = {
  createActions: ({ currentPathname, currentWorkspaceSlug, navigate }) => [
    {
      id: 'meeting-create',
      label: 'meeting-create',
      labelKey: 'sidebarActions.meeting-create',
      icon: Users,
      run: () => {
        const currentMeetingPath = currentWorkspaceSlug
          ? buildWorkspaceAppPath(currentWorkspaceSlug, 'meeting')
          : null;
        if (
          currentMeetingPath &&
          (currentPathname === currentMeetingPath ||
            currentPathname.startsWith(`${currentMeetingPath}/`))
        ) {
          window.dispatchEvent(new CustomEvent('meeting:create-event'));
          return;
        }

        navigate(
          currentWorkspaceSlug
            ? buildWorkspaceAppPath(currentWorkspaceSlug, 'meeting')
            : buildWorkspaceAppEntryPath('meeting'),
        );

        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('meeting:create-event'));
        }, 50);
      },
    },
  ],
};
