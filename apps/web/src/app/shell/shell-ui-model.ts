import type { ThemePreference } from '@/src/platform/auth/auth-api';
import {
  APP_CONTRACT_BY_ID,
  type AppId,
} from '@open-work-hub/contracts/app-contracts';
import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';

export type ResolvedThemePreference = 'light' | 'dark';
export type AppDisplayScope = 'company' | 'personal' | 'workspace';

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

export function resolveAppDisplayScope(
  appId: WorkspaceAppId,
): AppDisplayScope | null {
  const contract = APP_CONTRACT_BY_ID.get(appId as AppId);
  if (!contract) return null;
  if (contract.availability_scope === 'workspace') return 'workspace';
  return contract.execution_context_kind === 'personal'
    ? 'personal'
    : 'company';
}
