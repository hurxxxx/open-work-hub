import {
  APP_GLOBAL_ROUTES,
  APP_MODULE_MANIFESTS,
  NAV_ITEMS,
  SHELL_MODULE_MANIFESTS,
  getAppShellNavResolver,
  getAppModuleManifest,
} from './app/shell/app-registry';
import type { AppModuleId } from './app/shell/navigation-types';
import { hasAdminConsoleAccess, type AuthUser } from './platform/auth/auth-api';
import { canAccessWorkspaceApp } from './platform/workspaces/workspace-app-access';
import { getWorkspaceSlugFromPath } from './platform/workspaces/workspace-utils';
import {
  getShellPathname,
  routePathMatchesPathname,
  resolveGlobalRouteAppId,
  resolveManifestNavItemId,
  resolveWorkspaceRouteAppId,
} from './app-shell-navigation-model';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';

export type ShellAppId = AppModuleId | 'launcher' | 'profile';

export type ShellState = {
  activeAppId: ShellAppId;
  activeNavItemId: string;
};

const HOME_SHELL_STATE: ShellState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

const LAUNCHER_SHELL_STATE: ShellState = {
  activeAppId: 'launcher',
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
  enabledWorkspaceAppIds,
  user,
}: {
  appId: AppModuleId;
  enabledWorkspaceAppIds?: readonly string[];
  user: AuthUser | null | undefined;
}): boolean {
  if (appId === 'settings') {
    return hasAdminConsoleAccess(user);
  }

  return Boolean(user && enabledWorkspaceAppIds?.includes(appId));
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
  if (!canShowAppChrome(user, appId, workspaceSlug, enabledWorkspaceAppIds)) {
    return HOME_SHELL_STATE;
  }
  return {
    activeAppId: appId,
    activeNavItemId: resolveAppNavItemId({ appId, path, pathname }),
  };
}

function resolveGlobalRouteShellState({
  appId,
  enabledWorkspaceAppIds,
  path,
  pathname,
  user,
}: {
  appId: AppModuleId;
  enabledWorkspaceAppIds?: readonly string[];
  path: string;
  pathname: string;
  user: AuthUser | null | undefined;
}): ShellState {
  if (
    !canShowGlobalAppChrome({
      appId,
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
    return LAUNCHER_SHELL_STATE;
  }

  const appEntryMatch = /^\/apps\/([^/]+)$/.exec(pathname);
  const appEntryContract = appEntryMatch
    ? APP_CONTRACT_BY_ID.get((appEntryMatch[1] ?? '') as AppId)
    : null;
  if (appEntryContract?.availability_scope === 'workspace') {
    const appId = appEntryContract.app_id;
    if (
      getAppModuleManifest(appId) &&
      canShowGlobalAppChrome({ appId, enabledWorkspaceAppIds, user })
    ) {
      return { activeAppId: appId, activeNavItemId: '' };
    }
    return LAUNCHER_SHELL_STATE;
  }

  if (/^\/apps\/home\/workspaces\/[^/]+(?:\/|$)/.test(pathname)) {
    return HOME_SHELL_STATE;
  }

  const registeredGlobalRoute = APP_GLOBAL_ROUTES.find((route) =>
    routePathMatchesPathname(route.path, pathname),
  );
  const globalRouteAppId =
    registeredGlobalRoute?.appId ??
    resolveGlobalRouteAppId({
      manifests: [...APP_MODULE_MANIFESTS, ...SHELL_MODULE_MANIFESTS],
      pathname,
    });
  if (globalRouteAppId) {
    return resolveGlobalRouteShellState({
      appId: globalRouteAppId,
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

  return HOME_SHELL_STATE;
}
