import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  CalendarDays,
  ExternalLink,
  FileText,
  FolderKanban,
  Loader2,
  Search,
  Users,
  X,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  queryWorkspaceKeywordSearch,
  SearchApiError,
  type KeywordSearchEntityType,
  type KeywordSearchHit,
  type KeywordSearchResponse,
  type KeywordSearchSnippet,
} from '@/src/platform/search/search-api';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  getWorkspaceBySlug,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import {
  formatDateOnly,
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { cn } from '@/src/lib/utils';

const ENTITY_OPTIONS: Array<{ id: KeywordSearchEntityType | 'all'; labelKey: string }> = [
  { id: 'all', labelKey: 'search.entityAll' },
  { id: 'doc', labelKey: 'search.entityDoc' },
  { id: 'meeting', labelKey: 'search.entityMeeting' },
  { id: 'pms_issue', labelKey: 'search.entityPms' },
  { id: 'planner_event', labelKey: 'search.entityPlanner' },
];

type SearchSortField = 'relevance' | 'updated_at';

type UrlSearchState = {
  workspaceSlug: string | null;
  query: string;
  entityTypes: KeywordSearchEntityType[];
  sort: SearchSortField;
  selectedType: KeywordSearchEntityType | null;
  selectedId: string | null;
};

export function RagSearchView() {
  const { t } = useTranslation('apps');
  const { token, user, logout } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = useMemo(() => parseSearchParams(searchParams), [searchParams]);
  const urlEntityTypesKey = urlSearch.entityTypes.join('\u0000');
  const urlEntityTypes = useMemo(
    () => urlEntityTypesKey.split('\u0000').filter(isEntityType),
    [urlEntityTypesKey],
  );
  const workspaceSlug = getWorkspaceBySlug(user, urlSearch.workspaceSlug)?.slug
    ?? workspaceBootstrap.data?.workspace.slug
    ?? resolveShellWorkspaceSlug(user, null);
  const workspaceId = workspaceBootstrap.data?.workspace.id
    ?? getWorkspaceBySlug(user, workspaceSlug)?.id
    ?? null;
  const workspaceName = workspaceBootstrap.data?.workspace.name
    ?? getWorkspaceBySlug(user, workspaceSlug)?.name
    ?? workspaceSlug
    ?? '';
  const timeZone = normalizeTimeZone(user?.time_zone);

  const [queryInput, setQueryInput] = useState(urlSearch.query);
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<KeywordSearchEntityType[]>(urlSearch.entityTypes);
  const [sortField, setSortField] = useState<SearchSortField>(urlSearch.sort);
  const [response, setResponse] = useState<KeywordSearchResponse | null>(null);
  const [selectedHitKey, setSelectedHitKey] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeAbortRef = useRef<AbortController | null>(null);
  const lastSearchSignatureRef = useRef('');
  const requestSequenceRef = useRef(0);
  const queryInputRef = useRef(queryInput);
  const selectedEntityTypesRef = useRef(selectedEntityTypes);
  const sortFieldRef = useRef(sortField);

  useEffect(() => {
    setQueryInput(urlSearch.query);
  }, [urlSearch.query]);

  useEffect(() => {
    setSelectedEntityTypes(urlEntityTypes);
  }, [urlEntityTypes]);

  useEffect(() => {
    setSortField(urlSearch.sort);
  }, [urlSearch.sort]);

  useEffect(() => {
    queryInputRef.current = queryInput;
  }, [queryInput]);

  useEffect(() => {
    selectedEntityTypesRef.current = selectedEntityTypes;
  }, [selectedEntityTypes]);

  useEffect(() => {
    sortFieldRef.current = sortField;
  }, [sortField]);

  const runSearch = useCallback(async (options?: {
    query?: string;
    entityTypes?: KeywordSearchEntityType[];
    sort?: SearchSortField;
    offset?: number;
    append?: boolean;
    syncUrl?: boolean;
  }) => {
    if (!token) {
      setError(t('ai.search.authMissing'));
      return;
    }
    if (!workspaceSlug) {
      setError(t('ai.search.workspaceMissing'));
      return;
    }
    const nextQuery = options?.query ?? queryInputRef.current;
    const nextEntityTypes = options?.entityTypes ?? selectedEntityTypesRef.current;
    const nextSort = options?.sort ?? sortFieldRef.current;
    const nextOffset = options?.offset ?? 0;
    const sequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = sequence;
    activeAbortRef.current?.abort();
    const controller = new AbortController();
    activeAbortRef.current = controller;

    setSearching(true);
    setError(null);
    if (!options?.append) {
      setSelectedHitKey(null);
    }
    try {
      const nextResponse = await queryWorkspaceKeywordSearch(
        {
          workspace_id: workspaceId,
          query: nextQuery.trim(),
          entity_types: nextEntityTypes,
          sort: { field: nextSort, direction: 'desc' },
          limit: 20,
          offset: nextOffset,
        },
        token,
        workspaceSlug,
        { signal: controller.signal },
      );
      if (controller.signal.aborted || requestSequenceRef.current !== sequence) {
        return;
      }
      setResponse((current) => (
        options?.append && current
          ? { ...nextResponse, hits: [...current.hits, ...nextResponse.hits] }
          : nextResponse
      ));
      if (options?.syncUrl !== false) {
        setSearchParams(buildSearchParams({
          workspaceSlug,
          query: nextQuery.trim(),
          entityTypes: nextEntityTypes,
          sort: nextSort,
        }), { replace: true });
      }
    } catch (caughtError: unknown) {
      if (controller.signal.aborted || isAbortError(caughtError)) {
        return;
      }
      if (caughtError instanceof SearchApiError && caughtError.status === 401) {
        setError(t('ai.search.sessionExpired'));
        void logout();
        return;
      }
      setError(caughtError instanceof Error ? caughtError.message : t('ai.search.loadFailed'));
    } finally {
      if (requestSequenceRef.current === sequence) {
        setSearching(false);
      }
    }
  }, [
    logout,
    setSearchParams,
    token,
    workspaceId,
    workspaceSlug,
    t,
  ]);

  const searchSignature = [
    token ?? '',
    workspaceSlug ?? '',
    urlSearch.query,
    urlEntityTypesKey,
    urlSearch.sort,
  ].join('\u0001');

  useEffect(() => {
    if (!token || !workspaceSlug) {
      return;
    }
    if (lastSearchSignatureRef.current === searchSignature) {
      return;
    }
    lastSearchSignatureRef.current = searchSignature;
    if (!urlSearch.query && urlEntityTypes.length === 0) {
      void runSearch({ query: '', entityTypes: [], sort: urlSearch.sort, syncUrl: false });
      return;
    }
    void runSearch({
      query: urlSearch.query,
      entityTypes: urlEntityTypes,
      sort: urlSearch.sort,
      syncUrl: false,
    });
  }, [runSearch, searchSignature, token, urlEntityTypes, urlSearch.query, urlSearch.sort, workspaceSlug]);

  const requestedSelectedKey = urlSearch.selectedType && urlSearch.selectedId
    ? buildHitKeyFromParts(urlSearch.selectedType, urlSearch.selectedId)
    : null;

  useEffect(() => {
    if (!response?.hits.length) {
      setSelectedHitKey(null);
      return;
    }

    const availableKeys = new Set(response.hits.map(buildHitKey));
    if (requestedSelectedKey && availableKeys.has(requestedSelectedKey)) {
      setSelectedHitKey(requestedSelectedKey);
      return;
    }

    setSelectedHitKey((current) => {
      if (current && availableKeys.has(current) && !requestedSelectedKey) {
        return current;
      }
      return buildHitKey(response.hits[0]);
    });
  }, [requestedSelectedKey, response]);

  const selectedHit = useMemo(() => {
    if (!response?.hits.length || !selectedHitKey) {
      return null;
    }
    return response.hits.find((hit) => buildHitKey(hit) === selectedHitKey) ?? null;
  }, [response, selectedHitKey]);

  const selectHit = useCallback((hit: KeywordSearchHit) => {
    setSelectedHitKey(buildHitKey(hit));
    const next = new URLSearchParams(searchParams);
    next.set('selected_type', hit.entity_type);
    next.set('selected_id', hit.entity_id);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  if (!token) {
    return <div className="p-8 text-app-ink/60">{t('ai.search.authMissing')}</div>;
  }
  if (!workspaceSlug) {
    return <div className="p-8 text-app-ink/60">{t('ai.search.workspaceMissing')}</div>;
  }

  const toggleEntityType = (entityType: KeywordSearchEntityType | 'all') => {
    const nextTypes = entityType === 'all'
      ? []
      : selectedEntityTypes.includes(entityType)
        ? selectedEntityTypes.filter((item) => item !== entityType)
        : [...selectedEntityTypes, entityType];
    setSelectedEntityTypes(nextTypes);
    void runSearch({ entityTypes: nextTypes, syncUrl: true });
  };

  const changeSort = (nextSort: SearchSortField) => {
    setSortField(nextSort);
    void runSearch({ sort: nextSort, syncUrl: true });
  };

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="sticky top-0 z-10 border-b border-app-border bg-app-surface/95 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="app-text-title-lg text-app-ink">{t('ai.search.title')}</h1>
              <p className="app-text-caption mt-1 truncate text-app-ink/55">
                {workspaceName ? t('ai.search.subtitle', { workspace: workspaceName }) : t('ai.search.subtitleFallback')}
              </p>
            </div>
            <div className="hidden items-center gap-1 rounded-md border border-app-border bg-app-bg p-1 sm:flex">
              <SortButton active={sortField === 'relevance'} label={t('ai.search.sortRelevance')} onClick={() => changeSort('relevance')} />
              <SortButton active={sortField === 'updated_at'} label={t('ai.search.sortLatest')} onClick={() => changeSort('updated_at')} />
            </div>
          </div>

          <form
            className="flex items-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2 focus-within:border-app-accent"
            onSubmit={(event) => {
              event.preventDefault();
              void runSearch({ syncUrl: true });
            }}
          >
            <Search size={17} className="text-app-ink/35" />
            <input
              aria-label={t('ai.search.title')}
              className="app-text-body min-h-9 flex-1 bg-transparent text-app-ink outline-none"
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder={t('ai.search.placeholder')}
              value={queryInput}
            />
            {queryInput ? (
              <button
                aria-label={t('ai.search.clearQuery')}
                className="rounded-md p-1 text-app-ink/45 hover:bg-app-surface-hover"
                onClick={() => setQueryInput('')}
                type="button"
              >
                <X size={15} />
              </button>
            ) : null}
            <button
              className="inline-flex min-h-8 items-center gap-2 rounded-md bg-app-accent px-3 text-[0.84rem] font-semibold text-app-accent-fg disabled:opacity-60"
              disabled={searching}
              type="submit"
            >
              {searching ? <Loader2 size={14} className="animate-spin" /> : null}
              {t('ai.search.search')}
            </button>
          </form>

          <div className="flex flex-wrap items-center gap-2">
            {ENTITY_OPTIONS.map((option) => {
              const active = option.id === 'all'
                ? selectedEntityTypes.length === 0
                : selectedEntityTypes.includes(option.id);
              const count = option.id === 'all'
                ? response?.total
                : response?.facets.entity_types.find((facet) => facet.value === option.id)?.count;
              return (
                <button
                  key={option.id}
                  className={cn(
                    'inline-flex min-h-8 items-center gap-1.5 rounded-md border px-3 text-[0.8rem] font-medium transition-colors',
                    active
                      ? 'border-app-accent bg-app-accent/10 text-app-accent'
                      : 'border-app-border bg-app-bg text-app-ink/65 hover:bg-app-surface',
                  )}
                  onClick={() => toggleEntityType(option.id)}
                  type="button"
                >
                  {renderEntityIcon(option.id)}
                  <span>{t(`ai.${option.labelKey}`)}</span>
                  {typeof count === 'number' ? <span className="text-app-ink/40">{count}</span> : null}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col overflow-y-auto px-6 py-5">
        {error ? (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-[0.9rem] text-red-800">
            {error}
          </div>
        ) : null}

        <div className="mb-3 flex items-center justify-between">
          <p className="app-text-caption text-app-ink/55" role="status" aria-live="polite">
            {response
              ? t('ai.search.resultStatus', {
                total: response.total,
                shownPart: response.total > 0
                  ? t('ai.search.resultStatusShown', { shown: response.hits.length })
                  : '',
              })
              : t('ai.search.ready')}
          </p>
          <div className="flex items-center gap-1 rounded-md border border-app-border bg-app-bg p-1 sm:hidden">
            <SortButton active={sortField === 'relevance'} label={t('ai.search.sortRelevance')} onClick={() => changeSort('relevance')} />
            <SortButton active={sortField === 'updated_at'} label={t('ai.search.sortLatest')} onClick={() => changeSort('updated_at')} />
          </div>
        </div>

        {searching && !response ? (
          <div className="grid gap-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="h-20 animate-pulse rounded-md border border-app-border bg-app-surface" />
            ))}
          </div>
        ) : null}

        {response && response.hits.length === 0 && !searching ? (
          <div className="flex h-56 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/55">
            {t('ai.search.empty')}
          </div>
        ) : null}

        {response && response.hits.length > 0 ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface">
              {response.hits.map((hit) => {
                const isSelected = buildHitKey(hit) === selectedHitKey;
                return (
                  <div key={`${hit.entity_type}:${hit.entity_id}`}>
                    <SearchResultRow
                      hit={hit}
                      isSelected={isSelected}
                      onSelect={selectHit}
                      timeZone={timeZone}
                    />
                    {isSelected ? (
                      <div className="border-t border-app-border bg-app-bg/60 px-4 py-4 lg:hidden">
                        <SearchResultPreview hit={hit} timeZone={timeZone} variant="inline" />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
            <aside
              aria-label={t('ai.search.previewPane')}
              className="hidden lg:block"
            >
              <div className="sticky top-5">
                {selectedHit ? (
                  <SearchResultPreview hit={selectedHit} timeZone={timeZone} variant="side" />
                ) : (
                  <div className="rounded-md border border-app-border bg-app-surface px-4 py-6 text-[0.86rem] text-app-ink/55">
                    {t('ai.search.noSelectedResult')}
                  </div>
                )}
              </div>
            </aside>
          </div>
        ) : null}

        {response?.has_more ? (
          <button
            className="mx-auto mt-5 min-h-9 rounded-md border border-app-border bg-app-surface px-4 text-[0.86rem] font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-60"
            disabled={searching}
            onClick={() => void runSearch({ offset: response.next_offset ?? response.hits.length, append: true, syncUrl: false })}
            type="button"
          >
            {t('ai.search.more')}
          </button>
        ) : null}
      </main>
    </div>
  );
}

function SearchResultRow({
  hit,
  isSelected,
  onSelect,
  timeZone,
}: {
  hit: KeywordSearchHit;
  isSelected: boolean;
  onSelect: (hit: KeywordSearchHit) => void;
  timeZone: string;
}) {
  const { t } = useTranslation('apps');
  const openInNewTab = () => openSearchHitInNewTab(hit);

  return (
    <div
      className={cn(
        'flex items-stretch gap-2 px-3 py-3 transition-colors',
        isSelected ? 'bg-app-accent/5' : 'hover:bg-app-surface-hover',
      )}
    >
      <button
        aria-label={t('ai.search.selectResult', { title: hit.title })}
        aria-pressed={isSelected}
        className="min-w-0 flex-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-app-accent/50"
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey) {
            event.preventDefault();
            openInNewTab();
            return;
          }
          onSelect(hit);
        }}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
            event.preventDefault();
            openInNewTab();
          }
        }}
        type="button"
      >
        <div className="flex items-start gap-3">
          <SearchResultIcon entityType={hit.entity_type} active={isSelected} />
          <div className="min-w-0 flex-1">
            <SearchResultMetaLine hit={hit} />
            <h2 className="app-text-title-md mt-1 truncate text-app-ink">{hit.title}</h2>
            <p className="app-text-body mt-1 line-clamp-2 text-app-ink/65">
              <HighlightedSnippet snippet={hit.snippet} />
            </p>
            <SearchResultContext hit={hit} timeZone={timeZone} />
          </div>
        </div>
      </button>
      <Link
        aria-label={t('ai.search.openResult', { title: hit.title })}
        className="app-text-control-sm mt-1 inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-app-border bg-app-bg px-2.5 text-app-ink/65 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
        to={hit.deep_link}
      >
        <span className="hidden sm:inline">{t('ai.search.open')}</span>
        <ExternalLink size={13} />
      </Link>
    </div>
  );
}

function SearchResultPreview({
  hit,
  timeZone,
  variant,
}: {
  hit: KeywordSearchHit;
  timeZone: string;
  variant: 'side' | 'inline';
}) {
  const { t, i18n } = useTranslation('apps');
  const metadataEntries = getSearchHitMetadataEntries(hit, t);
  const dateMarkerEntries = getSearchHitDateMarkerEntries(hit, timeZone, i18n.language, t);

  return (
    <section
      aria-label={t('ai.search.preview', { title: hit.title })}
      className={cn(
        'rounded-md border border-app-border bg-app-surface',
        variant === 'inline' && 'bg-app-surface',
      )}
    >
      <div className="border-b border-app-border px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <SearchResultMetaLine hit={hit} />
            <h2 className="app-text-title-md mt-2 text-app-ink">{hit.title}</h2>
            <p className="app-text-caption mt-2 text-app-ink/50">
              {t('ai.search.updated', { date: formatDate(hit.updated_at, timeZone, i18n.language) })}
            </p>
          </div>
          <SearchResultIcon entityType={hit.entity_type} active />
        </div>
        <Link
          aria-label={t('ai.search.openSelectedResult', { title: hit.title })}
          className="app-text-control-sm mt-4 inline-flex min-h-8 items-center gap-1.5 rounded-md bg-app-accent px-3 text-app-accent-fg transition-opacity hover:opacity-90"
          to={hit.deep_link}
        >
          {t('ai.search.open')}
          <ExternalLink size={13} />
        </Link>
      </div>

      <div className="space-y-4 px-4 py-4">
        <div>
          <h3 className="app-text-overline text-app-ink/45">{t('ai.search.content')}</h3>
          <p className="app-text-body mt-2 text-app-ink/70">
            <HighlightedSnippet snippet={hit.snippet} />
          </p>
        </div>

        {hit.people.length > 0 || hit.containers.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            {hit.people.length > 0 ? (
              <PreviewField
                label={t('ai.search.metadataPeople')}
                values={hit.people.slice(0, 4).map((person) => `${personRoleLabel(person.role, t)} ${person.label}`)}
              />
            ) : null}
            {hit.containers.length > 0 ? (
              <PreviewField
                label={t('ai.search.metadataPosition')}
                values={hit.containers.slice(0, 4).map((container) => container.label)}
              />
            ) : null}
          </div>
        ) : null}

        {dateMarkerEntries.length > 0 || metadataEntries.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            {dateMarkerEntries.map((entry) => (
              <PreviewField key={entry.label} label={entry.label} values={[entry.value]} />
            ))}
            {metadataEntries.map((entry) => (
              <PreviewField key={entry.label} label={entry.label} values={[entry.value]} />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function SearchResultIcon({
  entityType,
  active = false,
}: {
  entityType: KeywordSearchEntityType;
  active?: boolean;
}) {
  return (
    <div
      className={cn(
        'mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border',
        active
          ? 'border-app-accent/30 bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/55',
      )}
    >
      {renderEntityIcon(entityType)}
    </div>
  );
}

function SearchResultMetaLine({ hit }: { hit: KeywordSearchHit }) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="text-[0.72rem] font-semibold text-app-ink/45">{entityLabel(hit.entity_type, t)}</span>
      {hit.status_label ? <span className="rounded-sm bg-app-bg px-1.5 py-0.5 text-[0.72rem] text-app-ink/55">{hit.status_label}</span> : null}
      {hit.visibility ? <span className="text-[0.72rem] text-app-ink/40">{visibilityLabel(hit.visibility, t)}</span> : null}
    </div>
  );
}

function SearchResultContext({ hit, timeZone }: { hit: KeywordSearchHit; timeZone: string }) {
  const { i18n } = useTranslation('apps');
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[0.76rem] text-app-ink/45">
      <span>{formatDate(hit.updated_at, timeZone, i18n.language)}</span>
      {hit.people.slice(0, 2).map((person) => (
        <span key={`${person.role}:${person.user_id}`}>{person.label}</span>
      ))}
      {hit.containers.slice(0, 2).map((container) => (
        <span key={`${container.type}:${container.id}`}>{container.label}</span>
      ))}
    </div>
  );
}

function PreviewField({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <h3 className="app-text-overline text-app-ink/45">{label}</h3>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {values.map((value) => (
          <span
            key={value}
            className="rounded-sm bg-app-bg px-2 py-1 text-[0.76rem] text-app-ink/65"
          >
            {value}
          </span>
        ))}
      </div>
    </div>
  );
}

function HighlightedSnippet({ snippet }: { snippet: KeywordSearchSnippet }) {
  if (snippet.highlights.length === 0) {
    return snippet.text;
  }
  const [highlight] = snippet.highlights;
  return (
    <>
      {snippet.text.slice(0, highlight.start)}
      <mark className="rounded-sm bg-yellow-200 px-0.5 text-app-ink">
        {snippet.text.slice(highlight.start, highlight.end)}
      </mark>
      {snippet.text.slice(highlight.end)}
    </>
  );
}

function SortButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={cn(
        'min-h-7 rounded px-2.5 text-[0.78rem] font-medium',
        active ? 'bg-app-surface text-app-ink' : 'text-app-ink/50 hover:text-app-ink',
      )}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function parseSearchParams(searchParams: URLSearchParams): UrlSearchState {
  const selectedType = searchParams.get('selected_type');
  return {
    workspaceSlug: searchParams.get('workspace')?.trim() || null,
    query: searchParams.get('q')?.trim() || '',
    entityTypes: searchParams.getAll('type').filter(isEntityType),
    sort: searchParams.get('sort') === 'updated_at' ? 'updated_at' : 'relevance',
    selectedType: selectedType && isEntityType(selectedType) ? selectedType : null,
    selectedId: searchParams.get('selected_id')?.trim() || null,
  };
}

function buildSearchParams(input: {
  workspaceSlug: string;
  query: string;
  entityTypes: KeywordSearchEntityType[];
  sort: SearchSortField;
}) {
  const params = new URLSearchParams();
  params.set('workspace', input.workspaceSlug);
  if (input.query) {
    params.set('q', input.query);
  }
  for (const entityType of input.entityTypes) {
    params.append('type', entityType);
  }
  if (input.sort !== 'relevance') {
    params.set('sort', input.sort);
  }
  return params;
}

function buildHitKey(hit: KeywordSearchHit): string {
  return buildHitKeyFromParts(hit.entity_type, hit.entity_id);
}

function buildHitKeyFromParts(entityType: KeywordSearchEntityType, entityId: string): string {
  return `${entityType}:${entityId}`;
}

function openSearchHitInNewTab(hit: KeywordSearchHit) {
  window.open(hit.deep_link, '_blank', 'noopener,noreferrer');
}

function getSearchHitDateMarkerEntries(
  hit: KeywordSearchHit,
  timeZone: string,
  locale: string,
  t: (key: string) => string,
) {
  const entries: Array<{ label: string; value: string }> = [];
  const labels: Record<string, string> = {
    due_date: t('ai.search.metadataDueDate'),
    start_date: t('ai.search.metadataStartDate'),
    event_start_at: t('ai.search.metadataEventStart'),
  };
  for (const key of ['due_date', 'start_date', 'event_start_at']) {
    const value = hit.date_markers[key];
    if (typeof value === 'string' && value) {
      entries.push({ label: labels[key], value: formatDate(value, timeZone, locale) });
    }
  }
  return entries;
}

function getSearchHitMetadataEntries(hit: KeywordSearchHit, t: (key: string) => string) {
  const labels: Record<string, string> = {
    all_day: t('ai.search.metadataAllDay'),
    attendee_count: t('ai.search.metadataAttendeeCount'),
    issue_number: t('ai.search.metadataIssueNumber'),
    location: t('ai.search.metadataLocation'),
    priority: t('ai.search.metadataPriority'),
    source_kind: t('ai.search.metadataSourceKind'),
    source_ref: t('ai.search.metadataSourceRef'),
  };
  return Object.entries(labels)
    .map(([key, label]) => {
      const value = hit.metadata[key];
      const formattedValue = formatMetadataValue(value, t);
      return formattedValue ? { label, value: formattedValue } : null;
    })
    .filter((entry): entry is { label: string; value: string } => Boolean(entry));
}

function formatMetadataValue(value: unknown, t: (key: string) => string): string | null {
  if (typeof value === 'string') {
    return value.trim() || null;
  }
  if (typeof value === 'number') {
    return String(value);
  }
  if (typeof value === 'boolean') {
    return value ? t('ai.search.yes') : t('ai.search.no');
  }
  return null;
}

function personRoleLabel(role: string, t: (key: string) => string): string {
  if (role === 'owner') return t('ai.search.metadataOwner');
  if (role === 'assignee') return t('ai.search.metadataAssignee');
  if (role === 'participant') return t('ai.search.metadataParticipant');
  return role;
}

function isEntityType(value: string): value is KeywordSearchEntityType {
  return ['doc', 'meeting', 'pms_issue', 'planner_event'].includes(value);
}

function renderEntityIcon(entityType: KeywordSearchEntityType | 'all') {
  if (entityType === 'doc') {
    return <FileText size={13} />;
  }
  if (entityType === 'meeting') {
    return <Users size={13} />;
  }
  if (entityType === 'pms_issue') {
    return <FolderKanban size={13} />;
  }
  if (entityType === 'planner_event') {
    return <CalendarDays size={13} />;
  }
  return <Search size={13} />;
}

function entityLabel(entityType: KeywordSearchEntityType, t: (key: string) => string): string {
  if (entityType === 'doc') return t('ai.search.entityDoc');
  if (entityType === 'meeting') return t('ai.search.entityMeeting');
  if (entityType === 'pms_issue') return 'PMS';
  return t('ai.search.entityPlanner');
}

function visibilityLabel(value: string, t: (key: string) => string): string {
  if (value === 'private') return t('ai.search.visibilityPrivate');
  if (value === 'public') return t('ai.search.visibilityPublic');
  if (value === 'shared') return t('ai.search.visibilityShared');
  return value;
}

function formatDate(value: string, timeZone: string, locale: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return formatDateOnly(value, { fallback: value, locale });
  }
  return formatDateTime(value, {
    dateStyle: 'medium',
    fallback: value,
    locale,
    timeZone,
  });
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
