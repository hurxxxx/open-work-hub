import { routePathMatchesPathname } from '@/src/app-shell-navigation-model';
import {
  getAppIdFromPath,
  type ShellAppId,
} from '@/src/platform/apps/app-links';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import type {
  ShellRouteChrome,
  ShellRouteSubSidebar,
} from './navigation-types';

export type ShellActiveState = {
  activeAppId: string;
  activeNavItemId: string;
};

export type ShellStateResolver = (
  path: string,
  user: AuthUser | null | undefined,
  enabledShellAppIds?: readonly string[],
) => ShellActiveState;

type ShellChromeRouteDefinition = {
  appId?: string;
  chrome?: ShellRouteChrome;
  path: string;
  subSidebar?: ShellRouteSubSidebar;
};

export interface ShellChromeState {
  activeAppId: string;
  activeNavItemId: string;
  canOpenMobileAppMenu: boolean;
  mainClassName: string;
  routeShellAppId: ShellAppId | null;
  showSubSidebar: boolean;
}

export interface ResolveShellChromeStateInput {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  enabledShellAppIds?: readonly string[] | null;
  pathname: string;
  resolveShellStateForPath?: ShellStateResolver;
  search: string;
  user: AuthUser | null;
  appRoutes?: readonly ShellChromeRouteDefinition[];
}

const SHELL_MAIN_HIDDEN_CHROME_CLASS_NAME = 'flex-1 overflow-hidden relative';
const SHELL_MAIN_SCROLLING_CLASS_NAME = 'flex-1 overflow-y-auto relative';

const SHELL_OWNED_ROUTE_OPTIONS: Array<{
  chrome?: ShellRouteChrome;
  path: string;
  subSidebar?: ShellRouteSubSidebar;
}> = [
  { path: '/', subSidebar: 'hidden' },
  { path: '/help', subSidebar: 'hidden' },
  { path: '/help/pms', subSidebar: 'hidden' },
];

const DEFAULT_SHELL_ACTIVE_STATE: ShellActiveState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

const resolveDefaultShellStateForPath: ShellStateResolver = () =>
  DEFAULT_SHELL_ACTIVE_STATE;

function findShellRoute({
  appGlobalRoutes = [],
  pathname,
  appRoutes = [],
}: {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  pathname: string;
  appRoutes?: readonly ShellChromeRouteDefinition[];
}) {
  const matchedRoute = [
    ...SHELL_OWNED_ROUTE_OPTIONS,
    ...appRoutes,
    ...appGlobalRoutes,
  ].find((route) => routePathMatchesPathname(route.path, pathname));
  return matchedRoute ?? null;
}

function routeOwnsShellMainScroll({
  appGlobalRoutes,
  pathname,
  appRoutes,
}: {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  pathname: string;
  appRoutes?: readonly ShellChromeRouteDefinition[];
}): boolean {
  const chrome = findShellRoute({
    appGlobalRoutes,
    pathname,
    appRoutes,
  })?.chrome;
  return (
    chrome === 'fullSurface' ||
    chrome === 'containedSurface' ||
    chrome === 'shared'
  );
}

function shouldShowSubSidebar({
  appGlobalRoutes,
  pathname,
  appRoutes,
}: {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  pathname: string;
  appRoutes?: readonly ShellChromeRouteDefinition[];
}): boolean {
  const matchedRoute = findShellRoute({
    appGlobalRoutes,
    pathname,
    appRoutes,
  });
  return (
    matchedRoute?.chrome !== 'fullSurface' &&
    matchedRoute?.chrome !== 'shared' &&
    matchedRoute?.subSidebar !== 'hidden'
  );
}

export function resolveShellChromeState({
  appGlobalRoutes,
  enabledShellAppIds,
  pathname,
  resolveShellStateForPath = resolveDefaultShellStateForPath,
  search,
  user,
  appRoutes,
}: ResolveShellChromeStateInput): ShellChromeState {
  const routeShellAppId = getAppIdFromPath(pathname);
  const shellState = resolveShellStateForPath(
    `${pathname}${search}`,
    user,
    enabledShellAppIds ?? undefined,
  );
  const showSubSidebar =
    shellState.activeAppId !== 'launcher' &&
    shouldShowSubSidebar({
      appGlobalRoutes,
      pathname,
      appRoutes,
    });
  const ownsShellMainScroll = routeOwnsShellMainScroll({
    appGlobalRoutes,
    pathname,
    appRoutes,
  });
  return {
    ...shellState,
    canOpenMobileAppMenu:
      showSubSidebar && shellState.activeAppId !== 'profile',
    mainClassName: ownsShellMainScroll
      ? SHELL_MAIN_HIDDEN_CHROME_CLASS_NAME
      : SHELL_MAIN_SCROLLING_CLASS_NAME,
    routeShellAppId,
    showSubSidebar,
  };
}
