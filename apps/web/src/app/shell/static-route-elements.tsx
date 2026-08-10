import { Route } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { ReactNode } from 'react';

import { pmsHelpGuideRegistration } from '@/src/app-modules/pms';

import { AdminGate } from './gates';
import {
  getDefaultAdminPath as getPlatformDefaultAdminPath,
  hasConfiguredAdminSectionAccess,
  type AdminSectionAccessResolver,
  type DefaultAdminPathResolver,
} from '@/src/platform/admin/admin-permissions';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import type { StaticRouteDefinition } from './navigation-types';
import {
  HelpAiGuidePage,
  HelpCenterPage,
  HelpPmsGuidePage,
} from './HelpCenterPage';
import { AdminLandingRedirect } from './redirects';
import {
  EMPTY_FEATURE_GUIDE_TOOL_IDS,
  type FeatureGuideToolIds,
} from './ai-feature-guides';

export type ShellStaticRouteDefinition = Omit<
  StaticRouteDefinition,
  'appId'
> & {
  appId?: string;
};

export type ShellAdminSectionRouteDefinition = ShellStaticRouteDefinition & {
  section: string;
};

export function resolveGlobalRouteGateAppId(route: {
  appId?: string;
  bootstrapAppId?: string;
}): string | undefined {
  return route.bootstrapAppId ?? route.appId;
}

export function isGlobalAppGateVisible(
  appId: string | undefined,
  visibleAppIds: readonly string[],
): boolean {
  return (
    !appId ||
    appId === 'home' ||
    appId === 'settings' ||
    visibleAppIds.includes(appId)
  );
}

export type GlobalRouteBootstrapState = {
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  visibleAppIds: readonly string[] | null;
};

export function resolveGlobalRouteBootstrapState({
  appId,
  defaultState,
  launcherGlobalAppIds,
  launcherGlobalState,
}: {
  appId: string | undefined;
  defaultState: GlobalRouteBootstrapState;
  launcherGlobalAppIds: readonly string[];
  launcherGlobalState: GlobalRouteBootstrapState;
}): GlobalRouteBootstrapState {
  return appId && launcherGlobalAppIds.includes(appId)
    ? launcherGlobalState
    : defaultState;
}

export function createDefaultHelpRoutes(
  featureGuideToolIds: FeatureGuideToolIds,
): readonly ShellStaticRouteDefinition[] {
  return [
    { path: '/help', element: <HelpCenterPage /> },
    {
      path: pmsHelpGuideRegistration.routePath,
      element: <HelpPmsGuidePage />,
    },
    {
      path: '/help/ai/:feature',
      element: <HelpAiGuidePage featureGuideToolIds={featureGuideToolIds} />,
    },
  ];
}

const defaultAdminLandingRoute: ShellStaticRouteDefinition = {
  path: '/admin',
  element: <AdminLandingRedirect />,
};

function GlobalAppGate({
  appId,
  bootstrapError,
  bootstrapLoading,
  children,
  visibleAppIds,
}: {
  appId: string | undefined;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  children: ReactNode;
  visibleAppIds: readonly string[] | null;
}) {
  const { t } = useTranslation('shell');
  if (!appId || appId === 'home' || appId === 'settings') {
    return children;
  }
  if (bootstrapLoading || visibleAppIds === null) {
    return (
      <div className="p-8 text-app-ink/55">{t('gates.workspaceLoading')}</div>
    );
  }
  if (bootstrapError) {
    return <AccessDeniedView description={bootstrapError} />;
  }
  if (!isGlobalAppGateVisible(appId, visibleAppIds)) {
    return <AccessDeniedView description={t('gates.appDisabled')} />;
  }
  return children;
}

export function StaticRouteElements({
  adminLandingRoute = defaultAdminLandingRoute,
  adminRedirectRoutes = [],
  adminSectionRoutes = [],
  appGlobalRoutes = [],
  bootstrapError,
  bootstrapLoading,
  featureGuideToolIds = EMPTY_FEATURE_GUIDE_TOOL_IDS,
  getDefaultAdminPath = getPlatformDefaultAdminPath,
  hasAdminSectionAccess = hasConfiguredAdminSectionAccess,
  helpRoutes,
  launcherGlobalAppIds = [],
  launcherGlobalBootstrapError = null,
  launcherGlobalBootstrapLoading = false,
  launcherGlobalVisibleAppIds = null,
  visibleAppIds,
  workspaceSettingsRoute = null,
}: {
  adminLandingRoute?: ShellStaticRouteDefinition;
  adminRedirectRoutes?: readonly ShellStaticRouteDefinition[];
  adminSectionRoutes?: readonly ShellAdminSectionRouteDefinition[];
  appGlobalRoutes?: readonly ShellStaticRouteDefinition[];
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  featureGuideToolIds?: FeatureGuideToolIds;
  getDefaultAdminPath?: DefaultAdminPathResolver;
  hasAdminSectionAccess?: AdminSectionAccessResolver;
  helpRoutes?: readonly ShellStaticRouteDefinition[];
  launcherGlobalAppIds?: readonly string[];
  launcherGlobalBootstrapError?: string | null;
  launcherGlobalBootstrapLoading?: boolean;
  launcherGlobalVisibleAppIds?: readonly string[] | null;
  visibleAppIds: readonly string[] | null;
  workspaceSettingsRoute?: ShellStaticRouteDefinition | null;
}) {
  const resolvedHelpRoutes =
    helpRoutes ?? createDefaultHelpRoutes(featureGuideToolIds);

  return (
    <>
      {appGlobalRoutes.map((route) => {
        const appId = resolveGlobalRouteGateAppId(route);
        const routeBootstrapState = resolveGlobalRouteBootstrapState({
          appId,
          defaultState: {
            bootstrapError,
            bootstrapLoading,
            visibleAppIds,
          },
          launcherGlobalAppIds,
          launcherGlobalState: {
            bootstrapError: launcherGlobalBootstrapError,
            bootstrapLoading: launcherGlobalBootstrapLoading,
            visibleAppIds: launcherGlobalVisibleAppIds,
          },
        });
        return (
          <Route
            key={route.path}
            path={route.path}
            element={
              <GlobalAppGate
                appId={appId}
                bootstrapError={routeBootstrapState.bootstrapError}
                bootstrapLoading={routeBootstrapState.bootstrapLoading}
                visibleAppIds={routeBootstrapState.visibleAppIds}
              >
                {route.element}
              </GlobalAppGate>
            }
          />
        );
      })}
      {workspaceSettingsRoute ? (
        <Route
          path={workspaceSettingsRoute.path}
          element={workspaceSettingsRoute.element}
        />
      ) : null}
      {resolvedHelpRoutes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element} />
      ))}
      <Route
        path={adminLandingRoute.path}
        element={
          adminLandingRoute === defaultAdminLandingRoute ? (
            <AdminLandingRedirect getDefaultAdminPath={getDefaultAdminPath} />
          ) : (
            adminLandingRoute.element
          )
        }
      />
      {adminRedirectRoutes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element} />
      ))}
      {adminSectionRoutes.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={
            <AdminGate
              hasAdminSectionAccess={hasAdminSectionAccess}
              section={route.section}
            >
              {route.element}
            </AdminGate>
          }
        />
      ))}
    </>
  );
}
