import {
  Calendar,
  CheckCircle2,
  FolderKanban,
  Inbox,
  User,
} from 'lucide-react';

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
  defaultActiveNavItemId: '',
  surfaces: { launcher: { defaultPinOrder: 0 } },
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
    '/w/:workspaceSlug/pms',
    '/w/:workspaceSlug/pms/assigned',
    '/w/:workspaceSlug/pms/today',
    '/w/:workspaceSlug/pms/lists/:taskListId',
    '/w/:workspaceSlug/pms/spaces/:spaceId',
    '/w/:workspaceSlug/pms/spaces/:spaceId/docs',
    '/w/:workspaceSlug/pms/spaces/:spaceId/docs/:docId',
    '/w/:workspaceSlug/pms/spaces/:spaceId/whiteboards',
    '/w/:workspaceSlug/pms/spaces/:spaceId/whiteboards/:whiteboardId',
  ],
};
