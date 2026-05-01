import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Excalidraw, serializeAsJSON, THEME } from '@excalidraw/excalidraw';
import type { ExcalidrawInitialDataState, ExcalidrawProps } from '@excalidraw/excalidraw/types';
import '@excalidraw/excalidraw/index.css';
import {
  Archive,
  Loader2,
  PencilRuler,
  Plus,
  RefreshCcw,
  Search,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  createWhiteboard,
  deleteWhiteboard,
  getWhiteboard,
  listWhiteboardHub,
  normalizeWhiteboardScene,
  recordWhiteboardView,
  updateWhiteboard,
  type WhiteboardDetail,
  type WhiteboardHubItem,
  type WhiteboardScene,
} from '../api/whiteboard-api';

type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';
type ExcalidrawOnChange = NonNullable<ExcalidrawProps['onChange']>;

function readExcalidrawTheme() {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
    ? THEME.DARK
    : THEME.LIGHT;
}

function viewFromSearch(value: string | null): 'all' | 'mine' | 'recent' | 'archived' {
  if (value === 'mine' || value === 'recent' || value === 'archived') {
    return value;
  }
  return 'all';
}

function sceneFromExcalidraw(
  elements: Parameters<ExcalidrawOnChange>[0],
  appState: Parameters<ExcalidrawOnChange>[1],
  files: Parameters<ExcalidrawOnChange>[2],
): WhiteboardScene {
  return normalizeWhiteboardScene(JSON.parse(serializeAsJSON(elements, appState, files, 'local')));
}

function sceneSignature(scene: WhiteboardScene): string {
  return JSON.stringify(scene);
}

export function WhiteboardView() {
  const { token, user } = useAuth();
  const { workspaceSlug, whiteboardId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<WhiteboardHubItem[]>([]);
  const [activeBoard, setActiveBoard] = useState<WhiteboardDetail | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [loadingList, setLoadingList] = useState(false);
  const [loadingBoard, setLoadingBoard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const saveTimerRef = useRef<number | null>(null);
  const saveInFlightRef = useRef(false);
  const pendingSceneRef = useRef<WhiteboardScene | null>(null);
  const pendingSceneSignatureRef = useRef<string | null>(null);
  const lastSavedSceneSignatureRef = useRef<string | null>(null);
  const activeBoardIdRef = useRef<string | null>(null);
  const [excalidrawTheme, setExcalidrawTheme] = useState(readExcalidrawTheme);
  const view = viewFromSearch(searchParams.get('view'));
  const currentWorkspace = user?.workspaces.find((workspace) => workspace.slug === workspaceSlug) ?? null;

  useEffect(() => {
    if (typeof document === 'undefined') {
      return undefined;
    }

    const root = document.documentElement;
    const syncTheme = () => setExcalidrawTheme(readExcalidrawTheme());
    syncTheme();

    const observer = new MutationObserver(syncTheme);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });

    return () => observer.disconnect();
  }, []);

  const containerFilter = useMemo(() => {
    const app = searchParams.get('container_app');
    const type = searchParams.get('container_type');
    const id = searchParams.get('container_id');
    if (!app || !type || !id) {
      return null;
    }
    return { app, type, id };
  }, [searchParams]);

  const activePath = useCallback(
    (id: string) => {
      const suffix = `/${id}${searchParams.toString() ? `?${searchParams}` : ''}`;
      return workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'whiteboard', suffix)
        : resolveDefaultWorkspaceAppPath(user, 'whiteboard', suffix);
    },
    [searchParams, user, workspaceSlug],
  );

  const rootPath = useCallback(() => {
    const suffix = searchParams.toString() ? `?${searchParams}` : '';
    return workspaceSlug
      ? buildWorkspaceAppPath(workspaceSlug, 'whiteboard', suffix)
      : resolveDefaultWorkspaceAppPath(user, 'whiteboard', suffix);
  }, [searchParams, user, workspaceSlug]);

  const loadList = useCallback(async () => {
    if (!token) return;
    setLoadingList(true);
    setError(null);
    try {
      const response = await listWhiteboardHub(
        token,
        {
          view,
          q: query,
          sort_by: containerFilter ? 'container_sort_order' : 'updated_at',
          sort_dir: containerFilter ? 'asc' : 'desc',
          page_size: 200,
          container_app: containerFilter?.app,
          container_type: containerFilter?.type,
          container_id: containerFilter?.id,
        },
        workspaceSlug,
      );
      setItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load whiteboards.');
      setItems([]);
    } finally {
      setLoadingList(false);
    }
  }, [containerFilter, query, token, view, workspaceSlug]);

  const loadBoard = useCallback(async (id: string) => {
    if (!token) return;
    setLoadingBoard(true);
    setError(null);
    try {
      const board = await getWhiteboard(token, id, workspaceSlug);
      const normalized = {
        ...board,
        scene: normalizeWhiteboardScene(board.scene),
      };
      lastSavedSceneSignatureRef.current = sceneSignature(normalized.scene);
      pendingSceneRef.current = null;
      pendingSceneSignatureRef.current = null;
      setActiveBoard(normalized);
      setTitleDraft(normalized.title);
      setSaveStatus('idle');
      void recordWhiteboardView(token, id, workspaceSlug);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load whiteboard.');
      setActiveBoard(null);
    } finally {
      setLoadingBoard(false);
    }
  }, [token, workspaceSlug]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (whiteboardId) {
      void loadBoard(whiteboardId);
    } else {
      setActiveBoard(null);
      setTitleDraft('');
      setSaveStatus('idle');
      pendingSceneRef.current = null;
      pendingSceneSignatureRef.current = null;
      lastSavedSceneSignatureRef.current = null;
    }
  }, [loadBoard, whiteboardId]);

  useEffect(() => {
    activeBoardIdRef.current = activeBoard?.id ?? null;
  }, [activeBoard?.id]);

  useEffect(() => () => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
    }
  }, []);

  const handleCreate = useCallback(async () => {
    if (!token) return;
    const primaryContainer = containerFilter
      ? { ...containerFilter, sort_order: items.length }
      : currentWorkspace
        ? {
            app: 'whiteboard',
            type: 'workspace_sidebar',
            id: currentWorkspace.id,
            sort_order: 0,
          }
        : null;
    try {
      const created = await createWhiteboard(
        token,
        {
          title: 'Untitled Whiteboard',
          source_app: primaryContainer?.app === 'pms' ? 'pms' : 'whiteboard',
          source_kind: 'manual',
          primary_container: primaryContainer,
        },
        workspaceSlug,
      );
      setItems((current) => [created, ...current]);
      navigate(activePath(created.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create whiteboard.');
    }
  }, [activePath, containerFilter, currentWorkspace, items.length, navigate, token, workspaceSlug]);

  useEffect(() => {
    const handler = () => {
      void handleCreate();
    };
    window.addEventListener('whiteboard:create', handler);
    return () => window.removeEventListener('whiteboard:create', handler);
  }, [handleCreate]);

  const saveTitle = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage) return;
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === activeBoard.title) return;
    try {
      const updated = await updateWhiteboard(token, activeBoard.id, { title: nextTitle }, workspaceSlug);
      setActiveBoard((current) => current ? { ...current, ...updated } : updated);
      setItems((current) => current.map((item) => (
        item.id === updated.id ? { ...item, title: updated.title, updated_at: updated.updated_at } : item
      )));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename whiteboard.');
      setTitleDraft(activeBoard.title);
    }
  }, [activeBoard, titleDraft, token, workspaceSlug]);

  const flushSceneSave = useCallback(async (boardId: string) => {
    if (!token || saveInFlightRef.current) return;
    const scene = pendingSceneRef.current;
    const signature = pendingSceneSignatureRef.current;
    if (!scene || !signature) return;
    pendingSceneRef.current = null;
    pendingSceneSignatureRef.current = null;
    saveInFlightRef.current = true;
    setSaveStatus('saving');
    try {
      const updated = await updateWhiteboard(token, boardId, { scene }, workspaceSlug);
      lastSavedSceneSignatureRef.current = signature;
      if (activeBoardIdRef.current === boardId) {
        setActiveBoard((current) => current ? { ...current, updated_at: updated.updated_at } : updated);
      }
      setItems((current) => current.map((item) => (
        item.id === updated.id ? { ...item, updated_at: updated.updated_at } : item
      )));
      if (pendingSceneRef.current === null) {
        setSaveStatus('saved');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save whiteboard.');
      setSaveStatus('error');
    } finally {
      saveInFlightRef.current = false;
      if (pendingSceneRef.current !== null && activeBoardIdRef.current === boardId && saveTimerRef.current === null) {
        saveTimerRef.current = window.setTimeout(() => {
          saveTimerRef.current = null;
          void flushSceneSave(boardId);
        }, 250);
      }
    }
  }, [token, workspaceSlug]);

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

    const boardId = activeBoard.id;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      void flushSceneSave(boardId);
    }, 800);
  }, [activeBoard?.can_edit, activeBoard?.id, flushSceneSave]);

  const handleArchive = useCallback(async () => {
    if (!token || !activeBoard || !activeBoard.can_manage) return;
    try {
      await deleteWhiteboard(token, activeBoard.id, workspaceSlug);
      setItems((current) => current.filter((item) => item.id !== activeBoard.id));
      navigate(rootPath());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to archive whiteboard.');
    }
  }, [activeBoard, navigate, rootPath, token, workspaceSlug]);

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

  const saveLabel = {
    idle: '',
    dirty: 'Saving...',
    saving: 'Saving...',
    saved: 'Saved',
    error: 'Save failed',
  }[saveStatus];

  return (
    <div className="flex h-full min-h-0 bg-app-bg text-app-ink">
      <aside className="flex w-80 shrink-0 flex-col border-r border-app-border bg-app-surface-sidebar">
        <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <PencilRuler size={18} className="text-app-accent" />
            <h1 className="app-text-title-md truncate">Whiteboards</h1>
          </div>
          <button
            type="button"
            onClick={handleCreate}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/70 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            title="Create whiteboard"
          >
            <Plus size={16} />
          </button>
        </div>

        <div className="border-b border-app-border p-3">
          <label className="flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 text-app-ink/60">
            <Search size={14} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search whiteboards"
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
            />
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {loadingList ? (
            <div className="flex items-center gap-2 px-3 py-3 text-app-ink/50">
              <Loader2 size={14} className="animate-spin" />
              <span className="app-text-body-sm">Loading</span>
            </div>
          ) : items.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <p className="app-text-body-sm text-app-ink/45">No whiteboards</p>
            </div>
          ) : (
            <div className="space-y-1">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => navigate(activePath(item.id))}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left transition-colors',
                    item.id === whiteboardId
                      ? 'bg-app-accent text-app-bg'
                      : 'text-app-ink/75 hover:bg-app-surface-hover hover:text-app-ink',
                  )}
                >
                  <PencilRuler size={14} className="shrink-0" />
                  <span className="app-text-body-sm min-w-0 flex-1 truncate">{item.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        {error ? (
          <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
            {error}
          </div>
        ) : null}

        {!activeBoard ? (
          <div className="flex min-h-0 flex-1 items-center justify-center px-8">
            <div className="text-center">
              <PencilRuler size={28} className="mx-auto mb-3 text-app-ink/30" />
              <p className="app-text-title-md mb-3 text-app-ink/70">No whiteboard selected</p>
              <button
                type="button"
                onClick={handleCreate}
                className="inline-flex items-center gap-2 rounded-md bg-app-accent px-3 py-2 text-sm font-medium text-app-bg transition-colors hover:bg-app-accent/90"
              >
                <Plus size={15} />
                <span>Create</span>
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex min-h-[56px] items-center gap-3 border-b border-app-border bg-app-surface px-4">
              <input
                value={titleDraft}
                onChange={(event) => setTitleDraft(event.target.value)}
                onBlur={saveTitle}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.currentTarget.blur();
                  }
                }}
                disabled={!activeBoard.can_manage}
                className="app-text-title-md min-w-0 flex-1 rounded-md bg-transparent px-2 py-1 text-app-ink outline-none transition-colors enabled:hover:bg-app-surface-hover enabled:focus:bg-app-bg"
              />
              {saveLabel ? (
                <span className={cn(
                  'app-text-caption shrink-0',
                  saveStatus === 'error' ? 'text-rose-500' : 'text-app-ink/45',
                )}
                >
                  {saveLabel}
                </span>
              ) : null}
              <button
                type="button"
                onClick={() => activeBoard && void loadBoard(activeBoard.id)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                title="Reload"
              >
                <RefreshCcw size={15} />
              </button>
              {activeBoard.can_manage ? (
                <button
                  type="button"
                  onClick={handleArchive}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-rose-500"
                  title="Archive"
                >
                  <Archive size={15} />
                </button>
              ) : null}
            </div>

            <div className="relative min-h-0 flex-1 bg-white">
              {loadingBoard ? (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-bg/60">
                  <Loader2 size={24} className="animate-spin text-app-ink/50" />
                </div>
              ) : null}
              {initialData ? (
                <Excalidraw
                  key={activeBoard.id}
                  initialData={initialData}
                  onChange={(elements, appState, files) => {
                    if (!activeBoard.can_edit) return;
                    scheduleSceneSave(sceneFromExcalidraw(elements, appState, files));
                  }}
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
          </>
        )}
      </main>
    </div>
  );
}
