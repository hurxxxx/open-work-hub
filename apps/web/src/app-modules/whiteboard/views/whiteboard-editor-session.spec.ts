import { describe, expect, it } from 'vitest';

import {
  WHITEBOARD_CLOSE_FLUSH_MAX_ATTEMPTS,
  WHITEBOARD_CLOSE_FLUSH_RETRY_MS,
  WHITEBOARD_LOCAL_CHANGE_FLUSH_MS,
  WHITEBOARD_SCENE_SAVE_DEBOUNCE_MS,
  WHITEBOARD_SCENE_SAVE_RETRY_MS,
  WHITEBOARD_SAVE_SETTLED_BUFFER_MS,
  describeWhiteboardLocalSceneChange,
  getWhiteboardSaveSettledDelay,
  resolveWhiteboardCloseFlushStep,
  resolveWhiteboardSaveSettledStatus,
  resolveWhiteboardSceneSaveSchedule,
} from './whiteboard-editor-session';

describe('whiteboard editor session', () => {
  it('decides whether a scene should be queued and scheduled for save', () => {
    expect(
      resolveWhiteboardSceneSaveSchedule({
        boardId: 'board-1',
        canEdit: true,
        lastSavedSignature: 'old',
        pendingSignature: null,
        saveInFlight: false,
        saveTimerActive: false,
        signature: 'new',
      }),
    ).toEqual({
      nextStatus: 'dirty',
      shouldQueue: true,
      shouldSchedule: true,
    });

    expect(
      resolveWhiteboardSceneSaveSchedule({
        boardId: 'board-1',
        canEdit: true,
        lastSavedSignature: 'new',
        pendingSignature: null,
        saveInFlight: false,
        saveTimerActive: false,
        signature: 'new',
      }).shouldQueue,
    ).toBe(false);
    expect(
      resolveWhiteboardSceneSaveSchedule({
        boardId: 'board-1',
        canEdit: true,
        lastSavedSignature: 'old',
        pendingSignature: null,
        saveInFlight: true,
        saveTimerActive: false,
        signature: 'new',
      }),
    ).toEqual({
      nextStatus: 'dirty',
      shouldQueue: true,
      shouldSchedule: false,
    });
  });

  it('reports when saved status can settle', () => {
    expect(
      resolveWhiteboardSaveSettledStatus({
        localChangeTimerActive: false,
        pendingLocalChange: false,
        pendingScene: false,
        saveInFlight: false,
      }),
    ).toBe('saved');
    expect(
      resolveWhiteboardSaveSettledStatus({
        localChangeTimerActive: true,
        pendingLocalChange: false,
        pendingScene: false,
        saveInFlight: false,
      }),
    ).toBeNull();
    expect(getWhiteboardSaveSettledDelay({ localChangeFlushMs: 160 })).toBe(
      160 + WHITEBOARD_SAVE_SETTLED_BUFFER_MS,
    );
  });

  it('describes local scene signature decisions', () => {
    expect(
      describeWhiteboardLocalSceneChange({
        lastAppliedRemoteSignature: 'same',
        lastPublishedCollabSignature: null,
        lastSavedSignature: null,
        pendingScene: false,
        pendingSceneSignature: null,
        saveInFlight: false,
        signature: 'same',
      }),
    ).toEqual({ nextStatus: 'idle', type: 'ignore-remote-echo' });
    expect(
      describeWhiteboardLocalSceneChange({
        lastAppliedRemoteSignature: null,
        lastPublishedCollabSignature: null,
        lastSavedSignature: 'same',
        pendingScene: true,
        pendingSceneSignature: null,
        saveInFlight: false,
        signature: 'same',
      }),
    ).toEqual({ nextStatus: null, type: 'ignore-saved' });
    expect(
      describeWhiteboardLocalSceneChange({
        lastAppliedRemoteSignature: null,
        lastPublishedCollabSignature: 'same',
        lastSavedSignature: null,
        pendingScene: false,
        pendingSceneSignature: null,
        saveInFlight: false,
        signature: 'same',
      }),
    ).toEqual({ nextStatus: 'saved', type: 'ignore-published' });
    expect(
      describeWhiteboardLocalSceneChange({
        lastAppliedRemoteSignature: null,
        lastPublishedCollabSignature: null,
        lastSavedSignature: null,
        pendingScene: true,
        pendingSceneSignature: 'same',
        saveInFlight: false,
        signature: 'same',
      }),
    ).toEqual({ type: 'ignore-pending-duplicate' });
    expect(
      describeWhiteboardLocalSceneChange({
        lastAppliedRemoteSignature: null,
        lastPublishedCollabSignature: null,
        lastSavedSignature: null,
        pendingScene: false,
        pendingSceneSignature: null,
        saveInFlight: false,
        signature: 'new',
      }),
    ).toEqual({ nextStatus: 'dirty', type: 'queue-local-scene' });
  });

  it('resolves close flush steps in priority order', () => {
    expect(
      resolveWhiteboardCloseFlushStep({
        attempt: WHITEBOARD_CLOSE_FLUSH_MAX_ATTEMPTS,
        lastSaveFailed: false,
        localChangeTimerActive: false,
        pendingLocalChange: false,
        pendingScene: false,
        saveInFlight: false,
      }),
    ).toBe('timed-out');
    expect(
      resolveWhiteboardCloseFlushStep({
        attempt: 0,
        lastSaveFailed: false,
        localChangeTimerActive: true,
        pendingLocalChange: false,
        pendingScene: true,
        saveInFlight: false,
      }),
    ).toBe('flush-local-change');
    expect(
      resolveWhiteboardCloseFlushStep({
        attempt: 0,
        lastSaveFailed: false,
        localChangeTimerActive: false,
        pendingLocalChange: false,
        pendingScene: true,
        saveInFlight: false,
      }),
    ).toBe('flush-scene-save');
    expect(
      resolveWhiteboardCloseFlushStep({
        attempt: 0,
        lastSaveFailed: true,
        localChangeTimerActive: false,
        pendingLocalChange: false,
        pendingScene: false,
        saveInFlight: false,
      }),
    ).toBe('settled-failed');
    expect(
      resolveWhiteboardCloseFlushStep({
        attempt: 0,
        lastSaveFailed: false,
        localChangeTimerActive: false,
        pendingLocalChange: false,
        pendingScene: false,
        saveInFlight: true,
      }),
    ).toBe('wait');
  });

  it('keeps timing constants explicit at the session seam', () => {
    expect(WHITEBOARD_SCENE_SAVE_DEBOUNCE_MS).toBe(800);
    expect(WHITEBOARD_SCENE_SAVE_RETRY_MS).toBe(250);
    expect(WHITEBOARD_LOCAL_CHANGE_FLUSH_MS).toBe(160);
    expect(WHITEBOARD_CLOSE_FLUSH_RETRY_MS).toBe(50);
  });
});
