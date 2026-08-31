import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import {
  ADMIN_SECTION_DEFINITIONS,
  type AdminSection,
} from '@/src/platform/admin/admin-sections';
import type { AdminAppsPage } from '@/src/platform/admin/admin-apps-section';

const AdminConsoleView = lazy(() =>
  import('@/src/platform/admin/admin-console').then((module) => ({
    default: module.AdminConsoleView,
  })),
);
const WorkspaceSettingsView = lazy(() =>
  import('@/src/platform/workspaces/WorkspaceSettingsView').then((module) => ({
    default: module.WorkspaceSettingsView,
  })),
);

export const workspaceSettingsRoute = {
  path: '/admin/workspaces/:workspaceSlug/settings',
  element: lazyRoute(createElement(WorkspaceSettingsView)),
};

export const adminRedirectRoutes = [] as const;

function createAdminSectionRoute(
  section: AdminSection,
  path: string,
  appsPage?: AdminAppsPage,
) {
  return {
    path,
    section,
    element: lazyRoute(
      createElement(AdminConsoleView, {
        appsPage,
        section,
      }),
    ),
  };
}

export const adminSectionRoutes = ADMIN_SECTION_DEFINITIONS.flatMap(
  (section) => {
    if (section.id !== 'apps') {
      return [createAdminSectionRoute(section.id, section.path)];
    }
    return [
      createAdminSectionRoute('apps', '/admin/apps/platform', 'platform'),
      createAdminSectionRoute('apps', '/admin/apps/workspace', 'workspace'),
      createAdminSectionRoute('apps', '/admin/apps/app-bar', 'app-bar'),
    ];
  },
);
