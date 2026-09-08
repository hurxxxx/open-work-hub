import { describe, expect, it } from 'vitest';

import type {
  WhiteboardDetail,
  WhiteboardHubItem,
  WhiteboardScene,
} from '../api/whiteboard-api';
import {
  createWhiteboardPreviewLoader,
  createWhiteboardPreviewState,
  getWhiteboardPreviewSourceKey,
  renderWhiteboardScenePreview,
  whiteboardPreviewReducer,
  type CreateWhiteboardPreviewLoaderOptions,
} from './whiteboard-preview-loader';

function hubItem(
  overrides: Partial<WhiteboardHubItem> = {},
): WhiteboardHubItem {
  return {
    id: 'board-1',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as WhiteboardHubItem;
}

function detail(scene: WhiteboardScene): WhiteboardDetail {
  return {
    ...hubItem(),
    scene,
  } as WhiteboardDetail;
}

function scene(
  elements: unknown[] = [{ id: 'element-1', type: 'rectangle' }],
): WhiteboardScene {
  return {
    elements,
    appState: {},
    files: {},
  };
}

describe('whiteboard preview loader', () => {
  it('builds source keys from the item id and update timestamp', () => {
    expect(
      getWhiteboardPreviewSourceKey(
        hubItem({ id: 'board-7', updated_at: 'v2' }),
      ),
    ).toBe('board-7:v2');
  });

  it('keeps preview state transitions deterministic', () => {
    const initial = createWhiteboardPreviewState('board-1:v1');
    const loading = whiteboardPreviewReducer(initial, {
      type: 'previewVisible',
      sourceKey: 'board-1:v1',
    });
    const ready = whiteboardPreviewReducer(loading, {
      type: 'previewLoaded',
      sourceKey: 'board-1:v1',
      previewUrl: 'blob:preview',
    });
    const empty = whiteboardPreviewReducer(ready, {
      type: 'previewLoaded',
      sourceKey: 'board-1:v1',
      previewUrl: null,
    });
    const failed = whiteboardPreviewReducer(ready, {
      type: 'previewFailed',
      sourceKey: 'board-1:v1',
    });

    expect(loading).toEqual({
      sourceKey: 'board-1:v1',
      status: 'loading',
      previewUrl: null,
    });
    expect(ready).toEqual({
      sourceKey: 'board-1:v1',
      status: 'ready',
      previewUrl: 'blob:preview',
    });
    expect(empty).toEqual({
      sourceKey: 'board-1:v1',
      status: 'empty',
      previewUrl: null,
    });
    expect(failed).toEqual({
      sourceKey: 'board-1:v1',
      status: 'error',
      previewUrl: null,
    });
  });

  it('resets stale preview state when the source key changes', () => {
    const ready = {
      sourceKey: 'board-1:v1',
      status: 'ready',
      previewUrl: 'blob:old',
    } as const;

    expect(
      whiteboardPreviewReducer(ready, {
        type: 'previewVisible',
        sourceKey: 'board-1:v2',
      }),
    ).toEqual({ sourceKey: 'board-1:v2', status: 'loading', previewUrl: null });
  });

  it('shares in-flight loads and caches resolved preview URLs', async () => {
    let fetchCalls = 0;
    let renderCalls = 0;
    const fetchWhiteboard: CreateWhiteboardPreviewLoaderOptions['fetchWhiteboard'] =
      async (_token, itemId) => {
        fetchCalls += 1;
        expect(itemId).toBe('board-1');
        return detail(scene());
      };
    const loader = createWhiteboardPreviewLoader({
      fetchWhiteboard,
      renderScenePreview: async () => {
        renderCalls += 1;
        return 'blob:preview';
      },
    });
    const item = hubItem();

    const first = loader.load('token', item);
    const second = loader.load('token', item);

    await expect(Promise.all([first, second])).resolves.toEqual([
      'blob:preview',
      'blob:preview',
    ]);
    await expect(loader.load('token', item)).resolves.toBe('blob:preview');
    expect(fetchCalls).toBe(1);
    expect(renderCalls).toBe(1);
  });

  it('caches null previews for empty scenes', async () => {
    let fetchCalls = 0;
    const loader = createWhiteboardPreviewLoader({
      fetchWhiteboard: async () => {
        fetchCalls += 1;
        return detail(scene());
      },
      renderScenePreview: async () => null,
    });

    await expect(loader.load('token', hubItem())).resolves.toBeNull();
    await expect(loader.load('token', hubItem())).resolves.toBeNull();
    expect(fetchCalls).toBe(1);
  });

  it('does not cache rejected preview loads', async () => {
    let renderCalls = 0;
    const loader = createWhiteboardPreviewLoader({
      fetchWhiteboard: async () => detail(scene()),
      renderScenePreview: async () => {
        renderCalls += 1;
        if (renderCalls === 1) throw new Error('preview failed');
        return 'blob:retry';
      },
    });

    await expect(loader.load('token', hubItem())).rejects.toThrow(
      'preview failed',
    );
    await expect(loader.load('token', hubItem())).resolves.toBe('blob:retry');
    expect(renderCalls).toBe(2);
  });

  it('does not render empty or deleted-only scenes', async () => {
    await expect(renderWhiteboardScenePreview(scene([]))).resolves.toBeNull();
    await expect(
      renderWhiteboardScenePreview(
        scene([{ id: 'deleted', type: 'rectangle', isDeleted: true }]),
      ),
    ).resolves.toBeNull();
  });
});
