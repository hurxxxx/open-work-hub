import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WhiteboardDetail, WhiteboardScene } from '../api/whiteboard-api';
import {
  useWhiteboardScenePersistence,
  type PendingWhiteboardEditorChange,
  type UseWhiteboardScenePersistenceOptions,
} from './useWhiteboardScenePersistence';

const api = vi.hoisted(() => ({
  updateWhiteboard: vi.fn(),
  updateSharedWhiteboard: vi.fn(),
  saveWhiteboardCollabSnapshot: vi.fn(),
}));
vi.mock('../api/whiteboard-api', async (original) => ({
  ...(await original<typeof import('../api/whiteboard-api')>()),
  ...api,
}));
vi.mock('@excalidraw/excalidraw', () => ({
  getSceneVersion: (elements: Array<{ version: number }>) =>
    elements.reduce((sum, element) => sum + element.version, 0),
  serializeAsJSON: (elements: unknown[], appState: unknown, files: unknown) =>
    JSON.stringify({ elements, appState, files }),
}));
const emptyScene: WhiteboardScene = { elements: [], appState: {}, files: {} };
function change(version: number): PendingWhiteboardEditorChange {
  return {
    elements: [{ id: 'shape', version }],
    appState: {},
    files: {},
  } as unknown as PendingWhiteboardEditorChange;
}
function options(
  shareToken: string | null = null,
): UseWhiteboardScenePersistenceOptions {
  const board = {
    id: 'board',
    can_edit: true,
    scene: emptyScene,
  } as WhiteboardDetail;
  return {
    activeBoard: board,
    activeBoardIdRef: { current: 'board' },
    activeBoardRef: { current: board },
    applyingRemoteSceneRef: { current: false },
    collabDocRef: { current: null },
    lastAppliedRemoteSceneSignatureRef: { current: null },
    lastPublishedCollabSignatureRef: { current: null },
    onBoardUpdated: vi.fn(),
    publishSceneToCollab: vi.fn(() => true),
    setActiveBoard: vi.fn(),
    setError: vi.fn(),
    shareToken,
    token: 'test-token',
    translate: (key) => key,
  };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('Whiteboard scene persistence lifecycle', () => {
  it('cancels queued autosave and collab publication when access invalidation removes the editor', async () => {
    const opts = options();
    const { result, unmount } = renderHook(() =>
      useWhiteboardScenePersistence(opts),
    );
    act(() => {
      result.current.resetLoadedScene(emptyScene);
      result.current.queueLocalChange(change(1));
    });
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.updateWhiteboard).not.toHaveBeenCalled();
    expect(opts.publishSceneToCollab).not.toHaveBeenCalled();
    expect(opts.onBoardUpdated).not.toHaveBeenCalled();
  });

  it.each([null, 'link-lens'])(
    'discards a late save response and cannot revive queued writes after invalidation (%s)',
    async (shareToken) => {
      const opts = options(shareToken);
      let resolveSave!: (value: WhiteboardDetail) => void;
      const save = shareToken
        ? api.updateSharedWhiteboard
        : api.updateWhiteboard;
      save.mockImplementationOnce(
        () =>
          new Promise<WhiteboardDetail>((resolve) => {
            resolveSave = resolve;
          }),
      );
      const { result, unmount } = renderHook(() =>
        useWhiteboardScenePersistence(opts),
      );
      act(() => {
        result.current.resetLoadedScene(emptyScene);
        result.current.queueLocalChange(change(1));
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(save).toHaveBeenCalledTimes(1);
      act(() => {
        result.current.queueLocalChange(change(2));
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200);
      });
      const publicationsBeforeUnmount = vi.mocked(opts.publishSceneToCollab)
        .mock.calls.length;
      unmount();
      await act(async () => {
        if (!opts.activeBoard) throw new Error('Expected active board');
        resolveSave(opts.activeBoard);
        await vi.advanceTimersByTimeAsync(5000);
      });
      expect(save).toHaveBeenCalledTimes(1);
      expect(opts.onBoardUpdated).not.toHaveBeenCalled();
      expect(opts.setActiveBoard).not.toHaveBeenCalled();
      expect(opts.publishSceneToCollab).toHaveBeenCalledTimes(
        publicationsBeforeUnmount,
      );
      expect(vi.getTimerCount()).toBe(0);
    },
  );
});
