import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type {
  DocsCollabSnapshotResponse,
  saveDocsCollabSnapshot,
} from '../api/docs-api';
import {
  type DocsCollabSnapshotSaveControllerOptions,
  useDocsCollabSnapshotSaveController,
} from './useDocsCollabSnapshotSaveController';

type SaveDocsCollabSnapshot = typeof saveDocsCollabSnapshot;

function renderController(
  overrides: Partial<DocsCollabSnapshotSaveControllerOptions> = {},
) {
  const snapshot: DocsCollabSnapshotResponse = {
    updated_at: '2026-06-19T00:00:00Z',
    last_snapshot_at: '2026-06-19T00:00:00Z',
  };
  const saveSnapshot = vi.fn<SaveDocsCollabSnapshot>(async () => snapshot);
  const onSavedSnapshot = vi.fn<(saved: DocsCollabSnapshotResponse) => void>();
  const hook = renderHook(() =>
    useDocsCollabSnapshotSaveController({
      token: 'token-1',
      saveSnapshot,
      onSavedSnapshot,
      ...overrides,
    }),
  );

  return { ...hook, onSavedSnapshot, saveSnapshot, snapshot };
}

describe('useDocsCollabSnapshotSaveController', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('debounces collaboration snapshot saves and persists the latest blocks', async () => {
    vi.useFakeTimers();
    const { result, saveSnapshot, onSavedSnapshot, snapshot } = renderController({
      workspaceSlug: 'ai-tft',
    });
    const oldBlocks = [{ type: 'paragraph', content: [{ text: 'Old' }] }];
    const latestBlocks = [{ type: 'paragraph', content: [{ text: 'Latest' }] }];

    act(() => {
      result.current.queueSnapshotSave('native_doc_page__page-1', oldBlocks);
      result.current.queueSnapshotSave('native_doc_page__page-1', latestBlocks);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(saveSnapshot).toHaveBeenCalledTimes(1);
    expect(saveSnapshot).toHaveBeenCalledWith(
      'token-1',
      'native_doc_page__page-1',
      { content_blocks: latestBlocks },
      'ai-tft',
    );
    expect(onSavedSnapshot).toHaveBeenCalledWith(snapshot);
  });

  it('flushes a pending collaboration snapshot immediately', async () => {
    vi.useFakeTimers();
    const { result, saveSnapshot } = renderController();
    const blocks = [{ type: 'paragraph', content: [{ text: 'Draft' }] }];

    act(() => {
      result.current.queueSnapshotSave('native_doc_page__page-1', blocks);
    });
    await act(async () => {
      await result.current.flushSnapshotSave();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(saveSnapshot).toHaveBeenCalledTimes(1);
    expect(saveSnapshot).toHaveBeenCalledWith(
      'token-1',
      'native_doc_page__page-1',
      { content_blocks: blocks },
      undefined,
    );
  });

  it('includes the latest Yjs state when one is provided', async () => {
    vi.useFakeTimers();
    const { result, saveSnapshot } = renderController();
    const blocks = [{ type: 'paragraph', content: [{ text: 'Yjs' }] }];

    act(() => {
      result.current.queueSnapshotSave(
        'native_doc_page__page-1',
        blocks,
        'base64-yjs-state',
      );
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });

    expect(saveSnapshot).toHaveBeenCalledWith(
      'token-1',
      'native_doc_page__page-1',
      { content_blocks: blocks, yjs_state: 'base64-yjs-state' },
      undefined,
    );
  });

  it('flushes a pending collaboration snapshot with keepalive before page unload', async () => {
    vi.useFakeTimers();
    const { result, saveSnapshot } = renderController();
    const blocks = [{ type: 'paragraph', content: [{ text: 'Unload' }] }];

    act(() => {
      result.current.queueSnapshotSave('native_doc_page__page-1', blocks);
      window.dispatchEvent(new Event('pagehide'));
    });

    expect(saveSnapshot).toHaveBeenCalledTimes(1);
    expect(saveSnapshot).toHaveBeenCalledWith(
      'token-1',
      'native_doc_page__page-1',
      { content_blocks: blocks },
      undefined,
      { keepalive: true },
    );
  });

  it('does not save without a token', async () => {
    vi.useFakeTimers();
    const { result, saveSnapshot } = renderController({ token: null });

    act(() => {
      result.current.queueSnapshotSave('native_doc_page__page-1', []);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(saveSnapshot).not.toHaveBeenCalled();
  });
});
