import { createContext, useContext, type ReactNode } from 'react';

import type { WorkspaceBootstrapResponse } from './workspaces-api';

export interface WorkspaceBootstrapContextValue {
  data: WorkspaceBootstrapResponse | null;
  error: string | null;
  loading: boolean;
}

const DEFAULT_VALUE: WorkspaceBootstrapContextValue = {
  data: null,
  error: null,
  loading: false,
};

const WorkspaceBootstrapContext =
  createContext<WorkspaceBootstrapContextValue>(DEFAULT_VALUE);

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
  return useContext(WorkspaceBootstrapContext);
}
