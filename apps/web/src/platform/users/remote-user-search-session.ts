import { useCallback, useEffect, useReducer, useRef } from 'react';

export type RemoteUserSearchStatus = 'idle' | 'searching' | 'loaded' | 'failed';

export type RemoteUserSearchLoadContext = {
  query: string;
  signal: AbortSignal;
  token: string;
};

export type RemoteUserSearchLoader<TUser> = (
  context: RemoteUserSearchLoadContext,
) => Promise<readonly TUser[]>;

export type RemoteUserSearchSessionHandlers<TUser> = {
  onIdle?: () => void;
  onStarted?: () => void;
  onLoaded?: (users: TUser[]) => void;
  onFailed?: (error: unknown) => void;
};

export type RemoteUserSearchSessionOptions<TUser> =
  RemoteUserSearchSessionHandlers<TUser> & {
    debounceMs?: number;
    enabled?: boolean;
    query: string;
    searchUsers: RemoteUserSearchLoader<TUser>;
    token: string | null | undefined;
  };

export type RemoteUserSearchSessionState<TUser> = {
  error: unknown | null;
  failed: boolean;
  loading: boolean;
  query: string;
  results: TUser[];
  searching: boolean;
  status: RemoteUserSearchStatus;
};

export type RemoteUserSearchSession<TUser> =
  RemoteUserSearchSessionState<TUser> & {
    reset: () => void;
  };

type RemoteUserSearchAction<TUser> =
  | { type: 'idle' }
  | { type: 'start'; query: string }
  | { type: 'success'; query: string; results: TUser[] }
  | { type: 'failure'; query: string; error: unknown };

const DEFAULT_REMOTE_USER_SEARCH_DEBOUNCE_MS = 250;

const INITIAL_REMOTE_USER_SEARCH_STATE: RemoteUserSearchSessionState<never> = {
  error: null,
  failed: false,
  loading: false,
  query: '',
  results: [],
  searching: false,
  status: 'idle',
};

function remoteUserSearchReducer<TUser>(
  state: RemoteUserSearchSessionState<TUser>,
  action: RemoteUserSearchAction<TUser>,
): RemoteUserSearchSessionState<TUser> {
  if (action.type === 'idle') {
    return INITIAL_REMOTE_USER_SEARCH_STATE;
  }

  if (action.type === 'start') {
    return {
      ...state,
      error: null,
      failed: false,
      loading: true,
      query: action.query,
      searching: true,
      status: 'searching',
    };
  }

  if (action.type === 'success') {
    return {
      error: null,
      failed: false,
      loading: false,
      query: action.query,
      results: action.results,
      searching: false,
      status: 'loaded',
    };
  }

  return {
    error: action.error,
    failed: true,
    loading: false,
    query: action.query,
    results: [],
    searching: false,
    status: 'failed',
  };
}

export function useRemoteUserSearchSession<TUser>({
  debounceMs = DEFAULT_REMOTE_USER_SEARCH_DEBOUNCE_MS,
  enabled = true,
  onFailed,
  onIdle,
  onLoaded,
  onStarted,
  query,
  searchUsers,
  token,
}: RemoteUserSearchSessionOptions<TUser>): RemoteUserSearchSession<TUser> {
  const [state, dispatch] = useReducer(
    remoteUserSearchReducer<TUser>,
    INITIAL_REMOTE_USER_SEARCH_STATE,
  );
  const handlersRef = useRef<RemoteUserSearchSessionHandlers<TUser>>({});
  const searchIdRef = useRef(0);

  handlersRef.current = {
    onFailed,
    onIdle,
    onLoaded,
    onStarted,
  };

  useEffect(() => {
    if (!enabled || !token) {
      searchIdRef.current += 1;
      dispatch({ type: 'idle' });
      return undefined;
    }

    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      searchIdRef.current += 1;
      dispatch({ type: 'idle' });
      handlersRef.current.onIdle?.();
      return undefined;
    }

    const searchId = searchIdRef.current + 1;
    searchIdRef.current = searchId;
    const controller = new AbortController();

    dispatch({ type: 'start', query: trimmedQuery });
    handlersRef.current.onStarted?.();

    const timeout = window.setTimeout(() => {
      searchUsers({
        query: trimmedQuery,
        signal: controller.signal,
        token,
      })
        .then((users) => {
          if (searchIdRef.current !== searchId || controller.signal.aborted) {
            return;
          }

          const results = Array.from(users);
          dispatch({ type: 'success', query: trimmedQuery, results });
          handlersRef.current.onLoaded?.(results);
        })
        .catch((error: unknown) => {
          if (searchIdRef.current !== searchId || controller.signal.aborted) {
            return;
          }

          dispatch({ type: 'failure', query: trimmedQuery, error });
          handlersRef.current.onFailed?.(error);
        });
    }, debounceMs);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [debounceMs, enabled, query, searchUsers, token]);

  const reset = useCallback(() => {
    searchIdRef.current += 1;
    dispatch({ type: 'idle' });
  }, []);

  return {
    ...state,
    reset,
  };
}
