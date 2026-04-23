import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  CalendarDays,
  FileText,
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

const DEFAULT_QUERY_PLACEHOLDER = '최근 회의와 PMS 이슈를 기준으로 현재 진행 리스크를 요약해줘';

type AnswerMode = 'search-only' | 'grounded-answer';

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
  const [searchError, setSearchError] = useState<string | null>(null);
  const [response, setResponse] = useState<RagQueryResponse | null>(null);
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
  const resolvedUrlSourceKinds = useMemo(
    () => resolveSelectedSourceKinds(urlSearch.sourceKinds, sources),
    [sources, urlSearch.sourceKinds],
  );

  const runSearch = useCallback(async (options?: {
    query?: string;
    answerMode?: AnswerMode;
    selectedSourceKinds?: string[];
    syncUrl?: boolean;
  }) => {
    const resolvedToken = token;
    if (!resolvedToken) {
      setSearchError('인증 정보가 없어 통합검색을 사용할 수 없습니다.');
      return;
    }
    const resolvedWorkspaceSlug = workspaceSlug;
    if (!resolvedWorkspaceSlug) {
      setSearchError('검색할 workspace를 찾을 수 없습니다.');
      return;
    }
    const nextQuery = options?.query?.trim() ?? queryInput.trim();
    const nextAnswerMode = options?.answerMode ?? answerMode;
    const nextSelectedSourceKinds = options?.selectedSourceKinds ?? selectedSourceKinds;

    if (!nextQuery) {
      setSearchError('검색어를 입력해주세요.');
      return;
    }
    if (nextSelectedSourceKinds.length === 0) {
      setSearchError('검색할 source를 하나 이상 선택해주세요.');
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
        error instanceof Error
          ? error.message
          : '검색 결과를 불러오지 못했습니다.',
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
            : '검색 source 목록을 불러오지 못했습니다.',
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
      setSearchError('현재 URL의 source 설정이 이 workspace에서 유효하지 않습니다. source를 다시 선택해주세요.');
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
        인증 정보가 없어 통합검색을 사용할 수 없습니다.
      </div>
    );
  }

  if (!workspaceSlug) {
    return (
      <div className="p-8 text-app-ink/60">
        검색할 workspace를 찾을 수 없습니다. workspace를 먼저 선택한 뒤 다시 시도해주세요.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="border-b border-app-border bg-app-surface px-6 py-5">
        <div className="mx-auto flex max-w-6xl flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-full border border-app-border bg-app-surface-sidebar px-3 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-app-ink/55">
                <Sparkles size={13} />
                Workspace RAG
              </div>
              <div>
                <h1 className="app-text-title-lg text-app-ink">아이두 통합검색</h1>
                <p className="app-text-body mt-1 text-app-ink/60">
                  {workspaceName
                    ? `${workspaceName}의 접근 가능한 업무 데이터를 근거 기반으로 검색합니다.`
                    : 'workspace 데이터를 근거 기반으로 검색합니다.'}
                </p>
              </div>
            </div>
            <div className="grid min-w-[220px] grid-cols-2 gap-2">
              <MetricCard label="표시 가능 Source" value={String(sources.length)} />
              <MetricCard label="응답 시간" value={response ? `${response.latency_ms}ms` : '-'} />
            </div>
          </div>

          <form
            className="rounded-2xl border border-app-border bg-app-surface-sidebar p-4"
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
                  rows={3}
                  className="app-text-body w-full resize-y rounded-2xl border border-app-border bg-app-bg px-11 py-3 text-app-ink outline-none transition-colors focus:border-app-accent"
                  placeholder={DEFAULT_QUERY_PLACEHOLDER}
                />
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <ModeButton
                  active={answerMode === 'grounded-answer'}
                  onClick={() => setAnswerMode('grounded-answer')}
                  label="근거 답변"
                />
                <ModeButton
                  active={answerMode === 'search-only'}
                  onClick={() => setAnswerMode('search-only')}
                  label="검색 결과만"
                />
                <div className="ml-auto inline-flex items-center gap-2 rounded-full border border-app-border bg-app-bg px-3 py-1.5 text-[0.78rem] text-app-ink/55">
                  <span>PDF/OCR 결과는 준비 중입니다</span>
                </div>
                <button
                  type="submit"
                  disabled={searching || sourcesLoading}
                  className="inline-flex items-center gap-2 rounded-xl bg-app-accent px-4 py-2 text-[0.9rem] font-semibold text-app-accent-fg transition-opacity hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {searching ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                  <span>{searching ? '검색 중...' : '검색 실행'}</span>
                </button>
              </div>
            </div>
          </form>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 overflow-y-auto px-6 py-6 xl:flex-row xl:overflow-hidden">
        <section className="min-w-0 flex-1 overflow-visible xl:overflow-y-auto">
          {searchError ? (
            <InlineError message={searchError} />
          ) : null}

          {response?.grounded_answer ? (
            <article className="mb-5 rounded-2xl border border-app-border bg-app-surface p-5">
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
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-[0.84rem] text-amber-800">
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
              <p className="app-text-caption mt-1 text-app-ink/55">
                {response
                  ? `${response.hits.length}건 · ${response.sources_used.length} source · trace ${response.trace_id ?? 'n/a'}`
                  : '검색 전에는 source 선택 상태와 grounded answer 설정만 표시됩니다.'}
              </p>
            </div>
          </div>

          {searching && !response ? (
            <div className="flex h-48 items-center justify-center rounded-2xl border border-app-border bg-app-surface text-app-ink/55">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : null}

          {!searching && response && response.hits.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-app-border bg-app-surface p-8 text-center text-app-ink/60">
              현재 조건에서 접근 가능한 결과를 찾지 못했습니다.
            </div>
          ) : null}

          <div className="grid gap-3">
            {response?.hits.map((hit, index) => (
              <SearchHitCard
                key={`${hit.resource_id}:${hit.citation ?? 'none'}:${index}`}
                hit={hit}
                href={buildResultHref(workspaceSlug, hit)}
                sourceLabel={sourceLabelByKind.get(hit.source_kind) ?? hit.source_kind}
              />
            ))}
          </div>
        </section>

        <aside className="w-full shrink-0 space-y-4 xl:w-80 xl:overflow-y-auto">
          <section className="rounded-2xl border border-app-border bg-app-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="app-text-title-md text-app-ink">검색 대상</h2>
              <div className="flex items-center gap-3 text-[0.78rem] font-medium">
                <button
                  type="button"
                  onClick={() => setSelectedSourceKinds(sources.map((source) => source.source_kind))}
                  className="text-app-accent"
                >
                  전체 선택
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedSourceKinds([])}
                  className="text-app-ink/55"
                >
                  전체 해제
                </button>
              </div>
            </div>
            {sourcesLoading ? (
              <div className="flex items-center gap-2 text-app-ink/55">
                <Loader2 size={14} className="animate-spin" />
                <span className="app-text-caption">source 불러오는 중</span>
              </div>
            ) : sourcesError ? (
              <InlineError message={sourcesError} compact />
            ) : sources.length === 0 ? (
              <div className="rounded-xl border border-dashed border-app-border px-3 py-4 text-[0.82rem] text-app-ink/55">
                현재 접근 가능한 검색 대상이 없습니다.
              </div>
            ) : (
              <div className="space-y-2">
                {sources.map((source) => {
                  const checked = selectedSourceKinds.includes(source.source_kind);
                  return (
                    <label
                      key={source.source_kind}
                      className="flex cursor-pointer items-start gap-3 rounded-xl border border-app-border px-3 py-3 hover:bg-app-surface-sidebar"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          setSelectedSourceKinds((current) => (
                            checked
                              ? current.filter((item) => item !== source.source_kind)
                              : [...current, source.source_kind]
                          ));
                        }}
                        className="mt-0.5 h-4 w-4 rounded border-app-border text-app-accent focus:ring-app-accent"
                      />
                      <div className="min-w-0">
                        <div className="app-text-control-sm text-app-ink">{source.label}</div>
                        <div className="mt-1 flex items-center gap-2">
                          <AppBadge appId={source.app_id} />
                          <span className="text-[0.74rem] text-app-ink/45">{source.resource_type}</span>
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
            {!sourcesLoading && !sourcesError && selectedSourceKinds.length === 0 ? (
              <p className="mt-3 text-[0.8rem] text-amber-700">
                검색을 실행하려면 source를 하나 이상 선택해주세요.
              </p>
            ) : null}
          </section>

          <section className="rounded-2xl border border-app-border bg-app-surface p-4">
            <h2 className="app-text-title-md mb-3 text-app-ink">실행 정보</h2>
            {response ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-[0.82rem] text-app-ink/65">
                <dt>응답 시간</dt>
                <dd>{response.latency_ms}ms</dd>
                <dt>반환 건수</dt>
                <dd>{response.hits.length}</dd>
                <dt>사용 Source</dt>
                <dd>{response.sources_used.join(', ') || '-'}</dd>
                <dt>Trace</dt>
                <dd className="break-all">{response.trace_id ?? '-'}</dd>
              </dl>
            ) : (
              <p className="app-text-caption text-app-ink/55">
                검색을 실행하면 latency, sources used, trace id를 여기서 확인할 수 있습니다.
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}

function ModeButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full border px-3 py-1.5 text-[0.8rem] font-medium transition-colors',
        active
          ? 'border-app-accent bg-app-accent text-app-accent-fg'
          : 'border-app-border bg-app-bg text-app-ink/65 hover:bg-app-surface',
      )}
    >
      {label}
    </button>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-app-border bg-app-surface-sidebar px-4 py-3">
      <div className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-app-ink/40">
        {label}
      </div>
      <div className="mt-1 text-[1.05rem] font-semibold text-app-ink">{value}</div>
    </div>
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
    <article className="rounded-2xl border border-app-border bg-app-surface p-4">
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
        <div className="shrink-0 text-right">
          <div className="text-[0.74rem] uppercase tracking-[0.08em] text-app-ink/35">점수</div>
          <div className="text-[0.98rem] font-semibold text-app-ink">
            {hit.score.toFixed(3)}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-[0.8rem] text-app-ink/55">
        {hit.owner_label ? <span>담당 {hit.owner_label}</span> : null}
        {hit.citation ? <span>인용 {hit.citation}</span> : null}
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
    <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
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
        'rounded-xl border border-red-200 bg-red-50 text-red-700',
        compact ? 'px-3 py-2 text-[0.8rem]' : 'mb-4 px-4 py-3 text-[0.9rem]',
      )}
    >
      {message}
    </div>
  );
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
