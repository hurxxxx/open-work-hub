import { WhiteboardGroupSharing } from './WhiteboardGroupSharing';
import {
  CaptureUpdateAction,
  Excalidraw,
  exportToBlob,
  exportToSvg,
  newElementWith,
  reconcileElements,
  restoreLibraryItems,
  serializeAsJSON,
  THEME,
} from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';
import type {
  ExcalidrawImperativeAPI,
  ExcalidrawInitialDataState,
  ExcalidrawProps,
  LibraryItems,
} from '@excalidraw/excalidraw/types';
import { Button, Dialog, DropdownMenu } from '@open-work-hub/ui';
import {
  ArchiveRestore,
  Download,
  FileJson,
  Grid3X3,
  Image,
  Link as LinkIcon,
  Loader2,
  MoreHorizontal,
  Pencil,
  RefreshCcw,
  Share2,
  Star,
  Trash2,
  X,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import type * as Y from 'yjs';
import { updateWhiteboardCompanySharing } from '../api/whiteboard-api';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import {
  deleteWhiteboard,
  deleteWhiteboardLinkShare,
  deleteWhiteboardUserShare,
  getSharedWhiteboard,
  getWhiteboard,
  getWhiteboardCollabSession,
  getWhiteboardSharing,
  listWhiteboardShareableUsers,
  normalizeWhiteboardScene,
  permanentlyDeleteWhiteboard,
  recordSharedWhiteboardView,
  recordWhiteboardView,
  restoreWhiteboard,
  toggleWhiteboardFavorite,
  updateSharedWhiteboard,
  updateWhiteboard,
  upsertWhiteboardLinkShare,
  upsertWhiteboardUserShare,
  type ShareableUserItem,
  type WhiteboardDetail,
  type WhiteboardScene,
  type WhiteboardSharingResponse,
  type WhiteboardVisibility,
} from '../api/whiteboard-api';
import architectureDiagramComponentsLibrary from '../libraries/architecture-diagram-components.excalidrawlib.json';
import awesomeIconsLibrary from '../libraries/awesome-icons.excalidrawlib.json';
import drwnioLibrary from '../libraries/drwnio.excalidrawlib.json';
import softwareArchitectureLibrary from '../libraries/software-architecture.excalidrawlib.json';
import systemDesignLibrary from '../libraries/system-design.excalidrawlib.json';
import { useWhiteboardScenePersistence } from './useWhiteboardScenePersistence';
import {
  createWhiteboardCollabDocumentState,
  createWhiteboardCollabProvider,
  WHITEBOARD_LOCAL_COLLAB_ORIGIN,
  WHITEBOARD_REMOTE_APPLY_GUARD_MS,
  type WhiteboardCollabProvider,
} from './whiteboard-collab-runtime';
import {
  buildWhiteboardCollaborators,
  createWhiteboardAwarenessUser,
  normalizeWhiteboardSelectedElementIds,
  resolveWhiteboardCollabStatus,
  resolveWhiteboardConnectionCloseStatus,
  resolveWhiteboardProviderStatus,
  type ActiveWhiteboardCollabStatus,
  type WhiteboardCollabStatusSnapshot,
} from './whiteboard-collab-runtime-model';
import {
  buildCollabSceneFromMaps,
  elementId,
  sceneSignature,
  selectedElementCount,
  writeCollabSceneToMaps,
  type WhiteboardCollabSceneMaps,
  type WhiteboardElement,
} from './whiteboard-collab-scene';
import {
  collabLabel,
  safeFilename,
  saveLabel,
} from './whiteboard-editor-utils';
import { buildWhiteboardSharePresenter } from './whiteboard-share-model';
import { WhiteboardAccessBoundary } from './WhiteboardAccessBoundary';
import { buildWhiteboardVisibilityMenuItems } from './WhiteboardViewParts';

type ExcalidrawOnChange = NonNullable<ExcalidrawProps['onChange']>;
type ExcalidrawLibraryFile = {
  library?: unknown;
  libraryItems?: unknown;
};
type ImportedLibraryItems = Parameters<typeof restoreLibraryItems>[0];

function libraryItemsFromFile(
  libraryFile: ExcalidrawLibraryFile,
): LibraryItems {
  const rawItems = Array.isArray(libraryFile.libraryItems)
    ? libraryFile.libraryItems
    : Array.isArray(libraryFile.library)
      ? libraryFile.library
      : [];
  return restoreLibraryItems(rawItems as ImportedLibraryItems, 'published');
}

const WHITEBOARD_LIBRARY_ITEMS: LibraryItems = [
  ...libraryItemsFromFile(softwareArchitectureLibrary as ExcalidrawLibraryFile),
  ...libraryItemsFromFile(systemDesignLibrary as ExcalidrawLibraryFile),
  ...libraryItemsFromFile(
    architectureDiagramComponentsLibrary as ExcalidrawLibraryFile,
  ),
  ...libraryItemsFromFile(drwnioLibrary as ExcalidrawLibraryFile),
  ...libraryItemsFromFile(awesomeIconsLibrary as ExcalidrawLibraryFile),
];

export interface WhiteboardEditorSurfaceProps {
  boardId: string;

  className?: string;
  showArchive?: boolean;
  showDetach?: boolean;
  shareToken?: string | null;
  onBoardLoaded?: (board: WhiteboardDetail) => void;
  onBoardUpdated?: (board: WhiteboardDetail) => void;
  onArchived?: (boardId: string) => void;
  onDeleted?: (boardId: string) => void;
  onRestored?: (board: WhiteboardDetail) => void;
  onClose?: () => void;
  onDetach?: () => void;
}

function readExcalidrawTheme() {
  return typeof document !== 'undefined' &&
    document.documentElement.classList.contains('dark')
    ? THEME.DARK
    : THEME.LIGHT;
}

function subscribeExcalidrawTheme(onStoreChange: () => void) {
  if (typeof document === 'undefined') return () => undefined;
  const observer = new MutationObserver(onStoreChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  });
  return () => observer.disconnect();
}

function markElementDeleted(
  element: Parameters<ExcalidrawOnChange>[0][number],
): Parameters<ExcalidrawOnChange>[0][number] {
  return newElementWith(
    element as never,
    { isDeleted: true } as never,
  ) as Parameters<ExcalidrawOnChange>[0][number];
}

type WhiteboardShareDialogProps = {
  board: WhiteboardDetail;

  open: boolean;
  onClose: () => void;
};

function WhiteboardShareDialog(props: WhiteboardShareDialogProps) {
  return <>{useWhiteboardShareDialogElement(props)}</>;
}

function useWhiteboardShareDialogElement({
  board,
  open,
  onClose,
}: WhiteboardShareDialogProps): ReactNode {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const [sharing, setSharing] = useState<WhiteboardSharingResponse | null>(
    null,
  );
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
        getWhiteboardSharing(token, board.id),
        listWhiteboardShareableUsers(token, query),
      ]);
      setSharing(sharingResponse);
      setUsers(usersResponse);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.shareLoadFailed'),
      );
    } finally {
      setBusy(false);
    }
  }, [board.id, open, query, token, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<WhiteboardSharingResponse>) {
    setBusy(true);
    setError(null);
    try {
      setSharing(await action());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.shareSaveFailed'),
      );
    } finally {
      setBusy(false);
    }
  }

  const sharePresenter = useMemo(
    () =>
      buildWhiteboardSharePresenter({
        origin: window.location.origin,
        sharing,
        users,
      }),
    [sharing, users],
  );

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
      title={t('whiteboard.shareTitle')}
      description={t('whiteboard.shareDescription')}
      maxWidth="max-w-2xl"
      actions={
        <Button variant="secondary" onClick={onClose}>
          {t('common:actions.close')}
        </Button>
      }
    >
      <div className="space-y-5 text-app-ink">
        {token ? (
          <WhiteboardGroupSharing
            key={board.id}
            token={token}
            resourceId={board.id}
            canManage={board.can_share}
            ownershipKind={board.ownership_kind}
          />
        ) : null}
        {error ? (
          <div className="rounded-md border border-rose-500/30 bg-app-danger/10 px-3 py-2 text-sm text-rose-500">
            {error}
          </div>
        ) : null}

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="app-text-control-sm text-app-ink">
              {t('whiteboard.linkShare')}
            </h3>
            {sharing?.link_share ? (
              <Button
                variant="secondary"
                size="dense"
                disabled={busy}
                onClick={() => {
                  if (!token) return;
                  void run(() => deleteWhiteboardLinkShare(token, board.id));
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
                  void run(() =>
                    upsertWhiteboardLinkShare(token, board.id, {
                      access_level: 'read',
                    }),
                  );
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
                aria-label={t('whiteboard.shareLinkUrl')}
                value={sharePresenter.linkUrl}
                className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink/70 outline-none"
              />
              <select
                value={sharing.link_share.access_level}
                disabled={busy}
                onChange={(event) => {
                  if (!token) return;
                  void run(() =>
                    upsertWhiteboardLinkShare(token, board.id, {
                      access_level: event.target.value as 'read' | 'edit',
                    }),
                  );
                }}
                className="app-field-input-sm w-auto"
              >
                <option value="read">{t('docs.share.access.read')}</option>
                <option value="edit">{t('docs.share.access.edit')}</option>
              </select>
              <Button
                variant="secondary"
                size="dense"
                disabled={busy}
                onClick={() => {
                  const linkShare = sharing?.link_share;
                  if (!token || !linkShare) return;
                  void run(() =>
                    upsertWhiteboardLinkShare(token, board.id, {
                      access_level: linkShare.access_level,
                      regenerate_token: true,
                    }),
                  );
                }}
              >
                {t('docs.share.regenerate')}
              </Button>
              <Button
                variant="secondary"
                size="dense"
                onClick={() =>
                  void navigator.clipboard.writeText(sharePresenter.linkUrl)
                }
              >
                {t('docs.share.copy')}
              </Button>
            </div>
          ) : null}
        </section>

        <section className="space-y-3">
          <div className="space-y-1">
            <label className="app-text-control-sm text-app-ink/70">
              {t('ai.search.metadataPeople')}
            </label>
            <input
              aria-label={t('pms.searchUser')}
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
                <div className="px-4 py-6 text-center text-sm text-app-ink/45">
                  {t('whiteboard.noShareableUsers')}
                </div>
              ) : (
                sharePresenter.userRows.map(
                  ({ currentShare, shared, user }) => {
                    return (
                      <div
                        key={user.id}
                        className="flex items-center justify-between gap-3 border-b border-app-border px-3 py-2 last:border-b-0"
                      >
                        <div className="min-w-0">
                          <p className="app-text-body-sm truncate text-app-ink">
                            {user.full_name}
                          </p>
                          <p className="app-text-caption truncate text-app-ink/45">
                            {user.email}
                          </p>
                        </div>
                        {shared && currentShare ? (
                          <div className="flex shrink-0 items-center gap-2">
                            <select
                              value={currentShare.access_level}
                              disabled={busy}
                              onChange={(event) => {
                                if (!token) return;
                                void run(() =>
                                  upsertWhiteboardUserShare(
                                    token,
                                    board.id,
                                    user.id,
                                    event.target.value as 'read' | 'edit',
                                  ),
                                );
                              }}
                              className="app-field-input-sm w-auto"
                            >
                              <option value="read">
                                {t('docs.share.access.read')}
                              </option>
                              <option value="edit">
                                {t('docs.share.access.edit')}
                              </option>
                            </select>
                            <Button
                              variant="ghost"
                              size="dense"
                              disabled={busy}
                              onClick={() => {
                                if (!token) return;
                                void run(() =>
                                  deleteWhiteboardUserShare(
                                    token,
                                    board.id,
                                    user.id,
                                  ),
                                );
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
                              void run(() =>
                                upsertWhiteboardUserShare(
                                  token,
                                  board.id,
                                  user.id,
                                  'read',
                                ),
                              );
                            }}
                          >
                            {t('common:actions.add')}
                          </Button>
                        )}
                      </div>
                    );
                  },
                )
              )}
            </div>
          )}
        </section>
      </div>
    </Dialog>
  );
}

export function WhiteboardEditorSurface(props: WhiteboardEditorSurfaceProps) {
  return (
    <WhiteboardAccessBoundary
      key={`${props.boardId}:${props.shareToken ?? ''}`}
      boardId={props.boardId}
      shareToken={props.shareToken ?? null}
    >
      {(isCurrent) => (
        <WhiteboardEditorSession {...props} isCurrent={isCurrent} />
      )}
    </WhiteboardAccessBoundary>
  );
}

function WhiteboardEditorSession({
  isCurrent,
  onBoardLoaded,
  onBoardUpdated,
  ...props
}: WhiteboardEditorSurfaceProps & { isCurrent: () => boolean }) {
  const notifyLoaded = useCallback(
    (board: WhiteboardDetail) => {
      if (isCurrent()) onBoardLoaded?.(board);
    },
    [isCurrent, onBoardLoaded],
  );
  const notifyUpdated = useCallback(
    (board: WhiteboardDetail) => {
      if (isCurrent()) onBoardUpdated?.(board);
    },
    [isCurrent, onBoardUpdated],
  );
  return (
    <>
      {useWhiteboardEditorSurfaceElement({
        ...props,
        onBoardLoaded: notifyLoaded,
        onBoardUpdated: notifyUpdated,
      })}
    </>
  );
}

function useWhiteboardEditorSurfaceElement({
  boardId,
  className,
  showArchive = true,
  showDetach = false,
  shareToken = null,
  onBoardLoaded,
  onBoardUpdated,
  onArchived,
  onDeleted,
  onRestored,
  onClose,
  onDetach,
}: WhiteboardEditorSurfaceProps): ReactNode {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const [activeBoard, setActiveBoard] = useState<WhiteboardDetail | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collabStatusSnapshot, setCollabStatusSnapshot] =
    useState<WhiteboardCollabStatusSnapshot | null>(null);
  const [collabRequestedBoardId, setCollabRequestedBoardId] = useState<
    string | null
  >(null);
  const [shareOpen, setShareOpen] = useState(false);
  const excalidrawTheme = useSyncExternalStore(
    subscribeExcalidrawTheme,
    readExcalidrawTheme,
    () => THEME.LIGHT,
  );
  const [gridModeEnabled, setGridModeEnabled] = useState(false);
  const [selectedElementsCount, setSelectedElementsCount] = useState(0);
  const [closePending, setClosePending] = useState(false);
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null);
  const activeBoardRef = useRef<WhiteboardDetail | null>(null);
  const activeBoardIdRef = useRef<string | null>(null);
  const loadRequestRef = useRef(0);
  const collabDocRef = useRef<Y.Doc | null>(null);
  const collabProviderRef = useRef<WhiteboardCollabProvider | null>(null);
  const collabElementsMapRef = useRef<Y.Map<unknown> | null>(null);
  const collabElementOrderRef = useRef<Y.Array<string> | null>(null);
  const collabFilesMapRef = useRef<Y.Map<unknown> | null>(null);
  const collabAppStateMapRef = useRef<Y.Map<unknown> | null>(null);
  const applyingRemoteSceneRef = useRef(false);
  const pendingRemoteSceneRef = useRef<WhiteboardScene | null>(null);
  const lastPublishedCollabSignatureRef = useRef<string | null>(null);
  const lastAppliedRemoteSceneSignatureRef = useRef<string | null>(null);
  const remoteApplyGuardTimerRef = useRef<number | null>(null);
  const editableBoardId =
    token && activeBoard?.id && activeBoard.can_edit && !shareToken
      ? activeBoard.id
      : null;
  const collabBoardId =
    editableBoardId && collabRequestedBoardId === editableBoardId
      ? editableBoardId
      : null;
  const canEditCanvas = Boolean(
    activeBoard?.can_edit && (shareToken || collabBoardId),
  );
  const collabStatus = resolveWhiteboardCollabStatus({
    boardId: collabBoardId,
    snapshot: collabStatusSnapshot,
  });

  const publishSceneToCollab = useCallback(
    (scene: WhiteboardScene, knownSignature?: string) => {
      const doc = collabDocRef.current;
      const elementsMap = collabElementsMapRef.current;
      const elementOrder = collabElementOrderRef.current;
      const filesMap = collabFilesMapRef.current;
      const appStateMap = collabAppStateMapRef.current;
      if (
        !doc ||
        !elementsMap ||
        !elementOrder ||
        !filesMap ||
        !appStateMap ||
        applyingRemoteSceneRef.current
      ) {
        return false;
      }
      const normalized = normalizeWhiteboardScene(scene);
      const signature = knownSignature ?? sceneSignature(normalized);
      if (signature === lastPublishedCollabSignatureRef.current) {
        return true;
      }
      const collabMaps: WhiteboardCollabSceneMaps = {
        elementsMap,
        elementOrder,
        filesMap,
        appStateMap,
      };
      doc.transact(() => {
        writeCollabSceneToMaps(collabMaps, normalized);
      }, WHITEBOARD_LOCAL_COLLAB_ORIGIN);
      lastPublishedCollabSignatureRef.current = signature;
      return true;
    },
    [],
  );

  const {
    flushPendingSceneBeforeClose,
    queueLocalChange,
    resetLoadedScene,
    saveStatus,
    schedulePendingCollabPublish,
  } = useWhiteboardScenePersistence({
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
    translate: t,
  });

  useEffect(
    () => () => {
      if (remoteApplyGuardTimerRef.current !== null) {
        window.clearTimeout(remoteApplyGuardTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    activeBoardIdRef.current = activeBoard?.id ?? null;
    activeBoardRef.current = activeBoard;
  }, [activeBoard]);

  useEffect(() => {
    setCollabRequestedBoardId(null);
  }, [activeBoard?.id]);

  const loadBoard = useCallback(async () => {
    if (!token) return;
    const requestId = ++loadRequestRef.current;
    setLoading(true);
    setError(null);
    try {
      const board = shareToken
        ? await getSharedWhiteboard(token, shareToken)
        : await getWhiteboard(token, boardId);
      if (loadRequestRef.current !== requestId) return;
      const normalized = {
        ...board,
        scene: normalizeWhiteboardScene(board.scene),
      };
      resetLoadedScene(normalized.scene);
      lastAppliedRemoteSceneSignatureRef.current = null;
      setSelectedElementsCount(0);
      setActiveBoard(normalized);
      setTitleDraft(normalized.title);
      setGridModeEnabled(Boolean(normalized.scene.appState.gridModeEnabled));
      onBoardLoaded?.(normalized);
      if (shareToken) {
        void recordSharedWhiteboardView(token, shareToken);
      } else {
        void recordWhiteboardView(token, boardId);
      }
    } catch (err) {
      if (loadRequestRef.current !== requestId) return;
      setError(err instanceof Error ? err.message : t('whiteboard.loadFailed'));
      setActiveBoard(null);
      setGridModeEnabled(false);
      setSelectedElementsCount(0);
    } finally {
      if (loadRequestRef.current === requestId) setLoading(false);
    }
  }, [boardId, onBoardLoaded, resetLoadedScene, shareToken, token, t]);

  useEffect(() => {
    void loadBoard();
    return () => {
      loadRequestRef.current += 1;
    };
  }, [loadBoard]);

  const applySceneToEditor = useCallback(
    (scene: WhiteboardScene) => {
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
      const remoteElements =
        normalized.elements as Parameters<ExcalidrawOnChange>[0];
      const elements =
        localElements.length > 0
          ? reconcileElements(
              localElements,
              remoteElements as never,
              api.getAppState(),
            )
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
        schedulePendingCollabPublish();
      }, WHITEBOARD_REMOTE_APPLY_GUARD_MS);
    },
    [schedulePendingCollabPublish],
  );

  const clearEditorCollaborators = useCallback(() => {
    apiRef.current?.updateScene({
      collaborators: new Map(),
      captureUpdate: CaptureUpdateAction.NEVER,
    });
  }, []);

  const updateCollabStatus = useCallback(
    (boardId: string, status: ActiveWhiteboardCollabStatus) => {
      setCollabStatusSnapshot({ boardId, status });
    },
    [],
  );

  const applyCollabScene = useCallback(
    (whiteboardId: string, scene: WhiteboardScene) => {
      setActiveBoard((current) =>
        current && current.id === whiteboardId
          ? { ...current, scene }
          : current,
      );
      applySceneToEditor(scene);
    },
    [applySceneToEditor],
  );

  const handleCollabStartError = useCallback(
    (boardId: string, err: unknown) => {
      updateCollabStatus(boardId, 'error');
      setError(
        err instanceof Error ? err.message : t('whiteboard.collabStartFailed'),
      );
    },
    [t, updateCollabStatus],
  );

  const updateAwarenessSelection = useCallback(
    (selectedElementIds: unknown) => {
      const provider = collabProviderRef.current;
      if (!provider) return;
      provider.awareness.setLocalStateField(
        'selectedElementIds',
        normalizeWhiteboardSelectedElementIds(selectedElementIds),
      );
    },
    [],
  );

  const publishPointerToCollab = useCallback<
    NonNullable<ExcalidrawProps['onPointerUpdate']>
  >(
    (payload) => {
      const provider = collabProviderRef.current;
      if (!provider) return;
      provider.awareness.setLocalStateField('cursor', payload.pointer);
      provider.awareness.setLocalStateField('button', payload.button);
      updateAwarenessSelection(
        apiRef.current?.getAppState().selectedElementIds ?? {},
      );
    },
    [updateAwarenessSelection],
  );

  useEffect(() => {
    let cancelled = false;
    let provider: WhiteboardCollabProvider | null = null;
    let doc: Y.Doc | null = null;
    let elementsMap: Y.Map<unknown> | null = null;
    let elementOrder: Y.Array<string> | null = null;
    let filesMap: Y.Map<unknown> | null = null;
    let appStateMap: Y.Map<unknown> | null = null;
    let observer:
      | ((event: { transaction: { origin: unknown } }) => void)
      | null = null;
    let remoteApplyTimer: number | null = null;
    let handleProviderStatus: ((event: { status?: string }) => void) | null =
      null;
    let handleConnectionClose: ((event: CloseEvent | null) => void) | null =
      null;
    let handleAwarenessChange: (() => void) | null = null;

    collabDocRef.current = null;
    collabProviderRef.current = null;
    collabElementsMapRef.current = null;
    collabElementOrderRef.current = null;
    collabFilesMapRef.current = null;
    collabAppStateMapRef.current = null;
    lastPublishedCollabSignatureRef.current = null;

    if (!token || !collabBoardId) {
      return undefined;
    }

    const whiteboardId = collabBoardId;
    const seedScene = normalizeWhiteboardScene(activeBoardRef.current?.scene);

    void getWhiteboardCollabSession(token, whiteboardId)
      .then((session) => {
        if (cancelled) return;
        if (!session.can_edit || session.realtime_status !== 'enabled') {
          updateCollabStatus(whiteboardId, 'offline');
          return;
        }

        const documentState = createWhiteboardCollabDocumentState({
          seedScene,
          session,
        });
        doc = documentState.doc;
        elementsMap = documentState.maps.elementsMap;
        elementOrder = documentState.maps.elementOrder;
        filesMap = documentState.maps.filesMap;
        appStateMap = documentState.maps.appStateMap;

        collabDocRef.current = doc;
        collabElementsMapRef.current = elementsMap;
        collabElementOrderRef.current = elementOrder;
        collabFilesMapRef.current = filesMap;
        collabAppStateMapRef.current = appStateMap;
        lastPublishedCollabSignatureRef.current =
          documentState.initialSignature;
        applyCollabScene(session.whiteboard_id, documentState.initialScene);

        observer = (event) => {
          if (
            event.transaction.origin === WHITEBOARD_LOCAL_COLLAB_ORIGIN ||
            !elementsMap ||
            !elementOrder ||
            !filesMap ||
            !appStateMap
          ) {
            return;
          }
          if (remoteApplyTimer !== null) {
            window.clearTimeout(remoteApplyTimer);
          }
          remoteApplyTimer = window.setTimeout(() => {
            if (!elementsMap || !elementOrder || !filesMap || !appStateMap)
              return;
            const normalized = buildCollabSceneFromMaps({
              elementsMap,
              elementOrder,
              filesMap,
              appStateMap,
            });
            const signature = sceneSignature(normalized);
            if (signature === lastPublishedCollabSignatureRef.current) {
              return;
            }
            lastPublishedCollabSignatureRef.current = signature;
            applyCollabScene(session.whiteboard_id, normalized);
          }, 0);
        };
        elementsMap.observe(observer);
        elementOrder.observe(observer);
        filesMap.observe(observer);
        appStateMap.observe(observer);

        provider = createWhiteboardCollabProvider({
          doc,
          roomKey: session.room_key,
          token,
          wsPath: session.ws_path,
        });
        collabProviderRef.current = provider;
        provider.awareness.setLocalStateField(
          'user',
          createWhiteboardAwarenessUser({
            id: session.user.id,
            fullName: session.user.full_name,
          }),
        );
        provider.awareness.setLocalStateField(
          'selectedElementIds',
          apiRef.current?.getAppState().selectedElementIds ?? {},
        );
        handleAwarenessChange = () => {
          if (!provider) return;
          const nextCollaborators = buildWhiteboardCollaborators({
            localClientId: provider.awareness.clientID,
            states: provider.awareness.getStates(),
          });
          apiRef.current?.updateScene({
            collaborators: nextCollaborators,
            captureUpdate: CaptureUpdateAction.NEVER,
          });
        };
        handleProviderStatus = (event) => {
          const nextStatus = resolveWhiteboardProviderStatus(event.status);
          if (nextStatus) {
            updateCollabStatus(whiteboardId, nextStatus);
          }
        };
        handleConnectionClose = (event) => {
          if (event?.code === 4429) {
            updateCollabStatus(whiteboardId, 'error');
            setCollabRequestedBoardId(null);
            setError(t('whiteboard.collabTooManyConnections'));
            provider?.disconnect();
            return;
          }
          const nextStatus = resolveWhiteboardConnectionCloseStatus(
            event?.code,
          );
          if (nextStatus) {
            updateCollabStatus(whiteboardId, nextStatus);
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
          handleCollabStartError(whiteboardId, err);
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
      clearEditorCollaborators();
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
    applyCollabScene,
    clearEditorCollaborators,
    collabBoardId,
    handleCollabStartError,
    schedulePendingCollabPublish,
    t,
    token,
    updateCollabStatus,
  ]);

  const saveTitle = useCallback(async (): Promise<boolean> => {
    if (!token || !activeBoard || !activeBoard.can_manage) return true;
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === activeBoard.title) return true;
    try {
      const updated = shareToken
        ? await updateSharedWhiteboard(token, shareToken, { title: nextTitle })
        : await updateWhiteboard(token, activeBoard.id, { title: nextTitle });
      setActiveBoard((current) =>
        current ? { ...current, ...updated } : updated,
      );
      onBoardUpdated?.(updated);
      return true;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.renameFailed'),
      );
      setTitleDraft(activeBoard.title);
      return false;
    }
  }, [activeBoard, onBoardUpdated, shareToken, titleDraft, token, t]);

  const handleArchive = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage) return;
    try {
      await deleteWhiteboard(token, activeBoard.id);
      onArchived?.(activeBoard.id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.archiveFailed'),
      );
    }
  }, [activeBoard, onArchived, token, t]);

  const handlePermanentDelete = useCallback(async () => {
    if (
      !token ||
      !activeBoard ||
      !activeBoard.can_manage ||
      !activeBoard.trashed_at
    )
      return;
    if (
      !window.confirm(
        t('whiteboard.deletePermanentConfirm', { title: activeBoard.title }),
      )
    )
      return;
    try {
      await permanentlyDeleteWhiteboard(token, activeBoard.id);
      onDeleted?.(activeBoard.id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.deleteFailed'),
      );
    }
  }, [activeBoard, onDeleted, token, t]);

  const handleRestore = useCallback(async () => {
    if (
      !token ||
      !activeBoard ||
      !activeBoard.can_manage ||
      !activeBoard.trashed_at
    )
      return;
    try {
      const restored = await restoreWhiteboard(token, activeBoard.id);
      const normalized = {
        ...restored,
        scene: normalizeWhiteboardScene(restored.scene),
      };
      setActiveBoard(normalized);
      onBoardUpdated?.(normalized);
      onRestored?.(normalized);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.restoreFailed'),
      );
    }
  }, [activeBoard, onBoardUpdated, onRestored, token, t]);

  const handleFavorite = useCallback(async () => {
    if (!token || !activeBoard || shareToken) return;
    try {
      const response = await toggleWhiteboardFavorite(token, activeBoard.id);
      setActiveBoard((current) =>
        current ? { ...current, is_favorite: response.is_favorite } : current,
      );
      onBoardUpdated?.({ ...activeBoard, is_favorite: response.is_favorite });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('whiteboard.favoriteFailed'),
      );
    }
  }, [activeBoard, onBoardUpdated, shareToken, token, t]);

  const handleVisibilityChange = useCallback(
    async (visibility: WhiteboardVisibility) => {
      if (!token || !activeBoard || shareToken || !activeBoard.can_manage)
        return;
      if ((visibility === 'company') === activeBoard.company_visible) return;
      if (
        visibility === 'company' &&
        !window.confirm(t('shell:contentPublication.confirm'))
      )
        return;
      try {
        const updated = await updateWhiteboardCompanySharing(
          token,
          activeBoard.id,
          visibility === 'company',
          true,
        );
        const normalized = {
          ...updated,
          scene: normalizeWhiteboardScene(updated.scene),
        };
        setActiveBoard(normalized);
        onBoardUpdated?.(normalized);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t('whiteboard.visibilityUpdateFailed'),
        );
      }
    },
    [activeBoard, onBoardUpdated, shareToken, t, token],
  );

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
    downloadBlobAsFile(blob, safeFilename(activeBoard.title, 'png'));
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
    downloadBlobAsFile(
      new Blob([svg.outerHTML], { type: 'image/svg+xml' }),
      safeFilename(activeBoard.title, 'svg'),
    );
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
    downloadBlobAsFile(
      new Blob([json], { type: 'application/json' }),
      safeFilename(activeBoard.title, 'excalidraw'),
    );
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
    if (canEditCanvas) {
      queueLocalChange({
        elements:
          api.getSceneElementsIncludingDeleted() as Parameters<ExcalidrawOnChange>[0],
        appState: nextAppState,
        files: api.getFiles(),
      });
    }
  }, [activeBoard, canEditCanvas, queueLocalChange]);

  const deleteSelectedElements = useCallback(() => {
    const api = apiRef.current;
    if (!api || !canEditCanvas) return;
    const appState = api.getAppState();
    const selectedElementIds = appState.selectedElementIds;
    const elements =
      api.getSceneElementsIncludingDeleted() as Parameters<ExcalidrawOnChange>[0];
    let deletedCount = 0;
    const nextElements = elements.map((element) => {
      const id = elementId(element);
      if (
        id &&
        selectedElementIds[id] === true &&
        !(element as WhiteboardElement).isDeleted
      ) {
        deletedCount += 1;
        return markElementDeleted(element);
      }
      return element;
    }) as Parameters<ExcalidrawOnChange>[0];
    if (deletedCount === 0) return;
    const nextAppState = {
      ...appState,
      selectedElementIds: {},
      selectedGroupIds: {},
      editingGroupId: null,
    } as Parameters<ExcalidrawOnChange>[1];
    api.updateScene({
      elements: nextElements as never,
      appState: nextAppState as never,
      captureUpdate: CaptureUpdateAction.IMMEDIATELY,
    });
    setSelectedElementsCount(0);
    updateAwarenessSelection({});
    queueLocalChange({
      elements: nextElements,
      appState: nextAppState,
      files: api.getFiles(),
    });
  }, [canEditCanvas, queueLocalChange, updateAwarenessSelection]);

  const handleClose = useCallback(async () => {
    if (!onClose || closePending) return;
    if (!activeBoard?.can_edit && !activeBoard?.can_manage) {
      onClose();
      return;
    }

    setClosePending(true);
    const titleSaved = await saveTitle();
    const sceneSaved = titleSaved
      ? await flushPendingSceneBeforeClose()
      : false;
    if (titleSaved && sceneSaved) {
      onClose();
      return;
    }
    setClosePending(false);
  }, [
    activeBoard?.can_edit,
    activeBoard?.can_manage,
    closePending,
    flushPendingSceneBeforeClose,
    onClose,
    saveTitle,
  ]);

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
      libraryItems: WHITEBOARD_LIBRARY_ITEMS,
    };
  }, [activeBoard]);

  const label = saveLabel(saveStatus, t);
  const liveLabel = collabLabel(collabStatus, t);
  const activeBoardVisibility: WhiteboardVisibility =
    activeBoard?.company_visible ? 'company' : 'personal';

  return (
    <div
      className={cn(
        'flex min-h-0 flex-1 flex-col bg-app-bg text-app-ink',
        className,
      )}
    >
      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-4 py-2 text-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {error}
        </div>
      ) : null}

      {!activeBoard ? (
        <div className="flex min-h-0 flex-1 items-center justify-center">
          {loading ? (
            <Loader2 size={24} className="animate-spin text-app-ink/40" />
          ) : (
            <p className="app-text-body text-app-ink/45">
              {t('whiteboard.loadFailed')}
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="flex min-h-[56px] items-center gap-2 border-b border-app-border bg-app-surface px-4">
            <input
              aria-label={t('whiteboard.titleInput')}
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
              <span
                className={cn(
                  'app-text-caption shrink-0',
                  saveStatus === 'error' ? 'text-rose-500' : 'text-app-ink/45',
                )}
              >
                {label}
              </span>
            ) : null}
            {liveLabel ? (
              <span
                className={cn(
                  'app-text-caption shrink-0 rounded-full border px-2 py-0.5',
                  collabStatus === 'connected'
                    ? 'border-app-success/25 text-app-success-text dark:text-app-success-text'
                    : 'border-amber-500/25 text-app-warning-text dark:text-app-warning-text',
                )}
              >
                {liveLabel}
              </span>
            ) : null}
            {!shareToken && activeBoard.can_edit && !collabBoardId ? (
              <button
                type="button"
                onClick={() => setCollabRequestedBoardId(activeBoard.id)}
                className="inline-flex items-center gap-2 rounded-md bg-app-accent px-3 py-1.5 text-[length:var(--ui-text-control)] font-medium text-app-accent-fg hover:opacity-90"
              >
                <Pencil size={14} />
                {t('whiteboard.startEditing')}
              </button>
            ) : null}
            {!shareToken ? (
              <button
                type="button"
                onClick={handleFavorite}
                className={cn(
                  'inline-flex size-8 items-center justify-center rounded-md transition-colors hover:bg-app-surface-hover',
                  activeBoard.is_favorite
                    ? 'text-app-warning'
                    : 'text-app-ink/60 hover:text-app-ink',
                )}
                title={
                  activeBoard.is_favorite
                    ? t('whiteboard.unfavorite')
                    : t('pms.actions.favorite')
                }
              >
                <Star
                  size={15}
                  fill={activeBoard.is_favorite ? 'currentColor' : 'none'}
                />
              </button>
            ) : null}
            <button
              type="button"
              onClick={toggleGridMode}
              aria-pressed={gridModeEnabled}
              className={cn(
                'inline-flex size-8 items-center justify-center rounded-md transition-colors hover:bg-app-surface-hover',
                gridModeEnabled
                  ? 'bg-app-surface-hover text-app-ink'
                  : 'text-app-ink/60 hover:text-app-ink',
              )}
              title={
                gridModeEnabled
                  ? t('whiteboard.hideGrid')
                  : t('whiteboard.showGrid')
              }
            >
              <Grid3X3 size={15} />
            </button>
            {canEditCanvas ? (
              <button
                type="button"
                onClick={deleteSelectedElements}
                disabled={selectedElementsCount === 0}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-rose-500 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-app-ink/60"
                title={
                  selectedElementsCount > 0
                    ? t('whiteboard.deleteSelectedElements', {
                        count: selectedElementsCount,
                      })
                    : t('whiteboard.deleteSelectedElementsDisabled')
                }
              >
                <Trash2 size={15} />
              </button>
            ) : null}
            <button
              type="button"
              onClick={exportPng}
              className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
              title={t('whiteboard.downloadPng')}
            >
              <Image size={15} />
            </button>
            <button
              type="button"
              onClick={exportSvg}
              className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
              title={t('whiteboard.downloadSvg')}
            >
              <Download size={15} />
            </button>
            <button
              type="button"
              onClick={exportJson}
              className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
              title={t('whiteboard.downloadJson')}
            >
              <FileJson size={15} />
            </button>
            {!shareToken && activeBoard.can_share ? (
              <button
                type="button"
                onClick={() => setShareOpen(true)}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
                title={t('common:actions.share')}
              >
                <Share2 size={15} />
              </button>
            ) : null}
            {!shareToken ? (
              <DropdownMenu
                align="end"
                side="bottom"
                trigger={
                  <button
                    type="button"
                    aria-label={t('whiteboard.actionsMenu')}
                    className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
                  >
                    <MoreHorizontal size={16} />
                  </button>
                }
                items={buildWhiteboardVisibilityMenuItems({
                  canManage: activeBoard.can_manage,
                  currentVisibility: activeBoardVisibility,
                  onChange: (visibility) =>
                    void handleVisibilityChange(visibility),
                  t,
                })}
              />
            ) : null}
            <button
              type="button"
              onClick={loadBoard}
              className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
              title={t('common:actions.reload')}
            >
              <RefreshCcw size={15} />
            </button>
            {showDetach && onDetach ? (
              <button
                type="button"
                onClick={onDetach}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500"
                title={t('whiteboard.detach')}
              >
                <Trash2 size={15} />
              </button>
            ) : null}
            {!shareToken &&
            showArchive &&
            activeBoard.can_manage &&
            !activeBoard.trashed_at ? (
              <button
                type="button"
                onClick={handleArchive}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500"
                title={t('whiteboard.moveToTrash')}
              >
                <Trash2 size={15} />
              </button>
            ) : null}
            {!shareToken &&
            showArchive &&
            activeBoard.can_manage &&
            activeBoard.trashed_at ? (
              <button
                type="button"
                onClick={() => void handleRestore()}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-success-text"
                title={t('whiteboard.restore')}
              >
                <ArchiveRestore size={15} />
              </button>
            ) : null}
            {!shareToken &&
            showArchive &&
            activeBoard.can_manage &&
            activeBoard.trashed_at ? (
              <button
                type="button"
                onClick={handlePermanentDelete}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-rose-500"
                title={t('common:actions.deletePermanently')}
              >
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
                  className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-wait disabled:opacity-60"
                  title={
                    closePending
                      ? t('whiteboard.savingBeforeClose')
                      : t('whiteboard.closeWhiteboard')
                  }
                >
                  {closePending ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <X size={16} />
                  )}
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
                  setSelectedElementsCount(
                    selectedElementCount(
                      apiRef.current?.getSceneElementsIncludingDeleted() ??
                        elements,
                      appState.selectedElementIds,
                    ),
                  );
                  if (!canEditCanvas) return;
                  updateAwarenessSelection(appState.selectedElementIds);
                  queueLocalChange({
                    elements:
                      (apiRef.current?.getSceneElementsIncludingDeleted() ??
                        elements) as Parameters<ExcalidrawOnChange>[0],
                    appState,
                    files,
                  });
                }}
                onPointerUpdate={publishPointerToCollab}
                isCollaborating={collabStatus === 'connected'}
                viewModeEnabled={!canEditCanvas}
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
              open={shareOpen}
              onClose={() => setShareOpen(false)}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
