import {
  APP_CONTRACT_BY_ID,
  type AppId,
  type AppRouteId,
} from '@open-work-hub/contracts/app-contracts';
import {
  buildAppEntryHref,
  buildAppHref,
  matchAppRoute,
} from '@open-work-hub/contracts/app-routes';

import type { NavItem } from '@/src/app/shell/navigation-types';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import { rewriteWorkspaceApiPathForWorkspace } from '@/src/platform/api/workspace-api-path-policy';

export type WorkspaceAppId = string;

type WorkspaceSelectionUser = Pick<AuthUser, 'workspaces'>;

function getContract(appId: string) {
  return APP_CONTRACT_BY_ID.get(appId as AppId) ?? null;
}

function requireWorkspaceApp(appId: string) {
  const app = getContract(appId);
  if (!app || app.availability_scope !== 'workspace') {
    throw new Error(`Unknown workspace app: ${appId}`);
  }
  return app;
}

export function getWorkspaceSlugFromPath(pathname: string): string | null {
  const route = matchAppRoute(pathname);
  return route?.contextScope === 'workspace' ? route.workspaceSlug : null;
}

export function getWorkspaceAppIdFromPath(
  pathname: string,
): WorkspaceAppId | null {
  const route = matchAppRoute(pathname);
  return route?.contextScope === 'workspace' ? route.appId : null;
}

export function getWorkspaceBySlug(
  user: WorkspaceSelectionUser | null | undefined,
  workspaceSlug: string | null | undefined,
) {
  if (!workspaceSlug) return null;
  return (
    user?.workspaces.find((workspace) => workspace.slug === workspaceSlug) ??
    null
  );
}

export function buildWorkspaceAppPath(
  workspaceSlug: string,
  appId: WorkspaceAppId,
): string {
  const app = requireWorkspaceApp(appId);
  return buildAppHref({
    routeId: app.entry_route_id,
    workspaceSlug,
  });
}

/** App entry is intentionally unresolved; the entry route owns selection. */
export function buildWorkspaceAppEntryPath(appId: WorkspaceAppId): string {
  const app = requireWorkspaceApp(appId);
  return buildAppEntryHref(app.app_id);
}

export function resolveRouteWorkspaceSlug(
  user: WorkspaceSelectionUser | null | undefined,
  pathname: string,
): string | null {
  return (
    getWorkspaceBySlug(user, getWorkspaceSlugFromPath(pathname))?.slug ?? null
  );
}

function resolveAppTarget(
  appId: string,
  workspaceSlug: string | null | undefined,
  suffix = '',
): string | null {
  const app = getContract(appId);
  if (!app) return null;
  const parsed = new URL(suffix || '/', 'https://app.invalid');
  const route =
    parsed.pathname === '/'
      ? app.routes.find(
          (candidate) => candidate.route_id === app.entry_route_id,
        )
      : app.routes.find(
          (candidate) =>
            candidate.suffix === parsed.pathname &&
            !candidate.suffix.includes(':'),
        );
  if (!route) return null;

  const queryParams: Record<string, string | string[]> = {};
  for (const key of new Set(parsed.searchParams.keys())) {
    const values = parsed.searchParams.getAll(key);
    queryParams[key] = values.length === 1 ? values[0] : values;
  }
  if (route.context_scope === 'workspace' && !workspaceSlug) {
    return buildAppEntryHref(app.app_id);
  }
  return buildAppHref({
    routeId: route.route_id as AppRouteId,
    queryParams,
    fragment: parsed.hash || undefined,
    ...(route.context_scope === 'workspace'
      ? { workspaceSlug: workspaceSlug as string }
      : {}),
  });
}

export function resolveAppInvocationHref(
  item: NavItem,
  currentWorkspaceSlug: string | null | undefined,
  _user: WorkspaceSelectionUser | null | undefined,
): string {
  if (item.absolutePath) return item.absolutePath;
  const targetAppId = item.linkAppId ?? item.appId;
  const target = resolveAppTarget(
    targetAppId === 'search' ? 'retrieval-search' : targetAppId,
    currentWorkspaceSlug,
    item.pathSuffix ?? '',
  );
  return target ?? '/';
}

export function resolveNavItemHref(
  item: NavItem,
  currentWorkspaceSlug: string | null | undefined,
  user: WorkspaceSelectionUser | null | undefined,
): string {
  return resolveAppInvocationHref(item, currentWorkspaceSlug, user);
}

/** Workspace API rewriting only accepts an explicit or canonical URL context. */
export function rewriteWorkspaceApiPath(
  rawPath: string,
  workspaceSlug?: string | null,
): string {
  const routeWorkspaceSlug =
    workspaceSlug ??
    (typeof window !== 'undefined'
      ? getWorkspaceSlugFromPath(window.location.pathname)
      : null);
  return rewriteWorkspaceApiPathForWorkspace(rawPath, routeWorkspaceSlug);
}
