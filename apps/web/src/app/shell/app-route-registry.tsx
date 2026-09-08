import { Route } from 'react-router-dom';

import { AppGate } from './gates';
import type { AppRouteDefinition } from './route-types';

export type ShellAppRouteDefinition = Omit<AppRouteDefinition, 'appId'> & {
  appId: string;
};

export function AppRouteElements({
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
  appRoutes = [],
}: {
  bootstrapAppIds: string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  appRoutes?: readonly ShellAppRouteDefinition[];
}) {
  return (
    <>
      {appRoutes.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={
            <AppGate
              appId={route.appId}
              bootstrapAppIds={bootstrapAppIds}
              bootstrapError={bootstrapError}
              bootstrapLoading={bootstrapLoading}
            >
              {route.element}
            </AppGate>
          }
        />
      ))}
    </>
  );
}
