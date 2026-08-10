import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  Database,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Table2,
  TerminalSquare,
} from 'lucide-react';
import DataEditor, {
  GridCellKind,
  type DataEditorProps,
  type DataEditorRef,
  type GetRowThemeCallback,
  type GridCell,
  type GridColumn as GlideGridColumn,
  type Rectangle,
  type Theme as GlideTheme,
} from '@glideapps/glide-data-grid';
import '@glideapps/glide-data-grid/dist/index.css';

import { cn } from '@/src/lib/utils';
import { APP_COLOR_FALLBACKS } from '@/src/platform/theme/app-color-fallbacks';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  fetchPlmRawTableRows,
  fetchPlmRawTables,
  getPlmRawPageSize,
  runPlmRawSqlQuery,
  type PlmRawColumn,
  type PlmRawRowsResponse,
  type PlmRawTable,
} from '../api/plm-raw-api';

type PlmTab = 'tables' | 'sql';

const EMPTY_GRID_CELL: GridCell = {
  allowOverlay: false,
  data: '',
  displayData: '',
  kind: GridCellKind.Text,
  readonly: true,
};

const DEFAULT_SQL = 'select * from infodba.viewpart';

export function PlmView() {
  return <>{usePlmViewElement()}</>;
}

function usePlmViewElement(): ReactNode {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab: PlmTab =
    searchParams.get('tab') === 'sql' ? 'sql' : 'tables';
  const pageSize = getPlmRawPageSize();
  const tableRequestIdRef = useRef(0);
  const sqlRequestIdRef = useRef(0);

  const [tables, setTables] = useState<PlmRawTable[]>([]);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [tablesError, setTablesError] = useState<string | null>(null);
  const [tableFilter, setTableFilter] = useState('');
  const [selectedTable, setSelectedTable] = useState<PlmRawTable | null>(null);
  const [tableResult, setTableResult] = useState<PlmRawRowsResponse | null>(
    null,
  );
  const [tableRowsLoading, setTableRowsLoading] = useState(false);
  const [tableRowsLoadingMore, setTableRowsLoadingMore] = useState(false);
  const [tableRowsError, setTableRowsError] = useState<string | null>(null);

  const [sqlDraft, setSqlDraft] = useState(DEFAULT_SQL);
  const [sqlActiveQuery, setSqlActiveQuery] = useState(DEFAULT_SQL);
  const [sqlResult, setSqlResult] = useState<PlmRawRowsResponse | null>(null);
  const [sqlLoading, setSqlLoading] = useState(false);
  const [sqlLoadingMore, setSqlLoadingMore] = useState(false);
  const [sqlError, setSqlError] = useState<string | null>(null);

  const updateTab = (tab: PlmTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'sql') {
      next.set('tab', 'sql');
    } else {
      next.delete('tab');
    }
    setSearchParams(next, { replace: false });
  };

  const loadTables = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setTablesLoading(true);
    setTablesError(null);
    try {
      const response = await fetchPlmRawTables(token, workspaceSlug);
      setTables(response.items);
      setSelectedTable((current) => {
        if (
          current &&
          response.items.some(
            (item) =>
              item.owner === current.owner && item.name === current.name,
          )
        ) {
          return current;
        }
        return response.items[0] ?? null;
      });
    } catch (error) {
      setTablesError(errorMessage(error, t('plm.errors.tablesLoadFailed')));
    } finally {
      setTablesLoading(false);
    }
  }, [t, token, workspaceSlug]);

  const loadTableRows = useCallback(
    async (table: PlmRawTable, offset: number, append: boolean) => {
      if (!token || !workspaceSlug) return;
      const requestId = ++tableRequestIdRef.current;
      if (append) {
        setTableRowsLoadingMore(true);
      } else {
        setTableRowsLoading(true);
        setTableResult(null);
      }
      setTableRowsError(null);
      try {
        const response = await fetchPlmRawTableRows({
          token,
          workspaceSlug,
          owner: table.owner,
          name: table.name,
          offset,
          limit: pageSize,
        });
        if (requestId !== tableRequestIdRef.current) return;
        setTableResult((current) =>
          append && current
            ? {
                ...response,
                columns:
                  current.columns.length > 0
                    ? current.columns
                    : response.columns,
                rows: [...current.rows, ...response.rows],
                offset: current.offset,
              }
            : response,
        );
      } catch (error) {
        if (requestId === tableRequestIdRef.current) {
          setTableRowsError(
            errorMessage(error, t('plm.errors.rowsLoadFailed')),
          );
        }
      } finally {
        if (requestId === tableRequestIdRef.current) {
          setTableRowsLoading(false);
          setTableRowsLoadingMore(false);
        }
      }
    },
    [pageSize, t, token, workspaceSlug],
  );

  const runSql = useCallback(
    async (offset: number, append: boolean) => {
      if (!token || !workspaceSlug) return;
      const requestId = ++sqlRequestIdRef.current;
      if (append) {
        setSqlLoadingMore(true);
      } else {
        setSqlLoading(true);
        setSqlResult(null);
      }
      setSqlError(null);
      const sqlToRun = append ? sqlActiveQuery : sqlDraft;
      try {
        const response = await runPlmRawSqlQuery({
          token,
          workspaceSlug,
          sql: sqlToRun,
          offset,
          limit: pageSize,
        });
        if (requestId !== sqlRequestIdRef.current) return;
        if (!append) {
          setSqlActiveQuery(sqlToRun);
        }
        setSqlResult((current) =>
          append && current
            ? {
                ...response,
                columns:
                  current.columns.length > 0
                    ? current.columns
                    : response.columns,
                rows: [...current.rows, ...response.rows],
                offset: current.offset,
              }
            : response,
        );
      } catch (error) {
        if (requestId === sqlRequestIdRef.current) {
          setSqlError(errorMessage(error, t('plm.errors.queryFailed')));
        }
      } finally {
        if (requestId === sqlRequestIdRef.current) {
          setSqlLoading(false);
          setSqlLoadingMore(false);
        }
      }
    },
    [pageSize, sqlActiveQuery, sqlDraft, t, token, workspaceSlug],
  );

  useEffect(() => {
    void loadTables();
  }, [loadTables]);

  useEffect(() => {
    if (activeTab !== 'tables' || !selectedTable) return;
    void loadTableRows(selectedTable, 0, false);
  }, [activeTab, loadTableRows, selectedTable]);

  const filteredTables = useMemo(() => {
    const query = tableFilter.trim().toLowerCase();
    if (!query) return tables;
    return tables.filter((table) =>
      `${table.owner}.${table.name} ${table.object_type}`
        .toLowerCase()
        .includes(query),
    );
  }, [tableFilter, tables]);

  const loadMoreTableRows = () => {
    if (!selectedTable || !tableResult?.has_more || tableRowsLoadingMore)
      return;
    void loadTableRows(selectedTable, tableResult.rows.length, true);
  };

  const loadMoreSqlRows = () => {
    if (!sqlResult?.has_more || sqlLoadingMore) return;
    void runSql(sqlResult.rows.length, true);
  };

  return (
    <main className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
      <header className="border-b border-app-border bg-app-bg px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface-sidebar text-app-accent">
              <Database size={18} />
            </span>
            <div className="min-w-0">
              <h1 className="app-text-title truncate">{t('plm.title')}</h1>
              <p className="app-text-caption text-app-ink/55">
                {t('plm.subtitle')}
              </p>
            </div>
          </div>
          <div className="inline-flex rounded-md border border-app-border bg-app-surface-sidebar p-0.5">
            <TabButton
              active={activeTab === 'tables'}
              icon={<Table2 size={14} />}
              label={t('plm.tabs.tables')}
              onClick={() => updateTab('tables')}
            />
            <TabButton
              active={activeTab === 'sql'}
              icon={<TerminalSquare size={14} />}
              label={t('plm.tabs.sql')}
              onClick={() => updateTab('sql')}
            />
          </div>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-b border-app-border bg-app-surface-sidebar lg:border-b-0 lg:border-r">
          <div className="border-b border-app-border p-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="app-text-control text-app-ink/75">
                {t('plm.tables.title')}
              </h2>
              <button
                type="button"
                onClick={() => void loadTables()}
                disabled={tablesLoading}
                className="flex size-7 items-center justify-center rounded-md text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink disabled:opacity-50"
                title={t('plm.actions.refreshTables')}
              >
                {tablesLoading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
              </button>
            </div>
            <label className="relative mt-2 block">
              <Search
                size={14}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-app-ink/35"
              />
              <input
                value={tableFilter}
                onChange={(event) => setTableFilter(event.currentTarget.value)}
                className="h-8 w-full rounded-md border border-app-border bg-app-bg pl-8 pr-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
                placeholder={t('plm.tables.filterPlaceholder')}
                aria-label={t('plm.tables.filterLabel')}
              />
            </label>
          </div>
          {tablesError ? <InlineError message={tablesError} /> : null}
          <div className="min-h-0 flex-1 overflow-y-auto">
            {tablesLoading && tables.length === 0 ? (
              <LoadingBlock label={t('common:feedback.loading')} />
            ) : filteredTables.length === 0 ? (
              <EmptyBlock label={t('plm.tables.empty')} />
            ) : (
              <ul className="divide-y divide-app-border/70">
                {filteredTables.map((table) => {
                  const active =
                    selectedTable?.owner === table.owner &&
                    selectedTable?.name === table.name;
                  return (
                    <li key={`${table.owner}.${table.name}`}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedTable(table);
                          updateTab('tables');
                        }}
                        className={cn(
                          'grid w-full min-w-0 gap-1 px-3 py-2 text-left transition-colors hover:bg-app-surface-hover',
                          active && 'bg-app-bg text-app-accent',
                        )}
                      >
                        <span className="truncate app-text-control">
                          {table.name}
                        </span>
                        <span className="flex min-w-0 items-center gap-2 app-text-caption text-app-ink/45">
                          <span className="truncate">{table.owner}</span>
                          <span className="shrink-0 rounded border border-app-border px-1.5 py-0.5">
                            {table.object_type}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>

        <section className="min-h-0 min-w-0">
          {activeTab === 'tables' ? (
            <TableBrowserPanel
              error={tableRowsError}
              loading={tableRowsLoading}
              loadingMore={tableRowsLoadingMore}
              onLoadMore={loadMoreTableRows}
              result={tableResult}
              selectedTable={selectedTable}
            />
          ) : (
            <SqlPanel
              error={sqlError}
              loading={sqlLoading}
              loadingMore={sqlLoadingMore}
              onLoadMore={loadMoreSqlRows}
              onRun={() => void runSql(0, false)}
              result={sqlResult}
              sqlDraft={sqlDraft}
              setSqlDraft={setSqlDraft}
            />
          )}
        </section>
      </div>
    </main>
  );
}

function TableBrowserPanel({
  error,
  loading,
  loadingMore,
  onLoadMore,
  result,
  selectedTable,
}: {
  error: string | null;
  loading: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  result: PlmRawRowsResponse | null;
  selectedTable: PlmRawTable | null;
}) {
  const { t } = useTranslation(['apps', 'common']);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-[3.25rem] flex-wrap items-center justify-between gap-2 border-b border-app-border bg-app-bg px-4 py-2">
        <div className="min-w-0">
          <h2 className="truncate app-text-title-sm">
            {selectedTable
              ? `${selectedTable.owner}.${selectedTable.name}`
              : t('plm.tables.noSelection')}
          </h2>
          <p className="app-text-caption text-app-ink/50">
            {t('plm.grid.loadedRows', { count: result?.rows.length ?? 0 })}
          </p>
        </div>
        {result?.has_more ? (
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 app-text-control text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-50"
          >
            {loadingMore ? (
              <Loader2 size={14} className="animate-spin" />
            ) : null}
            {t('plm.actions.loadMore')}
          </button>
        ) : null}
      </div>
      {error ? <InlineError message={error} /> : null}
      <RawGrid
        columns={result?.columns ?? []}
        emptyLabel={
          selectedTable ? t('plm.grid.empty') : t('plm.tables.noSelection')
        }
        hasMore={Boolean(result?.has_more)}
        loading={loading}
        loadingMore={loadingMore}
        onLoadMore={onLoadMore}
        rows={result?.rows ?? []}
      />
    </div>
  );
}

function SqlPanel({
  error,
  loading,
  loadingMore,
  onLoadMore,
  onRun,
  result,
  setSqlDraft,
  sqlDraft,
}: {
  error: string | null;
  loading: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onRun: () => void;
  result: PlmRawRowsResponse | null;
  setSqlDraft: (value: string) => void;
  sqlDraft: string;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onRun();
        }}
        className="border-b border-app-border bg-app-bg p-3"
      >
        <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto]">
          <label className="min-w-0">
            <span className="sr-only">{t('plm.sql.editorLabel')}</span>
            <textarea
              value={sqlDraft}
              onChange={(event) => setSqlDraft(event.currentTarget.value)}
              className="h-24 w-full resize-none rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 font-mono text-[12px] leading-5 text-app-ink outline-none focus:border-app-accent"
              spellCheck={false}
              placeholder={t('plm.sql.placeholder')}
            />
          </label>
          <div className="flex items-start gap-2 lg:flex-col">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-app-ink px-3 app-text-control text-app-bg hover:bg-app-ink/90 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              {t('plm.actions.run')}
            </button>
            {result?.has_more ? (
              <button
                type="button"
                onClick={onLoadMore}
                disabled={loadingMore}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 app-text-control text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-50"
              >
                {loadingMore ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : null}
                {t('plm.actions.loadMore')}
              </button>
            ) : null}
          </div>
        </div>
      </form>
      {error ? <InlineError message={error} /> : null}
      <div className="border-b border-app-border bg-app-bg px-4 py-2 app-text-caption text-app-ink/50">
        {t('plm.grid.loadedRows', { count: result?.rows.length ?? 0 })}
      </div>
      <RawGrid
        columns={result?.columns ?? []}
        emptyLabel={t('plm.sql.empty')}
        hasMore={Boolean(result?.has_more)}
        loading={loading}
        loadingMore={loadingMore}
        onLoadMore={onLoadMore}
        rows={result?.rows ?? []}
      />
    </div>
  );
}

function RawGrid({
  columns,
  emptyLabel,
  hasMore,
  loading,
  loadingMore,
  onLoadMore,
  rows,
}: {
  columns: PlmRawColumn[];
  emptyLabel: string;
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  rows: Array<Array<string | null>>;
}) {
  const { t } = useTranslation(['common']);
  const dataEditorRef = useRef<DataEditorRef | null>(null);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const glideTheme = usePlmGridTheme();
  const gridColumns = useMemo<GlideGridColumn[]>(
    () =>
      columns.map((column, index) => {
        const id = `${index}:${column.name}`;
        return {
          id,
          title: column.name || `C${index + 1}`,
          width: columnWidths[id] ?? estimateColumnWidth(column.name),
        } as GlideGridColumn;
      }),
    [columnWidths, columns],
  );

  const getCellContent = useCallback<DataEditorProps['getCellContent']>(
    ([columnIndex, rowIndex]) => {
      const row = rows[rowIndex];
      if (!row) return EMPTY_GRID_CELL;
      return createTextCell(row[columnIndex]);
    },
    [rows],
  );

  const handleColumnResize = useCallback<
    NonNullable<DataEditorProps['onColumnResize']>
  >((column, newSize) => {
    if (!column.id) return;
    setColumnWidths((current) => ({
      ...current,
      [column.id as string]: Math.round(newSize),
    }));
  }, []);

  const handleVisibleRegionChanged = useCallback<
    NonNullable<DataEditorProps['onVisibleRegionChanged']>
  >(
    (range: Rectangle) => {
      if (!hasMore || loadingMore) return;
      const bottomRow = range.y + range.height;
      if (bottomRow < rows.length - 20) return;
      onLoadMore();
    },
    [hasMore, loadingMore, onLoadMore, rows.length],
  );

  const getRowThemeOverride = useCallback<GetRowThemeCallback>(
    (row) => {
      if (row % 2 === 1) {
        return { bgCell: glideTheme.stripedRowBg };
      }
      return undefined;
    },
    [glideTheme.stripedRowBg],
  );

  if (loading) {
    return <LoadingBlock label={t('feedback.loading')} />;
  }
  if (rows.length === 0 || columns.length === 0) {
    return <EmptyBlock label={emptyLabel} />;
  }

  return (
    <div className="min-h-[28rem] flex-1 overflow-hidden bg-app-bg">
      <DataEditor
        ref={dataEditorRef}
        className="plm-raw-glide-grid"
        columns={gridColumns}
        copyHeaders
        drawFocusRing
        getCellContent={getCellContent}
        getCellsForSelection
        getRowThemeOverride={getRowThemeOverride}
        headerHeight={30}
        height="100%"
        maxColumnWidth={860}
        minColumnWidth={64}
        onColumnResize={handleColumnResize}
        onPaste={false}
        onVisibleRegionChanged={handleVisibleRegionChanged}
        rangeSelect="multi-rect"
        rowHeight={30}
        rowMarkers="number"
        rows={rows.length}
        smoothScrollX
        smoothScrollY
        theme={glideTheme.theme}
        verticalBorder
        width="100%"
      />
    </div>
  );
}

function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded px-3 app-text-control transition-colors',
        active
          ? 'bg-app-bg text-app-ink shadow-sm'
          : 'text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink',
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 border-b border-app-border bg-app-danger/10 px-4 py-2 app-text-body-sm text-app-danger">
      <AlertTriangle size={15} className="mt-0.5 shrink-0" />
      <span className="min-w-0 break-words">{message}</span>
    </div>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-72 flex-1 items-center justify-center gap-2 app-text-body-sm text-app-ink/50">
      <Loader2 size={16} className="animate-spin" />
      <span>{label}</span>
    </div>
  );
}

function EmptyBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-72 flex-1 items-center justify-center px-6 text-center app-text-body-sm text-app-ink/50">
      {label}
    </div>
  );
}

function createTextCell(value: string | null | undefined): GridCell {
  const displayData = value ?? '';
  return {
    allowOverlay: true,
    allowWrapping: false,
    copyData: displayData,
    data: displayData,
    displayData: displayData.replace(/\s+/g, ' ').slice(0, 1_000),
    kind: GridCellKind.Text,
    readonly: true,
  };
}

function estimateColumnWidth(name: string): number {
  return Math.min(Math.max(name.length * 9 + 56, 120), 320);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function readCssVariable(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

function usePlmGridTheme(): {
  stripedRowBg: string;
  theme: Partial<GlideTheme>;
} {
  const [theme, setTheme] = useState(() => createPlmGridTheme());
  useEffect(() => {
    const refreshTheme = () => setTheme(createPlmGridTheme());
    refreshTheme();
    if (
      typeof document === 'undefined' ||
      typeof MutationObserver === 'undefined'
    ) {
      return undefined;
    }
    const observer = new MutationObserver(refreshTheme);
    observer.observe(document.documentElement, {
      attributeFilter: ['class', 'style'],
      attributes: true,
    });
    return () => observer.disconnect();
  }, []);
  return theme;
}

function createPlmGridTheme(): {
  stripedRowBg: string;
  theme: Partial<GlideTheme>;
} {
  const bg = readCssVariable('--color-app-bg', APP_COLOR_FALLBACKS.bg);
  const surface = readCssVariable(
    '--color-app-surface-sidebar',
    APP_COLOR_FALLBACKS.surfaceSidebar,
  );
  const hover = readCssVariable(
    '--color-app-surface-hover',
    APP_COLOR_FALLBACKS.surfaceHover,
  );
  const border = readCssVariable(
    '--color-app-border',
    APP_COLOR_FALLBACKS.border,
  );
  const ink = readCssVariable('--color-app-ink', APP_COLOR_FALLBACKS.ink);
  const accent = readCssVariable(
    '--color-app-accent',
    APP_COLOR_FALLBACKS.accent,
  );
  return {
    stripedRowBg: surface,
    theme: {
      accentColor: accent,
      accentFg: readCssVariable('--color-app-bg', APP_COLOR_FALLBACKS.bg),
      bgCell: bg,
      bgCellMedium: surface,
      bgHeader: surface,
      bgHeaderHasFocus: hover,
      bgHeaderHovered: hover,
      borderColor: border,
      drilldownBorder: border,
      fgIconHeader: ink,
      textDark: ink,
      textHeader: ink,
      textLight: readCssVariable(
        '--color-app-ink-muted',
        APP_COLOR_FALLBACKS.inkMuted,
      ),
      textMedium: ink,
    },
  };
}
