import {
  hasAdminConsoleAccess,
  type AuthUser,
} from '@/src/platform/auth/auth-api';
import { getDefaultAdminPath } from '@/src/platform/admin/admin-permissions';
import type {
  LauncherGlobalPaths,
  NavItem,
  WorkspaceShellAppId,
} from '@/src/app/shell/navigation-types';
import { EMPTY_LAUNCHER_GLOBAL_PATHS } from '@/src/app/shell/navigation-types';
import { rewriteWorkspaceApiPathForWorkspace } from '@/src/platform/api/workspace-api-path-policy';

export type WorkspaceAppId = WorkspaceShellAppId;

const LAST_WORKSPACE_STORAGE_KEY = 'open-alm:last-workspace-slug';
const LAST_WORKSPACE_APP_STORAGE_KEY = 'open-alm:last-workspace-app';
const WORKSPACE_APP_PATH_PATTERN = /^\/w\/[^/]+\/([^/]+)(?:\/|$)/;
const WORKSPACE_APP_ID_MAX_LENGTH = 128;
const WORKSPACE_APP_ID_SEGMENT_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

type WorkspaceSelectionUser = Pick<AuthUser, 'workspaces'> &
  Partial<Pick<AuthUser, 'default_workspace_id'>>;

function isWorkspaceAppId(
  value: string | null | undefined,
): value is WorkspaceAppId {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value.length <= WORKSPACE_APP_ID_MAX_LENGTH &&
    WORKSPACE_APP_ID_SEGMENT_PATTERN.test(value)
  );
}

function normalizeWorkspaceAppId(
  value: string | null | undefined,
): WorkspaceAppId | null {
  if (!value) {
    return null;
  }
  return isWorkspaceAppId(value) ? value : null;
}

export function getWorkspaceSlugFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/w\/([^/]+)(?:\/|$)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function getWorkspaceAppIdFromPath(
  pathname: string,
): WorkspaceAppId | null {
  const match = pathname.match(WORKSPACE_APP_PATH_PATTERN);
  return normalizeWorkspaceAppId(match?.[1]);
}

function getCurrentWorkspaceSlug(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return getWorkspaceSlugFromPath(window.location.pathname);
}

export function getCurrentOrLastWorkspaceSlug(): string | null {
  return getCurrentWorkspaceSlug() ?? readLastWorkspaceSlug();
}

function readLastWorkspaceSlug(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage.getItem(LAST_WORKSPACE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function readLastWorkspaceAppId(): WorkspaceAppId | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(LAST_WORKSPACE_APP_STORAGE_KEY);
    return normalizeWorkspaceAppId(stored);
  } catch {
    return null;
  }
}

export function persistLastWorkspaceSlug(
  workspaceSlug: string | null | undefined,
): void {
  if (!workspaceSlug || typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(LAST_WORKSPACE_STORAGE_KEY, workspaceSlug);
  } catch {
    return;
  }
}

export function persistLastWorkspaceAppId(
  appId: WorkspaceAppId | null | undefined,
): void {
  if (!isWorkspaceAppId(appId) || typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(LAST_WORKSPACE_APP_STORAGE_KEY, appId);
  } catch {
    return;
  }
}

export function clearStoredWorkspaceSelection(): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.removeItem(LAST_WORKSPACE_STORAGE_KEY);
    window.localStorage.removeItem(LAST_WORKSPACE_APP_STORAGE_KEY);
  } catch {
    return;
  }
}

export function getWorkspaceBySlug(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  workspaceSlug: string | null | undefined,
) {
  if (!workspaceSlug) {
    return null;
  }
  return (
    user?.workspaces?.find((workspace) => workspace.slug === workspaceSlug) ??
    null
  );
}

function getDefaultWorkspace(user: WorkspaceSelectionUser | null | undefined) {
  const defaultWorkspaceId = user?.default_workspace_id;
  if (!defaultWorkspaceId) {
    return null;
  }
  return (
    user?.workspaces?.find(
      (workspace) => workspace.id === defaultWorkspaceId,
    ) ?? null
  );
}

function getFirstWorkspaceForApp(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  appId: WorkspaceAppId,
) {
  void appId;
  return user?.workspaces?.[0] ?? null;
}

export function getPreferredWorkspace(
  user: WorkspaceSelectionUser | null | undefined,
  appId?: WorkspaceAppId,
) {
  const defaultWorkspace = getDefaultWorkspace(user);
  if (defaultWorkspace) {
    return defaultWorkspace;
  }

  const lastWorkspace = getWorkspaceBySlug(user, readLastWorkspaceSlug());
  if (lastWorkspace) {
    return lastWorkspace;
  }
  if (appId) {
    return getFirstWorkspaceForApp(user, appId);
  }
  return user?.workspaces?.[0] ?? null;
}

export function resolveShellWorkspaceSlug(
  user: WorkspaceSelectionUser | null | undefined,
  routeWorkspaceSlug: string | null | undefined,
): string | null {
  const routeWorkspace = getWorkspaceBySlug(user, routeWorkspaceSlug);
  if (routeWorkspace) {
    return routeWorkspace.slug;
  }

  const defaultWorkspace = getDefaultWorkspace(user);
  if (defaultWorkspace) {
    return defaultWorkspace.slug;
  }

  const lastWorkspace = getWorkspaceBySlug(user, readLastWorkspaceSlug());
  if (lastWorkspace) {
    return lastWorkspace.slug;
  }

  return user?.workspaces?.[0]?.slug ?? null;
}

export function buildWorkspaceAppPath(
  workspaceSlug: string,
  appId: WorkspaceAppId,
  suffix = '',
): string {
  if (!isWorkspaceAppId(appId)) {
    throw new Error(`Invalid workspace app id: ${appId}`);
  }
  const routeBase = `/${appId}`;
  const normalizedSuffix = normalizeWorkspaceAppPathSuffix(suffix, routeBase);
  return `/w/${encodeURIComponent(workspaceSlug)}${routeBase}${normalizedSuffix}`;
}

function normalizeAppPathSuffix(suffix: string): string {
  return suffix
    ? suffix.startsWith('/') || suffix.startsWith('?') || suffix.startsWith('#')
      ? suffix
      : `/${suffix}`
    : '';
}

function normalizeWorkspaceAppPathSuffix(
  suffix: string,
  routeBase: string,
): string {
  const normalizedSuffix = normalizeAppPathSuffix(suffix);
  if (!normalizedSuffix.startsWith('/')) {
    return normalizedSuffix;
  }

  const normalizedRouteBase = routeBase.replace(/\/+$/, '');
  if (normalizedSuffix === normalizedRouteBase) {
    return '';
  }
  if (
    normalizedSuffix.startsWith(`${normalizedRouteBase}/`) ||
    normalizedSuffix.startsWith(`${normalizedRouteBase}?`) ||
    normalizedSuffix.startsWith(`${normalizedRouteBase}#`)
  ) {
    return normalizedSuffix.slice(normalizedRouteBase.length);
  }
  return normalizedSuffix;
}

export function resolveDefaultWorkspaceAppPath(
  user: WorkspaceSelectionUser | null | undefined,
  appId: WorkspaceAppId,
  suffix = '',
): string {
  const workspace = getPreferredWorkspace(user, appId);
  return workspace ? buildWorkspaceAppPath(workspace.slug, appId, suffix) : '/';
}

export function resolveRootEntryPath(
  user:
    | (WorkspaceSelectionUser & Pick<AuthUser, 'system_roles'>)
    | null
    | undefined,
  defaultWorkspaceAppId: WorkspaceAppId = 'home',
): string | null {
  const workspaceSlug = resolveShellWorkspaceSlug(user, null);
  if (workspaceSlug) {
    return buildWorkspaceAppPath(workspaceSlug, defaultWorkspaceAppId);
  }
  if (hasAdminConsoleAccess(user)) {
    return getDefaultAdminPath(user?.system_roles ?? []);
  }
  return user ? '/community' : null;
}

export function resolveWorkspaceSwitchPath(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  pathname: string,
  nextWorkspaceSlug: string,
  enabledWorkspaceAppIds: readonly string[],
): string {
  const nextWorkspace = getWorkspaceBySlug(user, nextWorkspaceSlug);
  if (!nextWorkspace) {
    return '/';
  }

  const enabledAppIds = new Set(enabledWorkspaceAppIds);
  const currentAppId = getWorkspaceAppIdFromPath(pathname);
  if (currentAppId && enabledAppIds.has(currentAppId)) {
    return buildWorkspaceAppPath(nextWorkspace.slug, currentAppId);
  }

  const lastWorkspaceAppId = readLastWorkspaceAppId();
  if (lastWorkspaceAppId && enabledAppIds.has(lastWorkspaceAppId)) {
    return buildWorkspaceAppPath(nextWorkspace.slug, lastWorkspaceAppId);
  }

  return '/';
}

export function getRequestedToolWorkspaceSlugFromSearch(
  pathname: string,
  search: string,
): string | null {
  if (!pathname.startsWith('/tool/')) {
    return null;
  }
  const requestedWorkspaceSlug = new URLSearchParams(search)
    .get('workspace')
    ?.trim();
  return requestedWorkspaceSlug || null;
}

export function getToolWorkspaceSlugFromSearch(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  pathname: string,
  search: string,
): string | null {
  const requestedWorkspaceSlug = getRequestedToolWorkspaceSlugFromSearch(
    pathname,
    search,
  );
  if (!requestedWorkspaceSlug) {
    return null;
  }
  if (!user) {
    return requestedWorkspaceSlug;
  }
  return getWorkspaceBySlug(user, requestedWorkspaceSlug)?.slug ?? null;
}

export function resolveBootstrapWorkspaceSlug(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  pathname: string,
  search: string,
  shellWorkspaceSlug: string | null | undefined,
): string | null {
  const routeWorkspaceSlug = getWorkspaceSlugFromPath(pathname);
  if (routeWorkspaceSlug) {
    return getWorkspaceBySlug(user, routeWorkspaceSlug)?.slug ?? null;
  }

  const requestedToolWorkspaceSlug = getRequestedToolWorkspaceSlugFromSearch(
    pathname,
    search,
  );
  if (requestedToolWorkspaceSlug) {
    return getToolWorkspaceSlugFromSearch(user, pathname, search);
  }

  const currentShellWorkspaceSlug =
    getWorkspaceBySlug(user, shellWorkspaceSlug)?.slug ?? null;
  return (
    currentShellWorkspaceSlug ??
    (pathname.startsWith('/tool/')
      ? resolveShellWorkspaceSlug(user, null)
      : null)
  );
}

/**
 * Resolve the href for invoking a specific tool (e.g. from a shortcut list or
 * slash command palette). Unlike `resolveNavItemHref`, a plain in-app item
 * (appId === currentApp, no linkAppId) routes to its dedicated /tool/:id page
 * rather than the app's generic landing, so selecting "search" from the AI
 * chat slash menu opens the search tool instead of no-op-ing on a category shell.
 *
 * Precedence:
 *   1. `absolutePath` — admin/static routes win outright.
 *   2. `linkAppId` that differs from `appId` — deep-link to another app,
 *      using its global launcher path or workspace path with pathSuffix.
 *   3. Otherwise — `/tool/:id` (the tool's working UI).
 */
export function resolveToolInvocationHref(
  item: NavItem,
  currentWorkspaceSlug: string | null | undefined,
  user: Parameters<typeof resolveDefaultWorkspaceAppPath>[0],
  launcherGlobalPaths: LauncherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
): string {
  if (item.absolutePath) {
    return item.absolutePath;
  }
  if (item.linkAppId && item.linkAppId !== item.appId) {
    const suffix = item.pathSuffix ?? '';
    const globalPath = launcherGlobalPaths.get(item.linkAppId);
    if (globalPath) {
      return `${globalPath}${suffix}`;
    }
    if (!isWorkspaceAppId(item.linkAppId)) {
      return `/tool/${item.id}`;
    }
    return currentWorkspaceSlug
      ? buildWorkspaceAppPath(currentWorkspaceSlug, item.linkAppId, suffix)
      : resolveDefaultWorkspaceAppPath(user, item.linkAppId, suffix);
  }
  if (item.workspaceScopedTool) {
    const workspaceSlug =
      currentWorkspaceSlug ?? resolveShellWorkspaceSlug(user, null);
    const toolPath = `/tool/${item.id}`;
    if (!workspaceSlug) {
      return toolPath;
    }
    return `${toolPath}?workspace=${encodeURIComponent(workspaceSlug)}`;
  }
  return `/tool/${item.id}`;
}

/**
 * Resolve the routing destination for a sidebar-style NavItem.
 * Respects `absolutePath` (admin routes), `linkAppId`, and `pathSuffix`
 * (tab/query targets like ?tab=recordings). Used by the left sub-sidebar and the slash
 * command palette so both routing paths stay in sync.
 */
export function resolveNavItemHref(
  item: NavItem,
  currentWorkspaceSlug: string | null | undefined,
  user: Parameters<typeof resolveDefaultWorkspaceAppPath>[0],
  launcherGlobalPaths: LauncherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
): string {
  if (item.absolutePath) {
    return item.absolutePath;
  }
  if (item.comingSoon) {
    return `/tool/${item.id}`;
  }
  if (item.workspaceScopedTool) {
    return resolveToolInvocationHref(
      item,
      currentWorkspaceSlug,
      user,
      launcherGlobalPaths,
    );
  }
  const targetApp = item.linkAppId ?? item.appId;
  const globalPath = launcherGlobalPaths.get(targetApp);
  if (globalPath) {
    return `${globalPath}${item.pathSuffix ?? ''}`;
  }
  if (!isWorkspaceAppId(targetApp)) {
    return `/tool/${item.id}`;
  }
  const suffix = item.pathSuffix ?? '';
  return currentWorkspaceSlug
    ? buildWorkspaceAppPath(currentWorkspaceSlug, targetApp, suffix)
    : resolveDefaultWorkspaceAppPath(user, targetApp, suffix);
}

export function rewriteWorkspaceApiPath(
  rawPath: string,
  workspaceSlug?: string | null,
): string {
  const resolvedWorkspaceSlug =
    workspaceSlug ??
    (typeof window !== 'undefined'
      ? getToolWorkspaceSlugFromSearch(
          null,
          window.location.pathname,
          window.location.search,
        )
      : null) ??
    getCurrentOrLastWorkspaceSlug();
  return rewriteWorkspaceApiPathForWorkspace(rawPath, resolvedWorkspaceSlug);
}
