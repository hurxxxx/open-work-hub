import { matchAppRoute } from '@open-work-hub/contracts/app-routes';
import {
  getShellPathname,
  resolveGlobalRouteAppId,
  resolveManifestNavItemId,
} from './app-shell-navigation-model';
import {
  NAV_ITEMS,
  SHELL_MODULE_MANIFESTS,
  getAppModuleManifest,
  getAppShellNavResolver,
} from './app/shell/app-registry';
import type { AppModuleId } from './app/shell/navigation-types';
import { canAccessApp } from './platform/apps/app-access';
import { hasAdminConsoleAccess, type AuthUser } from './platform/auth/auth-api';

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

export function resolveShellState(
  path: string,
  user: AuthUser | null | undefined,
  enabledAppIds?: readonly string[],
): ShellState {
  const pathname = getShellPathname(path);
  if (pathname === '/') return LAUNCHER_SHELL_STATE;
  const matched = matchAppRoute(pathname);
  const appId =
    matched?.appId ??
    resolveGlobalRouteAppId({ manifests: SHELL_MODULE_MANIFESTS, pathname });
  if (!appId) return HOME_SHELL_STATE;
  const admitted =
    appId === 'settings'
      ? hasAdminConsoleAccess(user)
      : canAccessApp({ appId, enabledAppIds, user });
  if (!admitted) return LAUNCHER_SHELL_STATE;
  return {
    activeAppId: appId,
    activeNavItemId: resolveAppNavItemId({ appId, path, pathname }),
  };
}
