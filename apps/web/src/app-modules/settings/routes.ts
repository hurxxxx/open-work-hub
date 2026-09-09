import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AdminAppsPage } from '@/src/platform/admin/admin-apps-section';
import {
  ADMIN_SECTION_DEFINITIONS,
  type AdminSection,
} from '@/src/platform/admin/admin-sections';

const AdminConsoleView = lazy(() =>
  import('@/src/platform/admin/admin-console').then((module) => ({
    default: module.AdminConsoleView,
  })),
);
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
      createAdminSectionRoute('apps', '/admin/apps/access', 'access'),
      createAdminSectionRoute('apps', '/admin/apps/app-bar', 'app-bar'),
    ];
  },
);
