import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronLeft,
  Copy,
  Download,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  Plus,
  RotateCcw,
  Send,
  X,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  patentAgentChat,
  patentAiSearch,
  patentAskBrainy,
  patentExtract,
  patentFetch,
  patentFilingAssist,
  patentPdfUrl,
  patentReport,
  patentSearchQuery,
  PatentApiError,
  type AiSearchResult,
  type PatentChatMessage,
  type PatentDetail,
  type SearchQueryResult,
} from '../api/patent-api';
import {
  buildReportHtml,
  ReportContent,
  stripReportMarkdown,
} from './patent-report-format';

type TabId = 'search' | 'report' | 'query';
type ReportCard = 'review' | 'improve' | 'invention-disclosure';

interface HistoryEntry {
  query: string;
  total: number;
  date: string;
}

interface SearchPreset {
  text: string;
  query: string;
}

const REPORT_CARDS: ReportCard[] = [
  'review',
  'improve',
  'invention-disclosure',
];
const REPORT_EMOJI: Record<ReportCard, string> = {
  review: '📋',
  improve: '💡',
  'invention-disclosure': '📄',
};
const TAB_EMOJI: Record<TabId, string> = {
  search: '✦',
  report: '📄',
  query: '🔎',
};

function historyStorageKey(workspaceSlug: string | null): string | null {
  return workspaceSlug ? `ai-do.patent.history.${workspaceSlug}` : null;
}

function readHistory(workspaceSlug: string | null): HistoryEntry[] {
  const key = historyStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function writeHistory(
  workspaceSlug: string | null,
  entries: HistoryEntry[],
): void {
  const key = historyStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(entries.slice(0, 30)));
  } catch {
    // Quota/disabled storage — history is best-effort only.
  }
}

// Report tab input|result split ratio (fraction of width given to the input
// pane). Clamped to a sane band so neither pane can be dragged shut.
const REPORT_SPLIT_KEY = 'ai-do.patent.report.split';
const SPLIT_MIN = 0.25;
const SPLIT_MAX = 0.75;

function clampSplit(value: number): number {
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value));
}

function readReportSplit(): number {
  if (typeof window === 'undefined') return 0.5;
  const raw = window.localStorage.getItem(REPORT_SPLIT_KEY);
  const value = raw ? Number.parseFloat(raw) : NaN;
  return Number.isFinite(value) ? clampSplit(value) : 0.5;
}

function writeReportSplit(ratio: number): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(REPORT_SPLIT_KEY, ratio.toFixed(3));
  } catch {
    // Quota/disabled storage — split ratio is best-effort only.
  }
}

// '내 검색' history sidebar width (px), drag-resizable from its right edge.
const HISTORY_WIDTH_KEY = 'ai-do.patent.history-width';
const HISTORY_MIN_WIDTH = 180;
const HISTORY_MAX_WIDTH = 420;
const HISTORY_DEFAULT_WIDTH = 224;

function readHistoryWidth(): number {
  if (typeof window === 'undefined') return HISTORY_DEFAULT_WIDTH;
  const raw = window.localStorage.getItem(HISTORY_WIDTH_KEY);
  const value = raw ? Number.parseInt(raw, 10) : NaN;
  return Number.isFinite(value)
    ? Math.min(HISTORY_MAX_WIDTH, Math.max(HISTORY_MIN_WIDTH, value))
    : HISTORY_DEFAULT_WIDTH;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof PatentApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

// KIPRIS detail page by application number. The kpat biblioFrame endpoint
// renders the actual patent (the khome SPA ignores URL query/hash, so the old
// `main.jsp#term=` link showed nothing). The Google Patents PDF URL is resolved
// by the backend (/patent/pdf-url) since it needs KIPRIS's number format.
function kiprisViewerUrl(detail: PatentDetail): string {
  const appNo = detail.app_no.replace(/[-\s]/g, '');
  return `http://kpat.kipris.or.kr/kpat/biblioa.do?method=biblioFrame&searchCondition=AN&searchValue=${appNo}`;
}

export function PatentComposeView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const locale = user?.locale ?? i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [tab, setTab] = useState<TabId>('search');
  const [historyOpen, setHistoryOpen] = useState(true);

  // ── '내 검색' 사이드바 너비 (드래그 리사이즈) ─────────────────────────────────
  const historyAsideRef = useRef<HTMLElement>(null);
  const [historyWidth, setHistoryWidth] = useState(HISTORY_DEFAULT_WIDTH);
  const [resizingHistory, setResizingHistory] = useState(false);

  useEffect(() => {
    setHistoryWidth(readHistoryWidth());
  }, []);

  useEffect(() => {
    if (!resizingHistory) return;
    const onMove = (event: MouseEvent) => {
      const node = historyAsideRef.current;
      if (!node) return;
      const left = node.getBoundingClientRect().left;
      setHistoryWidth(
        Math.min(
          HISTORY_MAX_WIDTH,
          Math.max(HISTORY_MIN_WIDTH, event.clientX - left),
        ),
      );
    };
    const onUp = () => setResizingHistory(false);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [resizingHistory]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(HISTORY_WIDTH_KEY, String(historyWidth));
  }, [historyWidth]);

  // ── AI 특허 검색 ──────────────────────────────────────────────────────────
  const [searchInput, setSearchInput] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResult, setSearchResult] = useState<AiSearchResult | null>(null);
  const [detail, setDetail] = useState<PatentDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  // ── AI 에이전트 채팅 ──────────────────────────────────────────────────────
  const [chatMessages, setChatMessages] = useState<PatentChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [agentConversationId, setAgentConversationId] = useState<string | null>(
    null,
  );

  // ── AI 보고서 ─────────────────────────────────────────────────────────────
  const [reportCard, setReportCard] = useState<ReportCard>('review');
  const [reportInput, setReportInput] = useState('');
  const [reportMemo, setReportMemo] = useState('');
  // Per-card state so each report card (review / improve / invention-disclosure)
  // generates independently — one card running must not block or show loading on
  // the others. Outputs are likewise keyed by card.
  const [reportBusy, setReportBusy] = useState<
    Partial<Record<ReportCard, boolean>>
  >({});
  const [reportErrors, setReportErrors] = useState<
    Partial<Record<ReportCard, string | null>>
  >({});
  const [reportOutputs, setReportOutputs] = useState<
    Partial<Record<ReportCard, string>>
  >({});
  const [attaching, setAttaching] = useState(false);
  const [attachStatus, setAttachStatus] = useState<{
    filename: string;
    count: number;
  } | null>(null);

  // ── 검색식 생성 ─────────────────────────────────────────────────────────────
  const [queryInput, setQueryInput] = useState('');
  const [queryBusy, setQueryBusy] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<SearchQueryResult | null>(
    null,
  );

  const detailRequestRef = useRef(0);

  useEffect(() => {
    setHistory(readHistory(workspaceSlug));
  }, [workspaceSlug]);

  const recordHistory = useCallback(
    (query: string, total: number) => {
      const date = formatDateTime(new Date(), {
        day: 'numeric',
        locale,
        month: 'long',
        timeZone,
      });
      setHistory((current) => {
        const next = [
          { query, total, date },
          ...current.filter((h) => h.query !== query),
        ].slice(0, 30);
        writeHistory(workspaceSlug, next);
        return next;
      });
    },
    [locale, timeZone, workspaceSlug],
  );

  const runAiSearch = useCallback(
    async (query: string, page = 1) => {
      const trimmed = query.trim();
      if (!trimmed || !token || searching) return;
      setSearching(true);
      setSearchError(null);
      setDetail(null);
      try {
        const result = await patentAiSearch({
          token,
          workspaceSlug,
          query: trimmed,
          page,
        });
        setSearchResult(result);
        setChatMessages([]);
        setAgentConversationId(null);
        recordHistory(trimmed, result.total);
      } catch (error) {
        setSearchError(
          errorMessage(error, t('apps:ai.patentCompose.errors.searchFailed')),
        );
      } finally {
        setSearching(false);
      }
    },
    [recordHistory, searching, t, token, workspaceSlug],
  );

  const runNumberSearch = useCallback(async () => {
    const trimmed = searchInput.trim();
    if (!trimmed || !token || searching) return;
    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;
    setSearching(true);
    setSearchError(null);
    try {
      const result = await patentFetch({
        token,
        workspaceSlug,
        patentNumber: trimmed,
      });
      if (detailRequestRef.current === requestId) {
        setDetail(result);
        setSearchResult(null);
        setChatMessages([]);
        setAgentConversationId(null);
      }
    } catch (error) {
      setSearchError(
        errorMessage(error, t('apps:ai.patentCompose.errors.searchFailed')),
      );
    } finally {
      setSearching(false);
    }
  }, [searchInput, searching, t, token, workspaceSlug]);

  // Open a patent's detail from a clicked search result (keeps the result list
  // so the user can go back). The result row lacks claims, so fetch the full
  // record by application number.
  const selectPatent = useCallback(
    async (patentNumber: string) => {
      if (!patentNumber || !token || loadingDetail) return;
      const requestId = detailRequestRef.current + 1;
      detailRequestRef.current = requestId;
      setLoadingDetail(true);
      setSearchError(null);
      try {
        const result = await patentFetch({
          token,
          workspaceSlug,
          patentNumber,
        });
        if (detailRequestRef.current === requestId) {
          setDetail(result);
        }
      } catch (error) {
        setSearchError(
          errorMessage(error, t('apps:ai.patentCompose.errors.searchFailed')),
        );
      } finally {
        if (detailRequestRef.current === requestId) {
          setLoadingDetail(false);
        }
      }
    },
    [loadingDetail, t, token, workspaceSlug],
  );

  const clearDetail = useCallback(() => setDetail(null), []);

  const sendChat = useCallback(async () => {
    const message = chatInput.trim();
    if (!message || !token || chatSending || !searchResult) return;
    const nextMessages: PatentChatMessage[] = [
      ...chatMessages,
      { role: 'user', content: message },
    ];
    setChatMessages(nextMessages);
    setChatInput('');
    setChatSending(true);
    try {
      const context = `${searchResult.tech_summary}\n${searchResult.ai_summary}`;
      const { reply, conversation_id } = await patentAgentChat({
        token,
        workspaceSlug,
        message,
        context,
        history: chatMessages,
        conversationId: agentConversationId,
      });
      setAgentConversationId(conversation_id ?? agentConversationId ?? null);
      setChatMessages([...nextMessages, { role: 'assistant', content: reply }]);
    } catch (error) {
      setChatMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: errorMessage(
            error,
            t('apps:ai.patentCompose.errors.connect'),
          ),
        },
      ]);
    } finally {
      setChatSending(false);
    }
  }, [
    chatInput,
    chatMessages,
    chatSending,
    searchResult,
    agentConversationId,
    t,
    token,
    workspaceSlug,
  ]);

  const runReport = useCallback(async () => {
    const base = reportInput.trim();
    const card = reportCard;
    // Only the same card being in-flight blocks a re-run; other cards are free.
    if (!base || !token || reportBusy[card]) return;
    const memo = reportMemo.trim();
    const content = memo ? `${base}\n\n${memo}` : base;
    setReportBusy((prev) => ({ ...prev, [card]: true }));
    setReportErrors((prev) => ({ ...prev, [card]: null }));
    setReportOutputs((prev) => ({ ...prev, [card]: '' }));
    try {
      if (card === 'review' || card === 'improve') {
        const { result } = await patentFilingAssist({
          token,
          workspaceSlug,
          invention: content,
          mode: card,
        });
        setReportOutputs((prev) => ({ ...prev, [card]: result }));
      } else {
        const { result } = await patentReport({
          token,
          workspaceSlug,
          content,
          reportType: card,
        });
        setReportOutputs((prev) => ({ ...prev, [card]: result }));
      }
    } catch (error) {
      setReportErrors((prev) => ({
        ...prev,
        [card]: errorMessage(error, t('apps:ai.patentCompose.errors.connect')),
      }));
    } finally {
      setReportBusy((prev) => ({ ...prev, [card]: false }));
    }
  }, [
    reportBusy,
    reportCard,
    reportInput,
    reportMemo,
    t,
    token,
    workspaceSlug,
  ]);

  const runExtract = useCallback(
    async (file: File) => {
      if (!token || attaching) return;
      // Attach fills the shared input; surface any extract error on the card the
      // user is currently viewing.
      const card = reportCard;
      setAttaching(true);
      setReportErrors((prev) => ({ ...prev, [card]: null }));
      try {
        const result = await patentExtract({ token, workspaceSlug, file });
        setReportInput(result.text);
        setAttachStatus({
          filename: result.filename,
          count: result.char_count,
        });
      } catch (error) {
        setReportErrors((prev) => ({
          ...prev,
          [card]: errorMessage(
            error,
            t('apps:ai.patentCompose.errors.connect'),
          ),
        }));
      } finally {
        setAttaching(false);
      }
    },
    [attaching, reportCard, t, token, workspaceSlug],
  );

  const runSearchQuery = useCallback(async () => {
    const technologyDescription = queryInput.trim();
    if (!technologyDescription || !token || queryBusy) return;
    setQueryBusy(true);
    setQueryError(null);
    try {
      const result = await patentSearchQuery({
        token,
        workspaceSlug,
        technologyDescription,
      });
      setQueryResult(result);
    } catch (error) {
      setQueryError(
        errorMessage(error, t('apps:ai.patentCompose.errors.connect')),
      );
    } finally {
      setQueryBusy(false);
    }
  }, [queryBusy, queryInput, t, token, workspaceSlug]);

  const resetAll = useCallback(() => {
    setSearchResult(null);
    setDetail(null);
    setSearchError(null);
    setChatMessages([]);
    setReportOutputs({});
    setReportErrors({});
    setReportBusy({});
    setAttachStatus(null);
    setQueryResult(null);
    setQueryError(null);
  }, []);

  const startReportFromCard = useCallback((card: ReportCard) => {
    setReportCard(card);
    setTab('report');
  }, []);

  // Switching cards reveals that card's own stored output/error/busy state
  // (blank if none); each card is independent, so nothing is cleared here.
  const handleReportCardChange = useCallback((card: ReportCard) => {
    setReportCard(card);
  }, []);

  const presets = useMemo(() => {
    const raw = t('ai.patentCompose.search.presets', {
      returnObjects: true,
    }) as unknown;
    return Array.isArray(raw) ? (raw as SearchPreset[]) : [];
  }, [t]);

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: 'search', label: t('apps:ai.patentCompose.tabs.search') },
    { id: 'report', label: t('apps:ai.patentCompose.tabs.report') },
    { id: 'query', label: t('apps:ai.patentCompose.tabs.query') },
  ];

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Left: search history (collapsible) */}
      {historyOpen ? (
        <aside
          ref={historyAsideRef}
          style={{ width: `${historyWidth}px` }}
          className="relative hidden shrink-0 flex-col overflow-hidden border-r border-app-border bg-app-surface-sidebar lg:flex"
        >
          <div className="flex h-16 items-center gap-1 border-b border-app-border px-2">
            <button
              type="button"
              onClick={() => setHistoryOpen(false)}
              title={t('apps:ai.patentCompose.search.collapse')}
              aria-label={t('apps:ai.patentCompose.search.collapse')}
              className="shrink-0 rounded-md p-1.5 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-accent"
            >
              <PanelLeftClose size={15} />
            </button>
            <button
              type="button"
              onClick={resetAll}
              className="flex flex-1 items-center gap-2 rounded-lg border border-app-border px-3 py-2 app-text-body-sm text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
            >
              <Plus size={14} />
              {t('apps:ai.patentCompose.search.newSearch')}
            </button>
          </div>
          <span className="sidebar-section-label px-3 py-2 text-app-ink/55">
            {t('apps:ai.patentCompose.search.historyTitle')}
          </span>
          <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
            {history.length === 0 ? (
              <p className="px-1 py-2 text-center app-text-micro text-app-ink/55">
                {t('apps:ai.patentCompose.search.historyEmpty')}
              </p>
            ) : (
              history.map((entry) => (
                <button
                  key={`${entry.query}-${entry.date}`}
                  type="button"
                  onClick={() => {
                    setTab('search');
                    setSearchInput(entry.query);
                    void runAiSearch(entry.query);
                  }}
                  className="flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left transition-colors hover:bg-app-surface-hover"
                >
                  <span className="app-text-body-sm truncate text-app-ink">
                    {entry.query}
                  </span>
                  <span className="app-text-micro text-app-ink/55">
                    {t('apps:ai.patentCompose.search.historyMeta', {
                      total: entry.total,
                      date: entry.date,
                    })}
                  </span>
                </button>
              ))
            )}
          </div>
          <button
            type="button"
            aria-label={t('apps:ai.patentCompose.search.resize')}
            title={t('apps:ai.patentCompose.search.resize')}
            onMouseDown={(event) => {
              event.preventDefault();
              setResizingHistory(true);
            }}
            className={cn(
              'absolute right-0 top-0 h-full w-1 cursor-col-resize border-0 bg-transparent p-0 transition-colors hover:bg-app-accent/30',
              resizingHistory && 'bg-app-accent/50',
            )}
          />
        </aside>
      ) : (
        <button
          type="button"
          onClick={() => setHistoryOpen(true)}
          title={t('apps:ai.patentCompose.search.expand')}
          aria-label={t('apps:ai.patentCompose.search.expand')}
          className="hidden w-9 shrink-0 flex-col items-center gap-2 border-r border-app-border bg-app-surface-sidebar py-3 text-app-ink/55 transition-colors hover:text-app-accent lg:flex"
        >
          <PanelLeftOpen size={16} />
          <span className="app-text-micro [writing-mode:vertical-rl]">
            {t('apps:ai.patentCompose.search.historyTitle')}
          </span>
        </button>
      )}

      {/* Main */}
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 items-center gap-2 border-b border-app-border px-4">
          <div className="flex gap-1">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={cn(
                  'app-text-control rounded-md px-3 py-1.5 transition-colors',
                  tab === item.id
                    ? 'bg-app-accent text-app-accent-fg'
                    : 'text-app-ink hover:bg-app-surface-hover',
                )}
              >
                {TAB_EMOJI[item.id]} {item.label}
              </button>
            ))}
          </div>
          <span className="flex-1" />
          <button
            type="button"
            onClick={resetAll}
            className="app-text-control flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1.5 text-app-ink transition-colors hover:border-app-accent"
          >
            <RotateCcw size={13} />
            {t('apps:ai.patentCompose.reset')}
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {tab === 'search' ? (
            <SearchTab
              token={token}
              workspaceSlug={workspaceSlug}
              input={searchInput}
              onInputChange={setSearchInput}
              onAiSearch={() => void runAiSearch(searchInput)}
              onNumberSearch={() => void runNumberSearch()}
              searching={searching}
              error={searchError}
              result={searchResult}
              detail={detail}
              loadingDetail={loadingDetail}
              onSelectPatent={(appNo) => void selectPatent(appNo)}
              onBackToResults={clearDetail}
              presets={presets}
              onSuggested={(q) => {
                setSearchInput(q);
                void runAiSearch(q);
              }}
              onStartReport={startReportFromCard}
              chatMessages={chatMessages}
              chatInput={chatInput}
              chatSending={chatSending}
              onChatInput={setChatInput}
              onChatSend={() => void sendChat()}
            />
          ) : null}
          {tab === 'report' ? (
            <ReportTab
              card={reportCard}
              onCardChange={handleReportCardChange}
              input={reportInput}
              onInputChange={setReportInput}
              memo={reportMemo}
              onMemoChange={setReportMemo}
              busy={reportBusy[reportCard] ?? false}
              error={reportErrors[reportCard] ?? null}
              output={reportOutputs[reportCard] ?? ''}
              onGenerate={() => void runReport()}
              attaching={attaching}
              attachStatus={attachStatus}
              onAttach={(file) => void runExtract(file)}
              onClearAttach={() => setAttachStatus(null)}
            />
          ) : null}
          {tab === 'query' ? (
            <QueryTab
              input={queryInput}
              onInputChange={setQueryInput}
              busy={queryBusy}
              error={queryError}
              result={queryResult}
              onGenerate={() => void runSearchQuery()}
            />
          ) : null}
        </div>
      </section>
    </div>
  );
}

// ── Search tab ────────────────────────────────────────────────────────────────
function SearchTab(props: {
  token: string | null;
  workspaceSlug: string | null;
  input: string;
  onInputChange: (value: string) => void;
  onAiSearch: () => void;
  onNumberSearch: () => void;
  searching: boolean;
  error: string | null;
  result: AiSearchResult | null;
  detail: PatentDetail | null;
  loadingDetail: boolean;
  onSelectPatent: (patentNumber: string) => void;
  onBackToResults: () => void;
  presets: SearchPreset[];
  onSuggested: (query: string) => void;
  onStartReport: (card: ReportCard) => void;
  chatMessages: PatentChatMessage[];
  chatInput: string;
  chatSending: boolean;
  onChatInput: (value: string) => void;
  onChatSend: () => void;
}) {
  const { t } = useTranslation('apps');

  if ((props.searching || props.loadingDetail) && !props.detail) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-app-ink/55">
        <Loader2 size={24} className="animate-spin text-app-accent" />
        <p className="app-text-body-sm">
          {t('ai.patentCompose.search.loading')}
        </p>
      </div>
    );
  }

  if (props.detail) {
    return (
      <PatentDetailPanel
        detail={props.detail}
        token={props.token}
        workspaceSlug={props.workspaceSlug}
        onBack={props.onBackToResults}
      />
    );
  }

  if (props.result) {
    return (
      <div className="p-4">
        {props.error ? (
          <p
            role="alert"
            className="mb-3 app-text-body-sm text-[var(--ui-color-danger)]"
          >
            {props.error}
          </p>
        ) : null}
        <SearchResultPanel
          result={props.result}
          onSelectPatent={props.onSelectPatent}
          onSuggested={props.onSuggested}
          chatMessages={props.chatMessages}
          chatInput={props.chatInput}
          chatSending={props.chatSending}
          onChatInput={props.onChatInput}
          onChatSend={props.onChatSend}
        />
      </div>
    );
  }

  // Initial centered hero view.
  return (
    <div className="flex flex-col items-center px-6 py-8">
      <div className="w-full max-w-2xl">
        <div className="mb-6 text-center">
          <div className="app-text-title-md text-app-ink">
            {t('ai.patentCompose.search.heading')}
          </div>
          <div className="mt-1.5 app-text-body-sm text-app-ink/55">
            {t('ai.patentCompose.search.subline')}
          </div>
        </div>
        <textarea
          value={props.input}
          onChange={(event) => props.onInputChange(event.target.value)}
          placeholder={t('ai.patentCompose.search.placeholder')}
          rows={4}
          className="w-full resize-none rounded-xl border-2 border-app-accent bg-app-surface-sidebar px-4 py-3 app-text-body-sm text-app-ink outline-none"
        />
        <div className="mt-2.5 flex justify-end gap-2">
          <button
            type="button"
            onClick={props.onNumberSearch}
            disabled={props.searching}
            className="app-text-control rounded-lg border border-app-border bg-app-surface px-4 py-2 text-app-ink transition-colors hover:border-app-accent disabled:opacity-60"
          >
            {t('ai.patentCompose.search.numberSearch')}
          </button>
          <button
            type="button"
            onClick={props.onAiSearch}
            disabled={props.searching}
            className="app-text-control rounded-lg bg-app-accent px-6 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {t('ai.patentCompose.search.aiSearch')}
          </button>
        </div>
      </div>

      <div className="mt-6 w-full max-w-2xl">
        <p className="mb-2.5 app-text-body-sm text-app-ink/55">
          {t('ai.patentCompose.search.suggestionsTitle')}
        </p>
        <div className="flex flex-col gap-2">
          {props.presets.map((preset) => (
            <button
              key={preset.query}
              type="button"
              onClick={() => props.onSuggested(preset.query)}
              className="rounded-lg border border-app-border bg-app-surface px-3 py-2.5 text-left app-text-body-sm text-app-ink transition-colors hover:border-app-accent"
            >
              {preset.text}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-8 w-full max-w-3xl">
        <p className="mb-4 text-center app-text-body-sm text-app-ink/55">
          {t('ai.patentCompose.report.quickStart')}
        </p>
        <div className="flex flex-wrap justify-center gap-2.5">
          {REPORT_CARDS.map((card) => (
            <button
              key={card}
              type="button"
              onClick={() => props.onStartReport(card)}
              className="flex w-44 flex-col items-start rounded-lg border border-app-border bg-app-surface p-3 text-left transition-colors hover:border-app-accent"
            >
              <span className="mb-1.5 app-text-body">{REPORT_EMOJI[card]}</span>
              <span className="app-text-body-sm font-semibold text-app-ink">
                {t(`ai.patentCompose.report.cards.${card}.label`)}
              </span>
              <span className="mt-1 app-text-micro text-app-ink/55">
                {t(`ai.patentCompose.report.cards.${card}.desc`)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SearchResultPanel(props: {
  result: AiSearchResult;
  onSelectPatent: (patentNumber: string) => void;
  onSuggested: (query: string) => void;
  chatMessages: PatentChatMessage[];
  chatInput: string;
  chatSending: boolean;
  onChatInput: (value: string) => void;
  onChatSend: () => void;
}) {
  const { t } = useTranslation('apps');
  const { result } = props;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="space-y-3">
        {result.ai_summary ? (
          <div className="rounded-xl border border-app-accent bg-app-surface-sidebar p-4">
            <p className="mb-1.5 app-text-caption text-app-ink/55">
              {t('ai.patentCompose.search.summaryTitle')}
            </p>
            {result.search_query ? (
              <p className="mb-2 app-text-body font-semibold text-app-ink">
                {result.search_query}
              </p>
            ) : null}
            {result.core_techs.length > 0 ? (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {result.core_techs.map((tech) => (
                  <span
                    key={tech}
                    className="app-text-micro rounded-full border border-app-border px-2 py-0.5 text-app-ink/80"
                  >
                    #{tech}
                  </span>
                ))}
              </div>
            ) : null}
            <p className="app-text-body-sm text-app-ink/80">
              {result.ai_summary}
            </p>
          </div>
        ) : null}

        {result.top_applicants.length > 0 ? (
          <div className="rounded-lg border border-app-border bg-app-surface-sidebar p-3.5">
            <p className="mb-2 app-text-caption text-app-ink/55">
              {t('ai.patentCompose.search.topApplicants')}
            </p>
            <ul className="space-y-0.5">
              {result.top_applicants.map((applicant) => (
                <li
                  key={applicant.name}
                  className="flex justify-between app-text-body-sm text-app-ink/80"
                >
                  <span className="truncate">{applicant.name}</span>
                  <span className="text-app-ink/55">{applicant.count}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <p className="app-text-caption text-app-ink/55">
          {t('ai.patentCompose.search.resultCount', { total: result.total })}
        </p>

        <ul className="space-y-2">
          {result.results.map((item) => (
            <li key={item.app_no || item.title}>
              <button
                type="button"
                onClick={() => props.onSelectPatent(item.app_no || item.reg_no)}
                disabled={!item.app_no && !item.reg_no}
                className="w-full rounded-lg border border-app-border bg-app-surface p-3 text-left transition-colors hover:border-app-accent disabled:cursor-default disabled:hover:border-app-border"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="app-text-body-sm font-semibold text-app-ink">
                    {item.title}
                  </span>
                  {item.relevance ? (
                    <span className="app-text-micro shrink-0 text-app-accent">
                      {item.relevance}%
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 app-text-micro text-app-ink/55">
                  {item.applicant} · {item.status} · {item.app_no}
                </p>
                {item.ai_tags.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.ai_tags.map((tag) => (
                      <span
                        key={tag}
                        className="app-text-micro text-app-ink/70"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <aside className="space-y-3">
        {result.suggested_queries.length > 0 ? (
          <div className="rounded-lg border border-app-border bg-app-surface p-3">
            <p className="mb-1.5 app-text-caption font-semibold text-app-ink">
              {t('ai.patentCompose.search.suggested')}
            </p>
            <div className="flex flex-wrap gap-1">
              {result.suggested_queries.map((query) => (
                <button
                  key={query}
                  type="button"
                  onClick={() => props.onSuggested(query)}
                  className="app-text-micro rounded-full border border-app-border px-2 py-0.5 text-app-ink/80 transition-colors hover:border-app-accent"
                >
                  {query}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <AgentChat
          messages={props.chatMessages}
          input={props.chatInput}
          sending={props.chatSending}
          onInput={props.onChatInput}
          onSend={props.onChatSend}
        />
      </aside>
    </div>
  );
}

function AgentChat(props: {
  messages: PatentChatMessage[];
  input: string;
  sending: boolean;
  onInput: (value: string) => void;
  onSend: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="rounded-lg border border-app-border bg-app-surface p-3">
      <p className="mb-1.5 app-text-caption font-semibold text-app-ink">
        {t('ai.patentCompose.agent.title')}
      </p>
      <div className="mb-2 max-h-56 space-y-2 overflow-y-auto">
        {props.messages.map((message, index) => (
          <div
            key={index}
            className={cn(
              'app-text-micro whitespace-pre-wrap rounded-md px-2 py-1',
              message.role === 'user'
                ? 'bg-app-surface-hover text-app-ink'
                : 'text-app-ink/80',
            )}
          >
            {message.content}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1">
        <input
          value={props.input}
          onChange={(event) => props.onInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              props.onSend();
            }
          }}
          placeholder={t('ai.patentCompose.agent.placeholder')}
          className="min-w-0 flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 app-text-micro text-app-ink outline-none focus:border-app-accent"
        />
        <button
          type="button"
          onClick={props.onSend}
          disabled={props.sending}
          className="rounded-md bg-app-accent p-1.5 text-app-accent-fg disabled:opacity-60"
        >
          {props.sending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Send size={13} />
          )}
        </button>
      </div>
    </div>
  );
}

function PatentDetailPanel({
  detail,
  token,
  workspaceSlug,
  onBack,
}: {
  detail: PatentDetail;
  token: string | null;
  workspaceSlug: string | null;
  onBack: () => void;
}) {
  const { t } = useTranslation('apps');

  // Open a blank tab synchronously (keeps the user gesture so popup blockers
  // allow it), then point it at the backend-resolved Google Patents URL.
  const openPdf = useCallback(() => {
    const win =
      typeof window !== 'undefined'
        ? window.open('about:blank', '_blank')
        : null;
    if (!token) {
      win?.close();
      return;
    }
    patentPdfUrl({
      token,
      workspaceSlug,
      appNo: detail.app_no,
      regNo: detail.reg_no,
    })
      .then((urls) => {
        if (win) win.location.href = urls.pdf_url;
      })
      .catch(() => win?.close());
  }, [detail.app_no, detail.reg_no, token, workspaceSlug]);

  const timeline = [
    {
      label: t('ai.patentCompose.detail.timelineStep.application'),
      date: detail.date,
    },
    {
      label: t('ai.patentCompose.detail.timelineStep.publication'),
      date: detail.pub_date || detail.open_date,
    },
    {
      label: t('ai.patentCompose.detail.timelineStep.registration'),
      date: detail.reg_date,
    },
  ].filter((step) => step.date);

  const biblio: Array<{ label: string; value: string }> = [
    { label: t('ai.patentCompose.detail.fields.appNo'), value: detail.app_no },
    { label: t('ai.patentCompose.detail.fields.appDate'), value: detail.date },
    {
      label: t('ai.patentCompose.detail.fields.openNo'),
      value: detail.open_no,
    },
    {
      label: t('ai.patentCompose.detail.fields.openDate'),
      value: detail.open_date,
    },
    { label: t('ai.patentCompose.detail.fields.regNo'), value: detail.reg_no },
    {
      label: t('ai.patentCompose.detail.fields.regDate'),
      value: detail.reg_date,
    },
    {
      label: t('ai.patentCompose.detail.fields.pubDate'),
      value: detail.pub_date,
    },
    { label: t('ai.patentCompose.detail.fields.ipc'), value: detail.ipc },
    {
      label: t('ai.patentCompose.detail.fields.finalDisposal'),
      value: detail.final_disposal,
    },
    { label: t('ai.patentCompose.detail.fields.status'), value: detail.status },
  ].filter((row) => row.value);

  const applicants = detail.applicant
    .split(/[|,]/)
    .map((name) => name.trim())
    .filter(Boolean);
  const ipcCodes = detail.ipc
    .split(',')
    .map((code) => code.trim())
    .filter(Boolean);
  const actionBtn =
    'app-text-control inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-app-ink transition-colors hover:border-app-accent';

  return (
    <div className="flex h-full overflow-hidden">
      <div className="min-w-0 flex-1 overflow-y-auto p-5">
        <div className="mb-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {detail.status ? (
                <span className="app-text-micro rounded bg-app-accent/10 px-2 py-0.5 font-semibold text-app-accent">
                  {detail.status}
                </span>
              ) : null}
              <span className="app-text-micro text-app-ink/55">
                {detail.app_no}
              </span>
            </div>
            <div className="flex gap-1.5">
              <button type="button" onClick={onBack} className={actionBtn}>
                <ChevronLeft size={13} />
                {t('ai.patentCompose.detail.back')}
              </button>
              <button type="button" onClick={openPdf} className={actionBtn}>
                {t('ai.patentCompose.detail.openPdf')}
              </button>
              <a
                href={kiprisViewerUrl(detail)}
                target="_blank"
                rel="noopener noreferrer"
                className={actionBtn}
              >
                {t('ai.patentCompose.detail.kipris')}
              </a>
            </div>
          </div>
          <h2 className="app-text-title-md text-app-ink">
            {detail.title || detail.app_no}
            {detail.title_eng ? (
              <span className="text-app-ink/60"> ({detail.title_eng})</span>
            ) : null}
          </h2>
        </div>

        {detail.warning ? (
          <p className="mb-4 app-text-caption text-app-warning-text dark:text-app-warning-text">
            {detail.warning}
          </p>
        ) : null}

        {timeline.length > 0 ? (
          <DetailSection title={t('ai.patentCompose.detail.timeline')}>
            <div className="flex items-center justify-between rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-4">
              {timeline.map((step, index) => (
                <div key={step.label} className="flex flex-1 items-center">
                  <div className="flex flex-col items-center gap-1">
                    <span className="app-text-micro text-app-ink/55">
                      {step.date}
                    </span>
                    <span className="size-2.5 rounded-full bg-app-accent" />
                    <span className="app-text-caption font-medium text-app-ink">
                      {step.label}
                    </span>
                  </div>
                  {index < timeline.length - 1 ? (
                    <div className="mx-1 h-px flex-1 bg-app-border" />
                  ) : null}
                </div>
              ))}
            </div>
          </DetailSection>
        ) : null}

        {detail.abstract ? (
          <DetailSection title={t('ai.patentCompose.detail.summary')}>
            <p className="rounded-lg border border-app-border bg-app-surface-sidebar p-3 app-text-body-sm text-app-ink/80">
              {detail.abstract}
            </p>
          </DetailSection>
        ) : null}

        {applicants.length > 0 ? (
          <DetailSection title={t('ai.patentCompose.detail.people')}>
            <div className="flex flex-wrap gap-1.5">
              {applicants.map((name) => (
                <span
                  key={name}
                  className="app-text-body-sm rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-app-ink"
                >
                  {name}
                </span>
              ))}
            </div>
          </DetailSection>
        ) : null}

        {biblio.length > 0 ? (
          <DetailSection title={t('ai.patentCompose.detail.biblio')}>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {biblio.map((row) => (
                <div key={row.label} className="flex gap-2">
                  <dt className="app-text-body-sm w-24 shrink-0 text-app-ink/55">
                    {row.label}
                  </dt>
                  <dd className="app-text-body-sm min-w-0 break-words text-app-ink">
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
          </DetailSection>
        ) : null}

        {detail.claims.length > 0 ? (
          <DetailSection title={t('ai.patentCompose.detail.claims')}>
            <ol className="space-y-2">
              {detail.claims.map((claim, index) => (
                <li
                  key={index}
                  className="whitespace-pre-wrap rounded-lg border border-app-border bg-app-surface-sidebar p-3 app-text-body-sm text-app-ink/80"
                >
                  {claim}
                </li>
              ))}
            </ol>
          </DetailSection>
        ) : null}

        <DetailSection title={t('ai.patentCompose.detail.family')}>
          <p className="mb-2 app-text-caption text-app-ink/55">
            {t('ai.patentCompose.detail.familyScope', { count: 1 })}
          </p>
          <div className="rounded-lg border border-app-border bg-app-surface-sidebar p-3">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
              <div className="flex gap-2">
                <dt className="app-text-body-sm w-24 shrink-0 text-app-ink/55">
                  {t('ai.patentCompose.detail.fields.docNo')}
                </dt>
                <dd className="app-text-body-sm min-w-0 break-words text-app-ink">
                  {detail.reg_no || detail.open_no || detail.app_no}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="app-text-body-sm w-24 shrink-0 text-app-ink/55">
                  {t('ai.patentCompose.detail.fields.appDate')}
                </dt>
                <dd className="app-text-body-sm min-w-0 break-words text-app-ink">
                  {detail.date}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="app-text-body-sm w-24 shrink-0 text-app-ink/55">
                  {t('ai.patentCompose.detail.fields.status')}
                </dt>
                <dd className="app-text-body-sm min-w-0 break-words text-app-ink">
                  {detail.status}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="app-text-body-sm w-24 shrink-0 text-app-ink/55">
                  {t('ai.patentCompose.detail.fields.title')}
                </dt>
                <dd className="app-text-body-sm min-w-0 break-words text-app-ink">
                  {detail.title}
                </dd>
              </div>
            </dl>
          </div>
        </DetailSection>

        <DetailSection title={t('ai.patentCompose.detail.citation')}>
          <p className="rounded-lg border border-app-border bg-app-surface-sidebar p-3 app-text-body-sm text-app-ink/55">
            {t('ai.patentCompose.detail.citationNote')}
          </p>
        </DetailSection>

        {ipcCodes.length > 0 ? (
          <DetailSection title={t('ai.patentCompose.detail.classification')}>
            <p className="mb-2 app-text-caption text-app-ink/55">
              {t('ai.patentCompose.detail.classificationDesc')}
            </p>
            <div className="space-y-1.5">
              {ipcCodes.map((code, index) => (
                <div
                  key={`${code}-${index}`}
                  className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5"
                >
                  <span className="app-text-micro w-12 shrink-0 font-semibold text-app-ink/55">
                    {t('ai.patentCompose.detail.patentClass')}
                  </span>
                  <span className="app-text-body-sm text-app-ink">{code}</span>
                </div>
              ))}
            </div>
          </DetailSection>
        ) : null}
      </div>

      <DetailAgent
        key={detail.app_no}
        detail={detail}
        token={token}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mb-6">
      <h3 className="mb-3 app-text-body font-semibold text-app-ink">{title}</h3>
      {children}
    </section>
  );
}

function DetailAgent({
  detail,
  token,
  workspaceSlug,
}: {
  detail: PatentDetail;
  token: string | null;
  workspaceSlug: string | null;
}) {
  const { t } = useTranslation('apps');
  const [messages, setMessages] = useState<PatentChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const context = useMemo(
    () =>
      `${detail.title}\n${detail.abstract}\n${(detail.claims ?? []).slice(0, 3).join('\n')}`.slice(
        0,
        12000,
      ),
    [detail],
  );

  useEffect(() => {
    setMessages([]);
    setConversationId(null);
  }, [context]);

  const ask = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || !token || sending) return;
      const next: PatentChatMessage[] = [
        ...messages,
        { role: 'user', content: trimmed },
      ];
      setMessages(next);
      setInput('');
      setSending(true);
      try {
        const { answer, conversation_id } = await patentAskBrainy({
          token,
          workspaceSlug,
          patentContext: context,
          messages,
          question: trimmed,
          conversationId,
        });
        setConversationId(conversation_id ?? conversationId ?? null);
        setMessages([...next, { role: 'assistant', content: answer }]);
      } catch (error) {
        setMessages([
          ...next,
          {
            role: 'assistant',
            content: errorMessage(error, t('ai.patentCompose.errors.connect')),
          },
        ]);
      } finally {
        setSending(false);
      }
    },
    [context, conversationId, messages, sending, t, token, workspaceSlug],
  );

  const suggestions = [
    t('ai.patentCompose.detail.agent.q1'),
    t('ai.patentCompose.detail.agent.q2'),
    t('ai.patentCompose.detail.agent.q3'),
  ];

  return (
    <aside className="hidden w-80 shrink-0 flex-col overflow-hidden border-l border-app-border lg:flex">
      <div className="border-b border-app-border px-4 py-3">
        <p className="app-text-body font-semibold text-app-ink">
          {t('ai.patentCompose.detail.agent.title')}
        </p>
        <p className="app-text-micro text-app-ink/55">
          {t('ai.patentCompose.detail.agent.suggestTitle')}
        </p>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {suggestions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => void ask(question)}
            disabled={sending}
            className="app-text-body-sm w-full rounded-lg border border-app-border bg-app-surface px-3 py-2 text-left text-app-ink transition-colors hover:border-app-accent disabled:opacity-60"
          >
            ✦ {question}
          </button>
        ))}
        {messages.map((message, index) => (
          <div
            key={index}
            className={cn(
              'app-text-body-sm whitespace-pre-wrap rounded-md px-2.5 py-1.5',
              message.role === 'user'
                ? 'bg-app-surface-hover text-app-ink'
                : 'text-app-ink/80',
            )}
          >
            {message.content}
          </div>
        ))}
      </div>
      <div className="flex items-end gap-1 border-t border-app-border p-2.5">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void ask(input);
            }
          }}
          rows={2}
          placeholder={t('ai.patentCompose.detail.agent.placeholder')}
          className="min-w-0 flex-1 resize-none rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5 app-text-micro text-app-ink outline-none focus:border-app-accent"
        />
        <button
          type="button"
          onClick={() => void ask(input)}
          disabled={sending}
          className="rounded-md bg-app-accent p-1.5 text-app-accent-fg disabled:opacity-60"
        >
          {sending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Send size={13} />
          )}
        </button>
      </div>
    </aside>
  );
}

// ── Report tab ──────────────────────────────────────────────────────────────
function ReportTab(props: {
  card: ReportCard;
  onCardChange: (card: ReportCard) => void;
  input: string;
  onInputChange: (value: string) => void;
  memo: string;
  onMemoChange: (value: string) => void;
  busy: boolean;
  error: string | null;
  output: string;
  onGenerate: () => void;
  attaching: boolean;
  attachStatus: { filename: string; count: number } | null;
  onAttach: (file: File) => void;
  onClearAttach: () => void;
}) {
  const { t } = useTranslation('apps');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const ratioRef = useRef(0.5);
  const [isWide, setIsWide] = useState(false);
  const [ratio, setRatio] = useState(0.5);

  useEffect(() => {
    const initial = readReportSplit();
    ratioRef.current = initial;
    setRatio(initial);
  }, []);

  // The drag splitter only exists on lg+ (panes stack below that).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(min-width: 1024px)');
    const update = () => setIsWide(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  const startDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const move = (moveEvent: PointerEvent) => {
      const node = containerRef.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      const next = clampSplit((moveEvent.clientX - rect.left) / rect.width);
      ratioRef.current = next;
      setRatio(next);
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      writeReportSplit(ratioRef.current);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
  }, []);

  return (
    <div
      ref={containerRef}
      className="flex h-full min-h-0 flex-col gap-4 p-4 lg:flex-row lg:gap-0"
    >
      <div
        className="flex min-w-0 flex-1 flex-col gap-3 lg:flex-none lg:shrink-0"
        style={isWide ? { width: `${ratio * 100}%` } : undefined}
      >
        <div className="rounded-lg border border-dashed border-app-border bg-app-surface-sidebar p-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="app-text-caption text-app-ink/80">
              {t('ai.patentCompose.report.attach.label')}
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pptx,.pdf,.docx,.xlsx"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) props.onAttach(file);
                event.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={props.attaching}
              className="app-text-control inline-flex items-center gap-1 rounded-md bg-app-accent px-2.5 py-1 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
            >
              {props.attaching ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Paperclip size={13} />
              )}
              {props.attaching
                ? t('ai.patentCompose.report.attach.extracting')
                : t('ai.patentCompose.report.attach.button')}
            </button>
          </div>
          {props.attachStatus ? (
            <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-app-border bg-app-surface px-2.5 py-1.5">
              <span className="app-text-micro truncate text-app-ink">
                <span aria-hidden="true">✅</span>{' '}
                {t('ai.patentCompose.report.attach.done', {
                  filename: props.attachStatus.filename,
                  count: props.attachStatus.count,
                })}
              </span>
              <button
                type="button"
                onClick={props.onClearAttach}
                className="app-text-micro inline-flex shrink-0 items-center gap-0.5 text-app-ink/55 hover:text-app-accent"
              >
                <X size={11} />
                {t('ai.patentCompose.report.attach.remove')}
              </button>
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {REPORT_CARDS.map((card) => (
            <button
              key={card}
              type="button"
              onClick={() => props.onCardChange(card)}
              className={cn(
                'app-text-control rounded-md border px-2.5 py-1.5 transition-colors',
                props.card === card
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border bg-app-surface text-app-ink hover:border-app-accent',
              )}
            >
              {REPORT_EMOJI[card]}{' '}
              {t(`ai.patentCompose.report.cards.${card}.label`)}
            </button>
          ))}
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-1">
          <span className="app-text-caption text-app-ink">
            {t('ai.patentCompose.report.contentLabel')}{' '}
            <span className="text-app-ink/55">
              {t('ai.patentCompose.report.contentHint')}
            </span>
          </span>
          <textarea
            value={props.input}
            onChange={(event) => props.onInputChange(event.target.value)}
            placeholder={t('ai.patentCompose.report.placeholder')}
            className="min-h-0 flex-1 resize-none rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2.5 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="app-text-caption text-app-ink">
            {t('ai.patentCompose.report.memo.label')}{' '}
            <span className="text-app-ink/55">
              {t('ai.patentCompose.report.memo.hint')}
            </span>
          </span>
          <textarea
            value={props.memo}
            onChange={(event) => props.onMemoChange(event.target.value)}
            placeholder={t('ai.patentCompose.report.memo.placeholder')}
            rows={3}
            className="resize-none rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
          />
        </div>
        <button
          type="button"
          onClick={props.onGenerate}
          disabled={props.busy}
          className="app-text-control inline-flex items-center justify-center gap-1.5 rounded-lg bg-app-accent px-3 py-2.5 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
        >
          {props.busy ? <Loader2 size={14} className="animate-spin" /> : null}
          {t('ai.patentCompose.report.generate')}
        </button>
        {props.error ? (
          <p
            role="alert"
            className="app-text-body-sm text-[var(--ui-color-danger)]"
          >
            {props.error}
          </p>
        ) : null}
      </div>

      {isWide ? (
        <div
          role="separator"
          aria-orientation="vertical"
          onPointerDown={startDrag}
          className="mx-1.5 w-1.5 shrink-0 cursor-col-resize self-stretch rounded-full bg-app-border transition-colors hover:bg-app-accent"
        />
      ) : null}
      <div className="flex min-h-[20rem] min-w-0 shrink-0 flex-col lg:min-h-0 lg:flex-1 lg:shrink">
        <OutputPanel text={props.output} busy={props.busy} card={props.card} />
      </div>
    </div>
  );
}

function OutputPanel({
  text,
  busy,
  card,
}: {
  text: string;
  busy: boolean;
  card: ReportCard;
}) {
  const { t } = useTranslation('apps');

  const downloadHtml = useCallback(() => {
    if (!text) return;
    const titleLabel = t(`ai.patentCompose.report.cards.${card}.label`);
    const dateStr = new Date().toISOString().slice(0, 10);
    const html = buildReportHtml(text, titleLabel, dateStr);
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${titleLabel}_${dateStr}.html`;
    document.body.appendChild(anchor);
    anchor.click();
    window.setTimeout(() => {
      URL.revokeObjectURL(url);
      anchor.remove();
    }, 1000);
  }, [card, t, text]);

  return (
    <div className="flex h-full min-h-[20rem] flex-col rounded-lg border border-app-border bg-app-surface p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <p className="app-text-caption font-semibold text-app-ink">
          {t('ai.patentCompose.report.outputTitle')}
        </p>
        {text ? (
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() =>
                void navigator.clipboard.writeText(stripReportMarkdown(text))
              }
              className="app-text-micro inline-flex items-center gap-1 text-app-ink/55 transition-colors hover:text-app-accent"
            >
              <Copy size={12} />
              {t('ai.patentCompose.report.copy')}
            </button>
            <button
              type="button"
              onClick={downloadHtml}
              title={t('ai.patentCompose.report.htmlDownloadHint')}
              className="app-text-micro inline-flex items-center gap-1 text-app-ink/55 transition-colors hover:text-app-accent"
            >
              <Download size={12} />
              {t('ai.patentCompose.report.htmlDownload')}
            </button>
          </div>
        ) : null}
      </div>
      {busy && !text ? (
        <div className="flex flex-1 items-center justify-center text-app-ink/55">
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : text ? (
        <div className="flex-1 overflow-y-auto pr-1">
          <ReportContent text={text} />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto app-text-body-sm text-app-ink/55">
          {t('ai.patentCompose.report.outputEmpty')}
        </div>
      )}
    </div>
  );
}

// ── Query tab ───────────────────────────────────────────────────────────────
// Accent left-bar section header — matches the report card style.
function QuerySectionHeader({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2 mt-4 rounded-r-lg border-l-4 border-app-accent bg-app-surface-sidebar px-3.5 py-2 app-text-body-sm font-bold tracking-tight text-app-accent">
      {children}
    </div>
  );
}

type ChipTone = 'kr' | 'en' | 'syn-kr' | 'syn-en';
const CHIP_TONE: Record<ChipTone, string> = {
  kr: 'border-app-accent/30 bg-app-accent/10 text-app-accent',
  en: 'border-app-success/30 bg-app-success/10 text-app-success',
  'syn-kr': 'border-app-border bg-app-surface italic text-app-ink/60',
  'syn-en': 'border-emerald-500/20 bg-app-success/5 italic text-app-success/80',
};

function KeywordChip({
  tone,
  children,
}: {
  tone: ChipTone;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        'app-text-micro rounded-full border px-2 py-0.5',
        CHIP_TONE[tone],
      )}
    >
      {children}
    </span>
  );
}

// Colour the boolean operators in a KIPRIS formula (AND/OR/NEAR).
function FormulaText({ value }: { value: string }) {
  const parts = value.split(/(\bAND\b|\bOR\b|\bNEAR\b)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (part === 'AND')
          return (
            <span key={index} className="font-bold text-app-danger">
              {part}
            </span>
          );
        if (part === 'OR')
          return (
            <span key={index} className="font-bold text-app-warning">
              {part}
            </span>
          );
        if (part === 'NEAR')
          return (
            <span key={index} className="font-bold text-app-accent">
              {part}
            </span>
          );
        return <Fragment key={index}>{part}</Fragment>;
      })}
    </>
  );
}

function QueryTab(props: {
  input: string;
  onInputChange: (value: string) => void;
  busy: boolean;
  error: string | null;
  result: SearchQueryResult | null;
  onGenerate: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="grid h-full gap-4 p-4 lg:grid-cols-2">
      <div className="flex flex-col gap-3">
        <textarea
          value={props.input}
          onChange={(event) => props.onInputChange(event.target.value)}
          placeholder={t('ai.patentCompose.query.placeholder')}
          rows={14}
          className="min-h-0 flex-1 resize-none rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2.5 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
        />
        <button
          type="button"
          onClick={props.onGenerate}
          disabled={props.busy}
          className="app-text-control inline-flex items-center justify-center gap-1.5 rounded-lg bg-app-accent px-3 py-2.5 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
        >
          {props.busy ? <Loader2 size={14} className="animate-spin" /> : null}
          {t('ai.patentCompose.query.generate')}
        </button>
        {props.error ? (
          <p
            role="alert"
            className="app-text-body-sm text-[var(--ui-color-danger)]"
          >
            {props.error}
          </p>
        ) : null}
      </div>

      <div className="min-h-[20rem] overflow-y-auto rounded-lg border border-app-border bg-app-surface p-3">
        {props.result ? (
          <div className="[&>*:first-child]:mt-0">
            {props.result.tech_summary ? (
              <>
                <QuerySectionHeader>
                  {t('ai.patentCompose.query.techSummary')}
                </QuerySectionHeader>
                <p className="my-2 app-text-body-sm leading-relaxed text-app-ink/80">
                  {props.result.tech_summary}
                </p>
              </>
            ) : null}

            {props.result.keyword_groups.length > 0 ? (
              <>
                <QuerySectionHeader>
                  {t('ai.patentCompose.query.keywords')}
                </QuerySectionHeader>
                <div className="space-y-2">
                  {props.result.keyword_groups.map((group) => {
                    const hasSynonyms =
                      group.synonyms_kr.length > 0 ||
                      group.synonyms_en.length > 0;
                    return (
                      <div
                        key={group.element}
                        className="rounded-lg border border-app-border bg-app-surface-sidebar p-3"
                      >
                        <p className="app-text-body-sm font-semibold text-app-ink">
                          {group.element}
                        </p>
                        {group.description ? (
                          <p className="mt-0.5 app-text-micro text-app-ink/55">
                            {group.description}
                          </p>
                        ) : null}
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {group.keywords_kr.map((keyword, index) => (
                            <KeywordChip
                              key={`kr-${keyword}-${index}`}
                              tone="kr"
                            >
                              {keyword}
                            </KeywordChip>
                          ))}
                          {group.keywords_en.map((keyword, index) => (
                            <KeywordChip
                              key={`en-${keyword}-${index}`}
                              tone="en"
                            >
                              {keyword}
                            </KeywordChip>
                          ))}
                        </div>
                        {hasSynonyms ? (
                          <>
                            <div className="mt-2 border-t border-dashed border-app-border pt-2 app-text-micro text-app-ink/55">
                              {t('ai.patentCompose.query.synonyms')}
                            </div>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              {group.synonyms_kr.map((keyword, index) => (
                                <KeywordChip
                                  key={`skr-${keyword}-${index}`}
                                  tone="syn-kr"
                                >
                                  {keyword}
                                </KeywordChip>
                              ))}
                              {group.synonyms_en.map((keyword, index) => (
                                <KeywordChip
                                  key={`sen-${keyword}-${index}`}
                                  tone="syn-en"
                                >
                                  {keyword}
                                </KeywordChip>
                              ))}
                            </div>
                          </>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </>
            ) : null}

            {props.result.ipc_codes.length > 0 ? (
              <>
                <QuerySectionHeader>
                  {t('ai.patentCompose.query.ipcCodes')}
                </QuerySectionHeader>
                <div className="flex flex-wrap gap-1.5">
                  {props.result.ipc_codes.map((code) => (
                    <span
                      key={code}
                      className="app-text-micro rounded-full border border-app-border px-2 py-0.5 font-mono text-app-ink/80"
                    >
                      {code}
                    </span>
                  ))}
                </div>
              </>
            ) : null}

            {props.result.search_formula ? (
              <>
                <div className="mb-2 mt-4 flex items-center justify-between rounded-r-lg border-l-4 border-app-accent bg-app-surface-sidebar px-3.5 py-2">
                  <span className="app-text-body-sm font-bold tracking-tight text-app-accent">
                    {t('ai.patentCompose.query.formula')}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      void navigator.clipboard.writeText(
                        props.result?.search_formula ?? '',
                      )
                    }
                    className="app-text-micro inline-flex items-center gap-1 text-app-ink/55 transition-colors hover:text-app-accent"
                  >
                    <Copy size={12} />
                    {t('ai.patentCompose.report.copy')}
                  </button>
                </div>
                <pre className="whitespace-pre-wrap break-words rounded-md border border-app-border bg-app-surface-sidebar p-2.5 app-text-micro leading-relaxed text-app-ink/90">
                  <FormulaText value={props.result.search_formula} />
                </pre>
              </>
            ) : null}
          </div>
        ) : (
          <p className="app-text-body-sm text-app-ink/55">
            {t('ai.patentCompose.query.empty')}
          </p>
        )}
      </div>
    </div>
  );
}
