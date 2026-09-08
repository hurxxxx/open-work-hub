import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DocsPageItem } from '../api/docs-api';
import {
  type DocsPageContentSaveControllerOptions,
  useDocsPageContentSaveController,
} from './useDocsPageContentSaveController';

function page(overrides: Partial<DocsPageItem> = {}): DocsPageItem {
  return {
    id: 'page-1',
    doc_id: 'doc-1',
    title: 'Page',
    parent_id: null,
    sort_order: 1000,
    depth: 0,
    content_format: 'block',
    content_blocks: [],
    content_text: null,
    can_edit: true,
    trashed_at: null,
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    ...overrides,
  } as DocsPageItem;
}

function renderController(
  overrides: Partial<DocsPageContentSaveControllerOptions> = {},
) {
  const savedPage = page({ id: 'saved-page' });
  const savePage = vi.fn<DocsPageContentSaveControllerOptions['savePage']>(
    async () => savedPage,
  );
  const onSavedPage = vi.fn<(updated: DocsPageItem) => void>();
  const hook = renderHook(() =>
    useDocsPageContentSaveController({
      token: 'token-1',
      savePage,
      onSavedPage,
      ...overrides,
    }),
  );

  return { ...hook, onSavedPage, savePage, savedPage };
}

describe('useDocsPageContentSaveController', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it.each(['block', 'text'] as const)(
    'cancels queued %s writes when the authority-owned view unmounts',
    async (format) => {
      vi.useFakeTimers();
      const { result, unmount, savePage } = renderController();
      act(() => {
        if (format === 'block')
          result.current.queueBlockSave('page-1', [{ type: 'paragraph' }]);
        else result.current.queueTextSave('page-1', 'revoked draft');
      });
      unmount();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(800);
      });
      expect(savePage).not.toHaveBeenCalled();
    },
  );

  it('debounces text saves and persists only the latest pending text', async () => {
    vi.useFakeTimers();
    const { result, savePage, onSavedPage, savedPage } = renderController({
      shareToken: 'share-1',
    });

    act(() => {
      result.current.queueTextSave('page-1', 'old');
      result.current.queueTextSave('page-2', 'latest');
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(savePage).toHaveBeenCalledTimes(1);
    expect(savePage).toHaveBeenCalledWith(
      'token-1',
      'page-2',
      { content_text: 'latest' },
      'share-1',
    );
    expect(onSavedPage).toHaveBeenCalledWith(savedPage);
  });

  it('flushes a pending text save immediately and clears the debounce timer', async () => {
    vi.useFakeTimers();
    const { result, savePage } = renderController();

    act(() => {
      result.current.queueTextSave('page-1', 'draft');
    });
    await act(async () => {
      await result.current.flushTextSave();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(savePage).toHaveBeenCalledTimes(1);
    expect(savePage).toHaveBeenCalledWith(
      'token-1',
      'page-1',
      { content_text: 'draft' },
      undefined,
    );
  });

  it('cancels a queued text save without persisting it', async () => {
    vi.useFakeTimers();
    const { result, savePage, onSavedPage } = renderController();

    act(() => {
      result.current.queueTextSave('page-1', 'draft');
      result.current.cancelQueuedSave();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(savePage).not.toHaveBeenCalled();
    expect(onSavedPage).not.toHaveBeenCalled();
  });

  it('debounces block saves with the current page blocks', async () => {
    vi.useFakeTimers();
    const { result, savePage } = renderController();
    const blocks = [{ type: 'paragraph', content: [{ text: 'Block' }] }];

    act(() => {
      result.current.queueBlockSave('page-1', blocks);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(savePage).toHaveBeenCalledTimes(1);
    expect(savePage).toHaveBeenCalledWith(
      'token-1',
      'page-1',
      { content_blocks: blocks },
      undefined,
    );
  });

  it('swallows save failures and leaves saved-page callbacks untouched', async () => {
    vi.useFakeTimers();
    const savePage = vi.fn<DocsPageContentSaveControllerOptions['savePage']>(
      async () => {
        throw new Error('save failed');
      },
    );
    const onSavedPage = vi.fn<(updated: DocsPageItem) => void>();
    const { result } = renderHook(() =>
      useDocsPageContentSaveController({
        token: 'token-1',
        savePage,
        onSavedPage,
      }),
    );

    act(() => {
      result.current.queueTextSave('page-1', 'draft');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(savePage).toHaveBeenCalledTimes(1);
    expect(onSavedPage).not.toHaveBeenCalled();
  });
});
