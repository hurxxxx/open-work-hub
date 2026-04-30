import { lazy } from 'react';
import { Navigate } from 'react-router-dom';

import { lazyRoute } from '@/src/app/shell/lazy-route';

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
  path: '/w/:workspaceSlug/settings',
  element: lazyRoute(<WorkspaceSettingsView />),
};

export const adminRedirectRoutes = [
  { path: '/admin/users', element: <Navigate replace to="/admin/people" /> },
  { path: '/admin/groups', element: <Navigate replace to="/admin/security" /> },
  { path: '/admin/feature-access', element: <Navigate replace to="/admin/security" /> },
  { path: '/admin/teams', element: <Navigate replace to="/admin/workspaces" /> },
];

export const adminSectionRoutes = [
  { path: '/admin/general', section: 'general', element: lazyRoute(<AdminConsoleView section="general" />) },
  { path: '/admin/people', section: 'people', element: lazyRoute(<AdminConsoleView section="people" />) },
  { path: '/admin/workspaces', section: 'workspaces', element: lazyRoute(<AdminConsoleView section="workspaces" />) },
  { path: '/admin/security', section: 'security', element: lazyRoute(<AdminConsoleView section="security" />) },
  { path: '/admin/audit', section: 'audit', element: lazyRoute(<AdminConsoleView section="audit" />) },
] as const;
