import { useCallback, useEffect, useRef } from 'react';

import type { DocsPageItem } from '../api/docs-api';

type DocsPageContentSavePayload =
  | { content_blocks: Record<string, unknown>[] }
  | { content_text: string };

interface PendingContentTextSave {
  pageId: string;
  contentText: string;
}

export interface DocsPageContentSaveControllerOptions {
  token: string | null | undefined;
  shareToken?: string | null;
  workspaceSlug?: string | null;
  debounceMs?: number;
  flushOnUnmount?: boolean;
  savePage: (
    token: string,
    pageId: string,
    payload: DocsPageContentSavePayload,
    shareToken?: string | null,
    workspaceSlug?: string | null,
  ) => Promise<DocsPageItem>;
  onSavedPage: (page: DocsPageItem) => void;
}

export function useDocsPageContentSaveController({
  token,
  shareToken,
  workspaceSlug,
  debounceMs = 800,
  flushOnUnmount = false,
  savePage,
  onSavedPage,
}: DocsPageContentSaveControllerOptions) {
  const latestConfigRef = useRef({
    token,
    shareToken,
    workspaceSlug,
    savePage,
    onSavedPage,
  });
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingContentTextSaveRef = useRef<PendingContentTextSave | null>(null);

  latestConfigRef.current = {
    token,
    shareToken,
    workspaceSlug,
    savePage,
    onSavedPage,
  };

  const clearSaveTimer = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
  }, []);

  const flushTextSave = useCallback(async () => {
    const pending = pendingContentTextSaveRef.current;
    if (!pending) return;
    const config = latestConfigRef.current;
    if (!config.token) return;
    clearSaveTimer();
    pendingContentTextSaveRef.current = null;
    try {
      const updated = await config.savePage(
        config.token,
        pending.pageId,
        { content_text: pending.contentText },
        config.shareToken,
        config.workspaceSlug,
      );
      config.onSavedPage(updated);
    } catch {
      // Local editor state remains the source of truth until the next save.
    }
  }, [clearSaveTimer]);

  const queueBlockSave = useCallback(
    (pageId: string, blocks: Record<string, unknown>[]) => {
      if (!latestConfigRef.current.token) return;
      clearSaveTimer();
      saveTimerRef.current = setTimeout(async () => {
        const config = latestConfigRef.current;
        if (!config.token) return;
        try {
          const updated = await config.savePage(
            config.token,
            pageId,
            { content_blocks: blocks },
            config.shareToken,
            config.workspaceSlug,
          );
          config.onSavedPage(updated);
        } catch {
          // Local editor state remains the source of truth until the next save.
        }
      }, debounceMs);
    },
    [clearSaveTimer, debounceMs],
  );

  const queueTextSave = useCallback(
    (pageId: string, contentText: string) => {
      if (!latestConfigRef.current.token) return;
      pendingContentTextSaveRef.current = { pageId, contentText };
      clearSaveTimer();
      saveTimerRef.current = setTimeout(() => {
        void flushTextSave();
      }, debounceMs);
    },
    [clearSaveTimer, debounceMs, flushTextSave],
  );

  const cancelQueuedSave = useCallback(() => {
    clearSaveTimer();
    pendingContentTextSaveRef.current = null;
  }, [clearSaveTimer]);

  useEffect(
    () => () => {
      if (!flushOnUnmount) return;
      clearSaveTimer();
      void flushTextSave();
    },
    [clearSaveTimer, flushOnUnmount, flushTextSave],
  );

  return {
    cancelQueuedSave,
    flushTextSave,
    queueBlockSave,
    queueTextSave,
  };
}
