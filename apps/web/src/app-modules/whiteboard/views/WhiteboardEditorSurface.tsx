import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CaptureUpdateAction,
  Excalidraw,
  exportToBlob,
  exportToSvg,
  serializeAsJSON,
  THEME,
} from '@excalidraw/excalidraw';
import type {
  Collaborator,
  ExcalidrawImperativeAPI,
  ExcalidrawInitialDataState,
  ExcalidrawProps,
  SocketId,
} from '@excalidraw/excalidraw/types';
import '@excalidraw/excalidraw/index.css';
import { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';
import {
  Archive,
  Download,
  FileJson,
  Image,
  Link as LinkIcon,
  Loader2,
  RefreshCcw,
  Share2,
  Star,
  Trash2,
} from 'lucide-react';
import { Button, Dialog } from '@aidoo/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  deleteWhiteboard,
  deleteWhiteboardLinkShare,
  deleteWhiteboardUserShare,
  getWhiteboardCollabSession,
  getWhiteboard,
  getWhiteboardSharing,
  getSharedWhiteboard,
  listWhiteboardShareableUsers,
  normalizeWhiteboardScene,
  permanentlyDeleteWhiteboard,
  recordSharedWhiteboardView,
  recordWhiteboardView,
  saveWhiteboardCollabSnapshot,
  toggleWhiteboardFavorite,
  updateSharedWhiteboard,
  updateWhiteboard,
  upsertWhiteboardLinkShare,
  upsertWhiteboardUserShare,
  type ShareableUserItem,
  type WhiteboardDetail,
  type WhiteboardScene,
  type WhiteboardSharingResponse,
} from '../api/whiteboard-api';

type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';
type CollabStatus = 'connecting' | 'connected' | 'offline' | 'error' | null;
type ExcalidrawOnChange = NonNullable<ExcalidrawProps['onChange']>;
const LOCAL_COLLAB_ORIGIN = 'whiteboard-local-scene';

type WhiteboardElement = Record<string, unknown> & {
  id?: string;
  version?: number;
  versionNonce?: number;
  updated?: number;
  isDeleted?: boolean;
};

type WhiteboardAwarenessState = {
  user?: {
    id: string;
    fullName: string;
    color: string;
  };
  cursor?: {
    x: number;
    y: number;
    tool: 'pointer' | 'laser';
  };
  button?: 'down' | 'up';
  selectedElementIds?: Record<string, true>;
};

const USER_COLORS = [
  '#0ea5e9',
  '#ef4444',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
  '#f97316',
] as const;

interface WhiteboardEditorSurfaceProps {
  boardId: string;
  workspaceSlug?: string | null;
  className?: string;
  showArchive?: boolean;
  showDetach?: boolean;
  shareToken?: string | null;
  onBoardLoaded?: (board: WhiteboardDetail) => void;
  onBoardUpdated?: (board: WhiteboardDetail) => void;
  onArchived?: (boardId: string) => void;
  onDeleted?: (boardId: string) => void;
  onDetach?: () => void;
}

function readExcalidrawTheme() {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
    ? THEME.DARK
    : THEME.LIGHT;
}

function sceneFromExcalidraw(
  elements: Parameters<ExcalidrawOnChange>[0],
  appState: Parameters<ExcalidrawOnChange>[1],
  files: Parameters<ExcalidrawOnChange>[2],
): WhiteboardScene {
  return normalizeWhiteboardScene(JSON.parse(serializeAsJSON(elements, appState, files, 'local')));
}

function sceneFromEditorAPI(api: ExcalidrawImperativeAPI): WhiteboardScene {
  return sceneFromExcalidraw(
    api.getSceneElementsIncludingDeleted() as Parameters<ExcalidrawOnChange>[0],
    api.getAppState(),
    api.getFiles(),
  );
}

function sceneSignature(scene: WhiteboardScene): string {
  return JSON.stringify(scene);
}

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

function colorForUser(userId: string): string {
  return USER_COLORS[hashString(userId) % USER_COLORS.length];
}

function elementId(element: unknown): string | null {
  if (!element || typeof element !== 'object') return null;
  const id = (element as WhiteboardElement).id;
  return typeof id === 'string' && id ? id : null;
}

function numericElementField(element: WhiteboardElement | undefined, key: 'updated' | 'version' | 'versionNonce'): number {
  const value = element?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function shouldAcceptElementUpdate(
  next: WhiteboardElement,
  current: WhiteboardElement | undefined,
): boolean {
  if (!current) return true;
  const nextVersion = numericElementField(next, 'version');
  const currentVersion = numericElementField(current, 'version');
  if (nextVersion !== currentVersion) {
    return nextVersion > currentVersion;
  }
  const nextUpdated = numericElementField(next, 'updated');
  const currentUpdated = numericElementField(current, 'updated');
  if (nextUpdated !== currentUpdated) {
    return nextUpdated > currentUpdated;
  }
  const nextNonce = numericElementField(next, 'versionNonce');
  const currentNonce = numericElementField(current, 'versionNonce');
  if (nextNonce !== currentNonce) {
    return nextNonce > currentNonce;
  }
  return JSON.stringify(next) !== JSON.stringify(current);
}

function objectFromYMap(map: Y.Map<unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  map.forEach((value, key) => {
    result[key] = value;
  });
  return result;
}

function sceneFromCollabMaps(
  elementsMap: Y.Map<unknown>,
  elementOrder: Y.Array<string>,
  filesMap: Y.Map<unknown>,
  appStateMap: Y.Map<unknown>,
): WhiteboardScene {
  const elements: unknown[] = [];
  const seen = new Set<string>();
  for (const id of elementOrder.toArray()) {
    const element = elementsMap.get(id);
    if (element) {
      elements.push(element);
      seen.add(id);
    }
  }
  elementsMap.forEach((element, id) => {
    if (!seen.has(id)) {
      elements.push(element);
    }
  });
  return normalizeWhiteboardScene({
    elements,
    appState: objectFromYMap(appStateMap),
    files: objectFromYMap(filesMap),
  });
}

function decodeBase64ToUint8Array(value: string): Uint8Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function encodeUint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return window.btoa(binary);
}

function toWebSocketUrl(wsPath: string): string {
  const resolved = new URL(wsPath, window.location.origin);
  resolved.protocol = resolved.protocol === 'https:' ? 'wss:' : 'ws:';
  return resolved.toString();
}

function collabLabel(status: CollabStatus): string {
  if (status === 'connecting') return 'Live connecting';
  if (status === 'connected') return 'Live';
  if (status === 'offline' || status === 'error') return 'Live offline';
  return '';
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function safeFilename(title: string, extension: string): string {
  const base = title.trim().replace(/[^a-zA-Z0-9가-힣._-]+/g, '-').replace(/^-+|-+$/g, '') || 'whiteboard';
  return `${base}.${extension}`;
}

function saveLabel(status: SaveStatus): string {
  return {
    idle: '',
    dirty: 'Saving...',
    saving: 'Saving...',
    saved: 'Saved',
    error: 'Save failed',
  }[status];
}

function WhiteboardShareDialog({
  board,
  workspaceSlug,
  open,
  onClose,
}: {
  board: WhiteboardDetail;
  workspaceSlug?: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const { token } = useAuth();
  const [sharing, setSharing] = useState<WhiteboardSharingResponse | null>(null);
  const [users, setUsers] = useState<ShareableUserItem[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token || !open) return;
    setBusy(true);
    setError(null);
    try {
      const [sharingResponse, usersResponse] = await Promise.all([
        getWhiteboardSharing(token, board.id, workspaceSlug),
        listWhiteboardShareableUsers(token, query, workspaceSlug),
      ]);
      setSharing(sharingResponse);
      setUsers(usersResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : '공유 정보를 불러올 수 없습니다.');
    } finally {
      setBusy(false);
    }
  }, [board.id, open, query, token, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<WhiteboardSharingResponse>) {
    setBusy(true);
    setError(null);
    try {
      setSharing(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : '공유 설정을 저장할 수 없습니다.');
    } finally {
      setBusy(false);
    }
  }

  const sharedUserIds = new Set(sharing?.users.map((item) => item.user_id) ?? []);
  const linkUrl = sharing?.link_share
    ? `${window.location.origin}${sharing.link_share.share_path}`
    : '';

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
      title="Whiteboard sharing"
      description="사용자 또는 링크로 화이트보드를 공유합니다."
      maxWidth="max-w-2xl"
      actions={<Button variant="secondary" onClick={onClose}>닫기</Button>}
    >
      <div className="space-y-5 text-app-ink">
        {error ? (
          <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-500">
            {error}
          </div>
        ) : null}

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="app-text-control-sm text-app-ink">Link share</h3>
            {sharing?.link_share ? (
              <Button
                variant="secondary"
                size="dense"
                disabled={busy}
                onClick={() => {
                  if (!token) return;
                  void run(() => deleteWhiteboardLinkShare(token, board.id, workspaceSlug));
                }}
              >
                Disable
              </Button>
            ) : (
              <Button
                variant="secondary"
                size="dense"
                disabled={busy}
                onClick={() => {
                  if (!token) return;
                  void run(() => upsertWhiteboardLinkShare(token, board.id, { access_level: 'read' }, workspaceSlug));
                }}
              >
                Enable read link
              </Button>
            )}
          </div>
          {sharing?.link_share ? (
            <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <LinkIcon size={14} className="shrink-0 text-app-ink/40" />
              <input
                readOnly
                value={linkUrl}
                className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink/70 outline-none"
              />
              <select
                value={sharing.link_share.access_level}
                disabled={busy}
                onChange={(event) => {
                  if (!token) return;
                  void run(() => upsertWhiteboardLinkShare(
                    token,
                    board.id,
                    { access_level: event.target.value as 'read' | 'edit' },
                    workspaceSlug,
                  ));
                }}
                className="rounded-md border border-app-border bg-app-bg px-2 py-1 text-sm"
              >
                <option value="read">read</option>
                <option value="edit">edit</option>
              </select>
              <Button
                variant="secondary"
                size="dense"
                onClick={() => void navigator.clipboard.writeText(linkUrl)}
              >
                Copy
              </Button>
            </div>
          ) : null}
        </section>

        <section className="space-y-3">
          <div className="space-y-1">
            <label className="app-text-control-sm text-app-ink/70">Users</label>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="이름 또는 이메일 검색"
              className="app-text-body-sm w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 outline-none focus:border-app-accent"
            />
          </div>

          {busy && !sharing ? (
            <div className="flex h-20 items-center justify-center text-app-ink/40">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
              {users.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-app-ink/45">표시할 사용자가 없습니다.</div>
              ) : (
                users.map((user) => {
                  const current = sharing?.users.find((item) => item.user_id === user.id);
                  return (
                    <div key={user.id} className="flex items-center justify-between gap-3 border-b border-app-border px-3 py-2 last:border-b-0">
                      <div className="min-w-0">
                        <p className="app-text-body-sm truncate text-app-ink">{user.full_name}</p>
                        <p className="app-text-caption truncate text-app-ink/45">{user.email}</p>
                      </div>
                      {sharedUserIds.has(user.id) && current ? (
                        <div className="flex shrink-0 items-center gap-2">
                          <select
                            value={current.access_level}
                            disabled={busy}
                            onChange={(event) => {
                              if (!token) return;
                              void run(() => upsertWhiteboardUserShare(
                                token,
                                board.id,
                                user.id,
                                event.target.value as 'read' | 'edit',
                                workspaceSlug,
                              ));
                            }}
                            className="rounded-md border border-app-border bg-app-bg px-2 py-1 text-sm"
                          >
                            <option value="read">read</option>
                            <option value="edit">edit</option>
                          </select>
                          <Button
                            variant="ghost"
                            size="dense"
                            disabled={busy}
                            onClick={() => {
                              if (!token) return;
                              void run(() => deleteWhiteboardUserShare(token, board.id, user.id, workspaceSlug));
                            }}
                          >
                            Remove
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="secondary"
                          size="dense"
                          disabled={busy}
                          onClick={() => {
                            if (!token) return;
                            void run(() => upsertWhiteboardUserShare(token, board.id, user.id, 'read', workspaceSlug));
                          }}
                        >
                          Add
                        </Button>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
        </section>
      </div>
    </Dialog>
  );
}

export function WhiteboardEditorSurface({
  boardId,
  workspaceSlug,
  className,
  showArchive = true,
  showDetach = false,
  shareToken = null,
  onBoardLoaded,
  onBoardUpdated,
  onArchived,
  onDeleted,
  onDetach,
}: WhiteboardEditorSurfaceProps) {
  const { token } = useAuth();
  const [activeBoard, setActiveBoard] = useState<WhiteboardDetail | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [collabStatus, setCollabStatus] = useState<CollabStatus>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [excalidrawTheme, setExcalidrawTheme] = useState(readExcalidrawTheme);
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null);
  const activeBoardRef = useRef<WhiteboardDetail | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const saveInFlightRef = useRef(false);
  const pendingSceneRef = useRef<WhiteboardScene | null>(null);
  const pendingSceneSignatureRef = useRef<string | null>(null);
  const lastSavedSceneSignatureRef = useRef<string | null>(null);
  const activeBoardIdRef = useRef<string | null>(null);
  const collabDocRef = useRef<Y.Doc | null>(null);
  const collabProviderRef = useRef<WebsocketProvider | null>(null);
  const collabElementsMapRef = useRef<Y.Map<unknown> | null>(null);
  const collabElementOrderRef = useRef<Y.Array<string> | null>(null);
  const collabFilesMapRef = useRef<Y.Map<unknown> | null>(null);
  const collabAppStateMapRef = useRef<Y.Map<unknown> | null>(null);
  const applyingRemoteSceneRef = useRef(false);
  const pendingRemoteSceneRef = useRef<WhiteboardScene | null>(null);
  const lastPublishedCollabSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const root = document.documentElement;
    const syncTheme = () => setExcalidrawTheme(readExcalidrawTheme());
    syncTheme();
    const observer = new MutationObserver(syncTheme);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => () => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
    }
  }, []);

  useEffect(() => {
    activeBoardIdRef.current = activeBoard?.id ?? null;
    activeBoardRef.current = activeBoard;
  }, [activeBoard]);

  const loadBoard = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const board = shareToken
        ? await getSharedWhiteboard(token, shareToken)
        : await getWhiteboard(token, boardId, workspaceSlug);
      const normalized = { ...board, scene: normalizeWhiteboardScene(board.scene) };
      lastSavedSceneSignatureRef.current = sceneSignature(normalized.scene);
      pendingSceneRef.current = null;
      pendingSceneSignatureRef.current = null;
      setActiveBoard(normalized);
      setTitleDraft(normalized.title);
      setSaveStatus('idle');
      onBoardLoaded?.(normalized);
      if (shareToken) {
        void recordSharedWhiteboardView(token, shareToken);
      } else {
        void recordWhiteboardView(token, boardId, workspaceSlug);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load whiteboard.');
      setActiveBoard(null);
    } finally {
      setLoading(false);
    }
  }, [boardId, onBoardLoaded, shareToken, token, workspaceSlug]);

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  const flushSceneSave = useCallback(async (resolvedBoardId: string) => {
    if (!token || saveInFlightRef.current) return;
    const scene = pendingSceneRef.current;
    const signature = pendingSceneSignatureRef.current;
    if (!scene || !signature) return;
    pendingSceneRef.current = null;
    pendingSceneSignatureRef.current = null;
    saveInFlightRef.current = true;
    setSaveStatus('saving');
    try {
      const collabDoc = collabDocRef.current;
      const updated = collabDoc && !shareToken
        ? await saveWhiteboardCollabSnapshot(
          token,
          resolvedBoardId,
          {
            scene,
            yjs_state: encodeUint8ArrayToBase64(Y.encodeStateAsUpdate(collabDoc)),
          },
          workspaceSlug,
        )
        : shareToken
          ? await updateSharedWhiteboard(token, shareToken, { scene })
          : await updateWhiteboard(token, resolvedBoardId, { scene }, workspaceSlug);
      lastSavedSceneSignatureRef.current = signature;
      if (activeBoardIdRef.current === resolvedBoardId) {
        setActiveBoard((current) => current ? { ...current, ...updated, scene } : current);
      }
      const currentBoard = activeBoardRef.current;
      if (currentBoard) {
        onBoardUpdated?.({ ...currentBoard, ...updated, scene });
      }
      if (pendingSceneRef.current === null) {
        setSaveStatus('saved');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save whiteboard.');
      setSaveStatus('error');
    } finally {
      saveInFlightRef.current = false;
      if (pendingSceneRef.current !== null && activeBoardIdRef.current === resolvedBoardId && saveTimerRef.current === null) {
        saveTimerRef.current = window.setTimeout(() => {
          saveTimerRef.current = null;
          void flushSceneSave(resolvedBoardId);
        }, 250);
      }
    }
  }, [onBoardUpdated, shareToken, token, workspaceSlug]);

  const scheduleSceneSave = useCallback((scene: WhiteboardScene) => {
    if (!activeBoard?.id || !activeBoard.can_edit) return;
    const signature = sceneSignature(scene);
    if (
      signature === lastSavedSceneSignatureRef.current
      || signature === pendingSceneSignatureRef.current
    ) {
      return;
    }
    pendingSceneRef.current = scene;
    pendingSceneSignatureRef.current = signature;
    setSaveStatus((current) => current === 'saving' ? current : 'dirty');
    if (saveInFlightRef.current || saveTimerRef.current !== null) return;

    const resolvedBoardId = activeBoard.id;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      void flushSceneSave(resolvedBoardId);
    }, 800);
  }, [activeBoard?.can_edit, activeBoard?.id, flushSceneSave]);

  const applySceneToEditor = useCallback((scene: WhiteboardScene) => {
    const api = apiRef.current;
    const board = activeBoardRef.current;
    if (!api || !board) {
      pendingRemoteSceneRef.current = scene;
      return;
    }
    applyingRemoteSceneRef.current = true;
    const normalized = normalizeWhiteboardScene(scene);
    const files = Object.values(normalized.files);
    if (files.length > 0) {
      api.addFiles(files as never);
    }
    api.updateScene({
      elements: normalized.elements as never,
      appState: {
        ...normalized.appState,
        name: board.title,
      } as never,
      captureUpdate: CaptureUpdateAction.NEVER,
    });
    window.setTimeout(() => {
      applyingRemoteSceneRef.current = false;
    }, 0);
  }, []);

  const publishSceneToCollab = useCallback((scene: WhiteboardScene) => {
    const doc = collabDocRef.current;
    const elementsMap = collabElementsMapRef.current;
    const elementOrder = collabElementOrderRef.current;
    const filesMap = collabFilesMapRef.current;
    const appStateMap = collabAppStateMapRef.current;
    if (
      !doc
      || !elementsMap
      || !elementOrder
      || !filesMap
      || !appStateMap
      || applyingRemoteSceneRef.current
    ) {
      return;
    }
    const signature = sceneSignature(scene);
    if (signature === lastPublishedCollabSignatureRef.current) {
      return;
    }
    lastPublishedCollabSignatureRef.current = signature;
    const elements = scene.elements as WhiteboardElement[];
    const order = elements.map((element) => elementId(element)).filter((id): id is string => Boolean(id));
    doc.transact(() => {
      for (const element of elements) {
        const id = elementId(element);
        if (!id) continue;
        const current = elementsMap.get(id) as WhiteboardElement | undefined;
        if (shouldAcceptElementUpdate(element, current)) {
          elementsMap.set(id, element);
        }
      }
      elementOrder.delete(0, elementOrder.length);
      elementOrder.insert(0, order);

      filesMap.clear();
      Object.entries(scene.files).forEach(([key, value]) => {
        filesMap.set(key, value);
      });

      appStateMap.clear();
      Object.entries(scene.appState).forEach(([key, value]) => {
        appStateMap.set(key, value);
      });
    }, LOCAL_COLLAB_ORIGIN);
  }, []);

  const updateAwarenessSelection = useCallback((selectedElementIds: unknown) => {
    const provider = collabProviderRef.current;
    if (!provider) return;
    provider.awareness.setLocalStateField(
      'selectedElementIds',
      selectedElementIds && typeof selectedElementIds === 'object'
        ? selectedElementIds
        : {},
    );
  }, []);

  const publishPointerToCollab = useCallback<NonNullable<ExcalidrawProps['onPointerUpdate']>>((payload) => {
    const provider = collabProviderRef.current;
    if (!provider) return;
    provider.awareness.setLocalStateField('cursor', payload.pointer);
    provider.awareness.setLocalStateField('button', payload.button);
    updateAwarenessSelection(apiRef.current?.getAppState().selectedElementIds ?? {});
  }, [updateAwarenessSelection]);

  useEffect(() => {
    let cancelled = false;
    let provider: WebsocketProvider | null = null;
    let doc: Y.Doc | null = null;
    let elementsMap: Y.Map<unknown> | null = null;
    let elementOrder: Y.Array<string> | null = null;
    let filesMap: Y.Map<unknown> | null = null;
    let appStateMap: Y.Map<unknown> | null = null;
    let observer: ((event: { transaction: { origin: unknown } }) => void) | null = null;
    let remoteApplyTimer: number | null = null;
    let handleProviderStatus: ((event: { status?: string }) => void) | null = null;
    let handleConnectionClose: ((event: CloseEvent | null) => void) | null = null;
    let handleAwarenessChange: (() => void) | null = null;

    collabDocRef.current = null;
    collabProviderRef.current = null;
    collabElementsMapRef.current = null;
    collabElementOrderRef.current = null;
    collabFilesMapRef.current = null;
    collabAppStateMapRef.current = null;
    lastPublishedCollabSignatureRef.current = null;

    if (!token || !activeBoard?.id || !activeBoard.can_edit || shareToken) {
      setCollabStatus(null);
      return undefined;
    }

    const seedScene = normalizeWhiteboardScene(activeBoardRef.current?.scene);
    setCollabStatus('connecting');

    void getWhiteboardCollabSession(token, activeBoard.id, workspaceSlug)
      .then((session) => {
        if (cancelled) return;
        if (!session.can_edit || session.realtime_status !== 'enabled') {
          setCollabStatus('offline');
          return;
        }

        doc = new Y.Doc();
        if (session.yjs_state) {
          Y.applyUpdate(doc, decodeBase64ToUint8Array(session.yjs_state));
        }

        const legacySceneMap = doc.getMap<WhiteboardScene>('whiteboard');
        elementsMap = doc.getMap<unknown>('whiteboard-elements');
        elementOrder = doc.getArray<string>('whiteboard-element-order');
        filesMap = doc.getMap<unknown>('whiteboard-files');
        appStateMap = doc.getMap<unknown>('whiteboard-app-state');

        const hasElementState = elementsMap.size > 0 || elementOrder.length > 0;
        const initialScene = hasElementState
          ? sceneFromCollabMaps(elementsMap, elementOrder, filesMap, appStateMap)
          : normalizeWhiteboardScene(
            legacySceneMap.get('scene') ?? session.snapshot_scene ?? seedScene,
          );
        if (!hasElementState) {
          const initialElements = initialScene.elements as WhiteboardElement[];
          const initialOrder = initialElements
            .map((element) => elementId(element))
            .filter((id): id is string => Boolean(id));
          doc.transact(() => {
            for (const element of initialElements) {
              const id = elementId(element);
              if (id) {
                elementsMap?.set(id, element);
              }
            }
            elementOrder?.insert(0, initialOrder);
            Object.entries(initialScene.files).forEach(([key, value]) => {
              filesMap?.set(key, value);
            });
            Object.entries(initialScene.appState).forEach(([key, value]) => {
              appStateMap?.set(key, value);
            });
          }, LOCAL_COLLAB_ORIGIN);
        }

        collabDocRef.current = doc;
        collabElementsMapRef.current = elementsMap;
        collabElementOrderRef.current = elementOrder;
        collabFilesMapRef.current = filesMap;
        collabAppStateMapRef.current = appStateMap;
        lastPublishedCollabSignatureRef.current = sceneSignature(initialScene);
        setActiveBoard((current) => current && current.id === session.whiteboard_id
          ? { ...current, scene: initialScene }
          : current);
        applySceneToEditor(initialScene);

        observer = (event) => {
          if (
            event.transaction.origin === LOCAL_COLLAB_ORIGIN
            || !elementsMap
            || !elementOrder
            || !filesMap
            || !appStateMap
          ) {
            return;
          }
          if (remoteApplyTimer !== null) {
            window.clearTimeout(remoteApplyTimer);
          }
          remoteApplyTimer = window.setTimeout(() => {
            if (!elementsMap || !elementOrder || !filesMap || !appStateMap) return;
            const normalized = sceneFromCollabMaps(
              elementsMap,
              elementOrder,
              filesMap,
              appStateMap,
            );
            const signature = sceneSignature(normalized);
            if (signature === lastPublishedCollabSignatureRef.current) {
              return;
            }
            lastPublishedCollabSignatureRef.current = signature;
            setActiveBoard((current) => current && current.id === session.whiteboard_id
              ? { ...current, scene: normalized }
              : current);
            applySceneToEditor(normalized);
            scheduleSceneSave(normalized);
          }, 0);
        };
        elementsMap.observe(observer);
        elementOrder.observe(observer);
        filesMap.observe(observer);
        appStateMap.observe(observer);

        provider = new WebsocketProvider(
          toWebSocketUrl(session.ws_path),
          session.room_key,
          doc,
          {
            maxBackoffTime: 4000,
            params: { token },
          },
        );
        collabProviderRef.current = provider;
        provider.awareness.setLocalStateField('user', {
          id: session.user.id,
          fullName: session.user.full_name,
          color: colorForUser(session.user.id),
        });
        provider.awareness.setLocalStateField(
          'selectedElementIds',
          apiRef.current?.getAppState().selectedElementIds ?? {},
        );
        handleAwarenessChange = () => {
          if (!provider) return;
          const nextCollaborators = new Map<SocketId, Collaborator>();
          provider.awareness.getStates().forEach((state, clientId) => {
            if (!provider || clientId === provider.awareness.clientID) return;
            const awareness = state as WhiteboardAwarenessState;
            const socketId = String(clientId) as SocketId;
            const color = awareness.user?.color ?? colorForUser(socketId);
            nextCollaborators.set(socketId, {
              id: awareness.user?.id ?? socketId,
              socketId,
              username: awareness.user?.fullName ?? 'User',
              pointer: awareness.cursor,
              button: awareness.button,
              selectedElementIds: awareness.selectedElementIds,
              color: {
                stroke: color,
                background: color,
              },
            });
          });
          apiRef.current?.updateScene({
            collaborators: nextCollaborators,
            captureUpdate: CaptureUpdateAction.NEVER,
          });
        };
        handleProviderStatus = (event) => {
          if (event.status === 'connected') {
            setCollabStatus('connected');
          } else if (event.status === 'connecting') {
            setCollabStatus('connecting');
          } else if (event.status === 'disconnected') {
            setCollabStatus('offline');
          }
        };
        handleConnectionClose = (event) => {
          if (event?.code === 4403 || event?.code === 1011 || event?.code === 1013) {
            setCollabStatus(event.code === 4403 ? 'error' : 'offline');
            provider?.disconnect();
          }
        };
        provider.awareness.on('change', handleAwarenessChange);
        provider.on('status', handleProviderStatus);
        provider.on('connection-close', handleConnectionClose);
        provider.connect();
      })
      .catch((err) => {
        if (!cancelled) {
          setCollabStatus('error');
          setError(err instanceof Error ? err.message : '실시간 협업 세션을 시작하지 못했습니다.');
        }
      });

    return () => {
      cancelled = true;
      if (remoteApplyTimer !== null) {
        window.clearTimeout(remoteApplyTimer);
      }
      if (provider && handleAwarenessChange) {
        provider.awareness.off('change', handleAwarenessChange);
      }
      if (provider && handleProviderStatus) {
        provider.off('status', handleProviderStatus);
      }
      if (provider && handleConnectionClose) {
        provider.off('connection-close', handleConnectionClose);
      }
      if (observer) {
        elementsMap?.unobserve(observer);
        elementOrder?.unobserve(observer);
        filesMap?.unobserve(observer);
        appStateMap?.unobserve(observer);
      }
      provider?.disconnect();
      (provider as { destroy?: () => void } | null)?.destroy?.();
      doc?.destroy();
      apiRef.current?.updateScene({
        collaborators: new Map(),
        captureUpdate: CaptureUpdateAction.NEVER,
      });
      if (collabProviderRef.current === provider) {
        collabProviderRef.current = null;
      }
      if (collabDocRef.current === doc) {
        collabDocRef.current = null;
      }
      if (collabElementsMapRef.current === elementsMap) {
        collabElementsMapRef.current = null;
      }
      if (collabElementOrderRef.current === elementOrder) {
        collabElementOrderRef.current = null;
      }
      if (collabFilesMapRef.current === filesMap) {
        collabFilesMapRef.current = null;
      }
      if (collabAppStateMapRef.current === appStateMap) {
        collabAppStateMapRef.current = null;
      }
    };
  }, [
    activeBoard?.can_edit,
    activeBoard?.id,
    applySceneToEditor,
    scheduleSceneSave,
    shareToken,
    token,
    workspaceSlug,
  ]);

  const saveTitle = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage) return;
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === activeBoard.title) return;
    try {
      const updated = shareToken
        ? await updateSharedWhiteboard(token, shareToken, { title: nextTitle })
        : await updateWhiteboard(token, activeBoard.id, { title: nextTitle }, workspaceSlug);
      setActiveBoard((current) => current ? { ...current, ...updated } : updated);
      onBoardUpdated?.(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename whiteboard.');
      setTitleDraft(activeBoard.title);
    }
  }, [activeBoard, onBoardUpdated, shareToken, titleDraft, token, workspaceSlug]);

  const handleArchive = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage) return;
    try {
      await deleteWhiteboard(token, activeBoard.id, workspaceSlug);
      onArchived?.(activeBoard.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to archive whiteboard.');
    }
  }, [activeBoard, onArchived, token, workspaceSlug]);

  const handlePermanentDelete = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage || !activeBoard.trashed_at) return;
    if (!window.confirm(`Delete "${activeBoard.title}" permanently?`)) return;
    try {
      await permanentlyDeleteWhiteboard(token, activeBoard.id, workspaceSlug);
      onDeleted?.(activeBoard.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete whiteboard.');
    }
  }, [activeBoard, onDeleted, token, workspaceSlug]);

  const handleFavorite = useCallback(async () => {
    if (!token || !activeBoard || shareToken) return;
    try {
      const response = await toggleWhiteboardFavorite(token, activeBoard.id, workspaceSlug);
      setActiveBoard((current) => current ? { ...current, is_favorite: response.is_favorite } : current);
      onBoardUpdated?.({ ...activeBoard, is_favorite: response.is_favorite });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update favorite.');
    }
  }, [activeBoard, onBoardUpdated, shareToken, token, workspaceSlug]);

  const currentApi = () => {
    const api = apiRef.current;
    if (!api || !activeBoard) return null;
    return api;
  };

  async function exportPng() {
    const api = currentApi();
    if (!api || !activeBoard) return;
    const blob = await exportToBlob({
      elements: api.getSceneElements(),
      appState: api.getAppState(),
      files: api.getFiles(),
      mimeType: 'image/png',
      exportPadding: 16,
    });
    downloadBlob(blob, safeFilename(activeBoard.title, 'png'));
  }

  async function exportSvg() {
    const api = currentApi();
    if (!api || !activeBoard) return;
    const svg = await exportToSvg({
      elements: api.getSceneElements(),
      appState: api.getAppState(),
      files: api.getFiles(),
      exportPadding: 16,
    });
    downloadBlob(new Blob([svg.outerHTML], { type: 'image/svg+xml' }), safeFilename(activeBoard.title, 'svg'));
  }

  function exportJson() {
    const api = currentApi();
    if (!api || !activeBoard) return;
    const json = serializeAsJSON(
      api.getSceneElementsIncludingDeleted(),
      api.getAppState(),
      api.getFiles(),
      'local',
    );
    downloadBlob(new Blob([json], { type: 'application/json' }), safeFilename(activeBoard.title, 'excalidraw'));
  }

  const initialData = useMemo<ExcalidrawInitialDataState | null>(() => {
    if (!activeBoard) return null;
    const scene = normalizeWhiteboardScene(activeBoard.scene);
    return {
      elements: scene.elements as ExcalidrawInitialDataState['elements'],
      appState: {
        ...scene.appState,
        name: activeBoard.title,
      } as ExcalidrawInitialDataState['appState'],
      files: scene.files as ExcalidrawInitialDataState['files'],
    };
  }, [activeBoard]);

  const label = saveLabel(saveStatus);
  const liveLabel = collabLabel(collabStatus);

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col bg-app-bg text-app-ink', className)}>
      {error ? (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
          {error}
        </div>
      ) : null}

      {!activeBoard ? (
        <div className="flex min-h-0 flex-1 items-center justify-center">
          {loading ? (
            <Loader2 size={24} className="animate-spin text-app-ink/40" />
          ) : (
            <p className="app-text-body text-app-ink/45">Whiteboard를 불러올 수 없습니다.</p>
          )}
        </div>
      ) : (
        <>
          <div className="flex min-h-[56px] items-center gap-2 border-b border-app-border bg-app-surface px-4">
            <input
              value={titleDraft}
              onChange={(event) => setTitleDraft(event.target.value)}
              onBlur={saveTitle}
              onKeyDown={(event) => {
                if (event.key === 'Enter') event.currentTarget.blur();
              }}
              disabled={!activeBoard.can_manage}
              className="app-text-title-md min-w-0 flex-1 rounded-md bg-transparent px-2 py-1 text-app-ink outline-none transition-colors enabled:hover:bg-app-surface-hover enabled:focus:bg-app-bg"
            />
            {label ? (
              <span className={cn('app-text-caption shrink-0', saveStatus === 'error' ? 'text-rose-500' : 'text-app-ink/45')}>
                {label}
              </span>
            ) : null}
            {liveLabel ? (
              <span
                className={cn(
                  'app-text-caption shrink-0 rounded-full border px-2 py-0.5',
                  collabStatus === 'connected'
                    ? 'border-emerald-500/25 text-emerald-600 dark:text-emerald-300'
                    : 'border-amber-500/25 text-amber-600 dark:text-amber-300',
                )}
              >
                {liveLabel}
              </span>
            ) : null}
            {!shareToken ? (
              <button
                type="button"
                onClick={handleFavorite}
                className={cn(
                  'inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors hover:bg-app-surface-hover',
                  activeBoard.is_favorite ? 'text-amber-500' : 'text-app-ink/60 hover:text-app-ink',
                )}
                title={activeBoard.is_favorite ? 'Unfavorite' : 'Favorite'}
              >
                <Star size={15} fill={activeBoard.is_favorite ? 'currentColor' : 'none'} />
              </button>
            ) : null}
            <button type="button" onClick={exportPng} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title="Download PNG">
              <Image size={15} />
            </button>
            <button type="button" onClick={exportSvg} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title="Download SVG">
              <Download size={15} />
            </button>
            <button type="button" onClick={exportJson} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title="Download Excalidraw JSON">
              <FileJson size={15} />
            </button>
            {!shareToken && activeBoard.can_share ? (
              <button type="button" onClick={() => setShareOpen(true)} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title="Share">
                <Share2 size={15} />
              </button>
            ) : null}
            <button type="button" onClick={loadBoard} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title="Reload">
              <RefreshCcw size={15} />
            </button>
            {showDetach && onDetach ? (
              <button type="button" onClick={onDetach} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500" title="Detach">
                <Trash2 size={15} />
              </button>
            ) : null}
            {!shareToken && showArchive && activeBoard.can_manage && !activeBoard.trashed_at ? (
              <button type="button" onClick={handleArchive} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500" title="Archive">
                <Archive size={15} />
              </button>
            ) : null}
            {!shareToken && showArchive && activeBoard.can_manage && activeBoard.trashed_at ? (
              <button type="button" onClick={handlePermanentDelete} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500" title="Delete permanently">
                <Trash2 size={15} />
              </button>
            ) : null}
          </div>

          <div className="relative min-h-0 flex-1 bg-white">
            {loading ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-bg/60">
                <Loader2 size={24} className="animate-spin text-app-ink/50" />
              </div>
            ) : null}
            {initialData ? (
              <Excalidraw
                key={activeBoard.id}
                excalidrawAPI={(api) => {
                  apiRef.current = api;
                  const pendingScene = pendingRemoteSceneRef.current;
                  if (pendingScene) {
                    pendingRemoteSceneRef.current = null;
                    applySceneToEditor(pendingScene);
                  }
                }}
                initialData={initialData}
                onChange={(elements, appState, files) => {
                  if (!activeBoard.can_edit) return;
                  updateAwarenessSelection(appState.selectedElementIds);
                  const scene = apiRef.current
                    ? sceneFromEditorAPI(apiRef.current)
                    : sceneFromExcalidraw(elements, appState, files);
                  publishSceneToCollab(scene);
                  scheduleSceneSave(scene);
                }}
                onPointerUpdate={publishPointerToCollab}
                isCollaborating={collabStatus === 'connected'}
                viewModeEnabled={!activeBoard.can_edit}
                theme={excalidrawTheme}
                aiEnabled={false}
                UIOptions={{
                  canvasActions: {
                    loadScene: false,
                    saveToActiveFile: false,
                    export: false,
                    toggleTheme: false,
                  },
                }}
              />
            ) : null}
          </div>

          {shareOpen ? (
            <WhiteboardShareDialog
              board={activeBoard}
              workspaceSlug={workspaceSlug}
              open={shareOpen}
              onClose={() => setShareOpen(false)}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
