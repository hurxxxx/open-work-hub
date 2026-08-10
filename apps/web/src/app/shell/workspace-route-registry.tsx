import { Route } from 'react-router-dom';

import { WorkspaceGate } from './gates';
import type { WorkspaceRouteDefinition } from './route-types';

export type ShellWorkspaceRouteDefinition = Omit<
  WorkspaceRouteDefinition,
  'appId' | 'bootstrapAppId'
> & {
  appId: string;
  bootstrapAppId?: string;
};

export function resolveWorkspaceRouteBootstrapAppId(
  route: Pick<ShellWorkspaceRouteDefinition, 'appId' | 'bootstrapAppId'>,
): string {
  return route.bootstrapAppId ?? route.appId;
}

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
              appId={resolveWorkspaceRouteBootstrapAppId(route)}
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
