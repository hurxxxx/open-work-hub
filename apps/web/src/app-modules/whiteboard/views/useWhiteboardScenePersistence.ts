import { getSceneVersion, serializeAsJSON } from '@excalidraw/excalidraw';
import type { ExcalidrawProps } from '@excalidraw/excalidraw/types';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from 'react';

import {
  saveWhiteboardCollabSnapshot,
  updateSharedWhiteboard,
  updateWhiteboard,
  type WhiteboardDetail,
  type WhiteboardScene,
} from '../api/whiteboard-api';
import {
  WHITEBOARD_REMOTE_APPLY_GUARD_MS,
  encodeWhiteboardCollabDocumentState,
  type WhiteboardCollabDocument,
} from './whiteboard-collab-runtime';
import { sceneFromExcalidraw, sceneSignature } from './whiteboard-collab-scene';
import {
  WHITEBOARD_CLOSE_FLUSH_RETRY_MS,
  WHITEBOARD_COLLAB_PUBLISH_RETRY_MS,
  WHITEBOARD_LOCAL_CHANGE_FLUSH_MS,
  WHITEBOARD_SCENE_SAVE_DEBOUNCE_MS,
  WHITEBOARD_SCENE_SAVE_RETRY_MS,
  describeWhiteboardLocalSceneChange,
  getWhiteboardSaveSettledDelay,
  resolveWhiteboardCloseFlushStep,
  resolveWhiteboardSaveSettledStatus,
  resolveWhiteboardSceneSaveSchedule,
} from './whiteboard-editor-session';
import { waitFor, type SaveStatus } from './whiteboard-editor-utils';

type ExcalidrawOnChange = NonNullable<ExcalidrawProps['onChange']>;

export type PendingWhiteboardEditorChange = {
  elements: Parameters<ExcalidrawOnChange>[0];
  appState: Parameters<ExcalidrawOnChange>[1];
  files: Parameters<ExcalidrawOnChange>[2];
};

type PendingCollabPublish = {
  scene: WhiteboardScene;
  signature: string;
};

export type UseWhiteboardScenePersistenceOptions = {
  activeBoard: WhiteboardDetail | null;
  activeBoardIdRef: MutableRefObject<string | null>;
  activeBoardRef: MutableRefObject<WhiteboardDetail | null>;
  applyingRemoteSceneRef: MutableRefObject<boolean>;
  collabDocRef: MutableRefObject<WhiteboardCollabDocument | null>;
  lastAppliedRemoteSceneSignatureRef: MutableRefObject<string | null>;
  lastPublishedCollabSignatureRef: MutableRefObject<string | null>;
  onBoardUpdated?: (board: WhiteboardDetail) => void;
  publishSceneToCollab: (
    scene: WhiteboardScene,
    knownSignature?: string,
  ) => boolean;
  setActiveBoard: Dispatch<SetStateAction<WhiteboardDetail | null>>;
  setError: Dispatch<SetStateAction<string | null>>;
  shareToken: string | null;
  token: string | null;
  translate: (key: string) => string;
};

export type WhiteboardScenePersistenceRuntime = {
  flushPendingSceneBeforeClose: () => Promise<boolean>;
  queueLocalChange: (change: PendingWhiteboardEditorChange) => void;
  resetLoadedScene: (scene: WhiteboardScene) => void;
  saveStatus: SaveStatus;
  schedulePendingCollabPublish: () => void;
};

function clearWindowTimer(timerRef: MutableRefObject<number | null>): void {
  if (timerRef.current === null) return;
  window.clearTimeout(timerRef.current);
  timerRef.current = null;
}

function elementsVersion(elements: readonly unknown[]): number {
  return getSceneVersion(elements as never);
}

export function useWhiteboardScenePersistence({
  activeBoard,
  activeBoardIdRef,
  activeBoardRef,
  applyingRemoteSceneRef,
  collabDocRef,
  lastAppliedRemoteSceneSignatureRef,
  lastPublishedCollabSignatureRef,
  onBoardUpdated,
  publishSceneToCollab,
  setActiveBoard,
  setError,
  shareToken,
  token,
  translate,
}: UseWhiteboardScenePersistenceOptions): WhiteboardScenePersistenceRuntime {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const mountedRef = useRef(true);
  const saveTimerRef = useRef<number | null>(null);
  const saveInFlightRef = useRef(false);
  const pendingSceneRef = useRef<WhiteboardScene | null>(null);
  const pendingSceneSignatureRef = useRef<string | null>(null);
  const lastSavedSceneSignatureRef = useRef<string | null>(null);
  const pendingLocalChangeRef = useRef<PendingWhiteboardEditorChange | null>(
    null,
  );
  const localChangeFlushTimerRef = useRef<number | null>(null);
  const queuedLocalElementsVersionRef = useRef<number | null>(null);
  const pendingCollabPublishRef = useRef<PendingCollabPublish | null>(null);
  const collabPublishRetryTimerRef = useRef<number | null>(null);
  const saveSettledTimerRef = useRef<number | null>(null);
  const lastSaveFailedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      pendingSceneRef.current = null;
      pendingSceneSignatureRef.current = null;
      pendingLocalChangeRef.current = null;
      pendingCollabPublishRef.current = null;
      clearWindowTimer(saveTimerRef);
      clearWindowTimer(localChangeFlushTimerRef);
      clearWindowTimer(collabPublishRetryTimerRef);
      clearWindowTimer(saveSettledTimerRef);
    };
  }, []);

  const resetLoadedScene = useCallback((scene: WhiteboardScene) => {
    lastSavedSceneSignatureRef.current = sceneSignature(scene);
    pendingSceneRef.current = null;
    pendingSceneSignatureRef.current = null;
    pendingLocalChangeRef.current = null;
    queuedLocalElementsVersionRef.current = null;
    pendingCollabPublishRef.current = null;
    lastSaveFailedRef.current = false;
    clearWindowTimer(saveTimerRef);
    clearWindowTimer(localChangeFlushTimerRef);
    clearWindowTimer(collabPublishRetryTimerRef);
    clearWindowTimer(saveSettledTimerRef);
    setSaveStatus('idle');
  }, []);

  const flushPendingCollabPublish = useCallback(() => {
    collabPublishRetryTimerRef.current = null;
    const pending = pendingCollabPublishRef.current;
    if (
      !mountedRef.current ||
      !pending ||
      shareToken ||
      !activeBoardRef.current?.can_edit
    ) {
      return;
    }

    if (publishSceneToCollab(pending.scene, pending.signature)) {
      if (pendingCollabPublishRef.current?.signature === pending.signature) {
        pendingCollabPublishRef.current = null;
      }
      return;
    }

    collabPublishRetryTimerRef.current = window.setTimeout(
      flushPendingCollabPublish,
      WHITEBOARD_COLLAB_PUBLISH_RETRY_MS,
    );
  }, [activeBoardRef, publishSceneToCollab, shareToken]);

  const schedulePendingCollabPublish = useCallback(() => {
    if (!mountedRef.current || collabPublishRetryTimerRef.current !== null)
      return;
    collabPublishRetryTimerRef.current = window.setTimeout(
      flushPendingCollabPublish,
      0,
    );
  }, [flushPendingCollabPublish]);

  const flushSceneSave = useCallback(
    async (resolvedBoardId: string): Promise<boolean> => {
      if (
        !mountedRef.current ||
        !token ||
        saveInFlightRef.current ||
        !activeBoardRef.current?.can_edit
      )
        return false;
      const scene = pendingSceneRef.current;
      const signature = pendingSceneSignatureRef.current;
      if (!scene || !signature) return true;
      pendingSceneRef.current = null;
      pendingSceneSignatureRef.current = null;
      saveInFlightRef.current = true;
      lastSaveFailedRef.current = false;
      setSaveStatus('saving');
      let saved = false;
      try {
        const collabDoc = collabDocRef.current;
        const updated =
          collabDoc && !shareToken
            ? await saveWhiteboardCollabSnapshot(token, resolvedBoardId, {
                scene,
                yjs_state: encodeWhiteboardCollabDocumentState(collabDoc),
              })
            : shareToken
              ? await updateSharedWhiteboard(token, shareToken, { scene })
              : await updateWhiteboard(token, resolvedBoardId, { scene });
        if (!mountedRef.current) return false;
        lastSavedSceneSignatureRef.current = signature;
        if (activeBoardIdRef.current === resolvedBoardId) {
          setActiveBoard((current) =>
            current ? { ...current, ...updated, scene } : current,
          );
        }
        const currentBoard = activeBoardRef.current;
        if (currentBoard) {
          onBoardUpdated?.({ ...currentBoard, ...updated, scene });
        }
        saved = true;
      } catch (err) {
        if (!mountedRef.current) return false;
        lastSaveFailedRef.current = true;
        setError(
          err instanceof Error
            ? err.message
            : translate('whiteboard.saveFailed'),
        );
        setSaveStatus('error');
      } finally {
        saveInFlightRef.current = false;
        if (
          mountedRef.current &&
          pendingSceneRef.current !== null &&
          activeBoardIdRef.current === resolvedBoardId &&
          saveTimerRef.current === null
        ) {
          saveTimerRef.current = window.setTimeout(() => {
            saveTimerRef.current = null;
            void flushSceneSave(resolvedBoardId);
          }, WHITEBOARD_SCENE_SAVE_RETRY_MS);
        } else if (mountedRef.current && saved) {
          if (!shareToken) {
            pendingCollabPublishRef.current = { scene, signature };
            schedulePendingCollabPublish();
          }
          setSaveStatus('saved');
          clearWindowTimer(saveSettledTimerRef);
          saveSettledTimerRef.current = window.setTimeout(
            () => {
              saveSettledTimerRef.current = null;
              const settledStatus = resolveWhiteboardSaveSettledStatus({
                localChangeTimerActive:
                  localChangeFlushTimerRef.current !== null,
                pendingLocalChange: pendingLocalChangeRef.current !== null,
                pendingScene: pendingSceneRef.current !== null,
                saveInFlight: saveInFlightRef.current,
              });
              if (settledStatus) {
                setSaveStatus(settledStatus);
              }
            },
            getWhiteboardSaveSettledDelay({
              localChangeFlushMs: WHITEBOARD_LOCAL_CHANGE_FLUSH_MS,
            }),
          );
        }
      }
      return saved;
    },
    [
      activeBoardIdRef,
      activeBoardRef,
      collabDocRef,
      onBoardUpdated,
      schedulePendingCollabPublish,
      setActiveBoard,
      setError,
      shareToken,
      token,
      translate,
    ],
  );

  const scheduleSceneSave = useCallback(
    (scene: WhiteboardScene, knownSignature?: string) => {
      if (!mountedRef.current) return;
      const signature = knownSignature ?? sceneSignature(scene);
      const decision = resolveWhiteboardSceneSaveSchedule({
        boardId: activeBoard?.id ?? null,
        canEdit: Boolean(activeBoard?.can_edit),
        lastSavedSignature: lastSavedSceneSignatureRef.current,
        pendingSignature: pendingSceneSignatureRef.current,
        saveInFlight: saveInFlightRef.current,
        saveTimerActive: saveTimerRef.current !== null,
        signature,
      });
      if (!decision.shouldQueue) {
        return;
      }
      pendingSceneRef.current = scene;
      pendingSceneSignatureRef.current = signature;
      const nextStatus = decision.nextStatus;
      if (nextStatus) {
        setSaveStatus((current) =>
          current === 'saving' ? current : nextStatus,
        );
      }
      if (!decision.shouldSchedule || !activeBoard?.id) return;

      const resolvedBoardId = activeBoard.id;
      saveTimerRef.current = window.setTimeout(() => {
        saveTimerRef.current = null;
        void flushSceneSave(resolvedBoardId);
      }, WHITEBOARD_SCENE_SAVE_DEBOUNCE_MS);
    },
    [activeBoard?.can_edit, activeBoard?.id, flushSceneSave],
  );

  const flushQueuedLocalChange = useCallback(() => {
    localChangeFlushTimerRef.current = null;
    const pending = pendingLocalChangeRef.current;
    pendingLocalChangeRef.current = null;
    queuedLocalElementsVersionRef.current = null;
    if (!mountedRef.current || !pending) {
      return;
    }
    if (applyingRemoteSceneRef.current) {
      pendingLocalChangeRef.current = pending;
      queuedLocalElementsVersionRef.current = elementsVersion(pending.elements);
      localChangeFlushTimerRef.current = window.setTimeout(
        flushQueuedLocalChange,
        WHITEBOARD_REMOTE_APPLY_GUARD_MS + 16,
      );
      return;
    }

    const scene = sceneFromExcalidraw(
      pending.elements,
      pending.appState,
      pending.files,
      (elements, appState, files) =>
        serializeAsJSON(elements, appState, files, 'local'),
    );
    const signature = sceneSignature(scene);
    const decision = describeWhiteboardLocalSceneChange({
      lastAppliedRemoteSignature: lastAppliedRemoteSceneSignatureRef.current,
      lastPublishedCollabSignature: lastPublishedCollabSignatureRef.current,
      lastSavedSignature: lastSavedSceneSignatureRef.current,
      pendingScene: pendingSceneRef.current !== null,
      pendingSceneSignature: pendingSceneSignatureRef.current,
      saveInFlight: saveInFlightRef.current,
      signature,
    });
    if (decision.type === 'ignore-pending-duplicate') {
      return;
    }
    if (decision.type !== 'queue-local-scene') {
      if (decision.nextStatus === 'idle') {
        setSaveStatus((current) => (current === 'dirty' ? 'idle' : current));
      } else if (decision.nextStatus) {
        setSaveStatus(decision.nextStatus);
      }
      return;
    }
    if (!publishSceneToCollab(scene, signature)) {
      pendingCollabPublishRef.current = { scene, signature };
      schedulePendingCollabPublish();
    }
    scheduleSceneSave(scene, signature);
  }, [
    applyingRemoteSceneRef,
    lastAppliedRemoteSceneSignatureRef,
    lastPublishedCollabSignatureRef,
    publishSceneToCollab,
    schedulePendingCollabPublish,
    scheduleSceneSave,
  ]);

  const queueLocalChange = useCallback(
    (change: PendingWhiteboardEditorChange) => {
      if (!mountedRef.current) return;
      const nextVersion = elementsVersion(change.elements);
      if (
        localChangeFlushTimerRef.current !== null &&
        queuedLocalElementsVersionRef.current === nextVersion
      ) {
        pendingLocalChangeRef.current = change;
        return;
      }
      queuedLocalElementsVersionRef.current = nextVersion;
      pendingLocalChangeRef.current = change;
      if (localChangeFlushTimerRef.current !== null) return;
      localChangeFlushTimerRef.current = window.setTimeout(
        flushQueuedLocalChange,
        WHITEBOARD_LOCAL_CHANGE_FLUSH_MS,
      );
    },
    [flushQueuedLocalChange],
  );

  const flushPendingSceneBeforeClose =
    useCallback(async (): Promise<boolean> => {
      if (!mountedRef.current) return false;
      const boardId = activeBoardIdRef.current;
      if (!boardId) return true;

      const flushQueuedLocalChangeNow = () => {
        clearWindowTimer(localChangeFlushTimerRef);
        if (pendingLocalChangeRef.current !== null) {
          flushQueuedLocalChange();
        }
      };

      lastSaveFailedRef.current = false;
      flushQueuedLocalChangeNow();
      clearWindowTimer(saveTimerRef);

      const flushUntilSettled = async (attempt: number): Promise<boolean> => {
        for (;;) {
          if (!mountedRef.current) return false;
          const step = resolveWhiteboardCloseFlushStep({
            attempt,
            lastSaveFailed: lastSaveFailedRef.current,
            localChangeTimerActive: localChangeFlushTimerRef.current !== null,
            pendingLocalChange: pendingLocalChangeRef.current !== null,
            pendingScene: pendingSceneRef.current !== null,
            saveInFlight: saveInFlightRef.current,
          });

          if (step === 'timed-out') {
            setError(translate('whiteboard.closeSaveIncomplete'));
            return false;
          }
          if (step === 'flush-local-change') {
            flushQueuedLocalChangeNow();
            clearWindowTimer(saveTimerRef);
            return flushUntilSettled(attempt + 1);
          }
          if (step === 'flush-scene-save') {
            clearWindowTimer(saveTimerRef);
            const saved = await flushSceneSave(boardId);
            if (!saved && pendingSceneRef.current === null) {
              return false;
            }
            return flushUntilSettled(attempt + 1);
          }
          if (step === 'settled-succeeded') {
            return true;
          }
          if (step === 'settled-failed') {
            return false;
          }
          break;
        }

        await waitFor(WHITEBOARD_CLOSE_FLUSH_RETRY_MS);
        return flushUntilSettled(attempt + 1);
      };

      return flushUntilSettled(0);
    }, [
      activeBoardIdRef,
      flushQueuedLocalChange,
      flushSceneSave,
      setError,
      translate,
    ]);

  return {
    flushPendingSceneBeforeClose,
    queueLocalChange,
    resetLoadedScene,
    saveStatus,
    schedulePendingCollabPublish,
  };
}
