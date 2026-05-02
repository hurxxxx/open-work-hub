import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Loader2,
  PencilRuler,
  Plus,
  Search,
  Star,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  createWhiteboard,
  listWhiteboardHub,
  resolveWhiteboardSharedLink,
  type WhiteboardDetail,
  type WhiteboardHubItem,
} from '../api/whiteboard-api';
import { WhiteboardEditorSurface } from './WhiteboardEditorSurface';

function viewFromSearch(value: string | null): 'all' | 'mine' | 'recent' | 'favorites' | 'archived' {
  if (value === 'mine' || value === 'recent' || value === 'favorites' || value === 'archived') {
    return value;
  }
  return 'all';
}

export function WhiteboardView() {
  const { token, user } = useAuth();
  const { workspaceSlug, whiteboardId, shareToken } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<WhiteboardHubItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [sharedItem, setSharedItem] = useState<WhiteboardHubItem | null>(null);
  const [loadingShared, setLoadingShared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const view = viewFromSearch(searchParams.get('view'));
  const currentWorkspace = user?.workspaces.find((workspace) => workspace.slug === workspaceSlug) ?? null;

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

  const loadList = useCallback(async () => {
    if (!token || shareToken) return;
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
  }, [containerFilter, query, shareToken, token, view, workspaceSlug]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

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
          <WhiteboardEditorSurface
            key={sharedItem.id}
            boardId={sharedItem.id}
            shareToken={shareToken}
            showArchive={false}
            onBoardUpdated={(updated) => setSharedItem({ ...sharedItem, ...updated })}
          />
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
            onClick={() => void handleCreate()}
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
                  {item.is_favorite ? (
                    <Star size={13} fill="currentColor" className="shrink-0 text-amber-500" />
                  ) : null}
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

        {!whiteboardId ? (
          <div className="flex min-h-0 flex-1 items-center justify-center px-8">
            <div className="text-center">
              <PencilRuler size={28} className="mx-auto mb-3 text-app-ink/30" />
              <p className="app-text-title-md mb-3 text-app-ink/70">No whiteboard selected</p>
              <button
                type="button"
                onClick={() => void handleCreate()}
                className="inline-flex items-center gap-2 rounded-md bg-app-accent px-3 py-2 text-sm font-medium text-app-bg transition-colors hover:bg-app-accent/90"
              >
                <Plus size={15} />
                <span>Create</span>
              </button>
            </div>
          </div>
        ) : (
          <WhiteboardEditorSurface
            key={whiteboardId}
            boardId={whiteboardId}
            workspaceSlug={workspaceSlug}
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
        )}
      </main>
    </div>
  );
}
