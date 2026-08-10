import { createContext, use, type ReactNode } from 'react';

import type {
  AppsBootstrapResponse,
  WorkspaceBootstrapResponse,
} from './workspaces-api';

export interface WorkspaceBootstrapContextValue {
  data: WorkspaceBootstrapResponse | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  reloadGlobalApps?: () => void;
  globalApps?: AppsBootstrapResponse | null;
  aiToolAppIds?: readonly string[];
}

export interface WorkspaceBootstrapContextProjection {
  apps: WorkspaceBootstrapResponse['apps'];
  nav: WorkspaceBootstrapResponse['nav'];
  aiToolAppIds: readonly string[];
  loading: boolean;
  error: string | null;
}

const DEFAULT_VALUE: WorkspaceBootstrapContextValue = {
  data: null,
  error: null,
  loading: false,
  reload: () => undefined,
  aiToolAppIds: [],
};

const EMPTY_WORKSPACE_BOOTSTRAP_APPS: WorkspaceBootstrapResponse['apps'] = [];
const EMPTY_WORKSPACE_BOOTSTRAP_NAV: WorkspaceBootstrapResponse['nav'] = [];

const WorkspaceBootstrapContext =
  createContext<WorkspaceBootstrapContextValue>(DEFAULT_VALUE);

export function projectWorkspaceBootstrapContext(
  value: WorkspaceBootstrapContextValue,
): WorkspaceBootstrapContextProjection {
  return {
    apps: value.data?.apps ?? EMPTY_WORKSPACE_BOOTSTRAP_APPS,
    nav: value.data?.nav ?? EMPTY_WORKSPACE_BOOTSTRAP_NAV,
    aiToolAppIds: value.aiToolAppIds ?? [],
    loading: value.loading,
    error: value.error,
  };
}

export function isWorkspaceBootstrapAppEnabled(
  data: WorkspaceBootstrapResponse | null | undefined,
  appId: string,
): boolean {
  if (!data) {
    return false;
  }
  return data.apps.some((app) => app.app_id === appId && app.enabled);
}

export function WorkspaceBootstrapProvider({
  value,
  children,
}: {
  value: WorkspaceBootstrapContextValue;
  children: ReactNode;
}) {
  return (
    <WorkspaceBootstrapContext.Provider value={value}>
      {children}
    </WorkspaceBootstrapContext.Provider>
  );
}

/**
 * Read workspace bootstrap state from React context.
 *
 * AppContent fetches `/api/v1/workspaces/:slug/bootstrap` once per workspace
 * switch and publishes the result here. Downstream views should consume the
 * context instead of calling `useWorkspaceBootstrap` again, which would issue
 * a duplicate request and briefly show stale/fallback data while the second
 * fetch resolves.
 *
 * If a consumer renders outside the provider (e.g. in storybook or tests that
 * forget to wrap), this returns a default `{ data: null, error: null,
 * loading: false }` so the UI degrades gracefully.
 */
export function useWorkspaceBootstrapContext(): WorkspaceBootstrapContextValue {
  return use(WorkspaceBootstrapContext);
}

export function useWorkspaceBootstrapProjection(): WorkspaceBootstrapContextProjection {
  return projectWorkspaceBootstrapContext(useWorkspaceBootstrapContext());
}
