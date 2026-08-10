import type { AuthUser, ThemePreference } from '@/src/platform/auth/auth-api';
import type { LauncherGlobalPaths } from './navigation-types';
import {
  buildWorkspaceAppPath,
  getPreferredWorkspace,
  type WorkspaceAppId,
} from '@/src/platform/workspaces/workspace-utils';

export type ResolvedThemePreference = 'light' | 'dark';

export const DARK_MODE_QUERY = '(prefers-color-scheme: dark)';

export function resolveThemePreference(
  themePreference: ThemePreference,
  systemDarkMode: boolean,
): ResolvedThemePreference {
  if (themePreference === 'system') {
    return systemDarkMode ? 'dark' : 'light';
  }

  return themePreference;
}

export function getSystemDarkModeSnapshot(): boolean {
  if (
    typeof window === 'undefined' ||
    typeof window.matchMedia !== 'function'
  ) {
    return false;
  }
  return window.matchMedia(DARK_MODE_QUERY).matches;
}

export function subscribeSystemDarkMode(onStoreChange: () => void): () => void {
  if (
    typeof window === 'undefined' ||
    typeof window.matchMedia !== 'function'
  ) {
    return () => undefined;
  }
  const mediaQuery = window.matchMedia(DARK_MODE_QUERY);
  mediaQuery.addEventListener('change', onStoreChange);
  return () => mediaQuery.removeEventListener('change', onStoreChange);
}

export function getInitials(label: string, fallback: string): string {
  const initials = label
    .trim()
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return initials || fallback;
}

export function resolveMobileAppLink(
  appId: WorkspaceAppId,
  currentUser: AuthUser,
  shellWorkspaceSlug: string | null,
  launcherGlobalPaths: LauncherGlobalPaths,
): string {
  const globalPath = launcherGlobalPaths.get(appId);
  if (globalPath) {
    return globalPath;
  }

  const workspaceForShellSlug = shellWorkspaceSlug
    ? currentUser.workspaces.find(
        (workspace) => workspace.slug === shellWorkspaceSlug,
      )
    : undefined;
  const selectedWorkspace =
    workspaceForShellSlug ?? getPreferredWorkspace(currentUser, appId);

  return selectedWorkspace
    ? buildWorkspaceAppPath(selectedWorkspace.slug, appId)
    : '/';
}
