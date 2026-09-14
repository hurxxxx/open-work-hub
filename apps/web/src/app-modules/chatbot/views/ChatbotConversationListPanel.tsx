import type { AppRouteId } from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import {
  MessageSquare,
  MoreHorizontal,
  Archive,
  Plus,
  Search,
  Sparkles,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import {
  DropdownMenu,
  useConfirm,
  useFeedback,
  usePrompt,
} from '@open-work-hub/ui';

import { cn } from '@/src/lib/utils';
import { updateHermesSession } from '../api/hermes-agent-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  CHATBOT_SIDEBAR_INITIAL_STATE,
  CONVERSATION_LIST_LIMIT,
  chatbotSidebarReducer,
  filterConversations,
  groupConversationsByDate,
  listConversationsWindow,
  shouldAutoLoadMoreForSearch,
} from '../ai-sidebar-model';
import {
  CONVERSATIONS_UPDATED_EVENT,
  deleteConversation,
  listConversations,
  renameConversation,
  type ConversationSummary,
} from '../api/conversations-api';

interface ChatbotConversationListPanelProps {
  activeConversationId: string | null;

  navigationDisabled?: boolean;
  pendingConversationTitle?: string | null;
  routeId?: AppRouteId;
  scopeRef?: string;
  scopeResourceId?: string;
  eyebrow?: string;
  title?: string;
  placement?: 'inline' | 'shell';
  onNavigate?: () => void;
}

interface ConversationListProps {
  conversations: ConversationSummary[];
  error: string | null;
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
  onDelete: (conversationId: string) => void | Promise<void>;
  onRename: (conversation: ConversationSummary) => void | Promise<void>;
  onUpdate: (
    conversation: ConversationSummary,
    changes: { pinned?: boolean; archived?: boolean },
  ) => void | Promise<void>;
  onLoadMore: () => void | Promise<void>;
  hasMore: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  navigationDisabled: boolean;
  pendingConversationTitle?: string | null;
  scopeRef?: string;
  scopeResourceId?: string;
  eyebrow?: string;
  title?: string;
}

function ConversationList({
  activeConversationId,
  conversations,
  error,
  hasMore,
  isLoading,
  isLoadingMore,
  navigationDisabled,
  pendingConversationTitle,
  onDelete,
  onLoadMore,
  onNewConversation,
  onRename,
  onUpdate,
  onSelect,
  scopeRef,
  scopeResourceId,
  eyebrow,
  title,
}: ConversationListProps) {
  const { t } = useTranslation(['apps', 'common']);
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const normalizedQuery = query.trim();
  const displayConversations = useMemo(() => {
    const pendingTitle = pendingConversationTitle?.trim();
    if (
      !pendingTitle ||
      (activeConversationId &&
        conversations.some(
          (conversation) => conversation.id === activeConversationId,
        ))
    ) {
      return conversations;
    }
    const now = new Date().toISOString();
    return [
      {
        createdAt: now,
        id: `pending:${activeConversationId ?? 'new'}`,
        scopeRef: scopeRef ?? null,
        scopeResourceId: scopeResourceId ?? null,
        title: pendingTitle,
        updatedAt: now,
      },
      ...conversations,
    ];
  }, [
    activeConversationId,
    conversations,
    pendingConversationTitle,
    scopeRef,
    scopeResourceId,
  ]);
  const filteredConversations = useMemo(() => {
    return filterConversations(
      displayConversations.filter(
        (item) => Boolean(item.archived) === showArchived,
      ),
      normalizedQuery,
      t('apps:ai.sidebar.untitledConversation'),
    );
  }, [displayConversations, normalizedQuery, showArchived, t]);
  const groups = useMemo(
    () => groupConversationsByDate(filteredConversations),
    [filteredConversations],
  );

  useEffect(() => {
    if (
      !shouldAutoLoadMoreForSearch({
        filteredCount: filteredConversations.length,
        hasMore,
        isLoadingMore,
        query: normalizedQuery,
      })
    ) {
      return;
    }
    void onLoadMore();
  }, [
    filteredConversations.length,
    hasMore,
    isLoadingMore,
    normalizedQuery,
    onLoadMore,
  ]);

  return (
    <>
      <div className="border-b border-app-border p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="app-text-micro font-medium text-app-ink/45">
              {eyebrow ?? 'AI'}
            </p>
            <h2 className="app-text-body-sm truncate font-semibold text-app-ink">
              {title ?? t('apps:ai.sidebar.recentConversations')}
            </h2>
          </div>
          <button
            type="button"
            onClick={onNewConversation}
            disabled={navigationDisabled}
            title={navigationDisabled ? t('apps:ai.message.typing') : undefined}
            className="app-text-control inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Plus size={14} />
            <span>{t('apps:ai.sidebar.newConversation')}</span>
          </button>
        </div>
        <label className="flex h-8 items-center gap-2 rounded-md border border-app-border bg-app-surface px-2 text-app-ink/45 transition-colors focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15">
          <Search size={13} />
          <input
            aria-label={t('apps:ai.sidebar.searchConversations')}
            className="min-w-0 flex-1 bg-transparent app-text-caption text-app-ink outline-none placeholder:text-app-ink/35"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('apps:ai.sidebar.searchConversations')}
          />
        </label>
        {normalizedQuery ? (
          <p className="mt-1 app-text-micro text-app-ink/55">
            {t('apps:ai.sidebar.searchLoadedTitles')}
          </p>
        ) : null}
        <button
          type="button"
          aria-pressed={showArchived}
          onClick={() => setShowArchived((value) => !value)}
          className="mt-2 flex items-center gap-1 app-text-caption text-app-ink/60"
        >
          <Archive size={13} />
          {t(
            showArchived
              ? 'apps:ai.sidebar.showRecent'
              : 'apps:ai.sidebar.showArchived',
          )}
        </button>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {isLoading && displayConversations.length === 0 ? (
          <p
            role="status"
            className="px-2 py-1.5 app-text-caption text-app-ink/55"
          >
            {t('apps:ai.sidebar.loadingMore')}
          </p>
        ) : error ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-warning-text dark:text-app-warning-text">
            {error}
          </div>
        ) : displayConversations.length === 0 ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-ink/45">
            {t('apps:ai.sidebar.noConversations')}
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-ink/45">
            {t('apps:ai.sidebar.noConversationSearchResults')}
          </div>
        ) : (
          <div className="space-y-3">
            {groups.map((group) => (
              <div key={group.id}>
                <span className="block px-2 py-1 app-text-micro font-semibold text-app-ink/40">
                  {t(`apps:ai.sidebar.${group.id}`)}
                </span>
                <ul className="space-y-0.5">
                  {group.items.map((conversation) => {
                    const isPending = conversation.id.startsWith('pending:');
                    const isActive =
                      isPending || conversation.id === activeConversationId;
                    const isScoped = Boolean(conversation.scopeRef);
                    const Icon = isScoped ? Sparkles : MessageSquare;
                    return (
                      <li
                        key={conversation.id}
                        className="group/conversation relative"
                      >
                        <button
                          type="button"
                          onClick={() => {
                            if (!isPending) {
                              onSelect(conversation.id);
                            }
                          }}
                          disabled={navigationDisabled || isPending}
                          title={
                            navigationDisabled
                              ? t('apps:ai.message.typing')
                              : isScoped
                                ? t('apps:ai.sidebar.boundScopedConversation')
                                : undefined
                          }
                          className={cn(
                            'flex h-8 w-full items-center gap-2 rounded-md px-2 pr-9 text-left transition-colors',
                            isActive
                              ? 'bg-app-surface-hover text-app-accent'
                              : 'text-app-ink/75 hover:bg-app-surface-hover hover:text-app-ink',
                            navigationDisabled &&
                              'cursor-not-allowed opacity-60',
                          )}
                        >
                          <Icon
                            size={13}
                            aria-label={
                              isScoped
                                ? t('apps:ai.sidebar.scopedContext')
                                : undefined
                            }
                            className={cn(
                              'shrink-0',
                              isActive || isScoped
                                ? 'text-app-accent'
                                : 'text-app-ink/40',
                            )}
                          />
                          <span className="min-w-0 flex-1 truncate app-text-caption">
                            {conversation.title ||
                              t('apps:ai.sidebar.untitledConversation')}
                          </span>
                        </button>
                        {!isPending ? (
                          <div className="absolute right-1 top-1/2 -translate-y-1/2">
                            <DropdownMenu
                              side="bottom"
                              trigger={
                                <button
                                  type="button"
                                  aria-label={t(
                                    'apps:ai.sidebar.conversationActions',
                                  )}
                                  disabled={navigationDisabled}
                                  className="flex size-7 items-center justify-center rounded text-app-ink/55 hover:bg-app-surface-hover focus-visible:ring-2 focus-visible:ring-app-accent"
                                >
                                  <MoreHorizontal size={16} />
                                </button>
                              }
                              items={[
                                {
                                  id: 'pin',
                                  label: t(
                                    conversation.pinned
                                      ? 'apps:ai.sidebar.unpinConversation'
                                      : 'apps:ai.sidebar.pinConversation',
                                  ),
                                  onSelect: () => {
                                    void onUpdate(conversation, {
                                      pinned: !conversation.pinned,
                                    });
                                  },
                                },
                                {
                                  id: 'archive',
                                  label: t(
                                    conversation.archived
                                      ? 'apps:ai.sidebar.restoreConversation'
                                      : 'apps:ai.sidebar.archiveConversation',
                                  ),
                                  onSelect: () => {
                                    void onUpdate(conversation, {
                                      archived: !conversation.archived,
                                    });
                                  },
                                },
                                {
                                  id: 'rename',
                                  label: t(
                                    'apps:ai.sidebar.renameConversation',
                                  ),
                                  onSelect: () => {
                                    void onRename(conversation);
                                  },
                                },
                                {
                                  id: 'delete',
                                  label: t(
                                    'apps:ai.sidebar.deleteConversation',
                                  ),
                                  tone: 'danger',
                                  separatorBefore: true,
                                  onSelect: () => {
                                    void onDelete(conversation.id);
                                  },
                                },
                              ]}
                            />
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
        {hasMore ? (
          <button
            type="button"
            onClick={() => {
              void onLoadMore();
            }}
            disabled={isLoadingMore}
            className="mt-2 h-8 w-full rounded-md px-2 text-left app-text-caption text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoadingMore
              ? t('apps:ai.sidebar.loadingMore')
              : t('apps:ai.sidebar.loadMore')}
          </button>
        ) : null}
      </div>
    </>
  );
}

export function ChatbotConversationListPanel({
  activeConversationId,
  navigationDisabled = false,
  pendingConversationTitle,
  routeId = 'chatbot.root',
  scopeRef,
  scopeResourceId,
  eyebrow,
  title,
  placement = 'inline',
  onNavigate,
}: ChatbotConversationListPanelProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const navigate = useNavigate();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const toast = useFeedback();
  const [isLoading, setIsLoading] = useState(true);
  const [state, dispatch] = useReducer(
    chatbotSidebarReducer,
    CHATBOT_SIDEBAR_INITIAL_STATE,
  );
  const loadedLimitRef = useRef(CONVERSATION_LIST_LIMIT);
  const requestVersion = useRef(0);
  const ownerKey = useMemo(
    () => ({ token, scopeRef, scopeResourceId }),
    [token, scopeRef, scopeResourceId],
  );
  const owner = useRef(ownerKey);
  owner.current = ownerKey;
  const selectedConversation = useRef(activeConversationId);
  selectedConversation.current = activeConversationId;
  const pendingUpdates = useRef(new Set<string>());

  const loadConversationWindow = useCallback(async () => {
    const version = ++requestVersion.current;
    const belongsHere = () =>
      version === requestVersion.current &&
      owner.current.token === token &&
      owner.current.scopeRef === scopeRef &&
      owner.current.scopeResourceId === scopeResourceId;
    if (!token) {
      setIsLoading(false);
      dispatch({ type: 'reset' });
      loadedLimitRef.current = CONVERSATION_LIST_LIMIT;
      return;
    }
    const requestedLimit = Math.max(
      CONVERSATION_LIST_LIMIT,
      loadedLimitRef.current,
    );
    setIsLoading(true);
    try {
      const response = await listConversationsWindow(
        listConversations,
        token,
        requestedLimit,
        { scopeRef, scopeResourceId },
      );
      if (!belongsHere()) return;
      loadedLimitRef.current = Math.max(
        CONVERSATION_LIST_LIMIT,
        response.items.length,
      );
      dispatch({
        type: 'loadSuccess',
        items: response.items,
        nextCursor: response.nextCursor ?? null,
      });
    } catch (caughtError) {
      if (!belongsHere()) return;
      dispatch({
        type: 'loadFailure',
        message:
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.loadConversationsFailed'),
      });
    } finally {
      if (belongsHere()) setIsLoading(false);
    }
  }, [scopeRef, scopeResourceId, t, token]);

  useEffect(() => {
    dispatch({ type: 'reset' });
    loadedLimitRef.current = CONVERSATION_LIST_LIMIT;
    void loadConversationWindow();
    return () => {
      requestVersion.current += 1;
    };
  }, [loadConversationWindow]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handler = () => {
      void loadConversationWindow();
    };
    window.addEventListener(CONVERSATIONS_UPDATED_EVENT, handler);
    return () => {
      window.removeEventListener(CONVERSATIONS_UPDATED_EVENT, handler);
    };
  }, [loadConversationWindow]);

  const navigateToAi = useCallback(
    (conversationId?: string) => {
      navigate(
        buildAppHref({
          routeId,
          queryParams: conversationId ? { c: conversationId } : {},
        }),
      );
      onNavigate?.();
    },
    [navigate, routeId, onNavigate],
  );

  const loadMoreConversations = useCallback(async () => {
    if (!token || !state.nextCursor || state.isLoadingMore) return;
    dispatch({ type: 'loadMoreStart' });
    const version = requestVersion.current;
    try {
      const response = await listConversations(token, {
        limit: CONVERSATION_LIST_LIMIT,
        cursor: state.nextCursor,
        scopeRef,
        scopeResourceId,
      });
      if (version !== requestVersion.current) return;
      loadedLimitRef.current = Math.max(
        CONVERSATION_LIST_LIMIT,
        state.conversations.length + response.items.length,
      );
      dispatch({
        type: 'loadMoreSuccess',
        items: response.items,
        nextCursor: response.nextCursor ?? null,
      });
    } catch (caughtError) {
      if (version !== requestVersion.current) return;
      dispatch({
        type: 'loadMoreFailure',
        message:
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.loadConversationsFailed'),
      });
    }
  }, [
    state.conversations.length,
    state.isLoadingMore,
    state.nextCursor,
    scopeRef,
    scopeResourceId,
    t,
    token,
  ]);

  const handleDeleteConversation = useCallback(
    async (conversationId: string) => {
      if (!token) return;
      const confirmed = await confirm({
        title: t('apps:ai.sidebar.deleteConversation'),
        description: t('apps:ai.sidebar.deleteConversationDescription'),
        confirmLabel: t('common:actions.delete'),
        cancelLabel: t('common:actions.cancel'),
        variant: 'danger',
      });
      if (!confirmed || owner.current !== ownerKey) return;
      try {
        await deleteConversation(token, conversationId, {});
        if (owner.current !== ownerKey) return;
        dispatch({ type: 'deleteSuccess', conversationId });
        if (selectedConversation.current === conversationId) navigateToAi();
      } catch (error) {
        if (owner.current === ownerKey)
          toast.error(
            error instanceof Error
              ? error.message
              : t('apps:hermesWorkspace.operationFailed'),
          );
      }
    },
    [ownerKey, confirm, navigateToAi, t, token, toast],
  );

  const handleRenameConversation = useCallback(
    async (conversation: ConversationSummary) => {
      if (!token) return;
      const nextTitle = await prompt({
        title: t('apps:ai.sidebar.renameConversation'),
        description: t('apps:ai.sidebar.renameConversationDescription'),
        defaultValue: conversation.title ?? '',
        placeholder: t('apps:ai.sidebar.untitledConversation'),
        submitLabel: t('common:actions.save'),
        cancelLabel: t('common:actions.cancel'),
      });
      const trimmedTitle = nextTitle?.trim() ?? '';
      if (
        owner.current !== ownerKey ||
        !trimmedTitle ||
        trimmedTitle === (conversation.title ?? '').trim()
      ) {
        return;
      }
      try {
        const detail = await renameConversation(
          token,
          conversation.id,
          trimmedTitle,
          {},
        );
        if (owner.current !== ownerKey) return;
        dispatch({
          type: 'renameSuccess',
          conversation: {
            ...conversation,
            title: detail.title,
            updatedAt: detail.updatedAt,
          },
        });
        toast.success(t('apps:ai.sidebar.renameConversationSuccess'));
      } catch (caughtError) {
        if (owner.current !== ownerKey) return;
        toast.error(
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.renameConversationFailed'),
        );
      }
    },
    [ownerKey, prompt, t, toast, token],
  );

  const handleUpdateConversation = async (
    conversation: ConversationSummary,
    changes: { pinned?: boolean; archived?: boolean },
  ) => {
    if (
      !token ||
      navigationDisabled ||
      pendingUpdates.current.has(conversation.id)
    )
      return;
    pendingUpdates.current.add(conversation.id);
    try {
      await updateHermesSession(token, conversation.id, changes);
      if (owner.current !== ownerKey) return;
      await loadConversationWindow();
      if (
        owner.current === ownerKey &&
        changes.archived &&
        selectedConversation.current === conversation.id
      )
        navigateToAi();
    } catch (error) {
      if (owner.current === ownerKey)
        toast.error(
          error instanceof Error
            ? error.message
            : t('apps:hermesWorkspace.operationFailed'),
        );
    } finally {
      pendingUpdates.current.delete(conversation.id);
    }
  };

  return (
    <>
      {confirmDialog}
      {promptDialog}
      <aside
        className={
          placement === 'shell'
            ? 'flex min-h-0 flex-col'
            : 'flex max-h-72 min-h-0 flex-col border-b border-app-border bg-app-surface-sidebar/70 lg:max-h-none lg:w-72 lg:shrink-0 lg:border-b-0 lg:border-r'
        }
      >
        <ConversationList
          conversations={state.conversations}
          error={state.error}
          activeConversationId={activeConversationId}
          onSelect={navigateToAi}
          onNewConversation={() => navigateToAi()}
          onDelete={handleDeleteConversation}
          onRename={handleRenameConversation}
          onUpdate={handleUpdateConversation}
          onLoadMore={loadMoreConversations}
          hasMore={Boolean(state.nextCursor)}
          isLoadingMore={state.isLoadingMore}
          isLoading={isLoading}
          navigationDisabled={navigationDisabled}
          pendingConversationTitle={pendingConversationTitle}
          scopeRef={scopeRef}
          scopeResourceId={scopeResourceId}
          eyebrow={eyebrow}
          title={title}
        />
      </aside>
    </>
  );
}
