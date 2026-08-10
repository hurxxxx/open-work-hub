import { useCallback, useEffect, useReducer } from 'react';

import {
  deleteRecording,
  listRecordings,
  retryRecording,
  type Recording,
  type RecordingListResponse,
  type RecordingViewFilter,
} from '../api/recording-api';

export type RecordingCollectionScope =
  | { kind: 'view'; view: RecordingViewFilter }
  | {
      kind: 'target';
      targetApp: string;
      targetType: string;
      targetId: string;
    };

export interface RecordingCollectionMessages {
  loadFailed: string;
  retryFailed: string;
  deleteFailed: string;
}

export interface RecordingCollectionClient {
  listRecordings: typeof listRecordings;
  retryRecording: typeof retryRecording;
  deleteRecording: typeof deleteRecording;
}

export interface RecordingCollectionWorkflowOptions {
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
  scope: RecordingCollectionScope;
  messages: RecordingCollectionMessages;
  client?: RecordingCollectionClient;
}

interface RecordingCollectionState {
  items: Recording[];
  loading: boolean;
  busyId: string | null;
  error: string | null;
}

type RecordingCollectionAction =
  | { type: 'loadStarted' }
  | { type: 'loadSucceeded'; items: Recording[] }
  | { type: 'loadFailed'; message: string }
  | { type: 'busyStarted'; id: string }
  | { type: 'busyFinished' }
  | { type: 'errorSet'; message: string };

export interface RecordingCollectionWorkflow extends RecordingCollectionState {
  refresh(): Promise<void>;
  retry(recordingId: string): Promise<void>;
  remove(recordingId: string, confirmDelete?: () => Promise<boolean>): Promise<void>;
  setError(error: unknown, fallback?: string): void;
}

export const recordingCollectionClient: RecordingCollectionClient = {
  listRecordings,
  retryRecording,
  deleteRecording,
};

const INITIAL_RECORDING_COLLECTION_STATE: RecordingCollectionState = {
  items: [],
  loading: false,
  busyId: null,
  error: null,
};

function recordingCollectionReducer(
  state: RecordingCollectionState,
  action: RecordingCollectionAction,
): RecordingCollectionState {
  switch (action.type) {
    case 'loadStarted':
      return { ...state, loading: true, error: null };
    case 'loadSucceeded':
      return { ...state, items: action.items, loading: false };
    case 'loadFailed':
      return { ...state, items: [], loading: false, error: action.message };
    case 'busyStarted':
      return { ...state, busyId: action.id, error: null };
    case 'busyFinished':
      return { ...state, busyId: null };
    case 'errorSet':
      return { ...state, error: action.message };
  }
}

function messageFromError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function scopeDeps(scope: RecordingCollectionScope): readonly [
  string,
  string,
  string,
  string,
] {
  if (scope.kind === 'view') {
    return [scope.kind, scope.view, '', ''];
  }
  return [
    scope.kind,
    scope.targetApp,
    scope.targetType,
    scope.targetId,
  ];
}

export function useRecordingCollectionWorkflow({
  token,
  workspaceSlug,
  scope,
  messages,
  client = recordingCollectionClient,
}: RecordingCollectionWorkflowOptions): RecordingCollectionWorkflow {
  const [state, dispatch] = useReducer(
    recordingCollectionReducer,
    INITIAL_RECORDING_COLLECTION_STATE,
  );
  const [
    scopeKind,
    scopeFirst,
    scopeSecond,
    scopeThird,
  ] = scopeDeps(scope);

  const refresh = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    dispatch({ type: 'loadStarted' });
    try {
      const options: Parameters<typeof listRecordings>[2] =
        scopeKind === 'view'
          ? { view: scopeFirst as RecordingViewFilter }
          : {
              target_app: scopeFirst,
              target_type: scopeSecond,
              target_id: scopeThird,
            };
      const response: RecordingListResponse = await client.listRecordings(
        token,
        workspaceSlug,
        options,
      );
      dispatch({ type: 'loadSucceeded', items: response.items });
    } catch (error) {
      dispatch({
        type: 'loadFailed',
        message: messageFromError(error, messages.loadFailed),
      });
    }
  }, [
    client,
    messages.loadFailed,
    scopeFirst,
    scopeKind,
    scopeSecond,
    scopeThird,
    token,
    workspaceSlug,
  ]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const retry = useCallback(async (recordingId: string) => {
    if (!token || !workspaceSlug) {
      dispatch({ type: 'errorSet', message: messages.retryFailed });
      return;
    }
    dispatch({ type: 'busyStarted', id: recordingId });
    try {
      await client.retryRecording(token, workspaceSlug, recordingId);
      await refresh();
    } catch (error) {
      const message = messageFromError(error, messages.retryFailed);
      dispatch({ type: 'errorSet', message });
    } finally {
      dispatch({ type: 'busyFinished' });
    }
  }, [client, messages.retryFailed, refresh, token, workspaceSlug]);

  const remove = useCallback(
    async (recordingId: string, confirmDelete?: () => Promise<boolean>) => {
      if (!token || !workspaceSlug) return;
      if (confirmDelete && !(await confirmDelete())) return;
      dispatch({ type: 'busyStarted', id: recordingId });
      try {
        await client.deleteRecording(token, workspaceSlug, recordingId);
        await refresh();
      } catch (error) {
        dispatch({
          type: 'errorSet',
          message: messageFromError(error, messages.deleteFailed),
        });
      } finally {
        dispatch({ type: 'busyFinished' });
      }
    },
    [client, messages.deleteFailed, refresh, token, workspaceSlug],
  );

  const setError = useCallback(
    (error: unknown, fallback = messages.loadFailed) => {
      dispatch({
        type: 'errorSet',
        message: messageFromError(error, fallback),
      });
    },
    [messages.loadFailed],
  );

  return {
    ...state,
    refresh,
    retry,
    remove,
    setError,
  };
}
