import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRequestError } from '@/src/platform/api/client';

import {
  deleteLegacyIssueGridPreference,
  fetchLegacyIssueGridPreference,
  updateLegacyIssueGridPreference,
  type LegacyIssueGridPreferenceKind,
  type LegacyIssueGridPreferenceUpdatePayload,
} from '../api/legacy-issue-dataset-api';

export type LegacyIssueGridPreferenceSaveStatus =
  | 'error'
  | 'idle'
  | 'loading'
  | 'saving';

type PreferenceOperation =
  | {
      kind: 'delete';
      conflictRetries: number;
    }
  | {
      kind: 'put';
      payload: LegacyIssueGridPreferenceUpdatePayload;
    };

type PreferenceSession = {
  disposed: boolean;
  failedOperation: PreferenceOperation | 'load' | null;
  gridKey: string;
  gridKind: LegacyIssueGridPreferenceKind;
  inFlight: Promise<void> | null;
  pendingOperation: PreferenceOperation | null;
  revision: number;
  timer: ReturnType<typeof setTimeout> | null;
  token: string;
  workspaceSlug: string;
};

const SAVE_DEBOUNCE_MS = 400;
const MAX_RESET_CONFLICT_RETRIES = 3;

export function useLegacyIssueGridPreference({
  gridKey,
  gridKind,
  onLoadError,
  onSaveError,
  token,
  workspaceSlug,
}: {
  gridKey: string | null;
  gridKind: LegacyIssueGridPreferenceKind;
  onLoadError?: (error: unknown) => void;
  onSaveError?: (error: unknown) => void;
  token: string | null;
  workspaceSlug: string | null;
}) {
  const [preference, setPreferenceState] = useState<
    LegacyIssueGridPreferenceUpdatePayload | null | undefined
  >(undefined);
  const [status, setStatus] =
    useState<LegacyIssueGridPreferenceSaveStatus>('loading');
  const [loadFailed, setLoadFailed] = useState(false);
  const sessionRef = useRef<PreferenceSession | null>(null);
  const onLoadErrorRef = useRef(onLoadError);
  const onSaveErrorRef = useRef(onSaveError);
  onLoadErrorRef.current = onLoadError;
  onSaveErrorRef.current = onSaveError;

  const isActive = useCallback(
    (session: PreferenceSession) =>
      sessionRef.current === session && !session.disposed,
    [],
  );

  const drain = useCallback(
    async (session: PreferenceSession): Promise<void> => {
      if (session.inFlight || !session.pendingOperation) return;
      const operation = session.pendingOperation;
      session.pendingOperation = null;
      session.failedOperation = null;
      if (isActive(session)) {
        setStatus('saving');
        setLoadFailed(false);
      }
      session.inFlight = (async () => {
        try {
          if (operation.kind === 'delete') {
            await deleteLegacyIssueGridPreference({
              expectedRevision: session.revision,
              gridKey: session.gridKey,
              gridKind: session.gridKind,
              token: session.token,
              workspaceSlug: session.workspaceSlug,
            });
            session.revision += 1;
            if (isActive(session)) setPreferenceState(null);
          } else {
            const saved = await updateLegacyIssueGridPreference({
              expectedRevision: session.revision,
              gridKey: session.gridKey,
              gridKind: session.gridKind,
              payload: operation.payload,
              token: session.token,
              workspaceSlug: session.workspaceSlug,
            });
            session.revision = saved.revision;
            if (isActive(session)) {
              setPreferenceState({
                column_order: saved.column_order,
                frozen_column_count: saved.frozen_column_count,
                hidden_column_keys: saved.hidden_column_keys,
              });
            }
          }
          if (isActive(session) && !session.pendingOperation) {
            setStatus('idle');
          }
        } catch (error) {
          let failure = error;
          if (error instanceof ApiRequestError && error.status === 409) {
            try {
              const response = await fetchLegacyIssueGridPreference({
                gridKey: session.gridKey,
                gridKind: session.gridKind,
                token: session.token,
                workspaceSlug: session.workspaceSlug,
              });
              session.revision = response.revision;
              const hasNewerLocalOperation = session.pendingOperation !== null;
              if (
                operation.kind === 'delete' &&
                !hasNewerLocalOperation &&
                operation.conflictRetries < MAX_RESET_CONFLICT_RETRIES
              ) {
                session.pendingOperation = {
                  kind: 'delete',
                  conflictRetries: operation.conflictRetries + 1,
                };
              }
              if (isActive(session)) {
                if (!session.pendingOperation) {
                  setPreferenceState(
                    response.preference
                      ? {
                          column_order: response.preference.column_order,
                          frozen_column_count:
                            response.preference.frozen_column_count,
                          hidden_column_keys:
                            response.preference.hidden_column_keys,
                        }
                      : null,
                  );
                }
                if (!session.pendingOperation) setStatus('idle');
              }
              if (
                operation.kind === 'put' ||
                hasNewerLocalOperation ||
                operation.conflictRetries < MAX_RESET_CONFLICT_RETRIES
              ) {
                return;
              }
            } catch (refreshError) {
              failure = refreshError;
            }
          }
          session.failedOperation = operation;
          if (isActive(session)) {
            setStatus('error');
            onSaveErrorRef.current?.(failure);
          }
        } finally {
          session.inFlight = null;
          if (session.pendingOperation) {
            void drain(session);
          }
        }
      })();
      await session.inFlight;
    },
    [isActive],
  );

  const load = useCallback(
    async (session: PreferenceSession) => {
      if (isActive(session)) {
        setStatus('loading');
        setLoadFailed(false);
        setPreferenceState(undefined);
      }
      try {
        const response = await fetchLegacyIssueGridPreference({
          gridKey: session.gridKey,
          gridKind: session.gridKind,
          token: session.token,
          workspaceSlug: session.workspaceSlug,
        });
        if (!isActive(session)) return;
        session.revision = response.revision;
        setPreferenceState(
          response.preference
            ? {
                column_order: response.preference.column_order,
                frozen_column_count:
                  response.preference.frozen_column_count,
                hidden_column_keys: response.preference.hidden_column_keys,
              }
            : null,
        );
        session.failedOperation = null;
        setStatus('idle');
      } catch (error) {
        if (!isActive(session)) return;
        session.failedOperation = 'load';
        setPreferenceState(null);
        setLoadFailed(true);
        setStatus('error');
        onLoadErrorRef.current?.(error);
      }
    },
    [isActive],
  );

  useEffect(() => {
    const previous = sessionRef.current;
    if (previous) {
      previous.disposed = true;
      if (previous.timer) clearTimeout(previous.timer);
      previous.timer = null;
      if (previous.pendingOperation) void drain(previous);
    }

    if (!gridKey || !token || !workspaceSlug) {
      sessionRef.current = null;
      setPreferenceState(null);
      setLoadFailed(false);
      setStatus('idle');
      return;
    }

    const session: PreferenceSession = {
      disposed: false,
      failedOperation: null,
      gridKey,
      gridKind,
      inFlight: null,
      pendingOperation: null,
      revision: 0,
      timer: null,
      token,
      workspaceSlug,
    };
    sessionRef.current = session;
    void load(session);
    return () => {
      session.disposed = true;
      if (session.timer) clearTimeout(session.timer);
      session.timer = null;
      if (session.pendingOperation) void drain(session);
    };
  }, [drain, gridKey, gridKind, load, token, workspaceSlug]);

  const updatePreference = useCallback(
    (next: LegacyIssueGridPreferenceUpdatePayload) => {
      const session = sessionRef.current;
      if (!session || session.disposed || loadFailed) return;
      setPreferenceState(next);
      setStatus('idle');
      session.failedOperation = null;
      session.pendingOperation = { kind: 'put', payload: next };
      if (session.timer) clearTimeout(session.timer);
      session.timer = setTimeout(() => {
        session.timer = null;
        void drain(session);
      }, SAVE_DEBOUNCE_MS);
    },
    [drain, loadFailed],
  );

  const resetPreference = useCallback(() => {
    const session = sessionRef.current;
    if (!session || session.disposed || loadFailed) return;
    setPreferenceState(null);
    session.failedOperation = null;
    session.pendingOperation = { kind: 'delete', conflictRetries: 0 };
    if (session.timer) clearTimeout(session.timer);
    session.timer = null;
    void drain(session);
  }, [drain, loadFailed]);

  const retry = useCallback(() => {
    const session = sessionRef.current;
    if (!session || session.disposed) return;
    if (session.failedOperation === 'load') {
      void load(session);
      return;
    }
    if (!session.failedOperation) return;
    session.pendingOperation =
      session.failedOperation.kind === 'delete'
        ? { kind: 'delete', conflictRetries: 0 }
        : session.failedOperation;
    session.failedOperation = null;
    void drain(session);
  }, [drain, load]);

  return {
    loadFailed,
    preference,
    resetPreference,
    retry,
    status,
    updatePreference,
  };
}
