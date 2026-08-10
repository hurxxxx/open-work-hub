import { routePathMatchesPathname } from '@/src/app-shell-navigation-model';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  getWorkspaceAppIdFromPath,
  getWorkspaceSlugFromPath,
  resolveBootstrapWorkspaceSlug,
  resolveShellWorkspaceSlug,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';
import type {
  ShellRouteChrome,
  ShellRouteSubSidebar,
} from './navigation-types';

export type ShellWorkspaceSelectionState = {
  key: string;
  slug: string | null;
};

export interface ShellRouteStorageSelection {
  appId: WorkspaceAppId;
  workspaceSlug: string;
}

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
  bootstrapAppId?: string;
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
  routeStorageSelection: ShellRouteStorageSelection | null;
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
  shellWorkspaceSlug: string | null;
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
  { path: '/tool/search', subSidebar: 'hidden' },
];

const DEFAULT_SHELL_ACTIVE_STATE: ShellActiveState = {
  activeAppId: 'home',
  activeNavItemId: '',
};

const resolveDefaultShellStateForPath: ShellStateResolver = () =>
  DEFAULT_SHELL_ACTIVE_STATE;

export function buildShellWorkspaceSelectionKey(
  user: AuthUser | null,
  routeWorkspaceSlug: string | null,
): string {
  if (!user) {
    return `anonymous:${routeWorkspaceSlug ?? ''}`;
  }
  return [
    user.id,
    user.default_workspace_id ?? '',
    routeWorkspaceSlug ?? '',
    ...user.workspaces.map((workspace) => `${workspace.id}:${workspace.slug}`),
  ].join('\u0000');
}

export function resolveInitialShellWorkspaceSlug(
  user: AuthUser | null,
  routeWorkspaceSlug: string | null,
): string | null {
  if (!user || user.workspaces.length === 0) {
    return null;
  }
  return resolveShellWorkspaceSlug(user, routeWorkspaceSlug);
}

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
  const chrome = findShellRoute({ appGlobalRoutes, pathname, workspaceRoutes })
    ?.chrome;
  return chrome === 'fullSurface' || chrome === 'containedSurface';
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
    matchedRoute?.subSidebar !== 'hidden'
  );
}

function resolveRouteStorageSelection({
  enabledWorkspaceAppIds,
  matchedWorkspaceRoute,
  routeWorkspaceAppId,
  routeWorkspaceSlug,
  user,
}: Pick<ShellChromeState, 'routeWorkspaceAppId' | 'routeWorkspaceSlug'> & {
  enabledWorkspaceAppIds?: readonly string[] | null;
  matchedWorkspaceRoute: ShellChromeRouteDefinition | null;
  user: AuthUser | null;
}): ShellRouteStorageSelection | null {
  const storageAppId = matchedWorkspaceRoute?.bootstrapAppId ?? routeWorkspaceAppId;
  if (!matchedWorkspaceRoute || !routeWorkspaceSlug || !storageAppId) {
    return null;
  }
  if (
    !user?.workspaces.some((workspace) => workspace.slug === routeWorkspaceSlug)
  ) {
    return null;
  }
  if (
    enabledWorkspaceAppIds !== null &&
    enabledWorkspaceAppIds !== undefined &&
    !enabledWorkspaceAppIds.includes(storageAppId)
  ) {
    return null;
  }
  return {
    appId: storageAppId,
    workspaceSlug: routeWorkspaceSlug,
  };
}

export function resolveShellChromeState({
  appGlobalRoutes,
  enabledWorkspaceAppIds,
  pathname,
  resolveShellStateForPath = resolveDefaultShellStateForPath,
  search,
  shellWorkspaceSlug,
  user,
  workspaceRoutes,
}: ResolveShellChromeStateInput): ShellChromeState {
  const routeWorkspaceSlug = getWorkspaceSlugFromPath(pathname);
  const routeWorkspaceAppId = getWorkspaceAppIdFromPath(pathname);
  const bootstrapWorkspaceSlug = resolveBootstrapWorkspaceSlug(
    user,
    pathname,
    search,
    shellWorkspaceSlug,
  );
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
  const matchedWorkspaceRoute =
    workspaceRoutes?.find((route) =>
      routePathMatchesPathname(route.path, pathname),
    ) ?? null;

  return {
    ...shellState,
    bootstrapWorkspaceSlug,
    canOpenMobileAppMenu:
      showSubSidebar &&
      shellState.activeAppId !== 'home' &&
      shellState.activeAppId !== 'profile',
    mainClassName: ownsShellMainScroll
      ? SHELL_MAIN_HIDDEN_CHROME_CLASS_NAME
      : SHELL_MAIN_SCROLLING_CLASS_NAME,
    routeStorageSelection: resolveRouteStorageSelection({
      enabledWorkspaceAppIds,
      matchedWorkspaceRoute,
      routeWorkspaceAppId,
      routeWorkspaceSlug,
      user,
    }),
    routeWorkspaceAppId,
    routeWorkspaceSlug,
    showSubSidebar,
  };
}
