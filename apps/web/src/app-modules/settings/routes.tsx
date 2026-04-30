import { Navigate } from 'react-router-dom';

import { AdminConsoleView } from '@/src/domains/admin/admin-console';
import { WorkspaceSettingsView } from '@/src/domains/workspaces/WorkspaceSettingsView';

export const workspaceSettingsRoute = {
  path: '/w/:workspaceSlug/settings',
  element: <WorkspaceSettingsView />,
};

export const adminRedirectRoutes = [
  { path: '/admin/users', element: <Navigate replace to="/admin/people" /> },
  { path: '/admin/groups', element: <Navigate replace to="/admin/security" /> },
  { path: '/admin/feature-access', element: <Navigate replace to="/admin/security" /> },
  { path: '/admin/teams', element: <Navigate replace to="/admin/workspaces" /> },
];

export const adminSectionRoutes = [
  { path: '/admin/general', section: 'general', element: <AdminConsoleView section="general" /> },
  { path: '/admin/people', section: 'people', element: <AdminConsoleView section="people" /> },
  { path: '/admin/workspaces', section: 'workspaces', element: <AdminConsoleView section="workspaces" /> },
  { path: '/admin/security', section: 'security', element: <AdminConsoleView section="security" /> },
  { path: '/admin/audit', section: 'audit', element: <AdminConsoleView section="audit" /> },
] as const;
