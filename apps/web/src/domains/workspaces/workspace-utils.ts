import type { AuthUser } from '@/src/domains/auth/auth-api';

export type WorkspaceAppId = 'ai' | 'pms' | 'docs' | 'planner' | 'meeting';

export const WORKSPACE_APP_IDS: readonly WorkspaceAppId[] = [
  'ai',
  'pms',
  'docs',
  'planner',
  'meeting',
] as const;

const WORKSPACE_API_PREFIXES = [
  '/api/v1/ai',
  '/api/v1/pms',
  '/api/v1/docs',
  '/api/v1/meeting',
  '/api/v1/search',
  '/api/v1/connectors/ocr',
] as const;

const LAST_WORKSPACE_STORAGE_KEY = 'aidoo:last-workspace-slug';

export function getWorkspaceSlugFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/w\/([^/]+)(?:\/|$)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
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
  return user?.workspaces?.find((workspace) => workspace.enabled_apps.includes(appId)) ?? null;
}

export function getPreferredWorkspace(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  appId?: WorkspaceAppId,
) {
  const lastWorkspace = getWorkspaceBySlug(user, readLastWorkspaceSlug());
  if (lastWorkspace && (!appId || lastWorkspace.enabled_apps.includes(appId))) {
    return lastWorkspace;
  }
  if (appId) {
    return getFirstWorkspaceForApp(user, appId);
  }
  return user?.workspaces?.[0] ?? null;
}

export function hasWorkspaceApp(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  workspaceSlug: string | null | undefined,
  appId: WorkspaceAppId,
): boolean {
  return getWorkspaceBySlug(user, workspaceSlug)?.enabled_apps.includes(appId) ?? false;
}

export function buildWorkspaceAppPath(
  workspaceSlug: string,
  appId: WorkspaceAppId,
  suffix = '',
): string {
  const normalizedSuffix = suffix
    ? suffix.startsWith('/')
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

export function rewriteLegacyAppPath(
  rawPath: string,
  workspaceSlug: string | null | undefined,
): string {
  if (!workspaceSlug) {
    return rawPath;
  }

  const match = rawPath.match(/^\/(ai|pms|docs|planner|meeting)(.*)$/);
  if (!match) {
    return rawPath;
  }

  const [, appId, suffix] = match;
  return buildWorkspaceAppPath(workspaceSlug, appId as WorkspaceAppId, suffix || '');
}

export function requireWorkspaceSlug(workspaceSlug?: string | null): string {
  const resolved = workspaceSlug ?? getCurrentOrLastWorkspaceSlug();
  if (!resolved) {
    throw new Error('Workspace context is not available.');
  }
  return resolved;
}

export function rewriteWorkspaceApiPath(
  rawPath: string,
  workspaceSlug?: string | null,
): string {
  if (
    !rawPath.startsWith('/api/v1/')
    || rawPath.startsWith('/api/v1/workspaces/')
    || !WORKSPACE_API_PREFIXES.some((prefix) => rawPath.startsWith(prefix))
  ) {
    return rawPath;
  }

  const resolvedWorkspaceSlug = workspaceSlug ?? getCurrentOrLastWorkspaceSlug();
  if (!resolvedWorkspaceSlug) {
    return rawPath;
  }
  return `/api/v1/workspaces/${encodeURIComponent(resolvedWorkspaceSlug)}${rawPath.slice('/api/v1'.length)}`;
}
