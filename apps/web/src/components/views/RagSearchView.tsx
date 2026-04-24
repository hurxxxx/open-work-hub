import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  CalendarDays,
  FileText,
  FolderKanban,
  Loader2,
  Search,
  Users,
  X,
} from 'lucide-react';

import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  queryWorkspaceKeywordSearch,
  SearchApiError,
  type KeywordSearchEntityType,
  type KeywordSearchHit,
  type KeywordSearchResponse,
  type KeywordSearchSnippet,
} from '@/src/domains/search/search-api';
import { useWorkspaceBootstrapContext } from '@/src/domains/workspaces/workspace-bootstrap-context';
import {
  getWorkspaceBySlug,
  resolveShellWorkspaceSlug,
} from '@/src/domains/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';

const ENTITY_OPTIONS: Array<{ id: KeywordSearchEntityType | 'all'; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'doc', label: '문서' },
  { id: 'meeting', label: '회의' },
  { id: 'pms_issue', label: 'PMS' },
  { id: 'planner_event', label: '일정' },
];

type SearchSortField = 'relevance' | 'updated_at';

type UrlSearchState = {
  workspaceSlug: string | null;
  query: string;
  entityTypes: KeywordSearchEntityType[];
  sort: SearchSortField;
};

export function RagSearchView() {
  const { token, user, logout } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = useMemo(() => parseSearchParams(searchParams), [searchParams]);
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

  const [queryInput, setQueryInput] = useState(urlSearch.query);
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<KeywordSearchEntityType[]>(urlSearch.entityTypes);
  const [sortField, setSortField] = useState<SearchSortField>(urlSearch.sort);
  const [response, setResponse] = useState<KeywordSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeAbortRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);
  const queryInputRef = useRef(queryInput);
  const selectedEntityTypesRef = useRef(selectedEntityTypes);
  const sortFieldRef = useRef(sortField);

  useEffect(() => {
    setQueryInput(urlSearch.query);
  }, [urlSearch.query]);

  useEffect(() => {
    setSelectedEntityTypes(urlSearch.entityTypes);
  }, [urlSearch.entityTypes]);

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
      setError('인증 정보가 없어 통합검색을 사용할 수 없습니다.');
      return;
    }
    if (!workspaceSlug) {
      setError('검색할 workspace를 찾을 수 없습니다.');
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
        setError('세션이 만료되었습니다. 다시 로그인해주세요.');
        void logout();
        return;
      }
      setError(caughtError instanceof Error ? caughtError.message : '검색 결과를 불러오지 못했습니다.');
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
  ]);

  useEffect(() => {
    if (!token || !workspaceSlug) {
      return;
    }
    if (!urlSearch.query && urlSearch.entityTypes.length === 0) {
      void runSearch({ query: '', entityTypes: [], sort: urlSearch.sort, syncUrl: false });
      return;
    }
    void runSearch({
      query: urlSearch.query,
      entityTypes: urlSearch.entityTypes,
      sort: urlSearch.sort,
      syncUrl: false,
    });
    return () => {
      activeAbortRef.current?.abort();
    };
  }, [runSearch, token, urlSearch.entityTypes, urlSearch.query, urlSearch.sort, workspaceSlug]);

  if (!token) {
    return <div className="p-8 text-app-ink/60">인증 정보가 없어 통합검색을 사용할 수 없습니다.</div>;
  }
  if (!workspaceSlug) {
    return <div className="p-8 text-app-ink/60">검색할 workspace를 찾을 수 없습니다.</div>;
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
              <h1 className="app-text-title-lg text-app-ink">아이두 통합검색</h1>
              <p className="app-text-caption mt-1 truncate text-app-ink/55">
                {workspaceName ? `${workspaceName}의 문서, 회의, PMS, 일정을 검색합니다.` : '업무 데이터를 검색합니다.'}
              </p>
            </div>
            <div className="hidden items-center gap-1 rounded-md border border-app-border bg-app-bg p-1 sm:flex">
              <SortButton active={sortField === 'relevance'} label="관련도" onClick={() => changeSort('relevance')} />
              <SortButton active={sortField === 'updated_at'} label="최신순" onClick={() => changeSort('updated_at')} />
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
              aria-label="통합검색어"
              className="app-text-body min-h-9 flex-1 bg-transparent text-app-ink outline-none"
              onChange={(event) => setQueryInput(event.target.value)}
              placeholder="문서, 회의, 이슈, 일정 검색"
              value={queryInput}
            />
            {queryInput ? (
              <button
                aria-label="검색어 지우기"
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
              검색
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
                  <span>{option.label}</span>
                  {typeof count === 'number' ? <span className="text-app-ink/40">{count}</span> : null}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col overflow-y-auto px-6 py-5">
        {error ? (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-[0.9rem] text-red-800">
            {error}
          </div>
        ) : null}

        <div className="mb-3 flex items-center justify-between">
          <p className="app-text-caption text-app-ink/55" role="status" aria-live="polite">
            {response ? `${response.total}건${response.total > 0 ? ` 중 ${response.hits.length}건 표시` : ''}` : '검색 결과를 준비 중입니다.'}
          </p>
          <div className="flex items-center gap-1 rounded-md border border-app-border bg-app-bg p-1 sm:hidden">
            <SortButton active={sortField === 'relevance'} label="관련도" onClick={() => changeSort('relevance')} />
            <SortButton active={sortField === 'updated_at'} label="최신순" onClick={() => changeSort('updated_at')} />
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
            검색 결과가 없습니다.
          </div>
        ) : null}

        {response && response.hits.length > 0 ? (
          <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface">
            {response.hits.map((hit) => (
              <SearchResultRow key={`${hit.entity_type}:${hit.entity_id}`} hit={hit} />
            ))}
          </div>
        ) : null}

        {response?.has_more ? (
          <button
            className="mx-auto mt-5 min-h-9 rounded-md border border-app-border bg-app-surface px-4 text-[0.86rem] font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-60"
            disabled={searching}
            onClick={() => void runSearch({ offset: response.next_offset ?? response.hits.length, append: true, syncUrl: false })}
            type="button"
          >
            더 보기
          </button>
        ) : null}
      </main>
    </div>
  );
}

function SearchResultRow({ hit }: { hit: KeywordSearchHit }) {
  return (
    <Link className="block px-4 py-3 transition-colors hover:bg-app-surface-hover" to={hit.deep_link}>
      <div className="flex items-start gap-3">
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink/55">
          {renderEntityIcon(hit.entity_type)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="text-[0.72rem] font-semibold text-app-ink/45">{entityLabel(hit.entity_type)}</span>
            {hit.status_label ? <span className="rounded-sm bg-app-bg px-1.5 py-0.5 text-[0.72rem] text-app-ink/55">{hit.status_label}</span> : null}
            {hit.visibility ? <span className="text-[0.72rem] text-app-ink/40">{visibilityLabel(hit.visibility)}</span> : null}
          </div>
          <h2 className="app-text-title-md mt-1 truncate text-app-ink">{hit.title}</h2>
          <p className="app-text-body mt-1 line-clamp-2 text-app-ink/65">
            <HighlightedSnippet snippet={hit.snippet} />
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[0.76rem] text-app-ink/45">
            <span>{formatDate(hit.updated_at)}</span>
            {hit.people.slice(0, 2).map((person) => (
              <span key={`${person.role}:${person.user_id}`}>{person.label}</span>
            ))}
            {hit.containers.slice(0, 2).map((container) => (
              <span key={`${container.type}:${container.id}`}>{container.label}</span>
            ))}
          </div>
        </div>
        <ArrowUpRight size={15} className="mt-2 text-app-ink/35" />
      </div>
    </Link>
  );
}

function HighlightedSnippet({ snippet }: { snippet: KeywordSearchSnippet }) {
  if (snippet.highlights.length === 0) {
    return <>{snippet.text}</>;
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
  return {
    workspaceSlug: searchParams.get('workspace')?.trim() || null,
    query: searchParams.get('q')?.trim() || '',
    entityTypes: searchParams.getAll('type').filter(isEntityType),
    sort: searchParams.get('sort') === 'updated_at' ? 'updated_at' : 'relevance',
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

function entityLabel(entityType: KeywordSearchEntityType): string {
  if (entityType === 'doc') return '문서';
  if (entityType === 'meeting') return '회의';
  if (entityType === 'pms_issue') return 'PMS';
  return '일정';
}

function visibilityLabel(value: string): string {
  if (value === 'private') return '비공개';
  if (value === 'public') return '공개';
  if (value === 'shared') return '공유됨';
  return value;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' }).format(date);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
