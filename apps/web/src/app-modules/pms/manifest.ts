import {
  Calendar,
  CheckCircle2,
  FolderKanban,
  Inbox,
  List as ListIcon,
  User,
} from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const pmsManifest: AppModuleManifest = {
  appBarItem: { id: 'pms', title: 'PMS', icon: FolderKanban },
  defaultActiveNavItemId: '',
  navItems: [
    { id: 'pms-inbox', title: 'Inbox', icon: Inbox, category: 'Personal', appId: 'pms' },
    { id: 'pms-tasks', title: 'My Tasks', icon: CheckCircle2, category: 'Personal', appId: 'pms', pathSuffix: '/assigned' },
    { id: 'pms-tasks-assigned', title: 'Assigned to me', icon: User, category: 'Personal', appId: 'pms', pathSuffix: '/assigned' },
    { id: 'pms-tasks-today', title: 'Today & Overdue', icon: Calendar, category: 'Personal', appId: 'pms', pathSuffix: '/today' },
    { id: 'pms-tasks-personal', title: 'Personal List', icon: ListIcon, category: 'Personal', appId: 'pms', pathSuffix: '/personal' },
  ],
  workspaceRoutePaths: [
    '/w/:workspaceSlug/pms',
    '/w/:workspaceSlug/pms/assigned',
    '/w/:workspaceSlug/pms/today',
    '/w/:workspaceSlug/pms/personal',
  ],
};
