import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, ChevronRight, Loader2, Send, User } from 'lucide-react';
import { NAV_ITEMS } from '@/src/constants';
import {
  getLlmHealth,
  sendAiChat,
  type AiChatMessage,
  type LlmHealthResponse,
} from '@/src/domains/ai/ai-api';
import { useAuth } from '@/src/domains/auth/auth-provider';

interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

const INITIAL_TURNS: ChatTurn[] = [
  {
    id: 'welcome',
    role: 'assistant',
    content: '무엇을 도와드릴까요?',
  },
];

function formatHealth(health: LlmHealthResponse | null): string {
  if (!health) {
    return '모델 상태 확인 중';
  }

  if (health.ready) {
    return `${health.model} 준비됨`;
  }

  return '모델 확인 필요';
}

export const AIView = () => {
  const { token } = useAuth();
  const [health, setHealth] = useState<LlmHealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>(INITIAL_TURNS);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const aiTools = useMemo(
    () => NAV_ITEMS.filter((item) => item.appId === 'ai'),
    [],
  );

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
                {formatHealth(health)}
              </div>
              <div className="app-text-micro text-gray-500">
                {healthError ??
                  (health?.ready ? 'Ollama 연결됨' : '상태 점검 중')}
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
        </aside>
      </section>
    </motion.div>
  );
};
