import { useCallback, useEffect, useRef } from 'react';

import type {
  DocsCollabSnapshotResponse,
  saveDocsCollabSnapshot,
} from '../api/docs-api';

type SaveDocsCollabSnapshot = typeof saveDocsCollabSnapshot;

interface PendingCollabSnapshotSave {
  pageRef: string;
  contentBlocks: Record<string, unknown>[];
  yjsState?: string | null;
}

interface FlushSnapshotSaveOptions {
  keepalive?: boolean;
}

export interface DocsCollabSnapshotSaveControllerOptions {
  token: string | null | undefined;

  debounceMs?: number;
  flushOnUnmount?: boolean;
  saveSnapshot: SaveDocsCollabSnapshot;
  onSavedSnapshot?: (snapshot: DocsCollabSnapshotResponse) => void;
}

export function useDocsCollabSnapshotSaveController({
  token,
  debounceMs = 250,
  flushOnUnmount = true,
  saveSnapshot,
  onSavedSnapshot,
}: DocsCollabSnapshotSaveControllerOptions) {
  const latestConfigRef = useRef({
    token,
    saveSnapshot,
    onSavedSnapshot,
  });
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSnapshotRef = useRef<PendingCollabSnapshotSave | null>(null);

  latestConfigRef.current = {
    token,
    saveSnapshot,
    onSavedSnapshot,
  };

  const clearSaveTimer = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
  }, []);

  const flushSnapshotSave = useCallback(
    async (options: FlushSnapshotSaveOptions = {}) => {
      const pending = pendingSnapshotRef.current;
      if (!pending) return;
      const config = latestConfigRef.current;
      if (!config.token) return;
      clearSaveTimer();
      pendingSnapshotRef.current = null;
      try {
        const snapshotPayload = {
          content_blocks: pending.contentBlocks,
          ...(pending.yjsState ? { yjs_state: pending.yjsState } : {}),
        };
        const snapshot = options.keepalive
          ? await config.saveSnapshot(
              config.token,
              pending.pageRef,
              snapshotPayload,
              { keepalive: true },
            )
          : await config.saveSnapshot(
              config.token,
              pending.pageRef,
              snapshotPayload,
            );
        config.onSavedSnapshot?.(snapshot);
      } catch {
        // Collaboration remains live; the next edit or server-side flush can retry.
      }
    },
    [clearSaveTimer],
  );

  const queueSnapshotSave = useCallback(
    (
      pageRef: string,
      contentBlocks: Record<string, unknown>[],
      yjsState?: string | null,
    ) => {
      if (!latestConfigRef.current.token) return;
      pendingSnapshotRef.current = { pageRef, contentBlocks, yjsState };
      clearSaveTimer();
      saveTimerRef.current = setTimeout(() => {
        void flushSnapshotSave();
      }, debounceMs);
    },
    [clearSaveTimer, debounceMs, flushSnapshotSave],
  );

  useEffect(() => {
    if (!flushOnUnmount) return undefined;

    const flushBeforePageLeaves = () => {
      void flushSnapshotSave({ keepalive: true });
    };
    const flushWhenHidden = () => {
      if (document.visibilityState === 'hidden') {
        void flushSnapshotSave({ keepalive: true });
      }
    };

    window.addEventListener('beforeunload', flushBeforePageLeaves);
    window.addEventListener('pagehide', flushBeforePageLeaves);
    document.addEventListener('visibilitychange', flushWhenHidden);

    return () => {
      window.removeEventListener('beforeunload', flushBeforePageLeaves);
      window.removeEventListener('pagehide', flushBeforePageLeaves);
      document.removeEventListener('visibilitychange', flushWhenHidden);
      clearSaveTimer();
      void flushSnapshotSave();
    };
  }, [clearSaveTimer, flushOnUnmount, flushSnapshotSave]);

  return {
    flushSnapshotSave,
    queueSnapshotSave,
  };
}
