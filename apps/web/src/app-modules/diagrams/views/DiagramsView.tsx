import { DropdownMenu, type DropdownItem } from '@open-work-hub/ui';
import {
  Archive,
  ArrowLeft,
  FileImage,
  Grid3X3,
  List as ListIcon,
  Loader2,
  Lock,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  Users,
  Workflow,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime as formatZonedDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  archiveDiagram,
  createDiagram,
  fetchDiagramPreviewUrl,
  getDiagram,
  listDiagramsHub,
  restoreDiagram,
  updateDiagram,
  type DiagramDetail,
  type DiagramItem,
  type DiagramVisibility,
} from '../api/diagrams-api';
import {
  DIAGRAM_HUB_PAGE_SIZE,
  INITIAL_HUB_STATE,
  VIEW_LABEL_KEYS,
  diagramsHubReducer,
  itemPath,
  readStoredDiagramLayoutMode,
  rootPath,
  viewFromSearch,
  writeStoredDiagramLayoutMode,
  type DiagramLayoutMode,
} from './diagrams-hub-model';
import {
  buildDrawioExportMessage,
  buildDrawioLoadMessage,
  currentDrawioEmbedConfig,
  isDrawioMessageOriginAllowed,
  parseDrawioEmbedMessage,
} from './drawio-embed-protocol';

const EMPTY_DIAGRAM_XML =
  '<mxfile host="Open Work Hub"><diagram id="page-1" name="Page-1"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>';

function formatDiagramDate(
  value: string,
  timeZone: string,
  locale: string,
): string {
  return formatZonedDateTime(value, {
    fallback: '-',
    locale,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  });
}

export function DiagramsView() {
  const { diagramId } = useParams();
  return diagramId ? <DiagramEditor /> : <DiagramsHub />;
}

function DiagramsHub() {
  const { t } = useTranslation(['apps', 'shell']);
  const { token, user } = useAuth();

  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [layoutMode, setLayoutMode] = useState<DiagramLayoutMode>(
    readStoredDiagramLayoutMode,
  );
  const [state, dispatch] = useReducer(diagramsHubReducer, INITIAL_HUB_STATE);
  const view = viewFromSearch(searchParams.get('view'));
  const timeZone = normalizeTimeZone(user?.time_zone);
  const isArchived = view === 'archived';
  const ViewIcon = isArchived ? Archive : Workflow;
  const personalItems = useMemo(
    () => state.items.filter((item) => item.visibility === 'personal'),
    [state.items],
  );
  const workspaceItems = useMemo(
    () => state.items.filter((item) => item.visibility === 'company'),
    [state.items],
  );

  const load = useCallback(async () => {
    if (!token) return;
    dispatch({ type: 'started' });
    try {
      const response = await listDiagramsHub(token, {
        view,
        q: query,
        sort_by: view === 'all' ? 'updated_at' : 'created_at',
        sort_dir: 'desc',
        page_size: DIAGRAM_HUB_PAGE_SIZE,
      });
      dispatch({ type: 'loaded', items: response.items });
    } catch (error) {
      dispatch({
        type: 'failed',
        error:
          error instanceof Error
            ? error.message
            : t('apps:diagrams.loadFailed'),
      });
    }
  }, [query, t, token, view]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    writeStoredDiagramLayoutMode(layoutMode);
  }, [layoutMode]);

  const handleCreate = useCallback(
    async (visibility: DiagramVisibility) => {
      if (!token) return;
      if (
        visibility === 'company' &&
        !window.confirm(t('shell:contentPublication.confirm'))
      )
        return;
      try {
        const created = await createDiagram(token, {
          title: t('apps:diagrams.untitled'),
          visibility,
          company_admin_read_acknowledged: visibility === 'company',
          xml: EMPTY_DIAGRAM_XML,
        });
        dispatch({ type: 'upsert', item: created });
        navigate(itemPath({ itemId: created.id }));
      } catch (error) {
        dispatch({
          type: 'setError',
          error:
            error instanceof Error
              ? error.message
              : t('apps:diagrams.createFailed'),
        });
      }
    },
    [navigate, t, token],
  );

  const handleVisibilityChange = useCallback(
    async (item: DiagramItem, visibility: DiagramVisibility) => {
      if (!token || item.visibility === visibility) return;
      if (
        visibility === 'company' &&
        !window.confirm(t('shell:contentPublication.confirm'))
      )
        return;
      try {
        const updated = await updateDiagram(token, item.id, {
          version: item.version,
          visibility,
          company_admin_read_acknowledged: visibility === 'company',
        });
        dispatch({ type: 'upsert', item: updated });
      } catch (error) {
        dispatch({
          type: 'setError',
          error:
            error instanceof Error
              ? error.message
              : t('apps:diagrams.visibilityUpdateFailed'),
        });
      }
    },
    [t, token],
  );

  useEffect(() => {
    const handler = () => {
      void handleCreate('personal');
    };
    window.addEventListener('diagrams:create', handler);
    return () => window.removeEventListener('diagrams:create', handler);
  }, [handleCreate]);

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-app-bg text-app-ink">
      <div className="border-b border-app-border bg-app-bg px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <ViewIcon size={20} className="shrink-0 text-app-success" />
              <h1 className="app-text-title-lg truncate">
                {t(VIEW_LABEL_KEYS[view])}
              </h1>
            </div>
            <p className="app-text-body-sm mt-1 text-app-ink/50">
              {t('apps:diagrams.count', { count: state.items.length })}
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="flex h-9 min-w-[260px] flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink/60 sm:max-w-md">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('apps:diagrams.search')}
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
            />
          </label>
          <div className="inline-flex h-9 rounded-md border border-app-border bg-app-surface p-1">
            <button
              type="button"
              onClick={() => setLayoutMode('list')}
              aria-pressed={layoutMode === 'list'}
              title={t('apps:diagrams.listView')}
              className={cn(
                'inline-flex h-7 w-8 items-center justify-center rounded text-app-ink/55 transition-colors hover:text-app-ink',
                layoutMode === 'list' && 'bg-app-bg text-app-ink shadow-sm',
              )}
            >
              <ListIcon size={15} />
            </button>
            <button
              type="button"
              onClick={() => setLayoutMode('grid')}
              aria-pressed={layoutMode === 'grid'}
              title={t('apps:diagrams.gridView')}
              className={cn(
                'inline-flex h-7 w-8 items-center justify-center rounded text-app-ink/55 transition-colors hover:text-app-ink',
                layoutMode === 'grid' && 'bg-app-bg text-app-ink shadow-sm',
              )}
            >
              <Grid3X3 size={15} />
            </button>
          </div>
        </div>
      </div>

      {state.error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-6 py-2 text-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {state.error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {state.loading ? (
          <div className="flex h-full min-h-[280px] items-center justify-center text-app-ink/45">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : (
          <div className="space-y-8">
            <DiagramSection
              visibility="personal"
              items={personalItems}
              token={token}
              timeZone={timeZone}
              archived={isArchived}
              layoutMode={layoutMode}
              onCreate={handleCreate}
              onOpen={(itemId) => navigate(itemPath({ itemId }))}
              onVisibilityChange={handleVisibilityChange}
            />
            <DiagramSection
              visibility="company"
              items={workspaceItems}
              token={token}
              timeZone={timeZone}
              archived={isArchived}
              layoutMode={layoutMode}
              onCreate={handleCreate}
              onOpen={(itemId) => navigate(itemPath({ itemId }))}
              onVisibilityChange={handleVisibilityChange}
            />
          </div>
        )}
      </div>
    </main>
  );
}

function DiagramSection({
  visibility,
  items,
  token,
  timeZone,
  archived,
  layoutMode,
  onCreate,
  onOpen,
  onVisibilityChange,
}: {
  visibility: DiagramVisibility;
  items: DiagramItem[];
  token: string | null;

  timeZone: string;
  archived: boolean;
  layoutMode: DiagramLayoutMode;
  onCreate: (visibility: DiagramVisibility) => void;
  onOpen: (itemId: string) => void;
  onVisibilityChange: (
    item: DiagramItem,
    visibility: DiagramVisibility,
  ) => void;
}) {
  const { t } = useTranslation('apps');
  const SectionIcon = visibility === 'company' ? Users : Lock;
  const titleKey =
    visibility === 'company'
      ? 'diagrams.workspaceSectionTitle'
      : 'diagrams.personalSectionTitle';
  const emptyKey = archived
    ? 'diagrams.archiveEmpty'
    : visibility === 'company'
      ? 'diagrams.workspaceSectionEmpty'
      : 'diagrams.personalSectionEmpty';
  const createKey =
    visibility === 'company'
      ? 'diagrams.createWorkspace'
      : 'diagrams.createPersonal';

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <SectionIcon
            size={18}
            className={cn(
              'shrink-0',
              visibility === 'company' ? 'text-app-success' : 'text-app-ink/55',
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
        layoutMode === 'grid' ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {items.map((item) => (
              <DiagramCard
                key={`${item.id}:${item.updated_at}`}
                item={item}
                token={token}
                timeZone={timeZone}
                onOpen={() => onOpen(item.id)}
                onVisibilityChange={onVisibilityChange}
              />
            ))}
          </div>
        ) : (
          <DiagramListTable
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

function buildDiagramVisibilityMenuItems({
  canManage,
  currentVisibility,
  onChange,
  t,
}: {
  canManage: boolean;
  currentVisibility: DiagramVisibility;
  onChange: (visibility: DiagramVisibility) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}): DropdownItem[] {
  return [
    {
      id: 'current',
      disabled: true,
      label: t('diagrams.visibilityCurrent', {
        visibility: t(
          currentVisibility === 'company'
            ? 'diagrams.visibilityWorkspace'
            : 'diagrams.visibilityPersonal',
        ),
      }),
    },
    {
      id: 'personal',
      separatorBefore: true,
      disabled: !canManage || currentVisibility === 'personal',
      label: (
        <span className="inline-flex items-center gap-2">
          <Lock size={14} />
          {t('diagrams.changeToPersonal')}
        </span>
      ),
      onSelect: () => onChange('personal'),
    },
    {
      id: 'company',
      disabled: !canManage || currentVisibility === 'company',
      label: (
        <span className="inline-flex items-center gap-2">
          <Users size={14} />
          {t('diagrams.changeToWorkspace')}
        </span>
      ),
      onSelect: () => onChange('company'),
    },
    {
      id: 'manage-required',
      separatorBefore: true,
      disabled: true,
      label: t('diagrams.visibilityManageRequired'),
    },
  ].filter((item) => item.id !== 'manage-required' || !canManage);
}

function DiagramCard({
  item,
  token,
  timeZone,
  onOpen,
  onVisibilityChange,
}: {
  item: DiagramItem;
  token: string | null;

  timeZone: string;
  onOpen: () => void;
  onVisibilityChange: (
    item: DiagramItem,
    visibility: DiagramVisibility,
  ) => void;
}) {
  const { t, i18n } = useTranslation('apps');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewStatus, setPreviewStatus] = useState<
    'idle' | 'loading' | 'ready' | 'error'
  >('idle');

  useEffect(() => {
    if (!token || !item.preview_available) return undefined;
    let active = true;
    let objectUrl: string | null = null;
    setPreviewStatus('loading');
    fetchDiagramPreviewUrl(token, item)
      .then((url) => {
        if (!active) {
          if (url) URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setPreviewUrl(url);
        setPreviewStatus(url ? 'ready' : 'idle');
      })
      .catch(() => {
        if (active) setPreviewStatus('error');
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item, token]);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen();
        }
      }}
      className="group flex min-h-[292px] flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-500/45 hover:shadow-md"
    >
      <div className="relative flex aspect-[16/10] w-full items-center justify-center overflow-hidden bg-white">
        {previewStatus === 'ready' && previewUrl ? (
          <img
            src={previewUrl}
            alt=""
            className="h-full w-full object-contain"
            draggable={false}
          />
        ) : previewStatus === 'loading' ? (
          <Loader2 size={18} className="animate-spin text-app-ink/35" />
        ) : (
          <div className="flex flex-col items-center gap-2 text-app-ink/40">
            <FileImage size={22} className="text-app-success" />
            <span className="app-text-body-sm">
              {previewStatus === 'error'
                ? t('diagrams.previewUnavailable')
                : t('diagrams.previewEmpty')}
            </span>
          </div>
        )}
        <div
          className="absolute right-2 top-2"
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <DropdownMenu
            align="end"
            side="bottom"
            trigger={
              <button
                type="button"
                aria-label={t('diagrams.actionsMenu')}
                className="inline-flex size-8 items-center justify-center rounded-md border border-app-border bg-app-bg/95 text-app-ink/65 shadow-sm backdrop-blur transition hover:text-app-ink"
              >
                <MoreHorizontal size={16} />
              </button>
            }
            items={buildDiagramVisibilityMenuItems({
              canManage: item.can_manage,
              currentVisibility: item.visibility,
              onChange: (visibility) => onVisibilityChange(item, visibility),
              t,
            })}
          />
        </div>
      </div>
      <div className="min-h-[108px] border-t border-app-border p-4">
        <div className="flex min-w-0 items-center gap-2">
          <Workflow size={15} className="shrink-0 text-app-success" />
          <p className="app-text-title-sm min-w-0 flex-1 truncate text-app-ink">
            {item.title}
          </p>
        </div>
        <p className="app-text-body-sm mt-2 truncate text-app-ink/55">
          {t('diagrams.updated', {
            date: formatDiagramDate(item.updated_at, timeZone, i18n.language),
          })}
        </p>
        <p className="app-text-body-sm mt-1 truncate text-app-ink/45">
          {item.created_by_name || t('diagrams.unknown')}
        </p>
        <div className="mt-3 inline-flex max-w-full items-center gap-1.5 rounded-md border border-app-border px-2 py-1 text-xs text-app-ink/55">
          {item.visibility === 'company' ? (
            <Users size={13} className="shrink-0 text-app-success" />
          ) : (
            <Lock size={13} className="shrink-0 text-app-ink/45" />
          )}
          <span className="truncate">
            {t(
              item.visibility === 'company'
                ? 'diagrams.visibilityWorkspace'
                : 'diagrams.visibilityPersonal',
            )}
          </span>
        </div>
      </div>
    </article>
  );
}

function DiagramListTable({
  items,
  timeZone,
  onOpen,
  onVisibilityChange,
}: {
  items: DiagramItem[];
  timeZone: string;
  onOpen: (itemId: string) => void;
  onVisibilityChange: (
    item: DiagramItem,
    visibility: DiagramVisibility,
  ) => void;
}) {
  const { t, i18n } = useTranslation('apps');

  return (
    <div className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse">
          <thead className="bg-app-surface-hover text-left">
            <tr className="app-text-caption text-app-ink/55">
              <th className="px-5 py-3 font-medium">
                {t('diagrams.tableName')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('diagrams.tableUpdated')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('diagrams.tableCreated')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('diagrams.tableCreator')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('diagrams.tableVisibility')}
              </th>
              <th className="w-12 px-4 py-3 font-medium">
                <span className="sr-only">{t('diagrams.actionsMenu')}</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {items.map((item) => (
              <tr
                key={item.id}
                onClick={() => onOpen(item.id)}
                className="cursor-pointer transition-colors hover:bg-app-surface-hover"
              >
                <td className="px-5 py-4">
                  <div className="flex min-w-0 items-center gap-2">
                    <Workflow size={16} className="shrink-0 text-app-success" />
                    <span className="app-text-title-sm min-w-0 truncate text-app-ink">
                      {item.title}
                    </span>
                  </div>
                </td>
                <td
                  className="app-text-body-sm px-5 py-4 text-app-ink/65"
                  title={formatDiagramDate(
                    item.updated_at,
                    timeZone,
                    i18n.language,
                  )}
                >
                  {formatDiagramDate(item.updated_at, timeZone, i18n.language)}
                </td>
                <td
                  className="app-text-body-sm px-5 py-4 text-app-ink/65"
                  title={formatDiagramDate(
                    item.created_at,
                    timeZone,
                    i18n.language,
                  )}
                >
                  {formatDiagramDate(item.created_at, timeZone, i18n.language)}
                </td>
                <td className="app-text-body-sm px-5 py-4 text-app-ink/65">
                  <span className="inline-block max-w-[180px] truncate">
                    {item.created_by_name || t('diagrams.unknown')}
                  </span>
                </td>
                <td className="px-5 py-4">
                  <span className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-app-border px-2 py-1 text-xs text-app-ink/55">
                    {item.visibility === 'company' ? (
                      <Users size={13} className="shrink-0 text-app-success" />
                    ) : (
                      <Lock size={13} className="shrink-0 text-app-ink/45" />
                    )}
                    <span className="truncate">
                      {t(
                        item.visibility === 'company'
                          ? 'diagrams.visibilityWorkspace'
                          : 'diagrams.visibilityPersonal',
                      )}
                    </span>
                  </span>
                </td>
                <td
                  className="px-4 py-4"
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={(event) => event.stopPropagation()}
                >
                  <DropdownMenu
                    align="end"
                    side="bottom"
                    trigger={
                      <button
                        type="button"
                        aria-label={t('diagrams.actionsMenu')}
                        className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 transition hover:bg-app-surface-hover hover:text-app-ink"
                      >
                        <MoreHorizontal size={16} />
                      </button>
                    }
                    items={buildDiagramVisibilityMenuItems({
                      canManage: item.can_manage,
                      currentVisibility: item.visibility,
                      onChange: (visibility) =>
                        onVisibilityChange(item, visibility),
                      t,
                    })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DiagramEditor() {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const { diagramId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const detailRef = useRef<DiagramDetail | null>(null);
  const loadedDiagramRef = useRef<string | null>(null);
  const pendingXmlRef = useRef<string | null>(null);
  const [detail, setDetail] = useState<DiagramDetail | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [drawioReady, setDrawioReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const [error, setError] = useState<string | null>(null);
  const drawioEmbedConfig = useMemo(() => currentDrawioEmbedConfig(), []);

  const applyDetail = useCallback(
    (nextDetail: DiagramDetail, options?: { syncTitle?: boolean }) => {
      detailRef.current = nextDetail;
      setDetail(nextDetail);
      if (options?.syncTitle ?? true) {
        setTitleDraft(nextDetail.title);
      }
    },
    [],
  );

  const postToDrawio = useCallback(
    (message: string) => {
      const target = iframeRef.current?.contentWindow;
      if (!target) return;
      target.postMessage(message, drawioEmbedConfig.origin);
    },
    [drawioEmbedConfig.origin],
  );

  const goBack = useCallback(() => {
    navigate(rootPath(searchParams));
  }, [navigate, searchParams]);

  useEffect(() => {
    if (!token || !diagramId) return undefined;
    let active = true;
    detailRef.current = null;
    loadedDiagramRef.current = null;
    pendingXmlRef.current = null;
    setDetail(null);
    setTitleDraft('');
    setSaveStatus('idle');
    setError(null);
    getDiagram(token, diagramId)
      .then((loaded) => {
        if (!active) return;
        applyDetail(loaded);
      })
      .catch((caught: Error) => {
        if (!active) return;
        setError(caught.message || t('apps:diagrams.loadFailed'));
      });
    return () => {
      active = false;
    };
  }, [applyDetail, diagramId, t, token]);

  useEffect(() => {
    if (!drawioReady || !detail) return;
    if (loadedDiagramRef.current === detail.id) return;
    loadedDiagramRef.current = detail.id;
    postToDrawio(buildDrawioLoadMessage(detail.xml));
  }, [detail, drawioReady, postToDrawio]);

  const persistDiagram = useCallback(
    async (xml: string, previewPngDataUrl: string | null) => {
      const currentDetail = detailRef.current;
      if (!token || !diagramId || !currentDetail) return;
      setSaveStatus('saving');
      setError(null);
      try {
        const updated = await updateDiagram(token, diagramId, {
          version: currentDetail.version,
          xml,
          preview_png_data_url: previewPngDataUrl,
        });
        applyDetail(updated, { syncTitle: false });
        setSaveStatus('saved');
      } catch (caught) {
        setSaveStatus('error');
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:diagrams.saveFailed'),
        );
      }
    },
    [applyDetail, diagramId, t, token],
  );

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (
        typeof window !== 'undefined' &&
        !isDrawioMessageOriginAllowed(event.origin, drawioEmbedConfig.origin)
      ) {
        return;
      }
      const message = parseDrawioEmbedMessage(event.data);
      if (!message?.event) return;
      if (message.event === 'init') {
        loadedDiagramRef.current = null;
        setDrawioReady(true);
        return;
      }
      if (
        (message.event === 'save' || message.event === 'autosave') &&
        message.xml
      ) {
        pendingXmlRef.current = message.xml;
        setSaveStatus('saving');
        postToDrawio(buildDrawioExportMessage(message.xml));
        return;
      }
      if (message.event === 'export') {
        if (message.format === 'xml' && message.xml) {
          pendingXmlRef.current = message.xml;
          setSaveStatus('saving');
          postToDrawio(buildDrawioExportMessage(message.xml));
          return;
        }
        const xml = message.xml ?? pendingXmlRef.current;
        pendingXmlRef.current = null;
        if (xml) void persistDiagram(xml, message.data ?? null);
        return;
      }
      if (message.event === 'exit') {
        goBack();
      }
    }
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [drawioEmbedConfig.origin, goBack, persistDiagram, postToDrawio]);

  const handleTitleSave = useCallback(async () => {
    const currentDetail = detailRef.current;
    if (!token || !diagramId || !currentDetail) return true;
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === currentDetail.title) return true;
    setSaveStatus('saving');
    setError(null);
    try {
      const updated = await updateDiagram(token, diagramId, {
        version: currentDetail.version,
        title: nextTitle,
      });
      applyDetail(updated);
      setSaveStatus('saved');
      return true;
    } catch (caught) {
      setSaveStatus('error');
      setError(
        caught instanceof Error
          ? caught.message
          : t('apps:diagrams.renameFailed'),
      );
      return false;
    }
  }, [applyDetail, diagramId, t, titleDraft, token]);

  const handleVisibilityChange = useCallback(
    async (visibility: DiagramVisibility) => {
      const currentDetail = detailRef.current;
      if (
        !token ||
        !diagramId ||
        !currentDetail ||
        currentDetail.visibility === visibility
      ) {
        return;
      }
      if (
        visibility === 'company' &&
        !window.confirm(t('shell:contentPublication.confirm'))
      )
        return;
      setSaveStatus('saving');
      setError(null);
      try {
        const updated = await updateDiagram(token, diagramId, {
          version: currentDetail.version,
          visibility,
          company_admin_read_acknowledged: visibility === 'company',
        });
        applyDetail(updated, { syncTitle: false });
        setSaveStatus('saved');
      } catch (caught) {
        setSaveStatus('error');
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:diagrams.visibilityUpdateFailed'),
        );
      }
    },
    [applyDetail, diagramId, t, token],
  );

  const handleArchive = useCallback(async () => {
    if (!token || !diagramId || !detail) return;
    try {
      await archiveDiagram(token, diagramId);
      goBack();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : t('apps:diagrams.archiveFailed'),
      );
    }
  }, [detail, diagramId, goBack, t, token]);

  const handleRestore = useCallback(async () => {
    if (!token || !diagramId) return;
    try {
      const restored = await restoreDiagram(token, diagramId);
      applyDetail(restored);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : t('apps:diagrams.restoreFailed'),
      );
    }
  }, [applyDetail, diagramId, t, token]);

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-app-bg text-app-ink">
      <div className="flex min-h-[60px] items-center gap-3 border-b border-app-border bg-app-bg px-4 py-2">
        <button
          type="button"
          onClick={goBack}
          title={t('common:actions.close')}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 transition hover:text-app-ink"
        >
          <ArrowLeft size={17} />
        </button>
        <Workflow size={18} className="shrink-0 text-app-success" />
        <label className="min-w-0 flex-1">
          <span className="sr-only">{t('apps:diagrams.titleInput')}</span>
          <input
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                event.currentTarget.blur();
              }
            }}
            onBlur={() => void handleTitleSave()}
            className="app-text-title-sm w-full min-w-0 bg-transparent outline-none"
          />
        </label>
        <div
          className={cn(
            'hidden min-w-[72px] items-center justify-center rounded-full px-2 py-1 text-xs sm:inline-flex',
            saveStatus === 'error'
              ? 'bg-app-danger-bg text-app-danger-text dark:bg-app-danger-bg dark:text-app-danger-text'
              : 'bg-app-surface text-app-ink/55',
          )}
        >
          {saveStatus === 'saving' ? (
            <Loader2 size={13} className="mr-1 animate-spin" />
          ) : null}
          {t(`apps:diagrams.${saveStatus}`)}
        </div>
        {detail ? (
          <DropdownMenu
            align="end"
            side="bottom"
            trigger={
              <button
                type="button"
                aria-label={t('apps:diagrams.actionsMenu')}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 transition hover:text-app-ink"
              >
                <MoreHorizontal size={16} />
              </button>
            }
            items={buildDiagramVisibilityMenuItems({
              canManage: detail.can_manage,
              currentVisibility: detail.visibility,
              onChange: (visibility) => void handleVisibilityChange(visibility),
              t: (key, options) => t(`apps:${key}`, options),
            })}
          />
        ) : null}
        {detail?.archived_at ? (
          <button
            type="button"
            onClick={() => void handleRestore()}
            title={t('apps:diagrams.restore')}
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 transition hover:text-app-ink"
          >
            <RotateCcw size={16} />
          </button>
        ) : detail?.can_manage ? (
          <button
            type="button"
            onClick={() => void handleArchive()}
            title={t('apps:diagrams.archive')}
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 transition hover:text-app-danger-text"
          >
            <Trash2 size={16} />
          </button>
        ) : null}
      </div>
      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-4 py-2 text-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {error}
        </div>
      ) : null}
      <div className="relative min-h-0 flex-1 bg-white">
        {!detail ? (
          <div className="absolute inset-0 flex items-center justify-center bg-app-bg text-app-ink/45">
            {error ? (
              <Pencil size={24} />
            ) : (
              <Loader2 size={24} className="animate-spin" />
            )}
          </div>
        ) : null}
        <iframe
          ref={iframeRef}
          title={t('apps:diagrams.editorTitle')}
          src={drawioEmbedConfig.src}
          className="h-full w-full border-0"
          sandbox="allow-downloads allow-forms allow-modals allow-popups allow-same-origin allow-scripts"
        />
      </div>
    </main>
  );
}
