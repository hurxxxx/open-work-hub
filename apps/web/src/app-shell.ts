import {
  APP_GLOBAL_ROUTES,
  APP_MODULE_MANIFESTS,
  NAV_ITEMS,
  getAppShellNavResolver,
  getAppModuleManifest,
  getNavItem,
  getToolViewRoute,
} from './app/shell/app-registry';
import type { AppModuleId } from './app/shell/navigation-types';
import { hasAdminConsoleAccess, type AuthUser } from './platform/auth/auth-api';
import { canAccessWorkspaceApp } from './platform/workspaces/workspace-app-access';
import {
  getWorkspaceAppIdFromPath,
  getWorkspaceSlugFromPath,
} from './platform/workspaces/workspace-utils';
import {
  getShellPathname,
  routePathMatchesPathname,
  resolveGlobalRouteAppId,
  resolveManifestNavItemId,
  resolveWorkspaceRouteAppId,
} from './app-shell-navigation-model';

export type ShellAppId = AppModuleId | 'search' | 'profile';

export type ShellState = {
  activeAppId: ShellAppId;
  activeNavItemId: string;
};

const HOME_SHELL_STATE: ShellState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

function canShowAppChrome(
  user: AuthUser | null | undefined,
  appId: AppModuleId,
  workspaceSlug?: string | null,
  enabledWorkspaceAppIds?: readonly string[],
): boolean {
  if (appId === 'settings') {
    return hasAdminConsoleAccess(user);
  }
  return canAccessWorkspaceApp({
    appId,
    enabledWorkspaceAppIds,
    user,
    workspaceSlug,
  });
}

function canShowGlobalAppChrome({
  appId,
  bootstrapAppId,
  enabledWorkspaceAppIds,
  user,
}: {
  appId: AppModuleId;
  bootstrapAppId?: AppModuleId;
  enabledWorkspaceAppIds?: readonly string[];
  user: AuthUser | null | undefined;
}): boolean {
  if (appId === 'settings') {
    return hasAdminConsoleAccess(user);
  }

  const gateAppId = bootstrapAppId ?? appId;
  return Boolean(user && enabledWorkspaceAppIds?.includes(gateAppId));
}

function resolveAppNavItemId({
  appId,
  path,
  pathname,
}: {
  appId: AppModuleId;
  path: string;
  pathname: string;
}): string {
  const manifest = getAppModuleManifest(appId);
  if (!manifest) {
    return '';
  }
  const shellNavResolver = getAppShellNavResolver(appId);
  const resolvedNavItemId = shellNavResolver?.({
    appId,
    manifest,
    navItems: NAV_ITEMS,
    path,
    pathname,
  });
  if (typeof resolvedNavItemId === 'string') {
    return resolvedNavItemId;
  }
  return resolveManifestNavItemId({
    appId,
    fallbackNavItemId: manifest.defaultActiveNavItemId,
    navItems: NAV_ITEMS,
    path,
  });
}

function resolveWorkspaceAppShellState({
  appId,
  enabledWorkspaceAppIds,
  path,
  pathname,
  user,
  workspaceSlug,
}: {
  appId: AppModuleId;
  enabledWorkspaceAppIds?: readonly string[];
  path: string;
  pathname: string;
  user: AuthUser | null | undefined;
  workspaceSlug: string | null;
}): ShellState {
  if (appId === 'home' || appId === 'settings') {
    return HOME_SHELL_STATE;
  }
  const bootstrapAppId = getWorkspaceAppIdFromPath(pathname) ?? appId;
  if (
    !canShowAppChrome(
      user,
      bootstrapAppId,
      workspaceSlug,
      enabledWorkspaceAppIds,
    )
  ) {
    return HOME_SHELL_STATE;
  }
  return {
    activeAppId: appId,
    activeNavItemId: resolveAppNavItemId({ appId, path, pathname }),
  };
}

function resolveGlobalRouteShellState({
  appId,
  bootstrapAppId,
  enabledWorkspaceAppIds,
  path,
  pathname,
  user,
}: {
  appId: AppModuleId;
  bootstrapAppId?: AppModuleId;
  enabledWorkspaceAppIds?: readonly string[];
  path: string;
  pathname: string;
  user: AuthUser | null | undefined;
}): ShellState {
  if (
    !canShowGlobalAppChrome({
      appId,
      bootstrapAppId,
      enabledWorkspaceAppIds,
      user,
    })
  ) {
    return HOME_SHELL_STATE;
  }
  return {
    activeAppId: appId,
    activeNavItemId: resolveAppNavItemId({ appId, path, pathname }),
  };
}

export function resolveShellState(
  path: string,
  user: AuthUser | null | undefined,
  enabledWorkspaceAppIds?: readonly string[],
): ShellState {
  const pathname = getShellPathname(path);
  const workspaceSlug = getWorkspaceSlugFromPath(pathname);

  if (pathname === '/') {
    return HOME_SHELL_STATE;
  }

  if (/^\/w\/[^/]+\/home(?:\/|$)/.test(pathname)) {
    return HOME_SHELL_STATE;
  }

  const registeredGlobalRoute = APP_GLOBAL_ROUTES.find((route) =>
    routePathMatchesPathname(route.path, pathname),
  );
  const globalRouteAppId =
    registeredGlobalRoute?.appId ??
    resolveGlobalRouteAppId({
      manifests: APP_MODULE_MANIFESTS,
      pathname,
    });
  if (globalRouteAppId) {
    return resolveGlobalRouteShellState({
      appId: globalRouteAppId,
      bootstrapAppId: registeredGlobalRoute?.bootstrapAppId,
      enabledWorkspaceAppIds,
      path,
      pathname,
      user,
    });
  }

  const workspaceRouteAppId = resolveWorkspaceRouteAppId({
    manifests: APP_MODULE_MANIFESTS,
    pathname,
  });
  if (workspaceRouteAppId) {
    return resolveWorkspaceAppShellState({
      appId: workspaceRouteAppId,
      enabledWorkspaceAppIds,
      path,
      pathname,
      user,
      workspaceSlug,
    });
  }

  if (!pathname.startsWith('/tool/')) {
    return HOME_SHELL_STATE;
  }

  const toolId = pathname.split('/')[2] ?? '';
  if (toolId === 'search') {
    return {
      activeAppId: 'search',
      activeNavItemId: 'search',
    };
  }

  const item = getNavItem(toolId);
  const matchedToolRoute = getToolViewRoute({ item, toolId });
  if (matchedToolRoute) {
    if (
      !canShowAppChrome(
        user,
        matchedToolRoute.bootstrapAppId ?? matchedToolRoute.appId,
        undefined,
        enabledWorkspaceAppIds,
      )
    ) {
      return HOME_SHELL_STATE;
    }
    return {
      activeAppId: matchedToolRoute.appId,
      activeNavItemId:
        matchedToolRoute.type === 'redirect_app_root'
          ? ''
          : (item?.id ?? toolId),
    };
  }

  if (!item) {
    return HOME_SHELL_STATE;
  }

  if (
    item.appId !== 'home' &&
    !canShowAppChrome(
      user,
      item.linkAppId ?? item.appId,
      undefined,
      enabledWorkspaceAppIds,
    )
  ) {
    return HOME_SHELL_STATE;
  }

  return {
    activeAppId: item.appId,
    activeNavItemId: item.id,
  };
}
