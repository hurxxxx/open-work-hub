import { Route } from 'react-router-dom';

import { aiWorkspaceRoutes } from '@/src/app-modules/ai/routes';
import { docsGlobalRoutes, docsWorkspaceRoutes } from '@/src/app-modules/docs/routes';
import { homeWorkspaceRoutes } from '@/src/app-modules/home/routes';
import { learningWorkspaceRoutes } from '@/src/app-modules/learning/routes';
import { meetingWorkspaceRoutes } from '@/src/app-modules/meeting/routes';
import { plannerWorkspaceRoutes } from '@/src/app-modules/planner/routes';
import { pmsWorkspaceRoutes } from '@/src/app-modules/pms/routes';
import { whiteboardGlobalRoutes, whiteboardWorkspaceRoutes } from '@/src/app-modules/whiteboard/routes';
import {
  adminRedirectRoutes,
  adminSectionRoutes,
  workspaceSettingsRoute,
} from '@/src/app-modules/settings/routes';
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
  ...whiteboardGlobalRoutes,
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
      {whiteboardGlobalRoutes.map((route) => (
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
