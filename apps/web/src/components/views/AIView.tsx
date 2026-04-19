import { Link, useParams } from 'react-router-dom';
import { motion } from 'motion/react';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  ChevronRight,
  Loader2,
  RefreshCcw,
  Send,
  Square,
} from 'lucide-react';
import { NAV_ITEMS } from '@/src/constants';
import {
  getLlmHealth,
  type AiBackendMode,
  type AiChatMessage,
  type LlmHealthResponse,
  type LlmPoolHealthResponse,
} from '@/src/domains/ai/ai-api';
import { useChatStream } from '@/src/domains/ai/useChatStream';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { useWorkspaceBootstrap } from '@/src/domains/workspaces/workspaces-api';
import { ChatThread } from '@/src/components/views/chat/ChatThread';
import { ApprovalModal } from '@/src/components/views/chat/ApprovalModal';
import { ToolCallCard } from '@/src/components/views/chat/ToolCallCard';
import type { ChatTurn } from '@/src/components/views/chat/MessageBubble';

const INITIAL_TURNS: ChatTurn[] = [
  {
    id: 'welcome',
    role: 'assistant',
    content: '무엇을 도와드릴까요?',
  },
];

const AI_BACKEND_MODE_STORAGE_KEY = 'aidoo.ai.backendMode';

const BACKEND_OPTIONS: Array<{
  value: AiBackendMode;
  label: string;
  description: string;
}> = [
  { value: 'auto', label: '자동', description: '정책 기반 라우팅' },
  { value: 'local', label: '로컬', description: 'local 풀 고정' },
];

function readInitialBackendMode(): AiBackendMode {
  if (typeof window === 'undefined') {
    return 'auto';
  }

  const savedMode = window.localStorage.getItem(AI_BACKEND_MODE_STORAGE_KEY);
  if (savedMode === 'auto' || savedMode === 'local') {
    return savedMode;
  }

  return 'auto';
}

function formatBackendMode(mode: AiBackendMode): string {
  if (mode === 'local') {
    return '로컬 고정';
  }

  return '자동';
}

function formatHealth(
  health: LlmHealthResponse | null,
  backendMode: AiBackendMode,
): string {
  const modeLabel = formatBackendMode(backendMode);
  if (!health) {
    return `${modeLabel}: 모델 상태 확인 중`;
  }

  if (backendMode === 'local') {
    return `${modeLabel}: ${health.local.canonical_model}`;
  }

  return `${modeLabel}: 정책 기반`;
}

function formatHealthDetail(
  health: LlmHealthResponse | null,
  backendMode: AiBackendMode,
): string {
  if (!health) {
    return '상태 점검 중';
  }

  if (backendMode === 'local') {
    return health.local.ready
      ? '로컬 풀만 사용'
      : `로컬 확인 필요: ${health.local.status}`;
  }

  const externalStatus = health.external
    ? health.external.ready
      ? 'external 준비'
      : `external ${health.external.status}`
    : 'external 비활성';
  const localStatus = health.local.ready
    ? 'local 준비'
    : `local ${health.local.status}`;
  return `정책 기반 · ${localStatus} · ${externalStatus}`;
}

function formatBackendStatus(
  backend: LlmPoolHealthResponse | null | undefined,
): string {
  if (!backend) {
    return '확인 안 됨';
  }

  if (backend.ready) {
    return '준비됨';
  }

  return backend.status;
}

function resolveAssistantTurnContent(
  contentBuffer: string,
  options: {
    status: 'done' | 'cancelled' | 'error';
    errorMessage: string | null;
    finishReason: 'stop' | 'length' | 'cancelled' | 'error' | null;
  },
): string {
  const { status, errorMessage, finishReason } = options;
  if (contentBuffer) {
    return contentBuffer;
  }
  if (status === 'cancelled') {
    return '응답이 중단되었습니다.';
  }
  if (status === 'error') {
    return errorMessage ?? '응답 중 오류가 발생했습니다.';
  }
  if (finishReason === 'length') {
    return '응답이 토큰 한도에 도달해 중간에서 잘렸습니다. 질문 범위를 줄이거나 이어서 요청하세요.';
  }
  return '응답을 생성하지 못했습니다.';
}

function BackendStatusRow({
  health,
  label,
}: {
  health: LlmPoolHealthResponse | null | undefined;
  label: string;
}) {
  const ready = Boolean(health?.ready);

  return (
    <div className="flex items-start justify-between gap-3 border-b border-app-border py-2 last:border-b-0">
      <div className="min-w-0">
        <div className="app-text-control-sm text-app-ink">{label}</div>
        <div className="app-text-micro truncate text-gray-500">
          {health?.model ?? '모델 확인 중'}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${ready ? 'bg-emerald-500' : 'bg-amber-500'}`}
        />
        <span className="app-text-micro text-gray-500">
          {formatBackendStatus(health)}
        </span>
      </div>
    </div>
  );
}

export const AIView = () => {
  const { token } = useAuth();
  const { workspaceSlug } = useParams();
  const [health, setHealth] = useState<LlmHealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [backendMode, setBackendMode] = useState<AiBackendMode>(
    readInitialBackendMode,
  );
  const [turns, setTurns] = useState<ChatTurn[]>(INITIAL_TURNS);
  const [input, setInput] = useState('');
  const [chatError, setChatError] = useState<string | null>(null);
  const [pendingUserTurnId, setPendingUserTurnId] = useState<string | null>(
    null,
  );
  const [pendingUserInput, setPendingUserInput] = useState('');
  const chat = useChatStream(token);
  const workspaceBootstrap = useWorkspaceBootstrap(token, workspaceSlug);
  const isSending = chat.state.status === 'streaming';
  const finalizedToolCalls = useMemo(
    () => turns.flatMap((turn) => turn.toolCalls ?? []),
    [turns],
  );
  const finalizedApprovals = useMemo(
    () => turns.flatMap((turn) => turn.pendingApprovals ?? []),
    [turns],
  );

  const aiTools = useMemo(
    () => {
      const registry = new Map(NAV_ITEMS.map((item) => [item.id, item]));
      return (workspaceBootstrap.data?.nav ?? [])
        .filter((item) => item.app_id === 'ai')
        .map((item) => {
          const localItem = registry.get(item.id);
          if (!localItem) {
            return null;
          }
          return {
            ...localItem,
            title: item.title,
            category: item.category,
          };
        })
        .filter((item): item is (typeof NAV_ITEMS)[number] => Boolean(item));
    },
    [workspaceBootstrap.data],
  );

  async function refreshHealth() {
    if (!token) {
      return;
    }

    setIsCheckingHealth(true);
    try {
      const nextHealth = await getLlmHealth(token);
      setHealth(nextHealth);
      setHealthError(null);
    } catch (error) {
      setHealth(null);
      setHealthError(
        error instanceof Error
          ? error.message
          : '모델 상태를 확인하지 못했습니다.',
      );
    } finally {
      setIsCheckingHealth(false);
    }
  }

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;
    getLlmHealth(token)
      .then((nextHealth) => {
        if (!cancelled) {
          setHealth(nextHealth);
          setHealthError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHealth(null);
          setHealthError(
            error instanceof Error
              ? error.message
              : '모델 상태를 확인하지 못했습니다.',
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(AI_BACKEND_MODE_STORAGE_KEY, backendMode);
    }
  }, [backendMode]);

  useEffect(() => {
    const status = chat.state.status;
    if (status === 'idle' || status === 'streaming') {
      return;
    }

    if (status === 'done' || status === 'cancelled' || chat.state.streamOpened) {
      setTurns((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: resolveAssistantTurnContent(chat.state.contentBuffer, {
            status,
            errorMessage: chat.state.errorMessage,
            finishReason: chat.state.finishReason,
          }),
          reasoning: chat.state.reasoningBuffer || undefined,
          reasoningStatus: status,
          finishReason: chat.state.finishReason,
          responseStatus: status === 'done' ? undefined : status,
          provider: chat.state.doneMeta?.provider ?? undefined,
          policy: chat.state.doneMeta?.policy ?? null,
          chosenPool: chat.state.doneMeta?.chosen_pool ?? null,
          decisionReason: chat.state.doneMeta?.decision_reason ?? null,
          forcedLocal: chat.state.doneMeta?.forced_local ?? false,
          piiHits: chat.state.doneMeta?.pii_hits ?? [],
          toolCalls: chat.state.toolCalls,
          pendingApprovals: chat.state.pendingApprovals,
        },
      ]);
      setChatError(null);
      setPendingUserTurnId(null);
      setPendingUserInput('');
      chat.reset();
    } else {
      setChatError(chat.state.errorMessage ?? 'AI 응답에 실패했습니다.');
      if (pendingUserTurnId) {
        setTurns((current) =>
          current.filter((turn) => turn.id !== pendingUserTurnId),
        );
      }
      if (pendingUserInput && !input) {
        setInput(pendingUserInput);
      }
      setPendingUserTurnId(null);
      setPendingUserInput('');
      chat.reset();
    }
    // intentionally excluding chat/pendingUserTurnId/pendingUserInput from deps:
    // the hook's state transitions drive the effect; adding unstable refs to
    // deps would retrigger the commit block.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.state.status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = input.trim();
    if (!trimmed || !token || isSending) {
      return;
    }

    const userTurn: ChatTurn = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    };
    const nextTurns = [...turns, userTurn];
    setTurns(nextTurns);
    setInput('');
    setChatError(null);
    setPendingUserTurnId(userTurn.id);
    setPendingUserInput(trimmed);
    chat.reset();

    const messages: AiChatMessage[] = [
      {
        role: 'system',
        content:
          '너는 두원공조 사내 업무를 돕는 한국어 AI 비서다. 답변은 간결하고 실행 가능하게 작성한다.',
      },
      ...nextTurns
        .filter((turn) => turn.id !== 'welcome')
        .map((turn) => ({
          role: turn.role,
          content: turn.content,
        })),
    ];

    void chat.send({
      messages,
      backend_mode: backendMode,
      temperature: 0.2,
      stream_reasoning: true,
    });
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto flex w-full max-w-7xl flex-col gap-8 p-6 lg:p-8"
    >
      <section className="grid min-h-[640px] grid-cols-1 overflow-hidden rounded-lg border border-app-border bg-app-surface lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-h-[640px] flex-col">
          <header className="flex flex-wrap items-start justify-between gap-4 border-b border-app-border px-5 py-4">
            <div className="space-y-1">
              <h1 className="app-text-title-lg text-app-ink">업무 챗봇</h1>
              <p className="app-text-body-sm text-gray-500 dark:text-gray-400">
                정책에 따라 local 또는 external 풀이 선택됩니다.
              </p>
            </div>
            <div className="rounded-md border border-app-border bg-app-bg px-3 py-2 text-right">
              <div className="app-text-caption text-app-ink">
                {formatHealth(health, backendMode)}
              </div>
              <div className="app-text-micro text-gray-500">
                {healthError ?? formatHealthDetail(health, backendMode)}
              </div>
            </div>
          </header>

          <ChatThread
            turns={turns}
            liveAssistant={
              isSending
                ? {
                    content: chat.state.contentBuffer,
                    reasoning: chat.state.reasoningBuffer,
                    status: chat.state.status,
                  }
                : null
            }
          />
          {finalizedToolCalls.map((call) => (
            <ToolCallCard key={call.call_id} call={call} />
          ))}
          {finalizedApprovals.map((approval) => (
            <ApprovalModal key={approval.approval_id} approval={approval} />
          ))}

          <form
            className="border-t border-app-border bg-app-surface p-4"
            onSubmit={handleSubmit}
          >
            {chatError && (
              <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 app-text-body-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
                {chatError}
              </div>
            )}
            <div className="flex min-h-12 gap-3">
              <textarea
                className="app-text-body-sm min-h-12 flex-1 resize-none rounded-lg border border-app-border bg-app-bg px-4 py-3 text-app-ink outline-none transition-colors placeholder:text-gray-400 focus:border-app-accent"
                disabled={isSending}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="메시지를 입력하세요"
                rows={2}
                value={input}
              />
              {isSending && chat.state.transport === 'stream' ? (
                <button
                  className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg border border-app-border bg-app-surface px-4 text-app-ink transition-colors hover:border-app-accent"
                  onClick={() => chat.abort()}
                  type="button"
                >
                  <Square size={16} />
                  <span className="hidden sm:inline">중단</span>
                </button>
              ) : isSending ? (
                <button
                  className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg border border-app-border bg-app-surface px-4 text-app-ink/70"
                  disabled
                  type="button"
                >
                  <Loader2 size={16} className="animate-spin" />
                  <span className="hidden sm:inline">처리 중</span>
                </button>
              ) : (
                <button
                  className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg bg-app-accent px-4 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={!input.trim()}
                  type="submit"
                >
                  <Send size={16} />
                  <span className="hidden sm:inline">전송</span>
                </button>
              )}
            </div>
          </form>
        </div>

        <aside className="border-t border-app-border bg-app-surface-sidebar p-5 lg:border-l lg:border-t-0">
          <div className="space-y-2">
            <h2 className="app-text-title-md text-app-ink">라우팅 모드</h2>
            <p className="app-text-body-sm text-gray-500 dark:text-gray-400">
              정책 기반 또는 local 고정 모드를 선택합니다.
            </p>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2">
            {BACKEND_OPTIONS.map((option) => (
              <button
                key={option.value}
                className={`min-h-16 rounded-lg border px-2 py-2 text-left transition-colors ${
                  backendMode === option.value
                    ? 'border-app-accent bg-app-bg text-app-ink'
                    : 'border-app-border bg-app-surface text-gray-500 hover:border-app-accent hover:text-app-ink'
                }`}
                onClick={() => setBackendMode(option.value)}
                type="button"
              >
                <span className="block app-text-control-sm">
                  {option.label}
                </span>
                <span className="block app-text-micro">
                  {option.description}
                </span>
              </button>
            ))}
          </div>

          <div className="mt-4 rounded-lg border border-app-border bg-app-surface px-3 py-2">
            <BackendStatusRow health={health?.local} label="Local pool" />
            <BackendStatusRow health={health?.external} label="External pool" />
          </div>

          <button
            className="app-text-control-sm mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-app-border bg-app-surface text-app-ink transition-colors hover:border-app-accent disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!token || isCheckingHealth}
            onClick={refreshHealth}
            type="button"
          >
            <RefreshCcw
              size={15}
              className={isCheckingHealth ? 'animate-spin' : ''}
            />
            상태 새로고침
          </button>

          <div className="mt-8 border-t border-app-border pt-5">
            <div className="space-y-2">
              <h2 className="app-text-title-md text-app-ink">바로가기</h2>
              <p className="app-text-body-sm text-gray-500 dark:text-gray-400">
                자주 쓰는 업무 도구로 이동합니다.
              </p>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-3">
              {aiTools.slice(0, 8).map((item) => (
                <Link
                  key={item.id}
                  to={`/tool/${item.id}`}
                  className="group flex items-center gap-3 rounded-lg border border-app-border bg-app-surface px-3 py-3 no-underline transition-colors hover:border-app-accent"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                    <item.icon size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="app-text-control-sm truncate text-app-ink">
                      {item.title}
                    </div>
                    <div className="app-text-micro truncate text-gray-500">
                      {item.description}
                    </div>
                  </div>
                  <ChevronRight
                    size={16}
                    className="shrink-0 text-gray-500 transition-colors group-hover:text-app-ink"
                  />
                </Link>
              ))}
            </div>
          </div>
        </aside>
      </section>
    </motion.div>
  );
};
