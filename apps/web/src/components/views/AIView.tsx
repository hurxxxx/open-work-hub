import { motion } from 'motion/react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getLlmHealth,
  type AiBackendMode,
  type AiChatMessage,
  type LlmHealthResponse,
} from '@/src/domains/ai/ai-api';
import { useChatStream } from '@/src/domains/ai/useChatStream';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { resolveToolInvocationHref } from '@/src/domains/workspaces/workspace-utils';
import { useWorkspaceBootstrap } from '@/src/domains/workspaces/workspaces-api';
import { NAV_ITEMS } from '@/src/constants';
import { ChatThread } from '@/src/components/views/chat/ChatThread';
import { ApprovalModal } from '@/src/components/views/chat/ApprovalModal';
import { ToolCallCard } from '@/src/components/views/chat/ToolCallCard';
import { ChatTopBar } from '@/src/components/views/chat/ChatTopBar';
import { ChatComposer } from '@/src/components/views/chat/ChatComposer';
import { EmptyState } from '@/src/components/views/chat/EmptyState';
import type { ChatTurn } from '@/src/components/views/chat/MessageBubble';
import type {
  PendingApproval,
  ToolCallBuffer,
} from '@/src/domains/ai/agent-events';
import type { NavItem } from '@/src/constants';

const AI_BACKEND_MODE_STORAGE_KEY = 'aidoo.ai.backendMode';

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

export const AIView = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  // TODO: AppContent already fetches this — lift bootstrap data into a
  // WorkspaceBootstrapContext so AIView (and other views) can reuse it instead
  // of issuing a second GET /api/v1/workspaces/:slug/bootstrap on every mount.
  // Until then the slash-menu falls back to the static NAV_ITEMS AI slice
  // during the loading window.
  const workspaceBootstrap = useWorkspaceBootstrap(token, workspaceSlug);
  const [health, setHealth] = useState<LlmHealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [backendMode, setBackendMode] = useState<AiBackendMode>(
    readInitialBackendMode,
  );
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [chatError, setChatError] = useState<string | null>(null);
  const [pendingUserTurnId, setPendingUserTurnId] = useState<string | null>(
    null,
  );
  const [pendingUserInput, setPendingUserInput] = useState('');
  const chat = useChatStream(token);
  const isSending = chat.state.status === 'streaming';
  const finalizedToolCalls = useMemo(
    () => turns.flatMap((turn) => turn.toolCalls ?? []),
    [turns],
  );
  const finalizedApprovals = useMemo(
    () => turns.flatMap((turn) => turn.pendingApprovals ?? []),
    [turns],
  );
  const visibleToolCalls = useMemo(
    () => mergeToolCalls(finalizedToolCalls, chat.state.toolCalls),
    [chat.state.toolCalls, finalizedToolCalls],
  );
  const visibleApprovals = useMemo(
    () => mergeApprovals(finalizedApprovals, chat.state.pendingApprovals),
    [chat.state.pendingApprovals, finalizedApprovals],
  );

  // Slash-command candidates: merge workspace bootstrap nav (filters out
  // disabled/unauthorized tools) with the local NAV_ITEMS registry (supplies
  // icons + full metadata). Falls back to the local AI-only list while
  // bootstrap is still loading so the menu stays usable.
  const slashCommandItems = useMemo(() => {
    const registry = new Map(NAV_ITEMS.map((item) => [item.id, item]));
    const bootstrapNav = workspaceBootstrap.data?.nav ?? null;
    if (!bootstrapNav) {
      return NAV_ITEMS.filter((item) => item.appId === 'ai');
    }
    return bootstrapNav
      .filter((entry) => entry.app_id === 'ai')
      .map((entry) => {
        const localItem = registry.get(entry.id);
        if (!localItem) {
          return null;
        }
        return {
          ...localItem,
          title: entry.title,
          category: entry.category,
        };
      })
      .filter((item): item is NavItem => item !== null);
  }, [workspaceBootstrap.data]);

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

  function handleSelectTool(item: NavItem) {
    // Tool invocation semantics: plain AI items land on their /tool/:id page,
    // deep-links (linkAppId, absolutePath) honor their NavItem metadata.
    navigate(resolveToolInvocationHref(item, workspaceSlug, user));
  }

  function handleSubmit() {
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

    // No client-side system message: the API prepends its own AGENT_SYSTEM_PROMPT
    // (apps/api/src/aidoo_api/domains/ai/agent.py) on every turn. Sending one
    // here produced two consecutive system messages, which providers like
    // mlx-lm reject with "System message must be at the beginning" (HTTP 404).
    const messages: AiChatMessage[] = nextTurns.map((turn) => ({
      role: turn.role,
      content: turn.content,
    }));

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
      <section className="flex min-h-[640px] flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface">
        <ChatTopBar
          title="업무 챗봇"
          backendMode={backendMode}
          onBackendModeChange={setBackendMode}
          health={health}
          healthError={healthError}
          isCheckingHealth={isCheckingHealth}
          onRefreshHealth={refreshHealth}
          canRefresh={Boolean(token)}
        />

        {turns.length === 0 && !isSending ? (
          <EmptyState
            composer={
              <ChatComposer
                input={input}
                onInputChange={setInput}
                onSubmit={handleSubmit}
                onAbort={() => chat.abort()}
                isSending={isSending}
                isStreaming={chat.state.transport === 'stream'}
                chatError={chatError}
                onSelectTool={handleSelectTool}
                toolItems={slashCommandItems}
                autoFocus
              />
            }
          />
        ) : (
          <>
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
            {visibleToolCalls.map((call) => (
              <ToolCallCard key={call.call_id} call={call} />
            ))}
            {visibleApprovals.map((approval) => (
              <ApprovalModal key={approval.approval_id} approval={approval} />
            ))}
            <div className="border-t border-app-border bg-app-surface p-4">
              <ChatComposer
                input={input}
                onInputChange={setInput}
                onSubmit={handleSubmit}
                onAbort={() => chat.abort()}
                isSending={isSending}
                isStreaming={chat.state.transport === 'stream'}
                chatError={chatError}
                onSelectTool={handleSelectTool}
                toolItems={slashCommandItems}
              />
            </div>
          </>
        )}
      </section>
    </motion.div>
  );
};

function mergeToolCalls(
  finalized: ToolCallBuffer[],
  live: ToolCallBuffer[],
): ToolCallBuffer[] {
  const merged = new Map<string, ToolCallBuffer>();
  for (const call of [...finalized, ...live]) {
    merged.set(call.call_id, call);
  }
  return Array.from(merged.values());
}

function mergeApprovals(
  finalized: PendingApproval[],
  live: PendingApproval[],
): PendingApproval[] {
  const merged = new Map<string, PendingApproval>();
  for (const approval of [...finalized, ...live]) {
    merged.set(approval.approval_id, approval);
  }
  return Array.from(merged.values());
}
