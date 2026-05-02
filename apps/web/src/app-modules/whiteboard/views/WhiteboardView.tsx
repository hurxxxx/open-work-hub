import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Clock3,
  Grid3X3,
  List as ListIcon,
  Loader2,
  MapPin,
  PencilRuler,
  Plus,
  Search,
  Star,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime as formatZonedDateTime,
  formatRelativeTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  createWhiteboard,
  getWhiteboard,
  listWhiteboardHub,
  normalizeWhiteboardScene,
  resolveWhiteboardSharedLink,
  type WhiteboardDetail,
  type WhiteboardHubItem,
  type WhiteboardScene,
} from '../api/whiteboard-api';

const WhiteboardEditorSurface = lazy(() =>
  import('./WhiteboardEditorSurface').then((module) => ({ default: module.WhiteboardEditorSurface })),
);

type WhiteboardHubView = 'all' | 'mine' | 'recent' | 'favorites' | 'archived';
type WhiteboardLayoutMode = 'cards' | 'list';
type WhiteboardSortValue = 'updated_desc' | 'viewed_desc' | 'created_desc' | 'title_asc';
type WhiteboardSortOption = { label: string; sortBy: string; sortDir: 'asc' | 'desc' };

const VIEW_MODE_STORAGE_KEY = 'aidoo:whiteboard:view-mode';

const VIEW_LABELS: Record<WhiteboardHubView, string> = {
  all: 'All Whiteboards',
  mine: 'My Whiteboards',
  recent: 'Recent',
  favorites: 'Favorites',
  archived: 'Archived',
};

const SORT_OPTIONS: Record<WhiteboardSortValue, WhiteboardSortOption> = {
  updated_desc: { label: 'Recently updated', sortBy: 'updated_at', sortDir: 'desc' },
  viewed_desc: { label: 'Recently viewed', sortBy: 'last_viewed_at', sortDir: 'desc' },
  created_desc: { label: 'Recently created', sortBy: 'created_at', sortDir: 'desc' },
  title_asc: { label: 'Name A-Z', sortBy: 'title', sortDir: 'asc' },
};

const previewCache = new Map<string, string | null>();
const previewPromiseCache = new Map<string, Promise<string | null>>();

function viewFromSearch(value: string | null): WhiteboardHubView {
  if (value === 'mine' || value === 'recent' || value === 'favorites' || value === 'archived') {
    return value;
  }
  return 'all';
}

function readStoredLayoutMode(): WhiteboardLayoutMode {
  if (typeof window === 'undefined') return 'cards';
  return window.localStorage.getItem(VIEW_MODE_STORAGE_KEY) === 'list' ? 'list' : 'cards';
}

function previewCacheKey(item: Pick<WhiteboardHubItem, 'id' | 'updated_at'>): string {
  return `${item.id}:${item.updated_at}`;
}

function isDeletedElement(element: unknown): boolean {
  return Boolean(element && typeof element === 'object' && (element as { isDeleted?: unknown }).isDeleted);
}

function ownerInitials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '?';
  const parts = trimmed.split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? '').join('') || '?';
}

function formatRelativeDate(value: string | null | undefined, timeZone: string): string {
  return formatRelativeTime(value, { fallback: 'Never', locale: 'en', timeZone });
}

function formatDateTime(value: string | null | undefined, timeZone: string): string {
  return formatZonedDateTime(value, {
    fallback: 'Never',
    locale: 'en',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  });
}

async function renderPreviewImage(scene: WhiteboardScene): Promise<string | null> {
  const normalized = normalizeWhiteboardScene(scene);
  const elements = normalized.elements.filter((element) => !isDeletedElement(element));
  if (elements.length === 0) return null;
  const { exportToBlob } = await import('@excalidraw/excalidraw');
  const blob = await exportToBlob({
    elements: elements as never,
    appState: {
      ...normalized.appState,
      exportBackground: true,
      viewBackgroundColor: '#ffffff',
    } as never,
    files: normalized.files as never,
    mimeType: 'image/png',
    exportPadding: 32,
    maxWidthOrHeight: 720,
  });
  return URL.createObjectURL(blob);
}

function loadPreviewImage(
  token: string,
  item: WhiteboardHubItem,
  workspaceSlug?: string | null,
): Promise<string | null> {
  const key = previewCacheKey(item);
  if (previewCache.has(key)) {
    return Promise.resolve(previewCache.get(key) ?? null);
  }
  const existing = previewPromiseCache.get(key);
  if (existing) return existing;
  const promise = getWhiteboard(token, item.id, workspaceSlug)
    .then((detail) => renderPreviewImage(detail.scene))
    .then((url) => {
      previewCache.set(key, url);
      return url;
    })
    .finally(() => {
      previewPromiseCache.delete(key);
    });
  previewPromiseCache.set(key, promise);
  return promise;
}

function WhiteboardPreview({
  item,
  token,
  workspaceSlug,
}: {
  item: WhiteboardHubItem;
  token: string | null;
  workspaceSlug?: string | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'empty' | 'error'>('idle');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (visible) return undefined;
    const node = containerRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '240px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible || !token) return undefined;
    let cancelled = false;
    setStatus('loading');
    setPreviewUrl(null);
    loadPreviewImage(token, item, workspaceSlug)
      .then((url) => {
        if (cancelled) return;
        setPreviewUrl(url);
        setStatus(url ? 'ready' : 'empty');
      })
      .catch(() => {
        if (cancelled) return;
        setPreviewUrl(null);
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [item, token, visible, workspaceSlug]);

  return (
    <div ref={containerRef} className="flex aspect-[16/10] w-full items-center justify-center overflow-hidden bg-white">
      {status === 'ready' && previewUrl ? (
        <img
          src={previewUrl}
          alt=""
          className="h-full w-full object-contain"
          draggable={false}
        />
      ) : status === 'loading' ? (
        <Loader2 size={18} className="animate-spin text-app-ink/35" />
      ) : (
        <div className="flex flex-col items-center gap-2 text-app-ink/40">
          <PencilRuler size={22} className="text-amber-500" />
          <span className="app-text-body-sm">
            {status === 'error' ? 'Preview unavailable' : 'Empty whiteboard'}
          </span>
        </div>
      )}
    </div>
  );
}

function WhiteboardCard({
  item,
  token,
  workspaceSlug,
  timeZone,
  onOpen,
}: {
  item: WhiteboardHubItem;
  token: string | null;
  workspaceSlug?: string | null;
  timeZone: string;
  onOpen: (item: WhiteboardHubItem) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className="group flex min-h-[300px] flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-app-accent/45 hover:shadow-md"
    >
      <WhiteboardPreview item={item} token={token} workspaceSlug={workspaceSlug} />
      <div className="flex min-h-[112px] items-start gap-3 border-t border-app-border px-4 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-app-ink text-xs font-semibold text-app-bg">
          {ownerInitials(item.created_by_name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <PencilRuler size={15} className="shrink-0 text-amber-500" />
            <p className="app-text-title-sm min-w-0 flex-1 truncate text-app-ink">{item.title}</p>
            {item.is_favorite ? (
              <Star size={14} fill="currentColor" className="shrink-0 text-amber-500" />
            ) : null}
          </div>
          <p className="app-text-body-sm mt-2 truncate text-app-ink/55">
            Edited {formatRelativeDate(item.updated_at, timeZone)}
          </p>
          <p className="app-text-body-sm mt-1 truncate text-app-ink/45">
            {item.location_label || 'Workspace'}
          </p>
        </div>
      </div>
    </button>
  );
}

function WhiteboardListTable({
  items,
  timeZone,
  onOpen,
}: {
  items: WhiteboardHubItem[];
  timeZone: string;
  onOpen: (item: WhiteboardHubItem) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <div className="overflow-x-auto">
        <table className="min-w-[960px] w-full border-collapse">
          <thead className="bg-app-surface-hover text-left">
            <tr className="app-text-caption text-app-ink/55">
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Location</th>
              <th className="px-5 py-3 font-medium">Date updated</th>
              <th className="px-5 py-3 font-medium">Date created</th>
              <th className="px-5 py-3 font-medium">Date viewed</th>
              <th className="px-5 py-3 font-medium">Creator</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {items.map((item) => (
              <tr
                key={item.id}
                onClick={() => onOpen(item)}
                className="cursor-pointer transition-colors hover:bg-app-surface-hover"
              >
                <td className="px-5 py-4">
                  <div className="flex min-w-0 items-center gap-2">
                    <PencilRuler size={16} className="shrink-0 text-amber-500" />
                    <span className="app-text-title-sm min-w-0 truncate text-app-ink">{item.title}</span>
                    {item.is_favorite ? (
                      <Star size={13} fill="currentColor" className="shrink-0 text-amber-500" />
                    ) : null}
                  </div>
                </td>
                <td className="app-text-body-sm px-5 py-4 text-app-ink/65">
                  <span className="inline-flex max-w-[220px] items-center gap-2 truncate">
                    <MapPin size={14} className="shrink-0 text-app-ink/35" />
                    <span className="truncate">{item.location_label || 'Workspace'}</span>
                  </span>
                </td>
                <td className="app-text-body-sm px-5 py-4 text-app-ink/65" title={formatDateTime(item.updated_at, timeZone)}>
                  {formatRelativeDate(item.updated_at, timeZone)}
                </td>
                <td className="app-text-body-sm px-5 py-4 text-app-ink/65" title={formatDateTime(item.created_at, timeZone)}>
                  {formatRelativeDate(item.created_at, timeZone)}
                </td>
                <td className="app-text-body-sm px-5 py-4 text-app-ink/65" title={formatDateTime(item.last_viewed_at, timeZone)}>
                  {formatRelativeDate(item.last_viewed_at, timeZone)}
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-app-ink text-[11px] font-semibold text-app-bg">
                      {ownerInitials(item.created_by_name)}
                    </div>
                    <span className="app-text-body-sm max-w-[180px] truncate text-app-ink/65">
                      {item.created_by_name || 'Unknown'}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function WhiteboardEditorFallback() {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center bg-app-bg text-app-ink/45">
      <Loader2 size={24} className="animate-spin" />
    </div>
  );
}

export function WhiteboardView() {
  const { token, user } = useAuth();
  const { workspaceSlug, whiteboardId, shareToken } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [sortValue, setSortValue] = useState<WhiteboardSortValue>('updated_desc');
  const [layoutMode, setLayoutMode] = useState<WhiteboardLayoutMode>(readStoredLayoutMode);
  const [items, setItems] = useState<WhiteboardHubItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [sharedItem, setSharedItem] = useState<WhiteboardHubItem | null>(null);
  const [loadingShared, setLoadingShared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const view = viewFromSearch(searchParams.get('view'));
  const sortOption = SORT_OPTIONS[sortValue];
  const currentWorkspace = user?.workspaces.find((workspace) => workspace.slug === workspaceSlug) ?? null;
  const timeZone = normalizeTimeZone(user?.time_zone);

  const containerFilter = useMemo(() => {
    const app = searchParams.get('container_app');
    const type = searchParams.get('container_type');
    const id = searchParams.get('container_id');
    if (!app || !type || !id) return null;
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

  const openItem = useCallback((item: WhiteboardHubItem) => {
    navigate(activePath(item.id));
  }, [activePath, navigate]);

  const loadList = useCallback(async () => {
    if (!token || shareToken || whiteboardId) return;
    setLoadingList(true);
    setError(null);
    try {
      const response = await listWhiteboardHub(
        token,
        {
          view,
          q: query,
          sort_by: sortOption.sortBy,
          sort_dir: sortOption.sortDir,
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
  }, [containerFilter, query, shareToken, sortOption.sortBy, sortOption.sortDir, token, view, whiteboardId, workspaceSlug]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, layoutMode);
  }, [layoutMode]);

  useEffect(() => {
    if (!shareToken || !token) return undefined;
    let cancelled = false;
    setLoadingShared(true);
    setError(null);
    resolveWhiteboardSharedLink(token, shareToken)
      .then((response) => {
        if (cancelled) return;
        setSharedItem(response.item);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message || 'Shared whiteboard를 열 수 없습니다.');
        setSharedItem(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingShared(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shareToken, token]);

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

  const upsertItem = useCallback((updated: WhiteboardDetail) => {
    setItems((current) => {
      if (current.some((item) => item.id === updated.id)) {
        return current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item));
      }
      return [updated, ...current];
    });
  }, []);

  if (shareToken) {
    return (
      <main className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
        {error ? (
          <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
            {error}
          </div>
        ) : null}
        {loadingShared ? (
          <div className="flex min-h-0 flex-1 items-center justify-center text-app-ink/40">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : sharedItem ? (
          <Suspense fallback={<WhiteboardEditorFallback />}>
            <WhiteboardEditorSurface
              key={sharedItem.id}
              boardId={sharedItem.id}
              shareToken={shareToken}
              showArchive={false}
              onBoardUpdated={(updated) => setSharedItem({ ...sharedItem, ...updated })}
            />
          </Suspense>
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center px-8 text-center">
            <div>
              <PencilRuler size={28} className="mx-auto mb-3 text-app-ink/30" />
              <p className="app-text-title-md text-app-ink/70">Shared whiteboard를 열 수 없습니다.</p>
            </div>
          </div>
        )}
      </main>
    );
  }

  if (whiteboardId) {
    return (
      <main className="flex h-full min-h-0 flex-col overflow-hidden bg-app-bg text-app-ink">
        <Suspense fallback={<WhiteboardEditorFallback />}>
          <WhiteboardEditorSurface
            key={whiteboardId}
            boardId={whiteboardId}
            workspaceSlug={workspaceSlug}
            onClose={() => navigate(rootPath())}
            onBoardLoaded={upsertItem}
            onBoardUpdated={upsertItem}
            onArchived={(archivedId) => {
              setItems((current) => current.filter((item) => item.id !== archivedId));
              navigate(rootPath());
            }}
            onDeleted={(deletedId) => {
              setItems((current) => current.filter((item) => item.id !== deletedId));
              navigate(rootPath());
            }}
          />
        </Suspense>
      </main>
    );
  }

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-app-bg text-app-ink">
      <div className="border-b border-app-border bg-app-bg px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <PencilRuler size={20} className="shrink-0 text-amber-500" />
              <h1 className="app-text-title-lg truncate">{VIEW_LABELS[view]}</h1>
            </div>
            <p className="app-text-body-sm mt-1 text-app-ink/50">
              {items.length} whiteboard{items.length === 1 ? '' : 's'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleCreate()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-app-ink px-3 text-sm font-medium text-app-bg transition hover:bg-app-ink/90"
          >
            <Plus size={16} />
            <span>New Whiteboard</span>
          </button>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="flex h-9 min-w-[260px] flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink/60 sm:max-w-md">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search"
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
            />
          </label>

          <label className="inline-flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink/65">
            <Clock3 size={15} className="text-app-ink/45" />
            <select
              value={sortValue}
              onChange={(event) => setSortValue(event.target.value as WhiteboardSortValue)}
              className="app-text-body-sm bg-transparent text-app-ink outline-none"
            >
              {(Object.entries(SORT_OPTIONS) as [WhiteboardSortValue, WhiteboardSortOption][]).map(([value, option]) => (
                <option key={value} value={value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="inline-flex h-9 rounded-md border border-app-border bg-app-surface p-1">
            <button
              type="button"
              onClick={() => setLayoutMode('list')}
              aria-pressed={layoutMode === 'list'}
              title="List view"
              className={cn(
                'inline-flex h-7 w-8 items-center justify-center rounded text-app-ink/55 transition-colors hover:text-app-ink',
                layoutMode === 'list' && 'bg-app-bg text-app-ink shadow-sm',
              )}
            >
              <ListIcon size={15} />
            </button>
            <button
              type="button"
              onClick={() => setLayoutMode('cards')}
              aria-pressed={layoutMode === 'cards'}
              title="Card view"
              className={cn(
                'inline-flex h-7 w-8 items-center justify-center rounded text-app-ink/55 transition-colors hover:text-app-ink',
                layoutMode === 'cards' && 'bg-app-bg text-app-ink shadow-sm',
              )}
            >
              <Grid3X3 size={15} />
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="border-b border-rose-200 bg-rose-50 px-6 py-2 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {loadingList ? (
          <div className="flex h-full min-h-[280px] items-center justify-center text-app-ink/45">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-full min-h-[360px] items-center justify-center px-8 text-center">
            <div>
              <PencilRuler size={30} className="mx-auto mb-3 text-app-ink/30" />
              <p className="app-text-title-md text-app-ink/70">No whiteboards</p>
              <button
                type="button"
                onClick={() => void handleCreate()}
                className="mt-4 inline-flex h-9 items-center gap-2 rounded-md bg-app-ink px-3 text-sm font-medium text-app-bg transition hover:bg-app-ink/90"
              >
                <Plus size={15} />
                <span>Create</span>
              </button>
            </div>
          </div>
        ) : layoutMode === 'cards' ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {items.map((item) => (
              <WhiteboardCard
                key={item.id}
                item={item}
                token={token}
                workspaceSlug={workspaceSlug}
                timeZone={timeZone}
                onOpen={openItem}
              />
            ))}
          </div>
        ) : (
          <WhiteboardListTable items={items} timeZone={timeZone} onOpen={openItem} />
        )}
      </div>

    </main>
  );
}
