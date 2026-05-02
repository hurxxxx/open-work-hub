import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Button,
  DataTable,
  DataTableToolbar,
  DetailDrawer,
  EmptyState,
  FilterBar,
  InlineNotice,
  SearchField,
  type DataTableColumn,
  useToast,
} from '@aidoo/ui';

import {
  searchDocuments,
  type SearchDocumentHit,
  type SearchDocumentsFilters,
  type SearchDocumentsResponse,
} from './documents-api';

const DEFAULT_QUERY = 'compressor specification latest revision';

const VIEW_PRESETS = {
  'engineering-specs': {
    query: 'compressor specification latest revision',
    docType: 'spec',
    scope: 'engineering',
  },
  'revision-notices': {
    query: 'seal material change notice',
    docType: 'revision-note',
    scope: 'project-a',
  },
  'quality-guides': {
    query: 'supplier quality containment response',
    docType: 'guide',
    scope: 'supplier-quality',
  },
} as const;

type SavedViewId = keyof typeof VIEW_PRESETS;
type ScopeFilterId = 'engineering' | 'project-a' | 'quality' | 'supplier-quality';
type SearchWorkbenchTranslate = (key: string) => string;

function buildColumns(t: SearchWorkbenchTranslate): DataTableColumn<SearchDocumentHit>[] {
  const searchColumns: DataTableColumn<SearchDocumentHit>[] = [
    {
      accessorKey: 'title',
      header: t('docs.searchWorkbench.columns.document'),
      cell: ({ row }) => (
        <span className="block">
          <strong className="block text-[0.94rem]">{row.original.title}</strong>
          <small className="mt-1 block text-[0.82rem] text-[var(--ui-color-ink-subtle)]">
            {row.original.summary}
          </small>
        </span>
      ),
    },
    { accessorKey: 'updated', header: t('docs.searchWorkbench.columns.updated') },
    { accessorKey: 'source_type', header: t('docs.searchWorkbench.columns.type') },
    { accessorKey: 'acl', header: 'ACL' },
  ];
  return searchColumns;
}

function buildFilters(docType: string, scope: ScopeFilterId): SearchDocumentsFilters {
  const filters: SearchDocumentsFilters = {
    doc_type: docType ? [docType] : [],
    project: [],
    department: [],
  };

  if (scope === 'project-a') {
    filters.project = ['Project A'];
  }
  if (scope === 'engineering') {
    filters.department = ['Engineering'];
  }
  if (scope === 'quality') {
    filters.department = ['Quality'];
  }
  if (scope === 'supplier-quality') {
    filters.department = ['Supplier Quality'];
  }

  return filters;
}

export interface SearchWorkbenchProps {
  token: string;
}

export function SearchWorkbench({ token }: SearchWorkbenchProps) {
  const { t } = useTranslation('apps');
  const columns = useMemo(() => buildColumns(t), [t]);
  const [savedView, setSavedView] = useState<SavedViewId>('engineering-specs');
  const [docType, setDocType] = useState('spec');
  const [scope, setScope] = useState<ScopeFilterId>('engineering');
  const [queryInput, setQueryInput] = useState(DEFAULT_QUERY);
  const [submittedQuery, setSubmittedQuery] = useState(DEFAULT_QUERY);
  const [searchState, setSearchState] = useState<SearchDocumentsResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [selectedRow, setSelectedRow] = useState<SearchDocumentHit | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const toast = useToast();

  useEffect(() => {
    let active = true;

    async function runSearch() {
      setSearching(true);
      setSearchError(null);

      try {
        const nextState = await searchDocuments(
          {
            query: submittedQuery,
            filters: buildFilters(docType, scope),
            top_k: 8,
            answer_mode: 'search-only',
          },
          token,
        );
        if (!active) {
          return;
        }

        setSearchState(nextState);
      } catch (caughtError) {
        if (!active) {
          return;
        }
        setSearchError(
          caughtError instanceof Error
            ? caughtError.message
            : t('docs.searchWorkbench.loadFailed'),
        );
      } finally {
        if (active) {
          setSearching(false);
        }
      }
    }

    void runSearch();

    return () => {
      active = false;
    };
  }, [docType, scope, submittedQuery, token, t]);

  useEffect(() => {
    if (!searchState?.hits.some((hit) => hit.document_id === selectedRow?.document_id)) {
      setSelectedRow(null);
      setDrawerOpen(false);
    }
  }, [searchState, selectedRow?.document_id]);

  const hits = searchState?.hits ?? [];
  const nextActions = searchState?.next_actions ?? [];

  function submitCurrentQuery() {
    setSubmittedQuery(queryInput.trim() || DEFAULT_QUERY);
  }

  function applySavedView(viewId: SavedViewId) {
    const preset = VIEW_PRESETS[viewId];
    setSavedView(viewId);
    setDocType(preset.docType);
    setScope(preset.scope);
    setQueryInput(preset.query);
    setSubmittedQuery(preset.query);
  }

  return (
    <>
      <div className="grid gap-3">
        <section className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-3.5">
          <div className="flex flex-col gap-2 border-b border-[var(--ui-color-border)] pb-2.5 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-2.5">
              <p className="m-0 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                {t('common:actions.search')}
              </p>
              <h2 className="m-0 text-[0.92rem] font-semibold text-[var(--ui-color-ink)]">
                {t('docs.searchWorkbench.title')}
              </h2>
              <span className="text-[0.76rem] text-[var(--ui-color-ink-subtle)]">
                {t('docs.searchWorkbench.citationRequired')}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() => applySavedView('engineering-specs')}
              >
                {t('docs.searchWorkbench.defaultView')}
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setDocType('spec');
                  setScope('engineering');
                  setQueryInput(DEFAULT_QUERY);
                  setSubmittedQuery(DEFAULT_QUERY);
                  toast.info(t('docs.searchWorkbench.filtersResetTitle'), t('docs.searchWorkbench.filtersResetDescription'));
                }}
              >
                {t('docs.searchWorkbench.resetFilters')}
              </Button>
            </div>
          </div>

          <div className="grid gap-2.5 pt-3">
            <div className="documents-workbench__search">
              <form
                className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_auto]"
                onSubmit={(event) => {
                  event.preventDefault();
                  submitCurrentQuery();
                }}
              >
                <SearchField
                  aria-label={t('docs.searchWorkbench.globalSearch')}
                  className="flex-1"
                  onChange={(event) => setQueryInput(event.target.value)}
                  shortcut="⌘K"
                  value={queryInput}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    className="w-full sm:w-auto"
                    size="comfortable"
                    type="submit"
                    variant="primary"
                  >
                    {t('common:actions.search')}
                  </Button>
                  <FilterBar
                    options={[
                      {
                        id: 'engineering-specs',
                        label: t('docs.searchWorkbench.views.engineeringSpecs'),
                        active: savedView === 'engineering-specs',
                        onSelect: () => applySavedView('engineering-specs'),
                      },
                      {
                        id: 'revision-notices',
                        label: t('docs.searchWorkbench.views.revisionNotices'),
                        active: savedView === 'revision-notices',
                        onSelect: () => applySavedView('revision-notices'),
                      },
                      {
                        id: 'quality-guides',
                        label: t('docs.searchWorkbench.views.qualityGuides'),
                        active: savedView === 'quality-guides',
                        onSelect: () => applySavedView('quality-guides'),
                      },
                    ]}
                  />
                </div>
              </form>
            </div>

            <div className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="grid gap-1.5">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                  {t('docs.searchWorkbench.type')}
                </span>
                <FilterBar
                  options={[
                    {
                      id: 'spec',
                      label: t('docs.searchWorkbench.docType.spec'),
                      active: docType === 'spec',
                      onSelect: () => {
                        setDocType('spec');
                        submitCurrentQuery();
                      },
                    },
                    {
                      id: 'revision-note',
                      label: t('docs.searchWorkbench.docType.revisionNote'),
                      active: docType === 'revision-note',
                      onSelect: () => {
                        setDocType('revision-note');
                        submitCurrentQuery();
                      },
                    },
                    {
                      id: 'memo',
                      label: t('docs.searchWorkbench.docType.memo'),
                      active: docType === 'memo',
                      onSelect: () => {
                        setDocType('memo');
                        submitCurrentQuery();
                      },
                    },
                    {
                      id: 'guide',
                      label: t('docs.searchWorkbench.docType.guide'),
                      active: docType === 'guide',
                      onSelect: () => {
                        setDocType('guide');
                        submitCurrentQuery();
                      },
                    },
                  ]}
                />
              </div>

              <div className="grid gap-1.5">
                <span className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                  {t('docs.searchWorkbench.scope')}
                </span>
                <FilterBar
                  options={[
                    {
                      id: 'engineering',
                      label: t('docs.searchWorkbench.scopeOption.engineering'),
                      active: scope === 'engineering',
                      onSelect: () => {
                        setScope('engineering');
                        submitCurrentQuery();
                      },
                    },
                    {
                      id: 'project-a',
                      label: t('docs.searchWorkbench.scopeOption.projectA'),
                      active: scope === 'project-a',
                      onSelect: () => {
                        setScope('project-a');
                        submitCurrentQuery();
                      },
                    },
                    {
                      id: 'quality',
                      label: t('docs.searchWorkbench.scopeOption.quality'),
                      active: scope === 'quality',
                      onSelect: () => {
                        setScope('quality');
                        submitCurrentQuery();
                      },
                    },
                    {
                      id: 'supplier-quality',
                      label: t('docs.searchWorkbench.scopeOption.supplierQuality'),
                      active: scope === 'supplier-quality',
                      onSelect: () => {
                        setScope('supplier-quality');
                        submitCurrentQuery();
                      },
                    },
                  ]}
                />
              </div>
            </div>
          </div>
        </section>

        {searchError ? (
          <div className="app-text-body rounded-[var(--ui-radius-md)] border border-rose-200 bg-rose-50 px-3 py-2 text-rose-700">
            {searchError}
          </div>
        ) : null}

        {nextActions.length ? (
          <InlineNotice title={t('docs.searchWorkbench.nextActions')}>{nextActions.join(' · ')}</InlineNotice>
        ) : null}

        <section className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)]">
          <div className="border-b border-[var(--ui-color-border)] px-3.5 py-2.5">
            <DataTableToolbar
              title={t('docs.searchWorkbench.topResults')}
              meta={
                searchState
                  ? t('docs.searchWorkbench.resultsMeta', { count: hits.length, profile: searchState.query_profile })
                  : t('docs.searchWorkbench.preparingContext')
              }
            />
          </div>
          <DataTable
            columns={columns}
            emptyState={
              <EmptyState
                title={t('docs.searchWorkbench.noResultsTitle')}
                description={t('docs.searchWorkbench.noResultsDescription')}
                action={{
                  label: t('docs.searchWorkbench.returnDefaultSearch'),
                  onClick: () => applySavedView('engineering-specs'),
                }}
              />
            }
            loading={searching}
            rows={hits}
            selection={{
              selectedRowId: selectedRow?.document_id,
              getRowId: (row) => row.document_id,
              onRowClick: (row) => {
                setSelectedRow(row);
                setDrawerOpen(true);
              },
            }}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--ui-color-border)] px-3.5 py-2 text-[0.76rem] text-[var(--ui-color-ink-subtle)]">
            <span>{t('docs.searchWorkbench.queryProfile', { profile: searchState?.query_profile ?? t('common:feedback.loading') })}</span>
            <span>
              {t('docs.searchWorkbench.filters', { filters: searchState?.filters_applied.doc_type.join(', ') || t('docs.searchWorkbench.all') })} /{' '}
              {searchState?.filters_applied.department.join(', ') ||
                searchState?.filters_applied.project.join(', ') ||
                t('docs.searchWorkbench.global')}
            </span>
          </div>
        </section>
      </div>

      <DetailDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        closeLabel={t('common:actions.close')}
        title={selectedRow?.title ?? t('docs.searchWorkbench.selectedDocument')}
        description={t('docs.searchWorkbench.drawerDescription')}
        actions={
          <>
            <Button
              fullWidth
              variant="primary"
              size="comfortable"
              onClick={() =>
                toast.success(
                  t('docs.searchWorkbench.citationAddedTitle'),
                  t('docs.searchWorkbench.citationAddedDescription'),
                )
              }
            >
              {t('docs.searchWorkbench.addEvidenceToDraft')}
            </Button>
            <Button
              fullWidth
              variant="secondary"
              size="comfortable"
              onClick={() =>
                toast.info(t('docs.searchWorkbench.openSourceTitle'), t('docs.searchWorkbench.openSourceDescription'))
              }
            >
              {t('docs.searchWorkbench.openSource')}
            </Button>
          </>
        }
      >
        {selectedRow ? (
          <div className="documents-detail">
            <InlineNotice title={t('docs.searchWorkbench.citationRequired')}>
              {t('docs.searchWorkbench.citationNotice')}
            </InlineNotice>

            <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-4">
              <div className="app-text-body mb-3 text-[var(--ui-color-ink-subtle)]">
                {selectedRow.title} · {selectedRow.page_reference}
              </div>
              <strong className="block text-base text-[var(--ui-color-ink)]">
                {t('docs.searchWorkbench.selectedEvidence')}
              </strong>
              <p className="documents-detail__quote">{selectedRow.citation}</p>
            </div>

            <ul className="documents-summary-list">
              <li>
                <strong>{t('docs.searchWorkbench.owner')}</strong>
                <span>{selectedRow.owner}</span>
              </li>
              <li>
                <strong>ACL</strong>
                <span>{selectedRow.acl} / {selectedRow.department}</span>
              </li>
              <li>
                <strong>{t('docs.searchWorkbench.project')}</strong>
                <span>{selectedRow.project}</span>
              </li>
              <li>
                <strong>{t('docs.searchWorkbench.nextActions')}</strong>
                <span>{selectedRow.next_actions.join(' · ')}</span>
              </li>
            </ul>
          </div>
        ) : null}
      </DetailDrawer>
    </>
  );
}
