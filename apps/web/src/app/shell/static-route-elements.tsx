import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Route } from 'react-router-dom';

import { pmsHelpGuideRegistration } from '@/src/app-modules/pms';

import {
  getDefaultAdminPath as getPlatformDefaultAdminPath,
  hasConfiguredAdminSectionAccess,
  type AdminSectionAccessResolver,
  type DefaultAdminPathResolver,
} from '@/src/platform/admin/admin-permissions';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  EMPTY_FEATURE_GUIDE_TOOL_IDS,
  type FeatureGuideToolIds,
} from './ai-feature-guides';
import { AdminGate } from './gates';
import {
  HelpAiGuidePage,
  HelpCenterPage,
  HelpPmsGuidePage,
} from './HelpCenterPage';
import type { StaticRouteDefinition } from './navigation-types';
import { AdminLandingRedirect } from './redirects';

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
}): string | undefined {
  return route.appId;
}

export function isGlobalAppGateEnabled(
  appId: string | undefined,
  enabledAppIds: readonly string[],
): boolean {
  return (
    !appId ||
    appId === 'home' ||
    appId === 'settings' ||
    enabledAppIds.includes(appId)
  );
}

export type GlobalAppGateState = 'allowed' | 'denied' | 'error' | 'loading';

export function resolveGlobalAppGateState({
  appId,
  bootstrapError,
  bootstrapLoading,
  enabledAppIds,
}: {
  appId: string | undefined;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  enabledAppIds: readonly string[] | null;
}): GlobalAppGateState {
  if (!appId || appId === 'home' || appId === 'settings') {
    return 'allowed';
  }
  if (bootstrapError) {
    return 'error';
  }
  if (bootstrapLoading || enabledAppIds === null) {
    return 'loading';
  }
  return isGlobalAppGateEnabled(appId, enabledAppIds) ? 'allowed' : 'denied';
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
  enabledAppIds,
}: {
  appId: string | undefined;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
  children: ReactNode;
  enabledAppIds: readonly string[] | null;
}) {
  const { t } = useTranslation('shell');
  const state = resolveGlobalAppGateState({
    appId,
    bootstrapError,
    bootstrapLoading,
    enabledAppIds,
  });
  if (state === 'allowed') {
    return children;
  }
  if (state === 'error') {
    return <AccessDeniedView description={bootstrapError ?? undefined} />;
  }
  if (state === 'loading') {
    return (
      <div className="p-8 text-app-ink/55">{t('appBootstrap.loading')}</div>
    );
  }
  return <AccessDeniedView description={t('gates.appDisabled')} />;
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
  enabledAppIds,
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
  enabledAppIds: readonly string[] | null;
}) {
  const resolvedHelpRoutes =
    helpRoutes ?? createDefaultHelpRoutes(featureGuideToolIds);

  return (
    <>
      {appGlobalRoutes.map((route) => {
        const appId = resolveGlobalRouteGateAppId(route);
        return (
          <Route
            key={route.path}
            path={route.path}
            element={
              <GlobalAppGate
                appId={appId}
                bootstrapError={bootstrapError}
                bootstrapLoading={bootstrapLoading}
                enabledAppIds={enabledAppIds}
              >
                {route.element}
              </GlobalAppGate>
            }
          />
        );
      })}

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
