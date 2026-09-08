import {
  Globe2,
  MessageSquare,
  Plus,
  Search,
  type LucideIcon,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ChatComposer,
  ChatThread,
  EmptyState,
  getConversation,
  listConversations,
  type ChatTurn,
  type ConversationDetail,
  type ConversationSummary,
  type ConversationTurn,
} from '@/src/app-modules/chatbot/public-api';
import { cn } from '@/src/lib/utils';
import { iterSseEvents } from '@/src/platform/api/sse-parser';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  WebSearchApiError,
  streamWebSearch,
  type WebSearchAnswerResponse,
  type WebSearchStreamEvent,
} from '../api/web-search-api';

export interface WebSearchExperience {
  apiPrefix: string;
  conversationScopeRef: string;
  icon: LucideIcon;
  i18nKey: string;
  maxUses?: number;
}

const DEFAULT_WEB_SEARCH_EXPERIENCE: WebSearchExperience = {
  apiPrefix: '/api/v1/web-search',
  conversationScopeRef: 'web_search',
  icon: Globe2,
  i18nKey: 'ai.webSearch',
};

const WEB_SEARCH_POLICY_DENIED_CODE = 'web_search.policy_denied';

interface ActiveWebSearchStream {
  controller: AbortController;
  conversationId: string | null;
}

function createId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function buildConversationTitle(question: string): string {
  const compact = question.replace(/\s+/g, ' ').trim();
  if (compact.length <= 36) {
    return compact;
  }
  return `${compact.slice(0, 36)}...`;
}

function escapeMarkdown(value: string): string {
  return value.replace(/([`*_~])/g, '\\$1');
}

function formatWebSearchAnswer(
  response: WebSearchAnswerResponse,
  t: (key: string, options?: Record<string, unknown>) => string,
  i18nKey: string,
): string {
  const lines = [response.answer.trim() || t(`${i18nKey}.noAnswer`)];
  if (response.citations.length > 0) {
    lines.push('', `**${t(`${i18nKey}.sources`)}**`);
    response.citations.forEach((citation, index) => {
      const title = escapeMarkdown(citation.title || citation.url);
      lines.push(`${index + 1}. [${title}](${citation.url})`);
      if (citation.cited_text) {
        lines.push(`   ${escapeMarkdown(citation.cited_text)}`);
      }
    });
  }
  return lines.join('\n');
}

function parseWebSearchStreamEvent(data: string): WebSearchStreamEvent | null {
  try {
    const parsed = JSON.parse(data) as Partial<WebSearchStreamEvent>;
    if (
      parsed.type === 'content_delta' ||
      parsed.type === 'conversation_attached' ||
      parsed.type === 'web_search_response' ||
      parsed.type === 'done' ||
      parsed.type === 'error'
    ) {
      return parsed as WebSearchStreamEvent;
    }
  } catch {
    return null;
  }
  return null;
}

function toChatTurn(turn: ConversationTurn): ChatTurn {
  return turn as ChatTurn;
}

function ConversationHistoryPanel({
  activeConversationId,
  conversations,
  i18nKey,
  onNewConversation,
  onSelectConversation,
}: {
  activeConversationId: string | null;
  conversations: ConversationSummary[];
  i18nKey: string;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
}) {
  const { t } = useTranslation('apps');
  const [query, setQuery] = useState('');
  const filteredConversations = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return conversations;
    }
    return conversations.filter((conversation) => {
      return conversation.title.toLowerCase().includes(normalized);
    });
  }, [conversations, query]);

  return (
    <aside className="flex max-h-72 min-h-0 flex-col border-b border-app-border bg-app-surface-sidebar/70 lg:max-h-none lg:w-72 lg:shrink-0 lg:border-b-0 lg:border-r">
      <div className="border-b border-app-border p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="app-text-micro font-medium text-app-ink/45">
              {t(`${i18nKey}.historyEyebrow`)}
            </p>
            <h2 className="truncate app-text-body-sm font-semibold text-app-ink">
              {t(`${i18nKey}.historyTitle`)}
            </h2>
          </div>
          <button
            type="button"
            onClick={onNewConversation}
            className="app-text-control inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
          >
            <Plus size={14} />
            <span>{t(`${i18nKey}.newConversation`)}</span>
          </button>
        </div>
        <label className="flex h-8 items-center gap-2 rounded-md border border-app-border bg-app-surface px-2 text-app-ink/45 transition-colors focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15">
          <Search size={13} />
          <input
            aria-label={t(`${i18nKey}.searchHistory`)}
            className="min-w-0 flex-1 bg-transparent app-text-caption text-app-ink outline-none placeholder:text-app-ink/35"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t(`${i18nKey}.searchHistory`)}
          />
        </label>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {conversations.length === 0 ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-ink/45">
            {t(`${i18nKey}.noHistory`)}
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-ink/45">
            {t(`${i18nKey}.noHistorySearchResults`)}
          </div>
        ) : (
          <ul className="space-y-0.5">
            {filteredConversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => onSelectConversation(conversation.id)}
                    className={cn(
                      'flex h-8 w-full items-center gap-2 rounded-md px-2 text-left transition-colors',
                      isActive
                        ? 'bg-app-surface-hover text-app-accent'
                        : 'text-app-ink/75 hover:bg-app-surface-hover hover:text-app-ink',
                    )}
                  >
                    <MessageSquare
                      size={13}
                      className={cn(
                        'shrink-0',
                        isActive ? 'text-app-accent' : 'text-app-ink/40',
                      )}
                    />
                    <span className="min-w-0 flex-1 truncate app-text-caption">
                      {conversation.title}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

export function WebSearchView() {
  return <WebSearchExperienceView experience={DEFAULT_WEB_SEARCH_EXPERIENCE} />;
}

export function WebSearchExperienceView({
  experience,
}: {
  experience: WebSearchExperience;
}) {
  const { t } = useTranslation('apps');
  const i18nKey = experience.i18nKey;
  const ExperienceIcon = experience.icon;
  const { token } = useAuth();

  const authToken = token ?? '';

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [activeConversation, setActiveConversation] =
    useState<ConversationDetail | null>(null);
  const [activeTurns, setActiveTurns] = useState<ChatTurn[]>([]);
  const [draftTitle, setDraftTitle] = useState<string | null>(null);
  const [activeStream, setActiveStreamState] =
    useState<ActiveWebSearchStream | null>(null);
  const [question, setQuestion] = useState('');
  const [liveAnswer, setLiveAnswer] = useState('');
  const [chatError, setChatError] = useState<string | null>(null);
  const activeStreamRef = useRef<ActiveWebSearchStream | null>(null);
  const liveAnswerRef = useRef('');

  const isCurrentViewStreaming = activeStream !== null;
  const turns = activeTurns;

  const loadConversationDetail = useCallback(
    async (conversationId: string) => {
      if (!authToken) {
        return;
      }
      const detail = await getConversation(authToken, conversationId, {});
      setActiveConversation(detail);
      setActiveConversationId(detail.id);
      setActiveTurns(detail.turns.map(toChatTurn));
      setDraftTitle(null);
    },
    [authToken],
  );

  const refreshConversationList = useCallback(async () => {
    if (!authToken) {
      setConversations([]);
      return [];
    }
    const result = await listConversations(authToken, {
      limit: 50,
      scopeRef: experience.conversationScopeRef,
      scopeResourceId: 'default',
    });
    setConversations(result.items);
    return result.items;
  }, [authToken, experience.conversationScopeRef]);

  useEffect(() => {
    if (!authToken) {
      setConversations([]);
      setActiveConversation(null);
      setActiveConversationId(null);
      setActiveTurns([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const items = await refreshConversationList();
        if (cancelled) {
          return;
        }
        const first = items[0] ?? null;
        if (first) {
          await loadConversationDetail(first.id);
        } else {
          setActiveConversation(null);
          setActiveConversationId(null);
          setActiveTurns([]);
        }
      } catch {
        if (!cancelled) {
          setConversations([]);
          setActiveConversation(null);
          setActiveConversationId(null);
          setActiveTurns([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    authToken,
    experience.conversationScopeRef,
    loadConversationDetail,
    refreshConversationList,
  ]);

  useEffect(() => {
    return () => {
      activeStreamRef.current?.controller.abort();
    };
  }, []);

  const setActiveStream = useCallback(
    (stream: ActiveWebSearchStream | null) => {
      activeStreamRef.current = stream;
      setActiveStreamState(stream);
    },
    [],
  );

  const handleAsk = useCallback(async () => {
    const trimmed = question.trim();
    if (!trimmed || !authToken) {
      return;
    }
    const existingStream = activeStreamRef.current;
    if (existingStream) {
      return;
    }

    const requestedConversationId = activeConversationId;
    let attachedConversationId = requestedConversationId;
    if (!requestedConversationId) {
      setDraftTitle(t(`${i18nKey}.pendingTitle`));
    }

    setQuestion('');
    setLiveAnswer('');
    liveAnswerRef.current = '';
    setChatError(null);
    const controller = new AbortController();
    setActiveStream({
      controller,
      conversationId: requestedConversationId,
    });
    let streamedAnswer = '';
    let didAttachConversation = false;
    try {
      const response = await streamWebSearch({
        token: authToken,
        question: trimmed,
        conversationId: requestedConversationId,
        apiPrefix: experience.apiPrefix,
        errorI18nKey: i18nKey,
        maxUses: experience.maxUses,
        signal: controller.signal,
      });
      if (!response.body) {
        throw new WebSearchApiError(0, t(`${i18nKey}.errors.connect`));
      }

      let finalResponse: WebSearchAnswerResponse | null = null;
      for await (const message of iterSseEvents(
        response.body,
        controller.signal,
      )) {
        const event = parseWebSearchStreamEvent(message.data);
        if (!event) {
          continue;
        }
        if (event.type === 'conversation_attached') {
          const nextConversationId = event.data.conversation_id;
          const displayQuestion = (
            event.data.display_question?.trim() || trimmed
          ).trim();
          didAttachConversation = true;
          attachedConversationId = nextConversationId;
          setActiveConversationId(nextConversationId);
          setActiveTurns((current) => [
            ...current,
            {
              id: createId('web-user'),
              seq: current.length + 1,
              role: 'user',
              content: displayQuestion,
              responseStatus: 'done',
            },
          ]);
          if (!requestedConversationId) {
            setDraftTitle(buildConversationTitle(displayQuestion));
          }
          setActiveStreamState((current) =>
            current?.controller === controller
              ? { ...current, conversationId: nextConversationId }
              : current,
          );
          continue;
        }
        if (event.type === 'content_delta') {
          if (activeStreamRef.current?.controller !== controller) {
            return;
          }
          streamedAnswer = `${streamedAnswer}${event.data.text}`;
          liveAnswerRef.current = streamedAnswer;
          setLiveAnswer(streamedAnswer);
          continue;
        }
        if (event.type === 'web_search_response') {
          finalResponse = event.data.response;
          continue;
        }
        if (event.type === 'error') {
          throw new WebSearchApiError(0, event.data.message, event.data.code);
        }
        if (event.type === 'done') {
          break;
        }
      }
      if (controller.signal.aborted) {
        return;
      }
      if (!finalResponse) {
        throw new WebSearchApiError(0, t(`${i18nKey}.errors.askFailed`));
      }
      if (activeStreamRef.current?.controller !== controller) {
        return;
      }
      const assistantTurn: ChatTurn = {
        id: createId('web-assistant'),
        role: 'assistant',
        content: formatWebSearchAnswer(finalResponse, t, i18nKey),
        responseStatus: 'done',
        finishReason: 'stop',
      };
      setActiveTurns((current) => [...current, assistantTurn]);
      await refreshConversationList();
      if (attachedConversationId) {
        await loadConversationDetail(attachedConversationId);
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError' || controller.signal.aborted) {
        return;
      }
      if (activeStreamRef.current?.controller !== controller) {
        return;
      }
      const message =
        error instanceof WebSearchApiError &&
        error.code === WEB_SEARCH_POLICY_DENIED_CODE
          ? t(`${i18nKey}.errors.policyDenied`)
          : error instanceof WebSearchApiError
            ? error.message
            : t(`${i18nKey}.errors.askFailed`);
      if (
        error instanceof WebSearchApiError &&
        error.code === WEB_SEARCH_POLICY_DENIED_CODE &&
        !requestedConversationId
      ) {
        setDraftTitle(t(`${i18nKey}.policyDeniedTitle`));
      }
      const errorTurn: ChatTurn = {
        id: createId('web-assistant-error'),
        role: 'assistant',
        content: message,
        responseStatus: 'error',
        finishReason: 'error',
      };
      setActiveTurns((current) => [...current, errorTurn]);
      setChatError(message);
      await refreshConversationList();
      if (didAttachConversation && attachedConversationId) {
        await loadConversationDetail(attachedConversationId);
      }
    } finally {
      if (activeStreamRef.current?.controller === controller) {
        setActiveStream(null);
        setLiveAnswer('');
        liveAnswerRef.current = '';
      }
    }
  }, [
    activeConversationId,
    authToken,
    experience.apiPrefix,
    experience.maxUses,
    loadConversationDetail,
    refreshConversationList,
    i18nKey,
    question,
    setActiveStream,
    t,
  ]);

  const composer = (
    <ChatComposer
      input={question}
      onInputChange={setQuestion}
      onSubmit={() => {
        void handleAsk();
      }}
      onAbort={() => {
        activeStreamRef.current?.controller.abort();
      }}
      isSending={isCurrentViewStreaming}
      isStreaming={isCurrentViewStreaming}
      chatError={chatError}
      placeholder={t(`${i18nKey}.placeholder`)}
      isDisabled={!authToken}
      leadingControls={null}
    />
  );

  return (
    <main className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-app-bg lg:flex-row">
      <ConversationHistoryPanel
        activeConversationId={activeConversationId}
        conversations={conversations}
        i18nKey={i18nKey}
        onNewConversation={() => {
          setActiveConversationId(null);
          setActiveConversation(null);
          setActiveTurns([]);
          setDraftTitle(null);
          setQuestion('');
          setChatError(null);
        }}
        onSelectConversation={(conversationId) => {
          void loadConversationDetail(conversationId);
          setChatError(null);
        }}
      />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-app-surface">
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-app-border px-4">
          <div className="flex min-w-0 items-center gap-2">
            <ExperienceIcon className="h-4 w-4 shrink-0 text-app-accent" />
            <h1 className="truncate app-text-control text-app-ink">
              {activeConversation?.title ?? draftTitle ?? t(`${i18nKey}.title`)}
            </h1>
          </div>
        </header>

        {turns.length === 0 && !isCurrentViewStreaming ? (
          <EmptyState
            greeting={t(`${i18nKey}.emptyGreeting`)}
            subline={t(`${i18nKey}.emptySubline`)}
          >
            {composer}
          </EmptyState>
        ) : (
          <>
            <ChatThread
              turns={turns}
              typingLabel={t(`${i18nKey}.thinking`)}
              jumpToBottomLabel={t(`${i18nKey}.jumpToBottom`)}
              liveAssistant={
                isCurrentViewStreaming
                  ? {
                      content: liveAnswer,
                      reasoning: '',
                      status: 'streaming',
                    }
                  : null
              }
              onCopyTurn={async (turn) => {
                await navigator.clipboard?.writeText(turn.content);
              }}
            />
            <div className="sticky bottom-0 z-10 space-y-2 border-t border-app-border bg-app-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
              {composer}
            </div>
          </>
        )}
      </section>
    </main>
  );
}
