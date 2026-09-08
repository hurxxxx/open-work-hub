import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { useCallback, useEffect, useReducer, useRef } from 'react';
export type BootstrapNavItem = ApiSchema<'BootstrapNavItemResponse'>;
export type BootstrapApp = ApiSchema<'BootstrapAppResponse'>;
export type BootstrapAppBarCategoryItem =
  ApiSchema<'BootstrapAppBarCategoryItemResponse'>;
export type BootstrapAppBarCategory =
  ApiSchema<'BootstrapAppBarCategoryResponse'> & {
    pinnable?: boolean;
    contextLabel?: string;
  };
export type BootstrapKeywordSearchEntityType =
  ApiSchema<'BootstrapKeywordSearchEntityTypeResponse'>;
export type BootstrapKeywordSearch =
  ApiSchema<'BootstrapKeywordSearchResponse'>;
export type AppsBootstrapResponse = Omit<
  ApiSchema<'AppsBootstrapResponse'>,
  'app_bar_categories'
> & {
  app_bar_categories: BootstrapAppBarCategory[];
};
export type AppsBootstrapApp = AppsBootstrapResponse['apps'][number];

async function getAppsBootstrap(token: string): Promise<AppsBootstrapResponse> {
  return apiFetchJsonWithMappedError<AppsBootstrapResponse>(
    '/api/v1/apps/bootstrap',
    token,
    {},
    (error) =>
      new Error(
        error.message ||
          i18n.t('shell:appBootstrap.requestFailed', {
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
  const requestIdRef = useRef(0);

  const requestedScopeKey = token && principalId ? principalId : null;

  const refresh = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    if (!token || !principalId || !requestedScopeKey) {
      dispatch({ type: 'reset' });
      return null;
    }

    dispatch({ type: 'loading', scopeKey: requestedScopeKey });
    try {
      const next = await getAppsBootstrap(token);
      if (requestIdRef.current === requestId) {
        dispatch({
          type: 'success',
          scopeKey: requestedScopeKey,
          data: next,
        });
      }
      return next;
    } catch (caughtError) {
      const error =
        caughtError instanceof Error
          ? caughtError
          : new Error(i18n.t('shell:appBootstrap.loadFailed'));
      if (requestIdRef.current === requestId) {
        dispatch({
          type: 'failure',
          scopeKey: requestedScopeKey,
          error: error.message,
        });
      }
      throw error;
    }
  }, [principalId, requestedScopeKey, token]);

  useEffect(() => {
    void refresh().catch(() => undefined);
    return () => {
      requestIdRef.current += 1;
    };
  }, [refresh]);

  const reload = useCallback(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

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
    refresh,
  };
}
