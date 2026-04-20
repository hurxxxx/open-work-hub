import { motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  getLlmHealth,
  type AiBackendMode,
  type AiChatMessage,
  type LlmHealthResponse,
} from '@/src/domains/ai/ai-api';
import {
  CONVERSATIONS_UPDATED_EVENT,
  getConversation,
  type ConversationDetail,
  type ConversationTurn as ApiConversationTurn,
} from '@/src/domains/ai/conversations-api';
import { useChatStream } from '@/src/domains/ai/useChatStream';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { resolveToolInvocationHref } from '@/src/domains/workspaces/workspace-utils';
import { useWorkspaceBootstrapContext } from '@/src/domains/workspaces/workspace-bootstrap-context';
import { NAV_ITEMS } from '@/src/constants';
import { ChatThread } from '@/src/components/views/chat/ChatThread';
import { ApprovalModal } from '@/src/components/views/chat/ApprovalModal';
import { ArtifactPanel } from '@/src/components/views/chat/ArtifactPanel';
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
    hasArtifacts: boolean;
  },
): string {
  const { status, errorMessage, finishReason, hasArtifacts } = options;
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
  // A successful response that streamed only artifacts has no chat-bubble
  // text — render an empty string so the message area shows the artifact
  // card alone instead of a bogus "failed" placeholder.
  if (hasArtifacts) {
    return '';
  }
  return '응답을 생성하지 못했습니다.';
}

export const AIView = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  // `c` query param is the durable source of truth for which persisted
  // conversation this tab is showing. The sidebar navigates to
  // `/w/:slug/ai?c=<id>` to switch threads; the bare `/w/:slug/ai` path
  // opens a fresh chat. Stream-created conversations write themselves back
  // into this param so a page refresh resumes the same thread.
  const routeConversationId = searchParams.get('c');
  // `a` query param tracks which artifact's side panel is open. Bookmarks
  // and page refreshes resume with the same panel visible; closing the
  // panel clears the param via `handleCloseArtifact`.
  const routeArtifactId = searchParams.get('a');
  // Read bootstrap state from the shell context (AppContent already fetched
  // it). Previously AIView issued its own GET /api/v1/workspaces/:slug/bootstrap
  // on every mount, which also briefly fell back to the full static NAV_ITEMS
  // slice in the slash menu while the duplicate request was in flight.
  const workspaceBootstrap = useWorkspaceBootstrapContext();
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
  // Only tracks a conversation id once the view can safely append to it:
  // either hydration succeeded for `?c=` or the current stream emitted
  // `conversation_attached`. This avoids writing into an existing thread
  // before its history has been loaded.
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const chat = useChatStream(token);
  const isSending = chat.state.status === 'streaming';
  const isConversationReady =
    routeConversationId === null || activeConversationId === routeConversationId;
  const isComposerDisabled =
    isSending || isLoadingConversation || !isConversationReady;
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

  // Hydrate turns whenever the URL conversation changes. Clearing `c` (from
  // the sidebar "+ 새 대화" action, say) resets the thread to an empty state;
  // setting it to a new id fetches the persisted turns so the thread renders
  // identically to what the user saw live. Guarded by token so we don't fire
  // a fetch before auth bootstrap completes.
  const abortHydrateRef = useRef<AbortController | null>(null);
  const skipHydrationConversationIdRef = useRef<string | null>(null);
  useEffect(() => {
    abortHydrateRef.current?.abort();

    if (
      routeConversationId &&
      routeConversationId === skipHydrationConversationIdRef.current
    ) {
      skipHydrationConversationIdRef.current = null;
      setActiveConversationId(routeConversationId);
      setChatError(null);
      setIsLoadingConversation(false);
      return;
    }

    setPendingUserTurnId(null);
    setPendingUserInput('');
    setInput('');
    chat.reset();

    if (!routeConversationId) {
      setActiveConversationId(null);
      setTurns([]);
      setChatError(null);
      setIsLoadingConversation(false);
      return;
    }

    setTurns([]);
    setActiveConversationId(null);
    setChatError(null);

    if (!token) {
      setIsLoadingConversation(false);
      return;
    }

    const controller = new AbortController();
    abortHydrateRef.current = controller;
    setIsLoadingConversation(true);
    getConversation(token, routeConversationId)
      .then((detail) => {
        if (controller.signal.aborted) {
          return;
        }
        setTurns(detailToTurns(detail));
        setActiveConversationId(detail.id);
        setChatError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setTurns([]);
        setActiveConversationId(null);
        setChatError(
          error instanceof Error
            ? error.message
            : '대화 기록을 불러오지 못했습니다.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingConversation(false);
        }
      });

    return () => {
      controller.abort();
    };
    // `workspaceSlug` is part of the deps because a same-mounted AIView
    // can see the workspace change via client-side routing (e.g. switching
    // `/w/<old>/ai?c=<id>` → `/w/<new>/ai?c=<id>`). Without it, the old
    // workspace's turns would linger under the new slug.
    // chat.reset is stable (useCallback in hook); excluded from deps to avoid
    // re-firing the hydration on every chat state transition.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeConversationId, token, workspaceSlug]);

  // When a stream lands a brand-new conversation id (first persisted turn
  // on an empty URL), push it back into `?c=` so a refresh or a bookmark
  // resumes the same thread. Uses replace so the history doesn't grow an
  // extra entry per new chat.
  useEffect(() => {
    const streamedId = chat.state.conversationId;
    if (!streamedId || streamedId === routeConversationId) {
      return;
    }
    setActiveConversationId(streamedId);
    skipHydrationConversationIdRef.current = streamedId;
    // Read the live URL rather than the hook's snapshot so a sibling
    // effect that just wrote `?a=<artifact>` in the same render tick
    // doesn't get clobbered when this one writes `?c=<conversation>`.
    const next = new URLSearchParams(
      typeof window === 'undefined' ? '' : window.location.search,
    );
    next.set('c', streamedId);
    setSearchParams(next, { replace: true });
  }, [
    chat.state.conversationId,
    routeConversationId,
    searchParams,
    setSearchParams,
  ]);

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
            hasArtifacts: chat.state.artifacts.length > 0,
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
          artifacts: chat.state.artifacts,
        },
      ]);
      setChatError(null);
      setPendingUserTurnId(null);
      setPendingUserInput('');
      // Notify the sidebar that this conversation's `updated_at` just
      // bumped on the server. Follow-up replies keep the same `?c=` so
      // the sidebar's URL-based effect wouldn't refetch otherwise.
      if (typeof window !== 'undefined' && chat.state.conversationId) {
        window.dispatchEvent(
          new CustomEvent(CONVERSATIONS_UPDATED_EVENT, {
            detail: { conversationId: chat.state.conversationId },
          }),
        );
      }
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

  // Gather every artifact the thread knows about — both persisted (on
  // finalized turns) and live (from the in-flight stream) — so the side
  // panel can resolve its active id regardless of where the artifact lives.
  const allArtifacts = useMemo(() => {
    const entries: { id: string; type: string; title: string | null; content: string; status: 'open' | 'closed' }[] = [];
    for (const turn of turns) {
      if (!turn.artifacts) continue;
      for (const artifact of turn.artifacts) {
        entries.push({
          id: artifact.id,
          type: artifact.type,
          title: artifact.title ?? null,
          content: artifact.content,
          status: artifact.status,
        });
      }
    }
    for (const artifact of chat.state.artifacts) {
      entries.push(artifact);
    }
    return entries;
  }, [chat.state.artifacts, turns]);

  const activeArtifact = useMemo(() => {
    if (!routeArtifactId) {
      return null;
    }
    return allArtifacts.find((entry) => entry.id === routeArtifactId) ?? null;
  }, [allArtifacts, routeArtifactId]);

  // Auto-open the first artifact the current stream produces so the user
  // doesn't have to hunt for the side panel. Fires at most once per new
  // artifact; if the user closes the panel, a subsequent artifact is
  // tracked as the new "latest" and reopens — matching Claude's pattern.
  const lastAutoOpenedArtifactRef = useRef<string | null>(null);
  useEffect(() => {
    const live = chat.state.artifacts;
    if (live.length === 0) {
      return;
    }
    const latest = live[live.length - 1];
    if (
      lastAutoOpenedArtifactRef.current === latest.id ||
      routeArtifactId === latest.id
    ) {
      return;
    }
    lastAutoOpenedArtifactRef.current = latest.id;
    // Read the live URL rather than the hook's `searchParams` snapshot:
    // the `conversation_attached` effect can fire in the same render tick
    // and write `?c=<id>`. Cloning the pre-update snapshot here would
    // drop that value and strand new threads without a persisted id.
    const next = new URLSearchParams(
      typeof window === 'undefined' ? '' : window.location.search,
    );
    next.set('a', latest.id);
    setSearchParams(next, { replace: true });
  }, [chat.state.artifacts, routeArtifactId, searchParams, setSearchParams]);

  const handleOpenArtifact = (artifactId: string) => {
    if (artifactId === routeArtifactId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set('a', artifactId);
    setSearchParams(next, { replace: false });
  };

  const handleCloseArtifact = () => {
    if (!routeArtifactId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('a');
    setSearchParams(next, { replace: false });
  };

  function handleSelectTool(item: NavItem) {
    // Tool invocation semantics: plain AI items land on their /tool/:id page,
    // deep-links (linkAppId, absolutePath) honor their NavItem metadata.
    navigate(resolveToolInvocationHref(item, workspaceSlug, user));
  }

  function handleSubmit() {
    const trimmed = input.trim();
    if (!trimmed || !token || isSending || !isConversationReady) {
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
      content: serializeTurnForModel(turn),
    }));

    void chat.send({
      messages,
      backend_mode: backendMode,
      temperature: 0.2,
      stream_reasoning: true,
      // Turn on server-side persistence once the user submits anything. The
      // backend returns a conversation_id via the `conversation_attached`
      // envelope which we capture in chat.state and thread back on follow-ups
      // so the whole thread lands on one Conversation row.
      persist: true,
      conversation_id: activeConversationId ?? undefined,
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
                isDisabled={isComposerDisabled}
                onSelectTool={handleSelectTool}
                toolItems={slashCommandItems}
                placeholder={
                  isLoadingConversation
                    ? '대화를 불러오는 중입니다.'
                    : !isConversationReady
                      ? '이 대화를 열 수 없습니다. 새 대화를 시작하거나 다른 대화를 선택하세요.'
                      : undefined
                }
                autoFocus
              />
            }
            greeting={
              isLoadingConversation
                ? '대화를 불러오는 중입니다.'
                : undefined
            }
            subline={
              isLoadingConversation
                ? '잠시만 기다려 주세요.'
                : undefined
            }
          />
        ) : (
          <>
            <ChatThread
              turns={turns}
              activeArtifactId={routeArtifactId}
              onOpenArtifact={handleOpenArtifact}
              liveAssistant={
                isSending
                  ? {
                      content: chat.state.contentBuffer,
                      reasoning: chat.state.reasoningBuffer,
                      status: chat.state.status,
                      artifacts: chat.state.artifacts,
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
                isDisabled={isComposerDisabled}
                onSelectTool={handleSelectTool}
                toolItems={slashCommandItems}
                placeholder={
                  isLoadingConversation
                    ? '대화를 불러오는 중입니다.'
                    : !isConversationReady
                      ? '이 대화를 열 수 없습니다. 새 대화를 시작하거나 다른 대화를 선택하세요.'
                      : undefined
                }
              />
            </div>
          </>
        )}
      </section>
      <ArtifactPanel artifact={activeArtifact} onClose={handleCloseArtifact} />
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

/**
 * Translate a server-side ConversationDetail into the ChatTurn[] shape the
 * thread renderer consumes. Keeps the reload path visually identical to a
 * live stream — reasoning/tool-calls/status fields all round-trip.
 */
function detailToTurns(detail: ConversationDetail): ChatTurn[] {
  return detail.turns.map(apiTurnToChatTurn);
}

/**
 * Rebuild the on-the-wire form of a prior assistant turn for the next LLM
 * request. The bubble's visible text was the short summary; the full document
 * bodies live on ``turn.artifacts``. Serializing only ``turn.content`` would
 * hide the generated document from the model, so revision asks like
 * "두 번째 문단을 고쳐줘" would operate on ghost text. Re-emit each artifact
 * using the exact ``<artifact>`` grammar the server parses so the model sees
 * the same canonical form it produced.
 */
function serializeTurnForModel(turn: ChatTurn): string {
  const artifacts = turn.artifacts ?? [];
  if (artifacts.length === 0) {
    return turn.content;
  }
  const blocks = artifacts.map((artifact) => {
    // The server's artifact tag grammar only understands double-quoted
    // attribute values without entity decoding. Swap embedded `"` for a
    // Unicode right-double-quote so the model sees a readable title on
    // follow-up turns instead of a literal `&quot;` leak. Titles are
    // display metadata, so the glyph shift is invisible in practice.
    const titleAttr = artifact.title
      ? ` title="${artifact.title.replace(/"/g, '\u201d')}"`
      : '';
    return `<artifact type="${artifact.type}"${titleAttr}>\n${artifact.content}\n</artifact>`;
  });
  if (!turn.content.trim()) {
    return blocks.join('\n\n');
  }
  return `${turn.content}\n\n${blocks.join('\n\n')}`;
}

function apiTurnToChatTurn(turn: ApiConversationTurn): ChatTurn {
  return {
    id: turn.id,
    role: turn.role,
    content: turn.content,
    reasoning: turn.reasoning ?? undefined,
    reasoningStatus: (turn.reasoningStatus ?? undefined) as ChatTurn['reasoningStatus'],
    finishReason: (turn.finishReason ?? null) as ChatTurn['finishReason'],
    responseStatus: (turn.responseStatus ?? undefined) as ChatTurn['responseStatus'],
    provider: turn.provider ?? undefined,
    policy: turn.policy ?? null,
    chosenPool: turn.chosenPool ?? null,
    decisionReason: turn.decisionReason ?? null,
    forcedLocal: Boolean(turn.forcedLocal),
    piiHits: turn.piiHits ?? [],
    toolCalls: (turn.toolCalls ?? []) as unknown as ChatTurn['toolCalls'],
    pendingApprovals:
      (turn.pendingApprovals ?? []) as unknown as ChatTurn['pendingApprovals'],
    artifacts: (turn.artifacts ?? []).map((artifact) => ({
      id: artifact.id,
      type: artifact.type,
      title: artifact.title ?? null,
      content: artifact.content,
      status: artifact.status === 'open' ? 'open' : 'closed',
    })),
  };
}
