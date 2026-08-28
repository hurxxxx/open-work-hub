import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState,
} from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Clock3,
  Grid3X3,
  List as ListIcon,
  Loader2,
  Lock,
  PencilRuler,
  Plus,
  Search,
  Trash2,
  Users,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  createWhiteboard,
  deleteWhiteboardTarget,
  listWhiteboardHub,
  resolveWhiteboardSharedLink,
  updateWhiteboardTarget,
  type WhiteboardDetail,
  type WhiteboardHubItem,
  type WhiteboardVisibility,
} from '../api/whiteboard-api';
import {
  WhiteboardCard,
  WhiteboardEditorFallback,
  WhiteboardListTable,
} from './WhiteboardViewParts';
import {
  SORT_OPTIONS,
  VIEW_LABEL_KEYS,
  WHITEBOARD_VIEW_INITIAL_STATE,
  buildWhiteboardCreatePayload,
  buildWhiteboardHubItemPath,
  buildWhiteboardHubListParams,
  buildWhiteboardHubRootPath,
  readStoredLayoutMode,
  readWhiteboardTargetFilter,
  viewFromSearch,
  whiteboardViewReducer,
  writeStoredLayoutMode,
  type WhiteboardLayoutMode,
  type WhiteboardSortOption,
  type WhiteboardSortValue,
} from './whiteboard-hub-model';

const WhiteboardEditorSurface = lazy(() =>
  import('./WhiteboardEditorSurface').then((module) => ({
    default: module.WhiteboardEditorSurface,
  })),
);

export function WhiteboardView() {
  return useWhiteboardViewElement();
}

function useWhiteboardViewElement() {
  const { t } = useTranslation(['apps', 'shell']);
  const { token, user } = useAuth();
  const { workspaceSlug, whiteboardId, shareToken } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [sortValue, setSortValue] =
    useState<WhiteboardSortValue>('updated_desc');
  const [layoutMode, setLayoutMode] =
    useState<WhiteboardLayoutMode>(readStoredLayoutMode);
  const [state, dispatch] = useReducer(
    whiteboardViewReducer,
    WHITEBOARD_VIEW_INITIAL_STATE,
  );
  const { items, loadingList, sharedItem, loadingShared, error } = state;
  const view = viewFromSearch(searchParams.get('view'));
  const currentWorkspaceId =
    user?.workspaces.find((workspace) => workspace.slug === workspaceSlug)
      ?.id ?? null;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const isTrashView = view === 'archived';
  const ViewIcon = isTrashView ? Trash2 : PencilRuler;
  const personalItems = useMemo(
    () => items.filter((item) => item.is_private),
    [items],
  );
  const workspaceItems = useMemo(
    () => items.filter((item) => !item.is_private),
    [items],
  );

  const targetFilter = useMemo(
    () => readWhiteboardTargetFilter(searchParams),
    [searchParams],
  );

  const activePath = useCallback(
    (id: string) => {
      return buildWhiteboardHubItemPath({
        itemId: id,
        searchParams,
        workspaceSlug,
      });
    },
    [searchParams, workspaceSlug],
  );

  const rootPath = useCallback(() => {
    return buildWhiteboardHubRootPath({
      searchParams,
      workspaceSlug,
    });
  }, [searchParams, workspaceSlug]);

  const openItem = useCallback(
    (item: WhiteboardHubItem) => {
      navigate(activePath(item.id));
    },
    [activePath, navigate],
  );

  const loadList = useCallback(async () => {
    if (!token || shareToken || whiteboardId) return;
    dispatch({ type: 'listStarted' });
    try {
      const response = await listWhiteboardHub(
        token,
        buildWhiteboardHubListParams({
          view,
          query,
          sortValue,
          targetFilter,
        }),
        workspaceSlug,
      );
      dispatch({ type: 'listLoaded', items: response.items });
    } catch (err) {
      dispatch({
        type: 'listFailed',
        error:
          err instanceof Error ? err.message : t('apps:whiteboard.loadFailed'),
      });
    }
  }, [
    query,
    shareToken,
    sortValue,
    t,
    targetFilter,
    token,
    view,
    whiteboardId,
    workspaceSlug,
  ]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    writeStoredLayoutMode(layoutMode);
  }, [layoutMode]);

  useEffect(() => {
    if (!shareToken || !token) return undefined;
    let cancelled = false;
    dispatch({ type: 'sharedStarted' });
    resolveWhiteboardSharedLink(token, shareToken)
      .then((response) => {
        if (cancelled) return;
        dispatch({ type: 'sharedLoaded', item: response.item });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'sharedFailed',
          error: err.message || t('apps:whiteboard.openSharedFailed'),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [shareToken, t, token]);

  const handleCreate = useCallback(
    async (visibility: WhiteboardVisibility = 'personal') => {
      if (!token) return;
      try {
        const created = await createWhiteboard(
          token,
          buildWhiteboardCreatePayload({
            title: t('apps:whiteboard.untitled'),
            targetFilter,
            currentWorkspaceId,
            itemCount: items.length,
            visibility,
          }),
          workspaceSlug,
        );
        dispatch({ type: 'upsertItem', item: created });
        navigate(activePath(created.id));
      } catch (err) {
        dispatch({
          type: 'setError',
          error:
            err instanceof Error
              ? err.message
              : t('apps:whiteboard.createFailed'),
        });
      }
    },
    [
      activePath,
      currentWorkspaceId,
      items.length,
      navigate,
      t,
      targetFilter,
      token,
      workspaceSlug,
    ],
  );

  const handleVisibilityChange = useCallback(
    async (item: WhiteboardHubItem, visibility: WhiteboardVisibility) => {
      if (!token) return;
      if ((visibility === 'personal') === item.is_private) return;
      try {
        const updated =
          visibility === 'personal'
            ? await deleteWhiteboardTarget(token, item.id, workspaceSlug)
            : currentWorkspaceId
              ? await updateWhiteboardTarget(
                  token,
                  item.id,
                  {
                    app: 'whiteboard',
                    type: 'workspace_sidebar',
                    id: currentWorkspaceId,
                    sort_order: 0,
                  },
                  workspaceSlug,
                )
              : null;
        if (!updated) {
          dispatch({
            type: 'setError',
            error: t('apps:whiteboard.workspaceMissing'),
          });
          return;
        }
        dispatch({ type: 'upsertItem', item: updated });
      } catch (err) {
        dispatch({
          type: 'setError',
          error:
            err instanceof Error
              ? err.message
              : t('apps:whiteboard.visibilityUpdateFailed'),
        });
      }
    },
    [currentWorkspaceId, t, token, workspaceSlug],
  );

  useEffect(() => {
    const handler = () => {
      void handleCreate('personal');
    };
    window.addEventListener('whiteboard:create', handler);
    return () => window.removeEventListener('whiteboard:create', handler);
  }, [handleCreate]);

  const upsertItem = useCallback((updated: WhiteboardDetail) => {
    dispatch({ type: 'upsertItem', item: updated });
  }, []);

  const handleSharedBoardUpdated = useCallback((updated: WhiteboardDetail) => {
    dispatch({ type: 'sharedUpdated', item: updated });
  }, []);

  const handleEditorClose = useCallback(() => {
    navigate(rootPath());
  }, [navigate, rootPath]);

  const handleArchived = useCallback(
    (archivedId: string) => {
      dispatch({ type: 'removeItem', id: archivedId });
      navigate(rootPath());
    },
    [navigate, rootPath],
  );

  const handleDeleted = useCallback(
    (deletedId: string) => {
      dispatch({ type: 'removeItem', id: deletedId });
      navigate(rootPath());
    },
    [navigate, rootPath],
  );

  const handleRestored = useCallback(
    (restored: WhiteboardDetail) => {
      dispatch({
        type: 'restoreItem',
        item: restored,
        archivedView: view === 'archived',
      });
    },
    [view],
  );

  if (shareToken) {
    return (
      <main className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
        {error ? (
          <div className="border-b border-app-danger-border bg-app-danger-bg px-4 py-2 text-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
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
              onBoardUpdated={handleSharedBoardUpdated}
            />
          </Suspense>
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center px-8 text-center">
            <div>
              <PencilRuler size={28} className="mx-auto mb-3 text-app-ink/30" />
              <p className="app-text-title-md text-app-ink/70">
                {t('apps:whiteboard.openSharedFailed')}
              </p>
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
            onClose={handleEditorClose}
            onBoardLoaded={upsertItem}
            onBoardUpdated={upsertItem}
            onArchived={handleArchived}
            onDeleted={handleDeleted}
            onRestored={handleRestored}
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
              <ViewIcon size={20} className="shrink-0 text-app-warning" />
              <h1 className="app-text-title-lg truncate">
                {t(VIEW_LABEL_KEYS[view])}
              </h1>
            </div>
            <p className="app-text-body-sm mt-1 text-app-ink/50">
              {t('apps:whiteboard.count', { count: items.length })}
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="flex h-9 min-w-[260px] flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink/60 sm:max-w-md">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('apps:whiteboard.search')}
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
            />
          </label>

          <label className="inline-flex h-9 items-center gap-2 text-app-ink/65">
            <Clock3 size={15} className="text-app-ink/45" />
            <select
              value={sortValue}
              onChange={(event) =>
                setSortValue(event.target.value as WhiteboardSortValue)
              }
              className="app-field-input-sm w-auto"
            >
              {(
                Object.entries(SORT_OPTIONS) as [
                  WhiteboardSortValue,
                  WhiteboardSortOption,
                ][]
              ).map(([value, option]) => (
                <option key={value} value={value}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <div className="inline-flex h-9 rounded-md border border-app-border bg-app-surface p-1">
            <button
              type="button"
              onClick={() => setLayoutMode('list')}
              aria-pressed={layoutMode === 'list'}
              title={t('apps:whiteboard.listView')}
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
              title={t('apps:whiteboard.cardView')}
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
        <div className="border-b border-app-danger-border bg-app-danger-bg px-6 py-2 text-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {loadingList ? (
          <div className="flex h-full min-h-[280px] items-center justify-center text-app-ink/45">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : (
          <div className="space-y-8">
            <WhiteboardSection
              visibility="personal"
              items={personalItems}
              token={token}
              workspaceSlug={workspaceSlug}
              timeZone={timeZone}
              archived={isTrashView}
              layoutMode={layoutMode}
              onCreate={handleCreate}
              onOpen={openItem}
              onVisibilityChange={handleVisibilityChange}
            />
            <WhiteboardSection
              visibility="workspace"
              items={workspaceItems}
              token={token}
              workspaceSlug={workspaceSlug}
              timeZone={timeZone}
              archived={isTrashView}
              layoutMode={layoutMode}
              onCreate={handleCreate}
              onOpen={openItem}
              onVisibilityChange={handleVisibilityChange}
            />
          </div>
        )}
      </div>
    </main>
  );
}

function WhiteboardSection({
  visibility,
  items,
  token,
  workspaceSlug,
  timeZone,
  archived,
  layoutMode,
  onCreate,
  onOpen,
  onVisibilityChange,
}: {
  visibility: WhiteboardVisibility;
  items: WhiteboardHubItem[];
  token: string | null;
  workspaceSlug?: string | null;
  timeZone: string;
  archived: boolean;
  layoutMode: WhiteboardLayoutMode;
  onCreate: (visibility: WhiteboardVisibility) => void;
  onOpen: (item: WhiteboardHubItem) => void;
  onVisibilityChange: (
    item: WhiteboardHubItem,
    visibility: WhiteboardVisibility,
  ) => void;
}) {
  const { t } = useTranslation('apps');
  const SectionIcon = visibility === 'workspace' ? Users : Lock;
  const titleKey =
    visibility === 'workspace'
      ? 'whiteboard.workspaceSectionTitle'
      : 'whiteboard.personalSectionTitle';
  const emptyKey = archived
    ? 'whiteboard.trashEmpty'
    : visibility === 'workspace'
      ? 'whiteboard.workspaceSectionEmpty'
      : 'whiteboard.personalSectionEmpty';
  const createKey =
    visibility === 'workspace'
      ? 'whiteboard.createWorkspace'
      : 'whiteboard.createPersonal';

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <SectionIcon
            size={18}
            className={cn(
              'shrink-0',
              visibility === 'workspace'
                ? 'text-app-warning'
                : 'text-app-ink/55',
            )}
          />
          <h2 className="app-text-title-md truncate text-app-ink">
            {t(titleKey)}
          </h2>
          <span className="rounded-full bg-app-surface px-2 py-0.5 text-xs text-app-ink/50">
            {items.length}
          </span>
        </div>
        {!archived ? (
          <button
            type="button"
            onClick={() => onCreate(visibility)}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-app-ink px-3 text-sm font-medium text-app-bg transition hover:bg-app-ink/90"
          >
            <Plus size={15} />
            <span>{t(createKey)}</span>
          </button>
        ) : null}
      </div>
      {items.length > 0 ? (
        layoutMode === 'cards' ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {items.map((item) => (
              <WhiteboardCard
                key={item.id}
                item={item}
                token={token}
                workspaceSlug={workspaceSlug}
                timeZone={timeZone}
                onOpen={onOpen}
                onVisibilityChange={onVisibilityChange}
              />
            ))}
          </div>
        ) : (
          <WhiteboardListTable
            items={items}
            timeZone={timeZone}
            onOpen={onOpen}
            onVisibilityChange={onVisibilityChange}
          />
        )
      ) : (
        <div className="flex min-h-[152px] items-center justify-center rounded-lg border border-dashed border-app-border bg-app-surface/40 px-6 text-center text-sm text-app-ink/45">
          {t(emptyKey)}
        </div>
      )}
    </section>
  );
}
