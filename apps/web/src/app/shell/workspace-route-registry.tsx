import { Route } from 'react-router-dom';

import { WorkspaceGate } from './gates';
import type { WorkspaceRouteDefinition } from './route-types';

export type ShellWorkspaceRouteDefinition = Omit<
  WorkspaceRouteDefinition,
  'appId'
> & {
  appId: string;
};

export function WorkspaceRouteElements({
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
  workspaceRoutes = [],
}: {
  bootstrapAppIds: string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  workspaceRoutes?: readonly ShellWorkspaceRouteDefinition[];
}) {
  return (
    <>
      {workspaceRoutes.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={
            <WorkspaceGate
              appId={route.appId}
              bootstrapAppIds={bootstrapAppIds}
              bootstrapError={bootstrapError}
              bootstrapLoading={bootstrapLoading}
            >
              {route.element}
            </WorkspaceGate>
          }
        />
      ))}
    </>
  );
}
