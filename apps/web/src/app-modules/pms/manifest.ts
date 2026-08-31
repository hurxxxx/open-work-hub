import {
  Calendar,
  CheckCircle2,
  FolderKanban,
  Inbox,
  User,
} from 'lucide-react';
import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const pmsManifest: AppModuleManifest = {
  appBarItem: { id: 'pms', title: 'PMS', icon: FolderKanban },
  contract: {
    owner: 'pms-platform',
    permissions: [],
    apiDomain: 'pms',
    workspaceApiPrefixes: ['/api/v1/pms'],
    aiCapabilities: [
      'pms.search_tasks',
      'pms.get_task',
      'pms.list_spaces',
      'pms.list_task_lists',
      'pms.create_task',
      'pms.update_task',
      'pms.add_comment',
      'pms.delete_task',
    ],
    writeAuditActions: [
      'pms.create_task',
      'pms.update_task',
      'pms.add_comment',
      'pms.delete_task',
    ],
    appLocalTests: [
      'apps/web/src/app-modules/pms/views/pms-view-route.spec.ts',
      'apps/api/tests/test_pms_issues.py',
    ],
  },
  defaultActiveNavItemId: 'pms-inbox',
  navItems: [
    {
      id: 'pms-inbox',
      title: 'pms-inbox',
      icon: Inbox,
      category: 'Personal',
      appId: 'pms',
    },
    {
      id: 'pms-tasks',
      title: 'pms-tasks',
      icon: CheckCircle2,
      category: 'Personal',
      appId: 'pms',
      pathSuffix: '/assigned',
    },
    {
      id: 'pms-tasks-assigned',
      title: 'pms-tasks-assigned',
      icon: User,
      category: 'Personal',
      appId: 'pms',
      pathSuffix: '/assigned',
    },
    {
      id: 'pms-tasks-today',
      title: 'pms-tasks-today',
      icon: Calendar,
      category: 'Personal',
      appId: 'pms',
      pathSuffix: '/today',
    },
  ],
  workspaceRoutePaths: [
    getAppRoutePattern('pms.root'),
    getAppRoutePattern('pms.assigned'),
    getAppRoutePattern('pms.today'),
    getAppRoutePattern('pms.list'),
    getAppRoutePattern('pms.space'),
    getAppRoutePattern('pms.space-docs'),
    getAppRoutePattern('pms.space-doc'),
    getAppRoutePattern('pms.space-whiteboards'),
    getAppRoutePattern('pms.space-whiteboard'),
  ],
};
