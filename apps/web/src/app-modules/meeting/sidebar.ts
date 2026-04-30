import { Users } from 'lucide-react';

import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/domains/workspaces/workspace-utils';

export const meetingSidebarConfig: AppSidebarConfig = {
  createActions: ({ currentPathname, currentWorkspaceSlug, navigate, user }) => [
    {
      id: 'meeting-create',
      label: 'Meeting',
      icon: Users,
      run: () => {
        if (currentPathname.includes('/meeting')) {
          window.dispatchEvent(new CustomEvent('meeting:create-event'));
          return;
        }

        navigate(
          currentWorkspaceSlug
            ? buildWorkspaceAppPath(currentWorkspaceSlug, 'meeting')
            : resolveDefaultWorkspaceAppPath(user, 'meeting'),
        );

        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('meeting:create-event'));
        }, 50);
      },
    },
  ],
};
