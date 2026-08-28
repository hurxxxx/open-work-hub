import { routePathMatchesPathname } from '@/src/app-shell-navigation-model';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  getWorkspaceAppIdFromPath,
  getWorkspaceSlugFromPath,
  resolveRouteWorkspaceSlug,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';
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
  enabledWorkspaceAppIds?: readonly string[],
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
  bootstrapWorkspaceSlug: string | null;
  canOpenMobileAppMenu: boolean;
  mainClassName: string;
  routeWorkspaceAppId: WorkspaceAppId | null;
  routeWorkspaceSlug: string | null;
  showSubSidebar: boolean;
}

export interface ResolveShellChromeStateInput {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  enabledWorkspaceAppIds?: readonly string[] | null;
  pathname: string;
  resolveShellStateForPath?: ShellStateResolver;
  search: string;
  user: AuthUser | null;
  workspaceRoutes?: readonly ShellChromeRouteDefinition[];
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
  workspaceRoutes = [],
}: {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  pathname: string;
  workspaceRoutes?: readonly ShellChromeRouteDefinition[];
}) {
  const matchedRoute = [
    ...SHELL_OWNED_ROUTE_OPTIONS,
    ...workspaceRoutes,
    ...appGlobalRoutes,
  ].find((route) => routePathMatchesPathname(route.path, pathname));
  return matchedRoute ?? null;
}

function routeOwnsShellMainScroll({
  appGlobalRoutes,
  pathname,
  workspaceRoutes,
}: {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  pathname: string;
  workspaceRoutes?: readonly ShellChromeRouteDefinition[];
}): boolean {
  const chrome = findShellRoute({
    appGlobalRoutes,
    pathname,
    workspaceRoutes,
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
  workspaceRoutes,
}: {
  appGlobalRoutes?: readonly ShellChromeRouteDefinition[];
  pathname: string;
  workspaceRoutes?: readonly ShellChromeRouteDefinition[];
}): boolean {
  const matchedRoute = findShellRoute({
    appGlobalRoutes,
    pathname,
    workspaceRoutes,
  });
  return (
    matchedRoute?.chrome !== 'fullSurface' &&
    matchedRoute?.chrome !== 'shared' &&
    matchedRoute?.subSidebar !== 'hidden'
  );
}

export function resolveShellChromeState({
  appGlobalRoutes,
  enabledWorkspaceAppIds,
  pathname,
  resolveShellStateForPath = resolveDefaultShellStateForPath,
  search,
  user,
  workspaceRoutes,
}: ResolveShellChromeStateInput): ShellChromeState {
  const routeWorkspaceSlug = getWorkspaceSlugFromPath(pathname);
  const routeWorkspaceAppId = getWorkspaceAppIdFromPath(pathname);
  const bootstrapWorkspaceSlug = resolveRouteWorkspaceSlug(user, pathname);
  const shellState = resolveShellStateForPath(
    `${pathname}${search}`,
    user,
    enabledWorkspaceAppIds ?? undefined,
  );
  const showSubSidebar = shouldShowSubSidebar({
    appGlobalRoutes,
    pathname,
    workspaceRoutes,
  });
  const ownsShellMainScroll = routeOwnsShellMainScroll({
    appGlobalRoutes,
    pathname,
    workspaceRoutes,
  });
  return {
    ...shellState,
    bootstrapWorkspaceSlug,
    canOpenMobileAppMenu:
      showSubSidebar && shellState.activeAppId !== 'profile',
    mainClassName: ownsShellMainScroll
      ? SHELL_MAIN_HIDDEN_CHROME_CLASS_NAME
      : SHELL_MAIN_SCROLLING_CLASS_NAME,
    routeWorkspaceAppId,
    routeWorkspaceSlug,
    showSubSidebar,
  };
}
