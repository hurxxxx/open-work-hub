import { useCallback, useEffect, useReducer, useState } from 'react';

import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';

export type WorkspaceBootstrapWorkspace =
  ApiSchema<'WorkspaceBootstrapWorkspaceResponse'>;

export type WorkspaceBootstrapNavItem =
  ApiSchema<'WorkspaceBootstrapNavItemResponse'> & {
    coming_soon?: boolean | null;
  };

export type WorkspaceBootstrapAppBarCategoryItem = Omit<
  ApiSchema<'WorkspaceBootstrapAppBarCategoryItemResponse'>,
  'coming_soon' | 'position'
> & {
  coming_soon?: boolean | null;
  position?: number;
};

export type WorkspaceBootstrapAppBarCategory = Omit<
  ApiSchema<'WorkspaceBootstrapAppBarCategoryResponse'>,
  'items'
> & {
  pinnable?: boolean;
  contextLabel?: string;
  showWorkspaceContext?: boolean;
  items: WorkspaceBootstrapAppBarCategoryItem[];
};

export type WorkspaceBootstrapApp = Omit<
  ApiSchema<'WorkspaceBootstrapAppResponse'>,
  'coming_soon' | 'nav_items'
> & {
  coming_soon?: boolean | null;
  nav_items: WorkspaceBootstrapNavItem[];
};

export type WorkspaceBootstrapKeywordSearchEntityType =
  ApiSchema<'WorkspaceBootstrapKeywordSearchEntityTypeResponse'>;

export type WorkspaceBootstrapKeywordSearch = Omit<
  ApiSchema<'WorkspaceBootstrapKeywordSearchResponse'>,
  'entity_types'
> & {
  entity_types: WorkspaceBootstrapKeywordSearchEntityType[];
};

export type WorkspaceBootstrapResponse = {
  workspace: WorkspaceBootstrapWorkspace;
  apps: WorkspaceBootstrapApp[];
  app_bar_categories?: WorkspaceBootstrapAppBarCategory[];
  nav: WorkspaceBootstrapNavItem[];
  /**
   * Workspace app ids exposed in the business-chat scope picker, after
   * applying runtime availability checks and the business-chat context policy.
   */
  chatbot_app_ids?: string[];
  keyword_search?: WorkspaceBootstrapKeywordSearch;
};

type GeneratedAppsBootstrapResponse = ApiSchema<'AppsBootstrapResponse'>;

export type AppsBootstrapResponse = Omit<
  GeneratedAppsBootstrapResponse,
  'app_bar_categories'
> & {
  app_bar_categories: WorkspaceBootstrapAppBarCategory[];
};

export type AppsBootstrapApp = AppsBootstrapResponse['apps'][number];
export type EligibleWorkspace = ApiSchema<'EligibleWorkspaceResponse'>;
export type EligibleWorkspacesResponse =
  ApiSchema<'EligibleWorkspacesResponse'>;
export type AppWorkspacePreferenceResponse =
  ApiSchema<'AppWorkspacePreferenceResponse'>;

async function getWorkspaceBootstrap(
  token: string,
  workspaceSlug: string,
): Promise<WorkspaceBootstrapResponse> {
  return apiFetchJsonWithMappedError<WorkspaceBootstrapResponse>(
    `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}/bootstrap`,
    token,
    {},
    (error) =>
      new Error(
        error.message ||
          i18n.t('apps:workspace.bootstrapRequestFailed', {
            status: error.status,
          }),
      ),
  );
}

interface WorkspaceBootstrapState {
  scopeKey: string | null;
  data: WorkspaceBootstrapResponse | null;
  error: string | null;
  loading: boolean;
}

type WorkspaceBootstrapAction =
  | { type: 'reset' }
  | { type: 'loading'; scopeKey: string }
  | { type: 'success'; scopeKey: string; data: WorkspaceBootstrapResponse }
  | { type: 'failure'; scopeKey: string; error: string };

const WORKSPACE_BOOTSTRAP_INITIAL_STATE: WorkspaceBootstrapState = {
  scopeKey: null,
  data: null,
  error: null,
  loading: false,
};

function workspaceBootstrapReducer(
  state: WorkspaceBootstrapState,
  action: WorkspaceBootstrapAction,
): WorkspaceBootstrapState {
  switch (action.type) {
    case 'reset':
      return state === WORKSPACE_BOOTSTRAP_INITIAL_STATE
        ? state
        : WORKSPACE_BOOTSTRAP_INITIAL_STATE;
    case 'loading':
      return {
        scopeKey: action.scopeKey,
        data: state.scopeKey === action.scopeKey ? state.data : null,
        error: null,
        loading: true,
      };
    case 'success':
      return {
        scopeKey: action.scopeKey,
        data: action.data,
        error: null,
        loading: false,
      };
    case 'failure':
      return {
        scopeKey: action.scopeKey,
        data: null,
        error: action.error,
        loading: false,
      };
  }
}

export function useWorkspaceBootstrap(
  token: string | null,
  principalId: string | null,
  workspaceSlug: string | null | undefined,
) {
  const [state, dispatch] = useReducer(
    workspaceBootstrapReducer,
    WORKSPACE_BOOTSTRAP_INITIAL_STATE,
  );
  const [reloadSeq, setReloadSeq] = useState(0);

  const requestedScopeKey =
    token && principalId && workspaceSlug
      ? JSON.stringify([principalId, workspaceSlug])
      : null;

  useEffect(() => {
    if (!token || !principalId || !workspaceSlug || !requestedScopeKey) {
      dispatch({ type: 'reset' });
      return;
    }

    let cancelled = false;
    dispatch({ type: 'loading', scopeKey: requestedScopeKey });
    getWorkspaceBootstrap(token, workspaceSlug)
      .then((next) => {
        if (cancelled) {
          return;
        }
        dispatch({ type: 'success', scopeKey: requestedScopeKey, data: next });
      })
      .catch((caughtError: unknown) => {
        if (cancelled) {
          return;
        }
        dispatch({
          type: 'failure',
          scopeKey: requestedScopeKey,
          error:
            caughtError instanceof Error
              ? caughtError.message
              : i18n.t('apps:workspace.bootstrapLoadFailed'),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [principalId, reloadSeq, requestedScopeKey, token, workspaceSlug]);

  const reload = useCallback(() => {
    setReloadSeq((current) => current + 1);
  }, []);

  const scopedState =
    requestedScopeKey !== null && state.scopeKey === requestedScopeKey
      ? state
      : WORKSPACE_BOOTSTRAP_INITIAL_STATE;
  return {
    data: scopedState.data,
    error: scopedState.error,
    loading:
      requestedScopeKey !== null &&
      (scopedState.loading || state.scopeKey !== requestedScopeKey),
    reload,
  };
}

async function getAppsBootstrap(token: string): Promise<AppsBootstrapResponse> {
  return apiFetchJsonWithMappedError<AppsBootstrapResponse>(
    '/api/v1/apps/bootstrap',
    token,
    {},
    (error) =>
      new Error(
        error.message ||
          i18n.t('apps:workspace.bootstrapRequestFailed', {
            status: error.status,
          }),
      ),
  );
}

interface AppsBootstrapState {
  scopeKey: string | null;
  data: AppsBootstrapResponse | null;
  error: string | null;
  loading: boolean;
}

type AppsBootstrapAction =
  | { type: 'reset' }
  | { type: 'loading'; scopeKey: string }
  | { type: 'success'; scopeKey: string; data: AppsBootstrapResponse }
  | { type: 'failure'; scopeKey: string; error: string };

const APPS_BOOTSTRAP_INITIAL_STATE: AppsBootstrapState = {
  scopeKey: null,
  data: null,
  error: null,
  loading: false,
};

function appsBootstrapReducer(
  state: AppsBootstrapState,
  action: AppsBootstrapAction,
): AppsBootstrapState {
  switch (action.type) {
    case 'reset':
      return state === APPS_BOOTSTRAP_INITIAL_STATE
        ? state
        : APPS_BOOTSTRAP_INITIAL_STATE;
    case 'loading':
      return {
        scopeKey: action.scopeKey,
        data: state.scopeKey === action.scopeKey ? state.data : null,
        error: null,
        loading: true,
      };
    case 'success':
      return {
        scopeKey: action.scopeKey,
        data: action.data,
        error: null,
        loading: false,
      };
    case 'failure':
      return {
        scopeKey: action.scopeKey,
        data: null,
        error: action.error,
        loading: false,
      };
  }
}

export function useAppsBootstrap(
  token: string | null,
  principalId: string | null,
) {
  const [state, dispatch] = useReducer(
    appsBootstrapReducer,
    APPS_BOOTSTRAP_INITIAL_STATE,
  );
  const [reloadSeq, setReloadSeq] = useState(0);

  const requestedScopeKey = token && principalId ? principalId : null;

  useEffect(() => {
    if (!token || !principalId || !requestedScopeKey) {
      dispatch({ type: 'reset' });
      return;
    }

    let cancelled = false;
    dispatch({ type: 'loading', scopeKey: requestedScopeKey });
    getAppsBootstrap(token)
      .then((next) => {
        if (!cancelled) {
          dispatch({
            type: 'success',
            scopeKey: requestedScopeKey,
            data: next,
          });
        }
      })
      .catch((caughtError: unknown) => {
        if (cancelled) return;
        dispatch({
          type: 'failure',
          scopeKey: requestedScopeKey,
          error:
            caughtError instanceof Error
              ? caughtError.message
              : i18n.t('apps:workspace.bootstrapLoadFailed'),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [principalId, reloadSeq, requestedScopeKey, token]);

  const reload = useCallback(() => {
    setReloadSeq((current) => current + 1);
  }, []);

  const scopedState =
    requestedScopeKey !== null && state.scopeKey === requestedScopeKey
      ? state
      : APPS_BOOTSTRAP_INITIAL_STATE;
  return {
    data: scopedState.data,
    error: scopedState.error,
    loading:
      requestedScopeKey !== null &&
      (scopedState.loading || state.scopeKey !== requestedScopeKey),
    reload,
  };
}

export async function getEligibleWorkspaces(
  token: string,
  appId: string,
  {
    page = 1,
    pageSize = 50,
    query = '',
    slug,
  }: { page?: number; pageSize?: number; query?: string; slug?: string } = {},
): Promise<EligibleWorkspacesResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (query.trim()) params.set('q', query.trim());
  if (slug?.trim()) params.set('slug', slug.trim());
  return apiFetchJsonWithMappedError<EligibleWorkspacesResponse>(
    `/api/v1/apps/${encodeURIComponent(appId)}/eligible-workspaces?${params.toString()}`,
    token,
    {},
    (error) =>
      new Error(error.message || i18n.t('apps:workspace.bootstrapLoadFailed')),
  );
}

export async function getAllEligibleWorkspaces(
  token: string,
  appId: string,
  { query = '' }: { query?: string } = {},
): Promise<EligibleWorkspace[]> {
  const pageSize = 100;
  const first = await getEligibleWorkspaces(token, appId, {
    page: 1,
    pageSize,
    query,
  });
  const pageCount = Math.ceil(first.total / pageSize);
  const remaining: EligibleWorkspacesResponse[] = [];
  for (let page = 2; page <= pageCount; page += 1) {
    remaining.push(
      await getEligibleWorkspaces(token, appId, { page, pageSize, query }),
    );
  }
  const items = [first, ...remaining].flatMap((response) => response.items);
  return Array.from(
    new Map(items.map((workspace) => [workspace.id, workspace])).values(),
  );
}

export async function setAppWorkspacePreference(
  token: string,
  appId: string,
  workspaceId: string,
): Promise<AppWorkspacePreferenceResponse> {
  return apiFetchJsonWithMappedError<AppWorkspacePreferenceResponse>(
    `/api/v1/apps/${encodeURIComponent(appId)}/workspace-preference`,
    token,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId }),
    },
    (error) =>
      new Error(error.message || i18n.t('apps:workspace.bootstrapLoadFailed')),
  );
}
