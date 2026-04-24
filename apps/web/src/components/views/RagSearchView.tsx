import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  CalendarDays,
  FileText,
  Filter,
  FolderKanban,
  Loader2,
  Search,
  Sparkles,
  Users,
} from 'lucide-react';

import { useAuth } from '@/src/domains/auth/auth-provider';
import type {
  RagGroundedCitation,
  RagQueryHit,
  RagQueryPayload,
  RagQueryResponse,
  RagSourceDescriptor,
} from '@/src/domains/rag/rag-api';
import {
  listWorkspaceRagSources,
  queryWorkspaceRag,
  RagApiError,
  RAG_QUERY_DEFAULT_TOP_K,
} from '@/src/domains/rag/rag-api';
import { useWorkspaceBootstrapContext } from '@/src/domains/workspaces/workspace-bootstrap-context';
import {
  buildWorkspaceAppPath,
  getWorkspaceBySlug,
  resolveShellWorkspaceSlug,
} from '@/src/domains/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';

const RAG_SEARCH_COPY = {
  placeholder: '문서, 회의, 이슈를 검색하거나 질문하세요',
  fallbackWorkspaceDescription: 'workspace 데이터를 근거 기반으로 검색합니다.',
  noWorkspace: '검색할 workspace를 찾을 수 없습니다. workspace를 먼저 선택한 뒤 다시 시도해주세요.',
  noToken: '인증 정보가 없어 통합검색을 사용할 수 없습니다.',
  emptyQuery: '검색어를 입력해주세요.',
  emptySources: '검색할 대상을 하나 이상 선택해주세요.',
  invalidUrlSources: '현재 URL의 검색 대상 설정이 이 workspace에서 유효하지 않습니다. 검색 대상을 다시 선택해주세요.',
  genericSearchError: '검색 결과를 불러오지 못했습니다.',
  sourceLoadError: '검색 대상 목록을 불러오지 못했습니다.',
  delayedTitle: '검색 서비스 응답 지연',
  delayedMessage: '검색 인덱스 또는 AI 응답이 지연되고 있습니다. 다시 시도하거나 검색 범위를 줄여보세요.',
  recommendationsTitle: '추천 질문',
  recentTitle: '최근 검색',
  sourcePreviewTitle: '검색 대상',
} as const;

const RECENT_SEARCHES_STORAGE_KEY = 'aidoo:rag-search:recent';
const MAX_RECENT_SEARCHES = 5;

const RECOMMENDED_QUERIES = [
  '최근 회의에서 나온 미해결 리스크를 요약해줘',
  '이번 주 PMS 이슈 중 지연 가능성이 높은 항목을 찾아줘',
  '구매 요청과 관련된 문서를 찾아줘',
] as const;

type AnswerMode = 'search-only' | 'grounded-answer';
type ResultFilter = 'all' | 'docs' | 'meeting' | 'pms' | 'planner';

type SearchErrorViewModel = {
  title: string;
  message: string;
  recoverable: boolean;
  canFallbackToSearchOnly: boolean;
  canReduceSources: boolean;
};

type UrlSearchState = {
  workspaceSlug: string | null;
  query: string;
  answerMode: AnswerMode;
  sourceKinds: string[];
};

const APP_BADGE_STYLES: Record<string, string> = {
  docs: 'bg-blue-50 text-blue-700 border-blue-200',
  meeting: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  pms: 'bg-amber-50 text-amber-700 border-amber-200',
  planner: 'bg-rose-50 text-rose-700 border-rose-200',
};

const APP_LABELS: Record<string, string> = {
  docs: '문서',
  meeting: '회의',
  pms: 'PMS',
  planner: '일정',
};

export function RagSearchView() {
  const { token, user, logout } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = useMemo(() => parseSearchParams(searchParams), [searchParams]);
  const requestedWorkspaceSlug = getWorkspaceBySlug(user, urlSearch.workspaceSlug)?.slug ?? null;
  const workspaceSlug = requestedWorkspaceSlug
    ?? workspaceBootstrap.data?.workspace.slug
    ?? resolveShellWorkspaceSlug(user, null);
  const workspaceName = workspaceBootstrap.data?.workspace.name
    ?? getWorkspaceBySlug(user, workspaceSlug)?.name
    ?? workspaceSlug
    ?? '';

  const [queryInput, setQueryInput] = useState(urlSearch.query);
  const [answerMode, setAnswerMode] = useState<AnswerMode>(urlSearch.answerMode);
  const [selectedSourceKinds, setSelectedSourceKinds] = useState<string[]>([]);
  const [sources, setSources] = useState<RagSourceDescriptor[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<SearchErrorViewModel | null>(null);
  const [response, setResponse] = useState<RagQueryResponse | null>(null);
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all');
  const [sourceFiltersOpen, setSourceFiltersOpen] = useState(false);
  const [recentSearches, setRecentSearches] = useState<string[]>(() => loadRecentSearches());
  const selectionInitializedRef = useRef(false);
  const activeSearchAbortRef = useRef<AbortController | null>(null);
  const activeSearchSequenceRef = useRef(0);
  const lastSearchKeyRef = useRef<string | null>(null);

  useEffect(() => {
    setQueryInput(urlSearch.query);
  }, [urlSearch.query]);

  useEffect(() => {
    setAnswerMode(urlSearch.answerMode);
  }, [urlSearch.answerMode]);

  const sourceLabelByKind = useMemo(
    () => new Map(sources.map((source) => [source.source_kind, source.label] as const)),
    [sources],
  );
  const hitByResourceId = useMemo(
    () => new Map((response?.hits ?? []).map((hit) => [hit.resource_id, hit] as const)),
    [response?.hits],
  );
  const groundedAnswerDegraded = response
    ? response.answer_mode === 'grounded-answer'
      && !response.grounded_answer
      && response.query_profile.grounded_answer_degraded === true
    : false;
  const resolvedUrlSourceKinds = useMemo(
    () => resolveSelectedSourceKinds(urlSearch.sourceKinds, sources),
    [sources, urlSearch.sourceKinds],
  );
  const resultFilterOptions = useMemo(
    () => buildResultFilterOptions(response?.hits ?? []),
    [response?.hits],
  );
  const visibleHits = useMemo(
    () => filterHitsByResultFilter(response?.hits ?? [], resultFilter),
    [response?.hits, resultFilter],
  );
  const selectedSourceLabels = useMemo(
    () => summarizeSelectedSources(sources, selectedSourceKinds),
    [selectedSourceKinds, sources],
  );

  const runSearch = useCallback(async (options?: {
    query?: string;
    answerMode?: AnswerMode;
    selectedSourceKinds?: string[];
    syncUrl?: boolean;
  }) => {
    const resolvedToken = token;
    if (!resolvedToken) {
      setSearchError(buildInlineSearchError(RAG_SEARCH_COPY.noToken));
      return;
    }
    const resolvedWorkspaceSlug = workspaceSlug;
    if (!resolvedWorkspaceSlug) {
      setSearchError(buildInlineSearchError('검색할 workspace를 찾을 수 없습니다.'));
      return;
    }
    const nextQuery = options?.query?.trim() ?? queryInput.trim();
    const nextAnswerMode = options?.answerMode ?? answerMode;
    const nextSelectedSourceKinds = options?.selectedSourceKinds ?? selectedSourceKinds;

    if (!nextQuery) {
      setSearchError(buildInlineSearchError(RAG_SEARCH_COPY.emptyQuery));
      return;
    }
    if (nextSelectedSourceKinds.length === 0) {
      setSearchError(buildInlineSearchError(RAG_SEARCH_COPY.emptySources));
      return;
    }

    const payload: RagQueryPayload = {
      query: nextQuery,
      answer_mode: nextAnswerMode,
      source_kinds: nextSelectedSourceKinds,
      top_k: RAG_QUERY_DEFAULT_TOP_K,
      filters: {},
    };
    const searchKey = buildSearchRequestKey(
      resolvedWorkspaceSlug,
      nextQuery,
      nextAnswerMode,
      nextSelectedSourceKinds,
    );
    const requestSequence = activeSearchSequenceRef.current + 1;
    activeSearchSequenceRef.current = requestSequence;
    lastSearchKeyRef.current = searchKey;
    activeSearchAbortRef.current?.abort();
    const controller = new AbortController();
    activeSearchAbortRef.current = controller;

    setSearching(true);
    setSearchError(null);

    try {
      const nextResponse = await queryWorkspaceRag(
        payload,
        resolvedToken,
        resolvedWorkspaceSlug,
        { signal: controller.signal },
      );
      if (controller.signal.aborted || activeSearchSequenceRef.current !== requestSequence) {
        return;
      }
      setResponse(nextResponse);
      setResultFilter('all');
      setRecentSearches(saveRecentSearch(nextQuery));
      if (options?.syncUrl !== false) {
        setSearchParams(
          buildSearchParams({
            workspaceSlug: resolvedWorkspaceSlug,
            query: nextQuery,
            answerMode: nextAnswerMode,
            selectedSourceKinds: nextSelectedSourceKinds,
          }),
          { replace: true },
        );
      }
    } catch (error: unknown) {
      if (controller.signal.aborted || isAbortError(error)) {
        return;
      }
      if (activeSearchSequenceRef.current !== requestSequence) {
        return;
      }
      if (error instanceof RagApiError && error.status === 401) {
        setSearchError('세션이 만료되었습니다. 다시 로그인해주세요.');
        void logout();
        return;
      }
      setSearchError(
        mapSearchError(error),
      );
    } finally {
      if (activeSearchSequenceRef.current === requestSequence) {
        setSearching(false);
      }
    }
  }, [
    answerMode,
    logout,
    queryInput,
    selectedSourceKinds,
    setSearchParams,
    token,
    workspaceSlug,
  ]);

  useEffect(() => {
    selectionInitializedRef.current = false;
    activeSearchAbortRef.current?.abort();
    activeSearchAbortRef.current = null;
    setSelectedSourceKinds([]);
    setResponse(null);
    setSearchError(null);
    setSourcesError(null);
    setSearching(false);
    lastSearchKeyRef.current = null;
  }, [workspaceSlug]);

  useEffect(() => {
    if (!token || !workspaceSlug) {
      setSources([]);
      setSourcesError(null);
      setSourcesLoading(false);
      return;
    }

    const controller = new AbortController();
    setSourcesLoading(true);
    setSourcesError(null);

    listWorkspaceRagSources(token, workspaceSlug, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) {
          return;
        }
        setSources(result.sources);
        selectionInitializedRef.current = true;
        setSelectedSourceKinds(resolveSelectedSourceKinds(urlSearch.sourceKinds, result.sources));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) {
          return;
        }
        setSources([]);
        setSourcesError(
          error instanceof Error
            ? error.message
            : RAG_SEARCH_COPY.sourceLoadError,
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSourcesLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [token, workspaceSlug]);

  useEffect(() => {
    if (!selectionInitializedRef.current) {
      return;
    }
    const nextSelection = resolveSelectedSourceKinds(urlSearch.sourceKinds, sources);
    setSelectedSourceKinds((current) => (
      sameStringArray(current, nextSelection) ? current : nextSelection
    ));
  }, [sources, urlSearch.sourceKinds]);

  useEffect(() => {
    if (!token || !workspaceSlug || !selectionInitializedRef.current) {
      return;
    }
    if (!urlSearch.query) {
      setResponse(null);
      setSearchError(null);
      lastSearchKeyRef.current = null;
      return;
    }
    if (resolvedUrlSourceKinds.length === 0) {
      setResponse(null);
      setSearchError(buildInlineSearchError(RAG_SEARCH_COPY.invalidUrlSources));
      lastSearchKeyRef.current = buildSearchRequestKey(
        workspaceSlug,
        urlSearch.query,
        urlSearch.answerMode,
        resolvedUrlSourceKinds,
      );
      return;
    }
    const nextSearchKey = buildSearchRequestKey(
      workspaceSlug,
      urlSearch.query,
      urlSearch.answerMode,
      resolvedUrlSourceKinds,
    );
    if (lastSearchKeyRef.current === nextSearchKey) {
      return;
    }
    void runSearch({
      query: urlSearch.query,
      answerMode: urlSearch.answerMode,
      selectedSourceKinds: resolvedUrlSourceKinds,
      syncUrl: false,
    });
  }, [
    resolvedUrlSourceKinds,
    runSearch,
    token,
    urlSearch.answerMode,
    urlSearch.query,
    workspaceSlug,
  ]);

  useEffect(() => (
    () => {
      activeSearchAbortRef.current?.abort();
    }
  ), []);

  if (!token) {
    return (
      <div className="p-8 text-app-ink/60">
        {RAG_SEARCH_COPY.noToken}
      </div>
    );
  }

  if (!workspaceSlug) {
    return (
      <div className="p-8 text-app-ink/60">
        {RAG_SEARCH_COPY.noWorkspace}
      </div>
    );
  }

  const toggleSourceKind = (sourceKind: string) => {
    setSelectedSourceKinds((current) => (
      current.includes(sourceKind)
        ? current.filter((item) => item !== sourceKind)
        : [...current, sourceKind]
    ));
  };

  const runPresetSearch = (query: string) => {
    setQueryInput(query);
    void runSearch({ query, syncUrl: true });
  };

  const retryCurrentSearch = () => {
    void runSearch({ syncUrl: true });
  };

  const retrySearchOnly = () => {
    setAnswerMode('search-only');
    void runSearch({ answerMode: 'search-only', syncUrl: true });
  };

  const reduceSourcesAndRetry = () => {
    const primarySource = selectedSourceKinds[0] ?? sources[0]?.source_kind;
    if (!primarySource) {
      return;
    }
    setSelectedSourceKinds([primarySource]);
    void runSearch({ selectedSourceKinds: [primarySource], syncUrl: true });
  };

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="border-b border-app-border bg-app-surface px-6 py-5">
        <div className="mx-auto flex max-w-6xl flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2.5 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-app-ink/55">
                <Sparkles size={13} />
                업무 통합검색
              </div>
              <div>
                <h1 className="app-text-title-lg text-app-ink">아이두 통합검색</h1>
                <p className="app-text-body mt-1 text-app-ink/60">
                  {workspaceName
                    ? `${workspaceName}의 접근 가능한 업무 데이터를 근거 기반으로 검색합니다.`
                    : RAG_SEARCH_COPY.fallbackWorkspaceDescription}
                </p>
              </div>
            </div>
          </div>

          <form
            className="rounded-lg border border-app-border bg-app-surface-sidebar p-4"
            onSubmit={(event) => {
              event.preventDefault();
              void runSearch({ syncUrl: true });
            }}
          >
            <div className="flex flex-col gap-3">
              <label className="app-text-control-sm text-app-ink/60" htmlFor="rag-search-query">
                질문 또는 검색어
              </label>
              <div className="relative">
                <Search
                  size={16}
                  className="pointer-events-none absolute left-4 top-4 text-app-ink/35"
                />
                <textarea
                  id="rag-search-query"
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  rows={1}
                  className="app-text-body min-h-11 w-full resize-y rounded-lg border border-app-border bg-app-bg px-11 py-3 text-app-ink outline-none transition-colors focus:border-app-accent"
                  placeholder={RAG_SEARCH_COPY.placeholder}
                />
              </div>

              <div className="flex flex-wrap items-center gap-2" aria-label={RAG_SEARCH_COPY.sourcePreviewTitle}>
                {sourcesLoading ? (
                  <span className="inline-flex items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 py-1.5 text-[0.8rem] text-app-ink/55">
                    <Loader2 size={13} className="animate-spin" />
                    검색 대상 확인 중
                  </span>
                ) : sources.map((source) => {
                  const checked = selectedSourceKinds.includes(source.source_kind);
                  return (
                    <button
                      key={source.source_kind}
                      type="button"
                      onClick={() => toggleSourceKind(source.source_kind)}
                      className={cn(
                        'inline-flex min-h-8 items-center gap-1.5 rounded-md border px-3 py-1.5 text-[0.8rem] font-medium transition-colors',
                        checked
                          ? 'border-app-accent bg-app-accent/10 text-app-accent'
                          : 'border-app-border bg-app-bg text-app-ink/65 hover:bg-app-surface',
                      )}
                    >
                      {renderAppIcon(source.app_id)}
                      <span>{formatSourceLabel(source)}</span>
                    </button>
                  );
                })}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <label className="inline-flex min-h-9 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 py-1.5 text-[0.82rem] font-medium text-app-ink/70">
                  <input
                    type="checkbox"
                    checked={answerMode === 'grounded-answer'}
                    onChange={(event) => setAnswerMode(event.target.checked ? 'grounded-answer' : 'search-only')}
                    className="h-4 w-4 rounded border-app-border text-app-accent focus:ring-app-accent"
                  />
                  <span>답변 포함</span>
                </label>
                <span className="text-[0.78rem] text-app-ink/45">
                  {selectedSourceLabels}
                </span>
                <button
                  type="submit"
                  disabled={searching || sourcesLoading}
                  className="ml-auto inline-flex items-center gap-2 rounded-lg bg-app-accent px-4 py-2 text-[0.9rem] font-semibold text-app-accent-fg transition-opacity hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {searching ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                  <span>{searching ? '검색 중' : '검색'}</span>
                </button>
              </div>
            </div>
          </form>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 overflow-y-auto px-6 py-6 xl:flex-row xl:overflow-hidden">
        <section className="min-w-0 flex-1 overflow-visible xl:overflow-y-auto">
          {searchError ? (
            <SearchErrorPanel
              error={searchError}
              onReduceSources={searchError.canReduceSources ? reduceSourcesAndRetry : undefined}
              onRetry={searchError.recoverable ? retryCurrentSearch : undefined}
              onSearchOnly={searchError.canFallbackToSearchOnly ? retrySearchOnly : undefined}
            />
          ) : null}

          {groundedAnswerDegraded ? (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[0.9rem] text-amber-800">
              근거 답변 생성에 실패해 검색 결과만 표시합니다. 인용과 원문 링크를 확인해주세요.
            </div>
          ) : null}

          {response?.grounded_answer ? (
            <article className="mb-5 rounded-lg border border-app-border bg-app-surface p-5">
              <div className="mb-3 flex items-center gap-2 text-[0.74rem] font-semibold uppercase tracking-[0.08em] text-app-ink/50">
                <Sparkles size={13} />
                근거 답변
              </div>
              <p className="app-text-body whitespace-pre-wrap leading-7 text-app-ink">
                {response.grounded_answer.text}
              </p>
              {response.grounded_answer.citations.length > 0 ? (
                <div className="mt-4 grid gap-3">
                  {response.grounded_answer.citations.map((citation, index) => (
                    <CitationCard
                      key={`${citation.resource_id}:${citation.locator ?? 'none'}:${index}`}
                      citation={citation}
                      sourceLabel={sourceLabelByKind.get(citation.source_kind) ?? citation.source_kind}
                      href={buildResultHref(workspaceSlug, hitByResourceId.get(citation.resource_id), citation)}
                    />
                  ))}
                </div>
              ) : null}
              {response.grounded_answer.unsupported_claims.length > 0 ? (
                <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-[0.84rem] text-amber-800">
                  <div className="font-semibold">검증 보류 주장</div>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {response.grounded_answer.unsupported_claims.map((claim, index) => (
                      <li key={`${claim}:${index}`}>{claim}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </article>
          ) : null}

          <div className="flex items-center justify-between pb-3">
            <div>
              <h2 className="app-text-title-md text-app-ink">검색 결과</h2>
              <p
                className="app-text-caption mt-1 text-app-ink/55"
                role="status"
                aria-live="polite"
              >
                {response
                  ? `${visibleHits.length}건 · ${response.sources_used.length}개 검색 대상`
                  : '질문을 입력하면 접근 가능한 문서, 회의, PMS, 일정에서 결과를 찾습니다.'}
              </p>
            </div>
          </div>

          {!response && !searching ? (
            <SearchStartPanel
              recentSearches={recentSearches}
              sources={sources}
              onRunQuery={runPresetSearch}
            />
          ) : null}

          {response ? (
            <ResultFilterChips
              activeFilter={resultFilter}
              options={resultFilterOptions}
              onChange={setResultFilter}
            />
          ) : null}

          {searching && !response ? (
            <div
              className="flex h-48 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-ink/55"
              role="status"
              aria-live="polite"
            >
              <Loader2 size={18} className="animate-spin" />
              <span className="ml-2">검색 중</span>
            </div>
          ) : null}

          {!searching && response && visibleHits.length === 0 ? (
            <div className="rounded-lg border border-dashed border-app-border bg-app-surface p-8 text-center text-app-ink/60">
              현재 조건에서 접근 가능한 결과를 찾지 못했습니다.
            </div>
          ) : null}

          <div className="grid gap-3">
            {visibleHits.map((hit, index) => (
              <SearchHitCard
                key={`${hit.resource_id}:${hit.citation ?? 'none'}:${index}`}
                hit={hit}
                href={buildResultHref(workspaceSlug, hit)}
                sourceLabel={sourceLabelByKind.get(hit.source_kind) ?? hit.source_kind}
              />
            ))}
          </div>
        </section>

        <section className="xl:hidden">
          <button
            type="button"
            onClick={() => setSourceFiltersOpen((open) => !open)}
            className="flex w-full items-center justify-between rounded-lg border border-app-border bg-app-surface px-4 py-3 text-left text-app-ink"
            aria-expanded={sourceFiltersOpen}
          >
            <span className="inline-flex items-center gap-2 app-text-control-sm">
              <Filter size={15} />
              상세 검색 대상
            </span>
            <span className="text-[0.78rem] text-app-ink/55">{selectedSourceLabels}</span>
          </button>
          {sourceFiltersOpen ? (
            <div className="mt-3">
              <SourceFilterPanel
                sources={sources}
                selectedSourceKinds={selectedSourceKinds}
                sourcesLoading={sourcesLoading}
                sourcesError={sourcesError}
                onSelectAll={() => setSelectedSourceKinds(sources.map((source) => source.source_kind))}
                onClear={() => setSelectedSourceKinds([])}
                onToggle={toggleSourceKind}
              />
            </div>
          ) : null}
        </section>

        <aside className="w-full shrink-0 space-y-4 xl:w-80 xl:overflow-y-auto">
          <div className="hidden xl:block">
            <SourceFilterPanel
              sources={sources}
              selectedSourceKinds={selectedSourceKinds}
              sourcesLoading={sourcesLoading}
              sourcesError={sourcesError}
              onSelectAll={() => setSelectedSourceKinds(sources.map((source) => source.source_kind))}
              onClear={() => setSelectedSourceKinds([])}
              onToggle={toggleSourceKind}
            />
          </div>

          <section className="rounded-lg border border-app-border bg-app-surface p-4">
            <h2 className="app-text-title-md mb-3 text-app-ink">결과 요약</h2>
            {response ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-[0.82rem] text-app-ink/65">
                <dt>반환 건수</dt>
                <dd>{response.hits.length}</dd>
                <dt>검색 대상</dt>
                <dd>{response.sources_used.join(', ') || '-'}</dd>
              </dl>
            ) : (
              <p className="app-text-caption text-app-ink/55">
                검색을 실행하면 결과 수와 사용된 검색 대상을 확인할 수 있습니다.
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}

function SearchStartPanel({
  recentSearches,
  sources,
  onRunQuery,
}: {
  recentSearches: string[];
  sources: RagSourceDescriptor[];
  onRunQuery: (query: string) => void;
}) {
  return (
    <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_0.8fr]">
      <section className="rounded-lg border border-app-border bg-app-surface p-4">
        <h2 className="app-text-title-md text-app-ink">{RAG_SEARCH_COPY.recommendationsTitle}</h2>
        <div className="mt-3 grid gap-2">
          {RECOMMENDED_QUERIES.map((query) => (
            <button
              key={query}
              type="button"
              onClick={() => onRunQuery(query)}
              className="flex min-h-10 w-full items-center justify-between rounded-lg border border-app-border px-3 py-2 text-left text-[0.88rem] text-app-ink transition-colors hover:border-app-accent hover:bg-app-surface-sidebar"
            >
              <span>{query}</span>
              <ArrowUpRight size={14} className="shrink-0 text-app-ink/40" />
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-app-border bg-app-surface p-4">
        <h2 className="app-text-title-md text-app-ink">{RAG_SEARCH_COPY.recentTitle}</h2>
        {recentSearches.length > 0 ? (
          <div className="mt-3 grid gap-2">
            {recentSearches.map((query) => (
              <button
                key={query}
                type="button"
                onClick={() => onRunQuery(query)}
                className="min-h-9 truncate rounded-lg border border-app-border px-3 py-2 text-left text-[0.84rem] text-app-ink/70 transition-colors hover:border-app-accent"
              >
                {query}
              </button>
            ))}
          </div>
        ) : (
          <p className="app-text-caption mt-3 text-app-ink/55">
            검색을 실행하면 이 workspace의 최근 검색어가 여기에 표시됩니다.
          </p>
        )}
        <div className="mt-4 border-t border-app-border pt-3">
          <div className="app-text-caption text-app-ink/55">{RAG_SEARCH_COPY.sourcePreviewTitle}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(countSourcesByApp(sources)).map(([appId, count]) => (
              <span
                key={appId}
                className="inline-flex items-center gap-1.5 rounded-md border border-app-border px-2 py-1 text-[0.76rem] text-app-ink/60"
              >
                {renderAppIcon(appId)}
                {getAppLabel(appId)} {count}
              </span>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function ResultFilterChips({
  activeFilter,
  options,
  onChange,
}: {
  activeFilter: ResultFilter;
  options: { id: ResultFilter; label: string; count: number }[];
  onChange: (filter: ResultFilter) => void;
}) {
  return (
    <div className="mb-4 flex flex-wrap gap-2" aria-label="결과 유형">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          className={cn(
            'min-h-8 rounded-md border px-3 py-1.5 text-[0.8rem] font-medium transition-colors',
            activeFilter === option.id
              ? 'border-app-accent bg-app-accent text-app-accent-fg'
              : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-sidebar',
          )}
        >
          {option.label} {option.count}
        </button>
      ))}
    </div>
  );
}

function SourceFilterPanel({
  sources,
  selectedSourceKinds,
  sourcesLoading,
  sourcesError,
  onSelectAll,
  onClear,
  onToggle,
}: {
  sources: RagSourceDescriptor[];
  selectedSourceKinds: string[];
  sourcesLoading: boolean;
  sourcesError: string | null;
  onSelectAll: () => void;
  onClear: () => void;
  onToggle: (sourceKind: string) => void;
}) {
  return (
    <fieldset className="rounded-lg border border-app-border bg-app-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <legend className="app-text-title-md text-app-ink">{RAG_SEARCH_COPY.sourcePreviewTitle}</legend>
        <div className="flex items-center gap-3 text-[0.78rem] font-medium">
          <button type="button" onClick={onSelectAll} className="text-app-accent">
            전체 선택
          </button>
          <button type="button" onClick={onClear} className="text-app-ink/55">
            전체 해제
          </button>
        </div>
      </div>
      {sourcesLoading ? (
        <div className="flex items-center gap-2 text-app-ink/55" role="status" aria-live="polite">
          <Loader2 size={14} className="animate-spin" />
          <span className="app-text-caption">검색 대상 확인 중</span>
        </div>
      ) : sourcesError ? (
        <InlineError message={sourcesError} compact />
      ) : sources.length === 0 ? (
        <div className="rounded-lg border border-dashed border-app-border px-3 py-4 text-[0.82rem] text-app-ink/55">
          현재 접근 가능한 검색 대상이 없습니다.
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map((source) => {
            const checked = selectedSourceKinds.includes(source.source_kind);
            return (
              <label
                key={source.source_kind}
                className="flex cursor-pointer items-start gap-3 rounded-lg border border-app-border px-3 py-3 hover:bg-app-surface-sidebar"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(source.source_kind)}
                  className="mt-0.5 h-4 w-4 rounded border-app-border text-app-accent focus:ring-app-accent"
                />
                <div className="min-w-0">
                  <div className="app-text-control-sm text-app-ink">{formatSourceLabel(source)}</div>
                  <div className="mt-1 flex items-center gap-2 text-[0.74rem] text-app-ink/45">
                    <AppBadge appId={source.app_id} />
                    <span>{source.label}</span>
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      )}
      {!sourcesLoading && !sourcesError && selectedSourceKinds.length === 0 ? (
        <p className="mt-3 text-[0.8rem] text-amber-700">
          검색을 실행하려면 대상을 하나 이상 선택해주세요.
        </p>
      ) : null}
    </fieldset>
  );
}

function SearchErrorPanel({
  error,
  onRetry,
  onSearchOnly,
  onReduceSources,
}: {
  error: SearchErrorViewModel;
  onRetry?: () => void;
  onSearchOnly?: () => void;
  onReduceSources?: () => void;
}) {
  return (
    <div
      className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-800"
      role="alert"
      aria-live="assertive"
    >
      <div className="font-semibold">{error.title}</div>
      <p className="mt-1 text-[0.9rem]">{error.message}</p>
      {onRetry || onSearchOnly || onReduceSources ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {onRetry ? <ErrorActionButton onClick={onRetry} label="다시 시도" /> : null}
          {onSearchOnly ? <ErrorActionButton onClick={onSearchOnly} label="검색 결과만 보기" /> : null}
          {onReduceSources ? <ErrorActionButton onClick={onReduceSources} label="검색 대상 줄이기" /> : null}
        </div>
      ) : null}
    </div>
  );
}

function ErrorActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="min-h-8 rounded-md border border-red-200 bg-white px-3 py-1.5 text-[0.8rem] font-medium text-red-800 transition-colors hover:bg-red-100"
    >
      {label}
    </button>
  );
}

function SearchHitCard({
  hit,
  href,
  sourceLabel,
}: {
  hit: RagQueryHit;
  href: string | null;
  sourceLabel: string;
}) {
  return (
    <article className="rounded-lg border border-app-border bg-app-surface p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <AppBadge appId={inferAppId(hit)} />
            <span className="text-[0.78rem] font-medium text-app-ink/55">{sourceLabel}</span>
          </div>
          <h3 className="app-text-title-md text-app-ink">
            {hit.title || `${sourceLabel} 결과`}
          </h3>
          {hit.summary ? (
            <p className="app-text-body mt-2 whitespace-pre-wrap text-app-ink/68">
              {hit.summary}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-[0.8rem] text-app-ink/55">
        {hit.owner_label ? <span>담당 {hit.owner_label}</span> : null}
        {hit.citation ? <span>인용 {hit.citation}</span> : null}
        {hit.origin_ref ? <span>원본 {hit.origin_ref}</span> : null}
        {href ? (
          <Link
            to={href}
            className="inline-flex items-center gap-1 font-medium text-app-accent"
          >
            <span>원문 열기</span>
            <ArrowUpRight size={13} />
          </Link>
        ) : (
          <span className="font-medium text-app-ink/40">원문 미지원</span>
        )}
      </div>
    </article>
  );
}

function CitationCard({
  citation,
  sourceLabel,
  href,
}: {
  citation: RagGroundedCitation;
  sourceLabel: string;
  href: string | null;
}) {
  return (
    <div className="rounded-lg border border-app-border bg-app-surface-sidebar p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[0.76rem] font-semibold uppercase tracking-[0.08em] text-app-ink/40">
          {sourceLabel}
        </span>
        {citation.locator ? (
          <span className="text-[0.76rem] text-app-ink/45">{citation.locator}</span>
        ) : null}
      </div>
      <p className="app-text-body text-app-ink/68">“{citation.quote}”</p>
      {href ? (
        <Link
          to={href}
          className="mt-3 inline-flex items-center gap-1 text-[0.82rem] font-medium text-app-accent"
        >
          <span>근거 문서 열기</span>
          <ArrowUpRight size={13} />
        </Link>
      ) : null}
    </div>
  );
}

function AppBadge({ appId }: { appId: string }) {
  const label = appId ? appId.toUpperCase() : 'RAG';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.72rem] font-semibold',
        APP_BADGE_STYLES[appId] ?? 'bg-app-surface-sidebar text-app-ink/65 border-app-border',
      )}
    >
      {renderAppIcon(appId)}
      <span>{label}</span>
    </span>
  );
}

function InlineError({
  message,
  compact = false,
}: {
  message: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border border-red-200 bg-red-50 text-red-700',
        compact ? 'px-3 py-2 text-[0.8rem]' : 'mb-4 px-4 py-3 text-[0.9rem]',
      )}
    >
      {message}
    </div>
  );
}

function buildInlineSearchError(message: string): SearchErrorViewModel {
  return {
    title: '검색할 수 없습니다',
    message,
    recoverable: false,
    canFallbackToSearchOnly: false,
    canReduceSources: false,
  };
}

function mapSearchError(error: unknown): SearchErrorViewModel {
  if (error instanceof RagApiError && error.status === 503) {
    return {
      title: RAG_SEARCH_COPY.delayedTitle,
      message: RAG_SEARCH_COPY.delayedMessage,
      recoverable: true,
      canFallbackToSearchOnly: true,
      canReduceSources: true,
    };
  }
  return {
    title: '검색 실패',
    message: error instanceof Error ? error.message : RAG_SEARCH_COPY.genericSearchError,
    recoverable: true,
    canFallbackToSearchOnly: false,
    canReduceSources: false,
  };
}

function loadRecentSearches(): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(RECENT_SEARCHES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === 'string').slice(0, MAX_RECENT_SEARCHES)
      : [];
  } catch {
    return [];
  }
}

function saveRecentSearch(query: string): string[] {
  const trimmed = query.trim();
  if (!trimmed) {
    return loadRecentSearches();
  }
  const next = [
    trimmed,
    ...loadRecentSearches().filter((item) => item !== trimmed),
  ].slice(0, MAX_RECENT_SEARCHES);
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(RECENT_SEARCHES_STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Ignore storage quota or privacy-mode failures; recent searches are optional.
    }
  }
  return next;
}

function getAppLabel(appId: string): string {
  return APP_LABELS[appId] ?? '기타';
}

function formatSourceLabel(source: Pick<RagSourceDescriptor, 'app_id' | 'label'>): string {
  return getAppLabel(source.app_id);
}

function summarizeSelectedSources(
  sources: RagSourceDescriptor[],
  selectedSourceKinds: string[],
): string {
  if (sources.length === 0) {
    return '검색 대상 없음';
  }
  if (selectedSourceKinds.length === sources.length) {
    return '전체 검색 대상';
  }
  if (selectedSourceKinds.length === 0) {
    return '선택된 검색 대상 없음';
  }
  return `${selectedSourceKinds.length}개 검색 대상`;
}

function countSourcesByApp(sources: RagSourceDescriptor[]): Record<string, number> {
  return sources.reduce<Record<string, number>>((counts, source) => {
    counts[source.app_id] = (counts[source.app_id] ?? 0) + 1;
    return counts;
  }, {});
}

function buildResultFilterOptions(hits: RagQueryHit[]) {
  const counts = hits.reduce<Record<ResultFilter, number>>(
    (nextCounts, hit) => {
      const appId = inferAppId(hit) as ResultFilter;
      nextCounts.all += 1;
      if (appId in nextCounts) {
        nextCounts[appId] += 1;
      }
      return nextCounts;
    },
    { all: 0, docs: 0, meeting: 0, pms: 0, planner: 0 },
  );
  return [
    { id: 'all' as const, label: '전체', count: counts.all },
    { id: 'docs' as const, label: '문서', count: counts.docs },
    { id: 'meeting' as const, label: '회의', count: counts.meeting },
    { id: 'pms' as const, label: 'PMS', count: counts.pms },
    { id: 'planner' as const, label: '일정', count: counts.planner },
  ].filter((option) => option.id === 'all' || option.count > 0);
}

function filterHitsByResultFilter(hits: RagQueryHit[], resultFilter: ResultFilter): RagQueryHit[] {
  if (resultFilter === 'all') {
    return hits;
  }
  return hits.filter((hit) => inferAppId(hit) === resultFilter);
}

function normalizeAnswerMode(value: string | null): AnswerMode {
  return value === 'search-only' ? 'search-only' : 'grounded-answer';
}

function parseSearchParams(searchParams: URLSearchParams): UrlSearchState {
  return {
    workspaceSlug: searchParams.get('workspace')?.trim() || null,
    query: searchParams.get('q')?.trim() || '',
    answerMode: normalizeAnswerMode(searchParams.get('mode')),
    sourceKinds: uniqueStrings(searchParams.getAll('source')),
  };
}

function buildSearchParams({
  workspaceSlug,
  query,
  answerMode,
  selectedSourceKinds,
}: {
  workspaceSlug: string;
  query: string;
  answerMode: AnswerMode;
  selectedSourceKinds: string[];
}) {
  const params = new URLSearchParams();
  params.set('workspace', workspaceSlug);
  params.set('q', query);
  params.set('mode', answerMode);
  for (const sourceKind of selectedSourceKinds) {
    params.append('source', sourceKind);
  }
  return params;
}

function buildSearchRequestKey(
  workspaceSlug: string,
  query: string,
  answerMode: AnswerMode,
  sourceKinds: string[],
) {
  return [
    workspaceSlug,
    query,
    answerMode,
    [...sourceKinds].sort().join(','),
  ].join('::');
}

function uniqueStrings(items: string[]) {
  return [...new Set(items.filter(Boolean))];
}

function resolveSelectedSourceKinds(
  requestedSourceKinds: string[],
  availableSources: RagSourceDescriptor[],
) {
  const allowedSourceKinds = new Set(availableSources.map((item) => item.source_kind));
  if (requestedSourceKinds.length > 0) {
    return uniqueStrings(
      requestedSourceKinds.filter((sourceKind) => allowedSourceKinds.has(sourceKind)),
    );
  }
  return availableSources.map((item) => item.source_kind);
}

function sameStringArray(left: string[], right: string[]) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((item, index) => item === right[index]);
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
}

function inferAppId(hit: Pick<RagQueryHit, 'resource_type' | 'source_kind'>): string {
  if (hit.resource_type === 'docs_native_doc') {
    return 'docs';
  }
  if (hit.resource_type === 'meeting') {
    return 'meeting';
  }
  if (hit.resource_type === 'pms_issue') {
    return 'pms';
  }
  if (hit.resource_type === 'planner_event') {
    return 'planner';
  }
  if (hit.source_kind === 'meeting') {
    return 'meeting';
  }
  return '';
}

function renderAppIcon(appId: string) {
  if (appId === 'docs') {
    return <FileText size={12} />;
  }
  if (appId === 'meeting') {
    return <Users size={12} />;
  }
  if (appId === 'pms') {
    return <FolderKanban size={12} />;
  }
  if (appId === 'planner') {
    return <CalendarDays size={12} />;
  }
  return <Sparkles size={12} />;
}

function buildResultHref(
  workspaceSlug: string,
  hit?: Pick<RagQueryHit, 'resource_type' | 'resource_id' | 'metadata'> | null,
  citation?: RagGroundedCitation,
): string | null {
  const resourceType = hit?.resource_type
    ?? resourceTypeForSourceKind(citation?.source_kind ?? null);
  const resourceId = hit?.resource_id ?? citation?.resource_id ?? null;
  if (!resourceType || !resourceId) {
    return null;
  }
  if (resourceType === 'docs_native_doc') {
    return buildWorkspaceAppPath(workspaceSlug, 'docs', `/${resourceId}`);
  }
  if (resourceType === 'meeting') {
    return buildWorkspaceAppPath(workspaceSlug, 'meeting', `/${resourceId}`);
  }
  if (resourceType === 'pms_issue') {
    const listId = typeof hit?.metadata?.list_id === 'string' ? hit.metadata.list_id : null;
    const query = new URLSearchParams({
      workspace: workspaceSlug,
      issue: resourceId,
    });
    return listId
      ? `/tool/pms-list-${encodeURIComponent(listId)}?${query.toString()}`
      : buildWorkspaceAppPath(workspaceSlug, 'pms', `?issue=${encodeURIComponent(resourceId)}`);
  }
  if (resourceType === 'planner_event') {
    return buildWorkspaceAppPath(workspaceSlug, 'planner', `?event=${encodeURIComponent(resourceId)}`);
  }
  return null;
}

function resourceTypeForSourceKind(sourceKind: string | null): string | null {
  if (sourceKind === 'meeting') {
    return 'meeting';
  }
  if (sourceKind === 'pms_issue') {
    return 'pms_issue';
  }
  if (sourceKind === 'planner_event') {
    return 'planner_event';
  }
  if (sourceKind) {
    return 'docs_native_doc';
  }
  return null;
}
