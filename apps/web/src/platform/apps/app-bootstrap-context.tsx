import { createContext, use, type ReactNode } from 'react';

import type { AppsBootstrapResponse } from './apps-api';

export interface AppBootstrapContextValue {
  data: AppsBootstrapResponse | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  aiToolAppIds?: readonly string[];
}

export interface AppBootstrapContextProjection {
  apps: AppsBootstrapResponse['apps'];
  nav: AppsBootstrapResponse['nav'];
  aiToolAppIds: readonly string[];
  loading: boolean;
  error: string | null;
}

const DEFAULT_VALUE: AppBootstrapContextValue = {
  data: null,
  error: null,
  loading: false,
  reload: () => undefined,
  aiToolAppIds: [],
};

const EMPTY_BOOTSTRAP_APPS: AppsBootstrapResponse['apps'] = [];
const EMPTY_BOOTSTRAP_NAV: AppsBootstrapResponse['nav'] = [];

const AppBootstrapContext =
  createContext<AppBootstrapContextValue>(DEFAULT_VALUE);

export function projectAppBootstrapContext(
  value: AppBootstrapContextValue,
): AppBootstrapContextProjection {
  return {
    apps: value.data?.apps ?? EMPTY_BOOTSTRAP_APPS,
    nav: value.data?.nav ?? EMPTY_BOOTSTRAP_NAV,
    aiToolAppIds: value.aiToolAppIds ?? [],
    loading: value.loading,
    error: value.error,
  };
}

export function isBootstrapAppEnabled(
  data: AppsBootstrapResponse | null | undefined,
  appId: string,
): boolean {
  if (!data) {
    return false;
  }
  return data.apps.some((app) => app.app_id === appId && app.enabled);
}

export function AppBootstrapProvider({
  value,
  children,
}: {
  value: AppBootstrapContextValue;
  children: ReactNode;
}) {
  return (
    <AppBootstrapContext.Provider value={value}>
      {children}
    </AppBootstrapContext.Provider>
  );
}

/** The shell fetches one user bootstrap; app consumers share this current snapshot. */
export function useAppBootstrapContext(): AppBootstrapContextValue {
  return use(AppBootstrapContext);
}

export function useAppBootstrapProjection(): AppBootstrapContextProjection {
  return projectAppBootstrapContext(useAppBootstrapContext());
}

export function useAppAdmission(appId: string): boolean {
  return isBootstrapAppEnabled(useAppBootstrapContext().data, appId);
}
