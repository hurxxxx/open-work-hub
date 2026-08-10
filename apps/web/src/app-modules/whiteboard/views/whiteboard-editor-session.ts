import type { SaveStatus } from './whiteboard-editor-utils';

export const WHITEBOARD_SCENE_SAVE_DEBOUNCE_MS = 800;
export const WHITEBOARD_SCENE_SAVE_RETRY_MS = 250;
export const WHITEBOARD_LOCAL_CHANGE_FLUSH_MS = 160;
export const WHITEBOARD_COLLAB_PUBLISH_RETRY_MS = 250;
export const WHITEBOARD_SAVE_SETTLED_BUFFER_MS = 80;
export const WHITEBOARD_CLOSE_FLUSH_MAX_ATTEMPTS = 80;
export const WHITEBOARD_CLOSE_FLUSH_RETRY_MS = 50;

export type WhiteboardSceneSaveScheduleDecision = {
  nextStatus: Extract<SaveStatus, 'dirty'> | null;
  shouldQueue: boolean;
  shouldSchedule: boolean;
};

export type WhiteboardCloseFlushStep =
  | 'timed-out'
  | 'flush-local-change'
  | 'flush-scene-save'
  | 'settled-failed'
  | 'settled-succeeded'
  | 'wait';

export type WhiteboardLocalSceneDecision =
  | {
      nextStatus: Extract<SaveStatus, 'idle'> | null;
      type: 'ignore-remote-echo';
    }
  | { nextStatus: Extract<SaveStatus, 'idle'> | null; type: 'ignore-saved' }
  | {
      nextStatus: Extract<SaveStatus, 'saved'> | null;
      type: 'ignore-published';
    }
  | { type: 'ignore-pending-duplicate' }
  | { nextStatus: Extract<SaveStatus, 'dirty'>; type: 'queue-local-scene' };

export function resolveWhiteboardSceneSaveSchedule({
  boardId,
  canEdit,
  lastSavedSignature,
  pendingSignature,
  saveInFlight,
  saveTimerActive,
  signature,
}: {
  boardId: string | null;
  canEdit: boolean;
  lastSavedSignature: string | null;
  pendingSignature: string | null;
  saveInFlight: boolean;
  saveTimerActive: boolean;
  signature: string;
}): WhiteboardSceneSaveScheduleDecision {
  if (
    !boardId ||
    !canEdit ||
    signature === lastSavedSignature ||
    signature === pendingSignature
  ) {
    return {
      nextStatus: null,
      shouldQueue: false,
      shouldSchedule: false,
    };
  }

  return {
    nextStatus: 'dirty',
    shouldQueue: true,
    shouldSchedule: !saveInFlight && !saveTimerActive,
  };
}

export function resolveWhiteboardSaveSettledStatus({
  localChangeTimerActive,
  pendingLocalChange,
  pendingScene,
  saveInFlight,
}: {
  localChangeTimerActive: boolean;
  pendingLocalChange: boolean;
  pendingScene: boolean;
  saveInFlight: boolean;
}): Extract<SaveStatus, 'saved'> | null {
  return !saveInFlight &&
    !pendingScene &&
    !pendingLocalChange &&
    !localChangeTimerActive
    ? 'saved'
    : null;
}

export function describeWhiteboardLocalSceneChange({
  lastAppliedRemoteSignature,
  lastPublishedCollabSignature,
  lastSavedSignature,
  pendingScene,
  pendingSceneSignature,
  saveInFlight,
  signature,
}: {
  lastAppliedRemoteSignature: string | null;
  lastPublishedCollabSignature: string | null;
  lastSavedSignature: string | null;
  pendingScene: boolean;
  pendingSceneSignature: string | null;
  saveInFlight: boolean;
  signature: string;
}): WhiteboardLocalSceneDecision {
  if (signature === lastAppliedRemoteSignature) {
    return {
      nextStatus: pendingScene ? null : 'idle',
      type: 'ignore-remote-echo',
    };
  }
  if (signature === lastSavedSignature) {
    return {
      nextStatus: pendingScene ? null : 'idle',
      type: 'ignore-saved',
    };
  }
  if (signature === lastPublishedCollabSignature) {
    return {
      nextStatus: !pendingScene && !saveInFlight ? 'saved' : null,
      type: 'ignore-published',
    };
  }
  if (signature === pendingSceneSignature) {
    return { type: 'ignore-pending-duplicate' };
  }
  return { nextStatus: 'dirty', type: 'queue-local-scene' };
}

export function getWhiteboardSaveSettledDelay({
  localChangeFlushMs,
}: {
  localChangeFlushMs: number;
}): number {
  return localChangeFlushMs + WHITEBOARD_SAVE_SETTLED_BUFFER_MS;
}

export function resolveWhiteboardCloseFlushStep({
  attempt,
  lastSaveFailed,
  localChangeTimerActive,
  maxAttempts = WHITEBOARD_CLOSE_FLUSH_MAX_ATTEMPTS,
  pendingLocalChange,
  pendingScene,
  saveInFlight,
}: {
  attempt: number;
  lastSaveFailed: boolean;
  localChangeTimerActive: boolean;
  maxAttempts?: number;
  pendingLocalChange: boolean;
  pendingScene: boolean;
  saveInFlight: boolean;
}): WhiteboardCloseFlushStep {
  if (attempt >= maxAttempts) {
    return 'timed-out';
  }
  if (pendingLocalChange || localChangeTimerActive) {
    return 'flush-local-change';
  }
  if (pendingScene && !saveInFlight) {
    return 'flush-scene-save';
  }
  if (!saveInFlight && !pendingScene) {
    return lastSaveFailed ? 'settled-failed' : 'settled-succeeded';
  }
  return 'wait';
}
