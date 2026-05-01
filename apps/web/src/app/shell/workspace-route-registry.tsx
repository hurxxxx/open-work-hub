import { Route } from 'react-router-dom';

import { aiWorkspaceRoutes } from '@/src/app-modules/ai';
import { docsGlobalRoutes, docsWorkspaceRoutes } from '@/src/app-modules/docs';
import { homeWorkspaceRoutes } from '@/src/app-modules/home';
import { learningWorkspaceRoutes } from '@/src/app-modules/learning';
import { meetingWorkspaceRoutes } from '@/src/app-modules/meeting';
import { plannerWorkspaceRoutes } from '@/src/app-modules/planner';
import { pmsWorkspaceRoutes } from '@/src/app-modules/pms';
import { whiteboardWorkspaceRoutes } from '@/src/app-modules/whiteboard';
import {
  adminRedirectRoutes,
  adminSectionRoutes,
  workspaceSettingsRoute,
} from '@/src/app-modules/settings';
import { AdminGate, WorkspaceGate } from './gates';

export const workspaceRouteDefinitions = [
  ...homeWorkspaceRoutes,
  ...aiWorkspaceRoutes,
  ...pmsWorkspaceRoutes,
  ...docsWorkspaceRoutes,
  ...whiteboardWorkspaceRoutes,
  ...plannerWorkspaceRoutes,
  ...meetingWorkspaceRoutes,
  ...learningWorkspaceRoutes,
];

export const globalRouteDefinitions = [
  ...docsGlobalRoutes,
  workspaceSettingsRoute,
  ...adminRedirectRoutes,
  ...adminSectionRoutes,
];

export function WorkspaceRouteElements({
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
}: {
  bootstrapAppIds: string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
}) {
  return (
    <>
      {workspaceRouteDefinitions.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={(
            <WorkspaceGate
              appId={route.appId}
              bootstrapAppIds={bootstrapAppIds}
              bootstrapError={bootstrapError}
              bootstrapLoading={bootstrapLoading}
            >
              {route.element}
            </WorkspaceGate>
          )}
        />
      ))}
    </>
  );
}

export function AdminSectionRouteElements() {
  return (
    <>
      {adminSectionRoutes.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={(
            <AdminGate section={route.section}>
              {route.element}
            </AdminGate>
          )}
        />
      ))}
    </>
  );
}

export function StaticRouteElements() {
  return (
    <>
      {docsGlobalRoutes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element} />
      ))}
      <Route path={workspaceSettingsRoute.path} element={workspaceSettingsRoute.element} />
      {adminRedirectRoutes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element} />
      ))}
      {AdminSectionRouteElements()}
    </>
  );
}
