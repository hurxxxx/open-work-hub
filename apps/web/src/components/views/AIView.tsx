import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  ChevronRight,
  Loader2,
  RefreshCcw,
  Send,
  User,
} from 'lucide-react';
import { NAV_ITEMS } from '@/src/constants';
import {
  getLlmHealth,
  sendAiChat,
  type AiBackendMode,
  type AiChatMessage,
  type LlmBackendHealthResponse,
  type LlmHealthResponse,
} from '@/src/domains/ai/ai-api';
import { useAuth } from '@/src/domains/auth/auth-provider';

interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  backend?: string;
  provider?: string;
  fallbackUsed?: boolean;
}

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
  { value: 'auto', label: '자동', description: '로컬 우선' },
  { value: 'local', label: '로컬', description: 'Ollama 고정' },
  { value: 'openrouter', label: 'OpenRouter', description: 'Fallback 고정' },
];

function readInitialBackendMode(): AiBackendMode {
  if (typeof window === 'undefined') {
    return 'auto';
  }

  const savedMode = window.localStorage.getItem(AI_BACKEND_MODE_STORAGE_KEY);
  if (
    savedMode === 'auto' ||
    savedMode === 'local' ||
    savedMode === 'openrouter'
  ) {
    return savedMode;
  }

  return 'auto';
}

function formatBackendMode(mode: AiBackendMode): string {
  if (mode === 'local') {
    return '로컬 Ollama';
  }

  if (mode === 'openrouter') {
    return 'OpenRouter';
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

  return `${modeLabel}: ${health.canonical_model}`;
}

function formatHealthDetail(
  health: LlmHealthResponse | null,
  backendMode: AiBackendMode,
): string {
  if (!health) {
    return '상태 점검 중';
  }

  if (backendMode === 'local') {
    return health.primary.ready
      ? '로컬 Ollama 사용'
      : `로컬 확인 필요: ${health.primary.status}`;
  }

  if (backendMode === 'openrouter') {
    return health.fallback?.ready
      ? 'OpenRouter 사용'
      : `OpenRouter 확인 필요: ${health.fallback?.status ?? 'not_configured'}`;
  }

  if (health.active_backend === 'fallback') {
    return '로컬 모델 장애, OpenRouter fallback 사용 중';
  }

  if (health.primary.ready) {
    return health.fallback?.ready
      ? 'Ollama 연결됨, fallback 대기'
      : 'Ollama 연결됨';
  }

  return health.detail ?? 'LLM 연결 확인 필요';
}

function formatBackendStatus(
  backend: LlmBackendHealthResponse | null | undefined,
): string {
  if (!backend) {
    return '확인 안 됨';
  }

  if (backend.ready) {
    return '준비됨';
  }

  return backend.status;
}

function BackendStatusRow({
  health,
  label,
}: {
  health: LlmBackendHealthResponse | null | undefined;
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
  const [health, setHealth] = useState<LlmHealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [backendMode, setBackendMode] = useState<AiBackendMode>(
    readInitialBackendMode,
  );
  const [turns, setTurns] = useState<ChatTurn[]>(INITIAL_TURNS);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const aiTools = useMemo(
    () => NAV_ITEMS.filter((item) => item.appId === 'ai'),
    [],
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
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [turns, isSending]);

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
    setIsSending(true);
    setChatError(null);

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

    try {
      const response = await sendAiChat(
        {
          messages,
          backend_mode: backendMode,
          max_tokens: 1024,
          temperature: 0.2,
          reasoning_effort: 'none',
        },
        token,
      );
      setTurns((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: response.content || '응답을 생성하지 못했습니다.',
          backend: response.backend,
          provider: response.provider,
          fallbackUsed: response.fallback_used,
        },
      ]);
    } catch (error) {
      setChatError(
        error instanceof Error
          ? error.message
          : 'AI 응답을 가져오지 못했습니다.',
      );
      setTurns((current) => current.filter((turn) => turn.id !== userTurn.id));
      setInput(trimmed);
    } finally {
      setIsSending(false);
    }
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
                질문을 입력하면 로컬 Qwen 모델이 답합니다.
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

          <div
            ref={scrollRef}
            className="custom-scrollbar flex-1 space-y-4 overflow-y-auto bg-app-bg px-5 py-5"
          >
            {turns.map((turn) => (
              <div
                key={turn.id}
                className={`flex gap-3 ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {turn.role === 'assistant' && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
                    <Bot size={16} />
                  </div>
                )}
                <div
                  className={`max-w-[min(720px,80%)] rounded-lg border px-4 py-3 app-text-body-sm leading-relaxed ${
                    turn.role === 'user'
                      ? 'border-app-accent bg-app-accent text-white'
                      : 'border-app-border bg-app-surface text-app-ink'
                  }`}
                >
                  <p className="m-0 whitespace-pre-wrap break-words">
                    {turn.content}
                  </p>
                  {turn.role === 'assistant' && turn.backend && (
                    <div className="mt-2 app-text-micro text-gray-500">
                      {turn.backend === 'fallback' ? 'OpenRouter' : 'Ollama'}{' '}
                      응답
                      {turn.fallbackUsed ? ' · fallback' : ''}
                    </div>
                  )}
                </div>
                {turn.role === 'user' && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-gray-500">
                    <User size={16} />
                  </div>
                )}
              </div>
            ))}
            {isSending && (
              <div className="flex items-center gap-3 text-gray-500">
                <div className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
                  <Loader2 size={16} className="animate-spin" />
                </div>
                <span className="app-text-body-sm">답변 작성 중</span>
              </div>
            )}
          </div>

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
              <button
                className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg bg-app-accent px-4 text-white transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!input.trim() || isSending}
                type="submit"
              >
                <Send size={16} />
                <span className="hidden sm:inline">전송</span>
              </button>
            </div>
          </form>
        </div>

        <aside className="border-t border-app-border bg-app-surface-sidebar p-5 lg:border-l lg:border-t-0">
          <div className="space-y-2">
            <h2 className="app-text-title-md text-app-ink">모델 경로</h2>
            <p className="app-text-body-sm text-gray-500 dark:text-gray-400">
              응답 경로를 선택합니다.
            </p>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2">
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
            <BackendStatusRow health={health?.primary} label="로컬 Ollama" />
            <BackendStatusRow health={health?.fallback} label="OpenRouter" />
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
            로컬 다시 확인
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
