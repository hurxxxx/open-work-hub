import {
  hasAdminConsoleAccess,
  type AuthUser,
} from '@/src/platform/auth/auth-api';
import { getDefaultAdminPath } from '@/src/platform/admin/admin-permissions';
import type { NavItem } from '@/src/app/shell/navigation-types';
import { i18n } from '@/src/platform/i18n';

export type WorkspaceAppId =
  | 'home'
  | 'ai'
  | 'pms'
  | 'docs'
  | 'whiteboard'
  | 'planner'
  | 'meeting'
  | 'learning';

export const WORKSPACE_APP_IDS: readonly WorkspaceAppId[] = [
  'home',
  'ai',
  'pms',
  'docs',
  'whiteboard',
  'planner',
  'meeting',
  'learning',
] as const;

const WORKSPACE_API_PREFIXES = [
  '/api/v1/ai',
  '/api/v1/calendar',
  '/api/v1/connectors',
  '/api/v1/pms',
  '/api/v1/docs',
  '/api/v1/whiteboard',
  '/api/v1/drafts',
  '/api/v1/meeting',
  '/api/v1/planner',
  '/api/v1/rag',
  '/api/v1/search',
  '/api/v1/conversations',
  '/api/v1/wiki',
] as const;

const LAST_WORKSPACE_STORAGE_KEY = 'aidoo:last-workspace-slug';
const LAST_WORKSPACE_APP_STORAGE_KEY = 'aidoo:last-workspace-app';
const WORKSPACE_APP_PATH_PATTERN = /^\/w\/[^/]+\/(home|ai|pms|docs|whiteboard|planner|meeting|learning)(?:\/|$)/;

function isWorkspaceAppId(value: string | null | undefined): value is WorkspaceAppId {
  return (WORKSPACE_APP_IDS as readonly string[]).includes(value ?? '');
}

export function getWorkspaceSlugFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/w\/([^/]+)(?:\/|$)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function getWorkspaceAppIdFromPath(pathname: string): WorkspaceAppId | null {
  const match = pathname.match(WORKSPACE_APP_PATH_PATTERN);
  return isWorkspaceAppId(match?.[1]) ? match[1] : null;
}

export function getCurrentWorkspaceSlug(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return getWorkspaceSlugFromPath(window.location.pathname);
}

export function getCurrentOrLastWorkspaceSlug(): string | null {
  return getCurrentWorkspaceSlug() ?? readLastWorkspaceSlug();
}

export function readLastWorkspaceSlug(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage.getItem(LAST_WORKSPACE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function readLastWorkspaceAppId(): WorkspaceAppId | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(LAST_WORKSPACE_APP_STORAGE_KEY);
    return isWorkspaceAppId(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function persistLastWorkspaceSlug(workspaceSlug: string | null | undefined): void {
  if (!workspaceSlug || typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(LAST_WORKSPACE_STORAGE_KEY, workspaceSlug);
  } catch {
    return;
  }
}

export function persistLastWorkspaceAppId(appId: WorkspaceAppId | null | undefined): void {
  if (!appId || typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(LAST_WORKSPACE_APP_STORAGE_KEY, appId);
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
  return user?.workspaces?.find((workspace) => workspace.slug === workspaceSlug) ?? null;
}

export function getFirstWorkspaceForApp(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  appId: WorkspaceAppId,
) {
  void appId;
  return user?.workspaces?.[0] ?? null;
}

export function getPreferredWorkspace(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  appId?: WorkspaceAppId,
) {
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
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  routeWorkspaceSlug: string | null | undefined,
): string | null {
  const routeWorkspace = getWorkspaceBySlug(user, routeWorkspaceSlug);
  if (routeWorkspace) {
    return routeWorkspace.slug;
  }

  const lastWorkspace = getWorkspaceBySlug(user, readLastWorkspaceSlug());
  if (lastWorkspace) {
    return lastWorkspace.slug;
  }

  return user?.workspaces?.[0]?.slug ?? null;
}

export function hasWorkspaceApp(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  workspaceSlug: string | null | undefined,
  appId: WorkspaceAppId,
): boolean {
  void appId;
  return getWorkspaceBySlug(user, workspaceSlug) != null;
}

export function buildWorkspaceAppPath(
  workspaceSlug: string,
  appId: WorkspaceAppId,
  suffix = '',
): string {
  const normalizedSuffix = suffix
    ? suffix.startsWith('/') || suffix.startsWith('?') || suffix.startsWith('#')
      ? suffix
      : `/${suffix}`
    : '';
  return `/w/${encodeURIComponent(workspaceSlug)}/${appId}${normalizedSuffix}`;
}

export function resolveDefaultWorkspaceAppPath(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  appId: WorkspaceAppId,
  suffix = '',
): string {
  const workspace = getPreferredWorkspace(user, appId);
  return workspace ? buildWorkspaceAppPath(workspace.slug, appId, suffix) : '/';
}

export function resolveRootEntryPath(
  user: Pick<AuthUser, 'workspaces' | 'system_roles'> | null | undefined,
): string | null {
  const workspaceSlug = resolveShellWorkspaceSlug(user, null);
  if (workspaceSlug) {
    return buildWorkspaceAppPath(workspaceSlug, 'home');
  }
  if (hasAdminConsoleAccess(user)) {
    return getDefaultAdminPath(user?.system_roles ?? []);
  }
  return null;
}

export function resolveWorkspaceSwitchPath(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  pathname: string,
  nextWorkspaceSlug: string,
): string {
  const nextWorkspace = getWorkspaceBySlug(user, nextWorkspaceSlug);
  if (!nextWorkspace) {
    return '/';
  }

  const currentAppId = getWorkspaceAppIdFromPath(pathname);
  if (currentAppId) {
    return buildWorkspaceAppPath(nextWorkspace.slug, currentAppId);
  }

  const lastWorkspaceAppId = readLastWorkspaceAppId();
  if (lastWorkspaceAppId) {
    return buildWorkspaceAppPath(nextWorkspace.slug, lastWorkspaceAppId);
  }

  return '/';
}

export function getToolWorkspaceSlugFromSearch(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  pathname: string,
  search: string,
): string | null {
  void user;
  if (!pathname.startsWith('/tool/')) {
    return null;
  }
  const requestedWorkspaceSlug = new URLSearchParams(search).get('workspace')?.trim();
  return requestedWorkspaceSlug || null;
}

export function resolveBootstrapWorkspaceSlug(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  pathname: string,
  search: string,
  shellWorkspaceSlug: string | null | undefined,
): string | null {
  return (
    getWorkspaceSlugFromPath(pathname)
    ?? getToolWorkspaceSlugFromSearch(user, pathname, search)
    ?? shellWorkspaceSlug
    ?? (pathname.startsWith('/tool/') ? resolveShellWorkspaceSlug(user, null) : null)
  );
}

export function requireWorkspaceSlug(workspaceSlug?: string | null): string {
  const resolved = workspaceSlug ?? getCurrentOrLastWorkspaceSlug();
  if (!resolved) {
    throw new Error(i18n.t('apps:workspace.contextUnavailable'));
  }
  return resolved;
}

/**
 * Resolve the href for invoking a specific tool (e.g. from a shortcut list or
 * slash command palette). Unlike `resolveNavItemHref`, a plain in-app item
 * (appId === currentApp, no linkAppId) routes to its dedicated /tool/:id page
 * rather than the app's generic landing, so selecting "search" from the AI
 * chat slash menu opens the search tool instead of no-op-ing on /w/:slug/ai.
 *
 * Precedence:
 *   1. `absolutePath` — admin/static routes win outright.
 *   2. `linkAppId` that differs from `appId` — deep-link to another app
 *      (e.g. meeting-minutes → /w/:slug/meeting?tab=recordings), delegated
 *      to `resolveNavItemHref` so pathSuffix is honored.
 *   3. Otherwise — `/tool/:id` (the tool's working UI).
 */
export function resolveToolInvocationHref(
  item: NavItem,
  currentWorkspaceSlug: string | null | undefined,
  user: Parameters<typeof resolveDefaultWorkspaceAppPath>[0],
): string {
  if (item.absolutePath) {
    return item.absolutePath;
  }
  if (item.linkAppId && item.linkAppId !== item.appId) {
    return resolveNavItemHref(item, currentWorkspaceSlug, user);
  }
  if (item.id === 'search') {
    const workspaceSlug = currentWorkspaceSlug ?? resolveShellWorkspaceSlug(user, null);
    if (!workspaceSlug) {
      return '/tool/search';
    }
    return `/tool/search?workspace=${encodeURIComponent(workspaceSlug)}`;
  }
  return `/tool/${item.id}`;
}

/**
 * Resolve the routing destination for a sidebar-style NavItem.
 * Respects `absolutePath` (admin routes), `linkAppId` (AI items that deep-link
 * into another app like meeting-minutes → meeting), and `pathSuffix` (tab/query
 * targets like ?tab=recordings). Used by the left sub-sidebar and the slash
 * command palette so both routing paths stay in sync.
 */
export function resolveNavItemHref(
  item: NavItem,
  currentWorkspaceSlug: string | null | undefined,
  user: Parameters<typeof resolveDefaultWorkspaceAppPath>[0],
): string {
  if (item.absolutePath) {
    return item.absolutePath;
  }
  if (item.comingSoon) {
    return `/tool/${item.id}`;
  }
  if (item.id === 'search') {
    return resolveToolInvocationHref(item, currentWorkspaceSlug, user);
  }
  const targetApp = (item.linkAppId ?? item.appId) as
    | WorkspaceAppId
    | 'home'
    | 'settings';
  if (targetApp === 'home' || targetApp === 'settings') {
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
  if (
    !rawPath.startsWith('/api/v1/')
    || rawPath.startsWith('/api/v1/workspaces/')
    || rawPath.startsWith('/api/v1/docs/shared-links/')
    || rawPath.startsWith('/api/v1/whiteboard/shared-links/')
    || rawPath.includes('share_token=')
    || !WORKSPACE_API_PREFIXES.some((prefix) => rawPath.startsWith(prefix))
  ) {
    return rawPath;
  }

  const resolvedWorkspaceSlug = (
    workspaceSlug
    ?? (
      typeof window !== 'undefined'
        ? getToolWorkspaceSlugFromSearch(null, window.location.pathname, window.location.search)
        : null
    )
    ?? getCurrentOrLastWorkspaceSlug()
  );
  if (!resolvedWorkspaceSlug) {
    return rawPath;
  }
  return `/api/v1/workspaces/${encodeURIComponent(resolvedWorkspaceSlug)}${rawPath.slice('/api/v1'.length)}`;
}
