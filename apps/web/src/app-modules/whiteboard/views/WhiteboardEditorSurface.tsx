import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CaptureUpdateAction,
  Excalidraw,
  exportToBlob,
  exportToSvg,
  getSceneVersion,
  reconcileElements,
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
  Grid3X3,
  Image,
  Link as LinkIcon,
  Loader2,
  RefreshCcw,
  Share2,
  Star,
  Trash2,
  X,
} from 'lucide-react';
import { Button, Dialog } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';

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
const LOCAL_CHANGE_FLUSH_MS = 160;
const REMOTE_APPLY_GUARD_MS = 32;

type PendingExcalidrawChange = {
  elements: Parameters<ExcalidrawOnChange>[0];
  appState: Parameters<ExcalidrawOnChange>[1];
  files: Parameters<ExcalidrawOnChange>[2];
};

type PendingCollabPublish = {
  scene: WhiteboardScene;
  signature: string;
};

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
  onClose?: () => void;
  onDetach?: () => void;
}

function readExcalidrawTheme() {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
    ? THEME.DARK
    : THEME.LIGHT;
}

function waitFor(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function sceneFromExcalidraw(
  elements: Parameters<ExcalidrawOnChange>[0],
  appState: Parameters<ExcalidrawOnChange>[1],
  files: Parameters<ExcalidrawOnChange>[2],
): WhiteboardScene {
  const serialized = normalizeWhiteboardScene(JSON.parse(serializeAsJSON(elements, appState, files, 'local')));
  return {
    ...serialized,
    elements: cloneCollabValue([...elements]),
  };
}

function sceneSignature(scene: WhiteboardScene): string {
  return JSON.stringify(scene);
}

function cloneCollabValue<T>(value: T): T {
  if (value === undefined || value === null) {
    return value;
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function cloneCollabElement(element: WhiteboardElement): WhiteboardElement {
  return cloneCollabValue(element);
}

function uniqueElementOrder(elements: readonly unknown[]): string[] {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const element of elements) {
    const id = elementId(element);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    order.push(id);
  }
  return order;
}

function elementsVersion(elements: readonly unknown[]): number {
  return getSceneVersion(elements as never);
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
    result[key] = cloneCollabValue(value);
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
    if (seen.has(id)) continue;
    const element = elementsMap.get(id);
    if (element) {
      elements.push(cloneCollabValue(element));
      seen.add(id);
    }
  }
  elementsMap.forEach((element, id) => {
    if (!seen.has(id)) {
      elements.push(cloneCollabValue(element));
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

function collabLabel(status: CollabStatus, t: (key: string) => string): string {
  if (status === 'connecting') return t('whiteboard.collabConnecting');
  if (status === 'connected') return t('whiteboard.collabLive');
  if (status === 'offline' || status === 'error') return t('whiteboard.collabOffline');
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

function saveLabel(status: SaveStatus, t: (key: string) => string): string {
  return {
    idle: '',
    dirty: t('common:actions.saving'),
    saving: t('common:actions.saving'),
    saved: t('whiteboard.saved'),
    error: t('whiteboard.saveFailed'),
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
  const { t } = useTranslation('apps');
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
      setError(err instanceof Error ? err.message : t('whiteboard.shareLoadFailed'));
    } finally {
      setBusy(false);
    }
  }, [board.id, open, query, token, workspaceSlug, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<WhiteboardSharingResponse>) {
    setBusy(true);
    setError(null);
    try {
      setSharing(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.shareSaveFailed'));
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
      title={t('whiteboard.shareTitle')}
      description={t('whiteboard.shareDescription')}
      maxWidth="max-w-2xl"
      actions={<Button variant="secondary" onClick={onClose}>{t('common:actions.close')}</Button>}
    >
      <div className="space-y-5 text-app-ink">
        {error ? (
          <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-500">
            {error}
          </div>
        ) : null}

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="app-text-control-sm text-app-ink">{t('whiteboard.linkShare')}</h3>
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
                {t('docs.share.disable')}
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
                {t('whiteboard.enableReadLink')}
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
                <option value="read">{t('docs.share.access.read')}</option>
                <option value="edit">{t('docs.share.access.edit')}</option>
              </select>
              <Button
                variant="secondary"
                size="dense"
                onClick={() => void navigator.clipboard.writeText(linkUrl)}
              >
                {t('docs.share.copy')}
              </Button>
            </div>
          ) : null}
        </section>

        <section className="space-y-3">
          <div className="space-y-1">
            <label className="app-text-control-sm text-app-ink/70">{t('ai.search.metadataPeople')}</label>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('pms.searchUser')}
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
                <div className="px-4 py-6 text-center text-sm text-app-ink/45">{t('whiteboard.noShareableUsers')}</div>
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
                            <option value="read">{t('docs.share.access.read')}</option>
                            <option value="edit">{t('docs.share.access.edit')}</option>
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
                            {t('pms.bulk.remove')}
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
                          {t('common:actions.add')}
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
  onClose,
  onDetach,
}: WhiteboardEditorSurfaceProps) {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const [activeBoard, setActiveBoard] = useState<WhiteboardDetail | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [collabStatus, setCollabStatus] = useState<CollabStatus>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [excalidrawTheme, setExcalidrawTheme] = useState(readExcalidrawTheme);
  const [gridModeEnabled, setGridModeEnabled] = useState(false);
  const [closePending, setClosePending] = useState(false);
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
  const lastAppliedRemoteSceneSignatureRef = useRef<string | null>(null);
  const remoteApplyGuardTimerRef = useRef<number | null>(null);
  const pendingLocalChangeRef = useRef<PendingExcalidrawChange | null>(null);
  const localChangeFlushTimerRef = useRef<number | null>(null);
  const queuedLocalElementsVersionRef = useRef<number | null>(null);
  const pendingCollabPublishRef = useRef<PendingCollabPublish | null>(null);
  const collabPublishRetryTimerRef = useRef<number | null>(null);
  const schedulePendingCollabPublishRef = useRef<(() => void) | null>(null);
  const saveSettledTimerRef = useRef<number | null>(null);
  const lastSaveFailedRef = useRef(false);

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
    if (remoteApplyGuardTimerRef.current !== null) {
      window.clearTimeout(remoteApplyGuardTimerRef.current);
    }
    if (localChangeFlushTimerRef.current !== null) {
      window.clearTimeout(localChangeFlushTimerRef.current);
    }
    if (collabPublishRetryTimerRef.current !== null) {
      window.clearTimeout(collabPublishRetryTimerRef.current);
    }
    if (saveSettledTimerRef.current !== null) {
      window.clearTimeout(saveSettledTimerRef.current);
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
      lastAppliedRemoteSceneSignatureRef.current = null;
      pendingSceneRef.current = null;
      pendingSceneSignatureRef.current = null;
      pendingLocalChangeRef.current = null;
      queuedLocalElementsVersionRef.current = null;
      pendingCollabPublishRef.current = null;
      if (localChangeFlushTimerRef.current !== null) {
        window.clearTimeout(localChangeFlushTimerRef.current);
        localChangeFlushTimerRef.current = null;
      }
      if (collabPublishRetryTimerRef.current !== null) {
        window.clearTimeout(collabPublishRetryTimerRef.current);
        collabPublishRetryTimerRef.current = null;
      }
      setActiveBoard(normalized);
      setTitleDraft(normalized.title);
      setGridModeEnabled(Boolean(normalized.scene.appState.gridModeEnabled));
      setSaveStatus('idle');
      onBoardLoaded?.(normalized);
      if (shareToken) {
        void recordSharedWhiteboardView(token, shareToken);
      } else {
        void recordWhiteboardView(token, boardId, workspaceSlug);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.loadFailed'));
      setActiveBoard(null);
      setGridModeEnabled(false);
    } finally {
      setLoading(false);
    }
  }, [boardId, onBoardLoaded, shareToken, token, workspaceSlug, t]);

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  const flushSceneSave = useCallback(async (resolvedBoardId: string): Promise<boolean> => {
    if (!token || saveInFlightRef.current) return false;
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
      saved = true;
    } catch (err) {
      lastSaveFailedRef.current = true;
      setError(err instanceof Error ? err.message : t('whiteboard.saveFailed'));
      setSaveStatus('error');
    } finally {
      saveInFlightRef.current = false;
      if (pendingSceneRef.current !== null && activeBoardIdRef.current === resolvedBoardId && saveTimerRef.current === null) {
        saveTimerRef.current = window.setTimeout(() => {
          saveTimerRef.current = null;
          void flushSceneSave(resolvedBoardId);
        }, 250);
      } else if (saved) {
        if (!shareToken) {
          pendingCollabPublishRef.current = { scene, signature };
          schedulePendingCollabPublishRef.current?.();
        }
        setSaveStatus('saved');
        if (saveSettledTimerRef.current !== null) {
          window.clearTimeout(saveSettledTimerRef.current);
        }
        saveSettledTimerRef.current = window.setTimeout(() => {
          saveSettledTimerRef.current = null;
          if (
            !saveInFlightRef.current
            && pendingSceneRef.current === null
            && pendingLocalChangeRef.current === null
            && localChangeFlushTimerRef.current === null
          ) {
            setSaveStatus('saved');
          }
        }, LOCAL_CHANGE_FLUSH_MS + 80);
      }
    }
    return saved;
  }, [onBoardUpdated, shareToken, token, workspaceSlug, t]);

  const scheduleSceneSave = useCallback((scene: WhiteboardScene, knownSignature?: string) => {
    if (!activeBoard?.id || !activeBoard.can_edit) return;
    const signature = knownSignature ?? sceneSignature(scene);
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
    lastAppliedRemoteSceneSignatureRef.current = sceneSignature(normalized);
    if (remoteApplyGuardTimerRef.current !== null) {
      window.clearTimeout(remoteApplyGuardTimerRef.current);
    }
    const files = Object.values(normalized.files);
    if (files.length > 0) {
      api.addFiles(files as never);
    }
    setGridModeEnabled(Boolean(normalized.appState.gridModeEnabled));
    const localElements = api.getSceneElementsIncludingDeleted();
    const remoteElements = normalized.elements as Parameters<ExcalidrawOnChange>[0];
    const elements = localElements.length > 0
      ? reconcileElements(localElements, remoteElements as never, api.getAppState())
      : remoteElements;
    api.updateScene({
      elements: elements as never,
      appState: {
        ...normalized.appState,
        name: board.title,
      } as never,
      captureUpdate: CaptureUpdateAction.NEVER,
    });
    remoteApplyGuardTimerRef.current = window.setTimeout(() => {
      remoteApplyGuardTimerRef.current = null;
      applyingRemoteSceneRef.current = false;
      schedulePendingCollabPublishRef.current?.();
    }, REMOTE_APPLY_GUARD_MS);
  }, []);

  const publishSceneToCollab = useCallback((scene: WhiteboardScene, knownSignature?: string) => {
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
      return false;
    }
    const normalized = normalizeWhiteboardScene(scene);
    const signature = knownSignature ?? sceneSignature(normalized);
    if (signature === lastPublishedCollabSignatureRef.current) {
      return true;
    }
    const elements = normalized.elements as WhiteboardElement[];
    const order = uniqueElementOrder(elements);
    doc.transact(() => {
      for (const element of elements) {
        const id = elementId(element);
        if (!id) continue;
        const current = elementsMap.get(id) as WhiteboardElement | undefined;
        if (shouldAcceptElementUpdate(element, current)) {
          elementsMap.set(id, cloneCollabElement(element));
        }
      }
      elementOrder.delete(0, elementOrder.length);
      elementOrder.insert(0, order);

      filesMap.clear();
      Object.entries(normalized.files).forEach(([key, value]) => {
        filesMap.set(key, cloneCollabValue(value));
      });

      appStateMap.clear();
      Object.entries(normalized.appState).forEach(([key, value]) => {
        appStateMap.set(key, cloneCollabValue(value));
      });
    }, LOCAL_COLLAB_ORIGIN);
    lastPublishedCollabSignatureRef.current = signature;
    return true;
  }, []);

  const flushPendingCollabPublish = useCallback(() => {
    collabPublishRetryTimerRef.current = null;
    const pending = pendingCollabPublishRef.current;
    if (!pending || shareToken || !activeBoardRef.current?.can_edit) {
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
      250,
    );
  }, [publishSceneToCollab, shareToken]);

  const schedulePendingCollabPublish = useCallback(() => {
    if (collabPublishRetryTimerRef.current !== null) return;
    collabPublishRetryTimerRef.current = window.setTimeout(
      flushPendingCollabPublish,
      0,
    );
  }, [flushPendingCollabPublish]);

  schedulePendingCollabPublishRef.current = schedulePendingCollabPublish;

  const flushQueuedLocalChange = useCallback(() => {
    localChangeFlushTimerRef.current = null;
    const pending = pendingLocalChangeRef.current;
    pendingLocalChangeRef.current = null;
    queuedLocalElementsVersionRef.current = null;
    if (!pending) {
      return;
    }
    if (applyingRemoteSceneRef.current) {
      pendingLocalChangeRef.current = pending;
      queuedLocalElementsVersionRef.current = elementsVersion(pending.elements);
      localChangeFlushTimerRef.current = window.setTimeout(
        flushQueuedLocalChange,
        REMOTE_APPLY_GUARD_MS + 16,
      );
      return;
    }

    const scene = sceneFromExcalidraw(pending.elements, pending.appState, pending.files);
    const signature = sceneSignature(scene);
    if (signature === lastAppliedRemoteSceneSignatureRef.current) {
      if (pendingSceneRef.current === null) {
        setSaveStatus((current) => current === 'dirty' ? 'idle' : current);
      }
      return;
    }
    if (signature === lastSavedSceneSignatureRef.current) {
      setSaveStatus((current) => current === 'dirty' ? 'idle' : current);
      return;
    }
    if (signature === lastPublishedCollabSignatureRef.current) {
      if (pendingSceneRef.current === null && !saveInFlightRef.current) {
        setSaveStatus('saved');
      }
      return;
    }
    if (signature === pendingSceneSignatureRef.current) {
      return;
    }
    if (!publishSceneToCollab(scene, signature)) {
      pendingCollabPublishRef.current = { scene, signature };
      schedulePendingCollabPublish();
    }
    scheduleSceneSave(scene, signature);
  }, [publishSceneToCollab, schedulePendingCollabPublish, scheduleSceneSave]);

  const queueLocalChange = useCallback((change: PendingExcalidrawChange) => {
    const nextVersion = elementsVersion(change.elements);
    if (
      localChangeFlushTimerRef.current !== null
      && queuedLocalElementsVersionRef.current === nextVersion
    ) {
      pendingLocalChangeRef.current = change;
      return;
    }
    queuedLocalElementsVersionRef.current = nextVersion;
    pendingLocalChangeRef.current = change;
    if (localChangeFlushTimerRef.current !== null) return;
    localChangeFlushTimerRef.current = window.setTimeout(
      flushQueuedLocalChange,
      LOCAL_CHANGE_FLUSH_MS,
    );
  }, [flushQueuedLocalChange]);

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
          const initialOrder = uniqueElementOrder(initialElements);
          doc.transact(() => {
            for (const element of initialElements) {
              const id = elementId(element);
              if (id) {
                elementsMap?.set(id, cloneCollabElement(element));
              }
            }
            elementOrder?.insert(0, initialOrder);
            Object.entries(initialScene.files).forEach(([key, value]) => {
              filesMap?.set(key, cloneCollabValue(value));
            });
            Object.entries(initialScene.appState).forEach(([key, value]) => {
              appStateMap?.set(key, cloneCollabValue(value));
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
        schedulePendingCollabPublish();
      })
      .catch((err) => {
        if (!cancelled) {
          setCollabStatus('error');
          setError(err instanceof Error ? err.message : t('whiteboard.collabStartFailed'));
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
    schedulePendingCollabPublish,
    shareToken,
    token,
    workspaceSlug,
    t,
  ]);

  const saveTitle = useCallback(async (): Promise<boolean> => {
    if (!token || !activeBoard || !activeBoard.can_manage) return true;
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === activeBoard.title) return true;
    try {
      const updated = shareToken
        ? await updateSharedWhiteboard(token, shareToken, { title: nextTitle })
        : await updateWhiteboard(token, activeBoard.id, { title: nextTitle }, workspaceSlug);
      setActiveBoard((current) => current ? { ...current, ...updated } : updated);
      onBoardUpdated?.(updated);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.renameFailed'));
      setTitleDraft(activeBoard.title);
      return false;
    }
  }, [activeBoard, onBoardUpdated, shareToken, titleDraft, token, workspaceSlug, t]);

  const handleArchive = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage) return;
    try {
      await deleteWhiteboard(token, activeBoard.id, workspaceSlug);
      onArchived?.(activeBoard.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.archiveFailed'));
    }
  }, [activeBoard, onArchived, token, workspaceSlug, t]);

  const handlePermanentDelete = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage || !activeBoard.trashed_at) return;
    if (!window.confirm(t('whiteboard.deletePermanentConfirm', { title: activeBoard.title }))) return;
    try {
      await permanentlyDeleteWhiteboard(token, activeBoard.id, workspaceSlug);
      onDeleted?.(activeBoard.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.deleteFailed'));
    }
  }, [activeBoard, onDeleted, token, workspaceSlug, t]);

  const handleFavorite = useCallback(async () => {
    if (!token || !activeBoard || shareToken) return;
    try {
      const response = await toggleWhiteboardFavorite(token, activeBoard.id, workspaceSlug);
      setActiveBoard((current) => current ? { ...current, is_favorite: response.is_favorite } : current);
      onBoardUpdated?.({ ...activeBoard, is_favorite: response.is_favorite });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.favoriteFailed'));
    }
  }, [activeBoard, onBoardUpdated, shareToken, token, workspaceSlug, t]);

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

  const toggleGridMode = useCallback(() => {
    const api = apiRef.current;
    if (!api || !activeBoard) return;
    const appState = api.getAppState();
    const nextGridMode = !appState.gridModeEnabled;
    const nextAppState = {
      ...appState,
      gridModeEnabled: nextGridMode,
    } as Parameters<ExcalidrawOnChange>[1];
    api.updateScene({
      appState: nextAppState as never,
      captureUpdate: CaptureUpdateAction.IMMEDIATELY,
    });
    setGridModeEnabled(nextGridMode);
    if (activeBoard.can_edit) {
      queueLocalChange({
        elements: api.getSceneElementsIncludingDeleted() as Parameters<ExcalidrawOnChange>[0],
        appState: nextAppState,
        files: api.getFiles(),
      });
    }
  }, [activeBoard, queueLocalChange]);

  const flushPendingSceneBeforeClose = useCallback(async (): Promise<boolean> => {
    const boardId = activeBoardIdRef.current;
    if (!boardId) return true;

    const flushQueuedLocalChangeNow = () => {
      if (localChangeFlushTimerRef.current !== null) {
        window.clearTimeout(localChangeFlushTimerRef.current);
        localChangeFlushTimerRef.current = null;
      }
      if (pendingLocalChangeRef.current !== null) {
        flushQueuedLocalChange();
      }
    };

    const clearScheduledSave = () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };

    lastSaveFailedRef.current = false;
    flushQueuedLocalChangeNow();
    clearScheduledSave();

    for (let attempt = 0; attempt < 80; attempt += 1) {
      if (pendingLocalChangeRef.current !== null || localChangeFlushTimerRef.current !== null) {
        flushQueuedLocalChangeNow();
      }

      clearScheduledSave();

      if (pendingSceneRef.current !== null && !saveInFlightRef.current) {
        const saved = await flushSceneSave(boardId);
        if (!saved && pendingSceneRef.current === null) {
          return false;
        }
        continue;
      }

      if (
        !saveInFlightRef.current
        && pendingSceneRef.current === null
        && pendingLocalChangeRef.current === null
        && localChangeFlushTimerRef.current === null
      ) {
        return !lastSaveFailedRef.current;
      }

      await waitFor(50);
    }

    setError(t('whiteboard.closeSaveIncomplete'));
    return false;
  }, [flushQueuedLocalChange, flushSceneSave, t]);

  const handleClose = useCallback(async () => {
    if (!onClose || closePending) return;
    if (!activeBoard?.can_edit && !activeBoard?.can_manage) {
      onClose();
      return;
    }

    setClosePending(true);
    const titleSaved = await saveTitle();
    const sceneSaved = titleSaved ? await flushPendingSceneBeforeClose() : false;
    if (titleSaved && sceneSaved) {
      onClose();
      return;
    }
    setClosePending(false);
  }, [activeBoard?.can_edit, activeBoard?.can_manage, closePending, flushPendingSceneBeforeClose, onClose, saveTitle]);

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

  const label = saveLabel(saveStatus, t);
  const liveLabel = collabLabel(collabStatus, t);

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
            <p className="app-text-body text-app-ink/45">{t('whiteboard.loadFailed')}</p>
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
                title={activeBoard.is_favorite ? t('whiteboard.unfavorite') : t('pms.actions.favorite')}
              >
                <Star size={15} fill={activeBoard.is_favorite ? 'currentColor' : 'none'} />
              </button>
            ) : null}
            <button
              type="button"
              onClick={toggleGridMode}
              aria-pressed={gridModeEnabled}
              className={cn(
                'inline-flex h-8 w-8 items-center justify-center rounded-md transition-colors hover:bg-app-surface-hover',
                gridModeEnabled ? 'bg-app-surface-hover text-app-ink' : 'text-app-ink/60 hover:text-app-ink',
              )}
              title={gridModeEnabled ? t('whiteboard.hideGrid') : t('whiteboard.showGrid')}
            >
              <Grid3X3 size={15} />
            </button>
            <button type="button" onClick={exportPng} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title={t('whiteboard.downloadPng')}>
              <Image size={15} />
            </button>
            <button type="button" onClick={exportSvg} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title={t('whiteboard.downloadSvg')}>
              <Download size={15} />
            </button>
            <button type="button" onClick={exportJson} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title={t('whiteboard.downloadJson')}>
              <FileJson size={15} />
            </button>
            {!shareToken && activeBoard.can_share ? (
              <button type="button" onClick={() => setShareOpen(true)} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title={t('common:actions.share')}>
                <Share2 size={15} />
              </button>
            ) : null}
            <button type="button" onClick={loadBoard} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink" title={t('common:actions.reload')}>
              <RefreshCcw size={15} />
            </button>
            {showDetach && onDetach ? (
              <button type="button" onClick={onDetach} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500" title={t('whiteboard.detach')}>
                <Trash2 size={15} />
              </button>
            ) : null}
            {!shareToken && showArchive && activeBoard.can_manage && !activeBoard.trashed_at ? (
              <button type="button" onClick={handleArchive} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500" title={t('common:actions.archive')}>
                <Archive size={15} />
              </button>
            ) : null}
            {!shareToken && showArchive && activeBoard.can_manage && activeBoard.trashed_at ? (
              <button type="button" onClick={handlePermanentDelete} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500" title={t('common:actions.deletePermanently')}>
                <Trash2 size={15} />
              </button>
            ) : null}
            {onClose ? (
              <>
                <div className="mx-1 h-6 w-px bg-app-border" />
                <button
                  type="button"
                  onClick={() => void handleClose()}
                  disabled={closePending}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-wait disabled:opacity-60"
                  title={closePending ? t('whiteboard.savingBeforeClose') : t('whiteboard.closeWhiteboard')}
                >
                  {closePending ? <Loader2 size={15} className="animate-spin" /> : <X size={16} />}
                </button>
              </>
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
                  setGridModeEnabled(Boolean(appState.gridModeEnabled));
                  if (!activeBoard.can_edit) return;
                  updateAwarenessSelection(appState.selectedElementIds);
                  queueLocalChange({
                    elements: (apiRef.current?.getSceneElementsIncludingDeleted() ?? elements) as Parameters<ExcalidrawOnChange>[0],
                    appState,
                    files,
                  });
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
