import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import {
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { AppRouteId } from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import { useConfirm, useFeedback, usePrompt } from '@open-work-hub/ui';

import {
  CONVERSATIONS_UPDATED_EVENT,
  deleteConversation,
  listConversations,
  renameConversation,
  type ConversationSummary,
} from '../api/conversations-api';
import {
  CHATBOT_SIDEBAR_INITIAL_STATE,
  CONVERSATION_LIST_LIMIT,
  chatbotSidebarReducer,
  filterConversations,
  groupConversationsByDate,
  listConversationsWindow,
  shouldAutoLoadMoreForSearch,
} from '../ai-sidebar-model';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { cn } from '@/src/lib/utils';

interface ChatbotConversationListPanelProps {
  activeConversationId: string | null;
  currentWorkspaceSlug?: string | null;
  navigationDisabled?: boolean;
  pendingConversationTitle?: string | null;
  routeId?: AppRouteId;
  scopeRef?: string;
  scopeResourceId?: string;
  eyebrow?: string;
  title?: string;
}

interface ConversationListProps {
  conversations: ConversationSummary[];
  error: string | null;
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
  onDelete: (conversationId: string) => void | Promise<void>;
  onRename: (conversation: ConversationSummary) => void | Promise<void>;
  onLoadMore: () => void | Promise<void>;
  hasMore: boolean;
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
  isLoadingMore,
  navigationDisabled,
  pendingConversationTitle,
  onDelete,
  onLoadMore,
  onNewConversation,
  onRename,
  onSelect,
  scopeRef,
  scopeResourceId,
  eyebrow,
  title,
}: ConversationListProps) {
  const { t } = useTranslation(['apps', 'common']);
  const [query, setQuery] = useState('');
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
      displayConversations,
      normalizedQuery,
      t('apps:ai.sidebar.untitledConversation'),
    );
  }, [displayConversations, normalizedQuery, t]);
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
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {error ? (
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
                            'flex h-8 w-full items-center gap-2 rounded-md px-2 pr-14 text-left transition-colors',
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
                          <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition-opacity group-focus-within/conversation:opacity-100 group-hover/conversation:opacity-100">
                            <button
                              type="button"
                              aria-label={t(
                                'apps:ai.sidebar.renameConversation',
                              )}
                              onClick={(event) => {
                                event.stopPropagation();
                                void onRename(conversation);
                              }}
                              className="flex size-6 items-center justify-center rounded text-app-ink/35 transition-colors hover:bg-app-surface hover:text-app-accent"
                            >
                              <Pencil size={12} />
                            </button>
                            <button
                              type="button"
                              aria-label={t(
                                'apps:ai.sidebar.deleteConversation',
                              )}
                              disabled={navigationDisabled}
                              title={
                                navigationDisabled
                                  ? t('apps:ai.message.typing')
                                  : undefined
                              }
                              onClick={(event) => {
                                event.stopPropagation();
                                void onDelete(conversation.id);
                              }}
                              className="flex size-6 items-center justify-center rounded text-app-ink/35 transition-colors hover:bg-app-surface hover:text-app-danger disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              <Trash2 size={12} />
                            </button>
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
  currentWorkspaceSlug,
  navigationDisabled = false,
  pendingConversationTitle,
  routeId = 'chatbot.root',
  scopeRef,
  scopeResourceId,
  eyebrow,
  title,
}: ChatbotConversationListPanelProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const navigate = useNavigate();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const toast = useFeedback();
  const [state, dispatch] = useReducer(
    chatbotSidebarReducer,
    CHATBOT_SIDEBAR_INITIAL_STATE,
  );
  const loadedLimitRef = useRef(CONVERSATION_LIST_LIMIT);

  const loadConversationWindow = useCallback(async () => {
    if (!token || !currentWorkspaceSlug) {
      dispatch({ type: 'reset' });
      loadedLimitRef.current = CONVERSATION_LIST_LIMIT;
      return;
    }
    const requestedLimit = Math.max(
      CONVERSATION_LIST_LIMIT,
      loadedLimitRef.current,
    );
    try {
      const response = await listConversationsWindow(
        listConversations,
        token,
        requestedLimit,
        { scopeRef, scopeResourceId, workspaceSlug: currentWorkspaceSlug },
      );
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
      dispatch({
        type: 'loadFailure',
        message:
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.loadConversationsFailed'),
      });
    }
  }, [currentWorkspaceSlug, scopeRef, scopeResourceId, t, token]);

  useEffect(() => {
    void loadConversationWindow();
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
      if (!currentWorkspaceSlug) return;
      navigate(
        buildAppHref({
          routeId,
          workspaceSlug: currentWorkspaceSlug,
          queryParams: conversationId ? { c: conversationId } : {},
        }),
      );
    },
    [currentWorkspaceSlug, navigate, routeId],
  );

  const loadMoreConversations = useCallback(async () => {
    if (!token || !state.nextCursor || state.isLoadingMore) return;
    dispatch({ type: 'loadMoreStart' });
    try {
      const response = await listConversations(token, {
        limit: CONVERSATION_LIST_LIMIT,
        cursor: state.nextCursor,
        scopeRef,
        scopeResourceId,
        workspaceSlug: currentWorkspaceSlug,
      });
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
      dispatch({
        type: 'loadMoreFailure',
        message:
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.loadConversationsFailed'),
      });
    }
  }, [
    currentWorkspaceSlug,
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
      if (!confirmed) return;
      await deleteConversation(token, conversationId, {
        workspaceSlug: currentWorkspaceSlug,
      });
      dispatch({ type: 'deleteSuccess', conversationId });
      if (activeConversationId === conversationId) {
        navigateToAi();
      }
    },
    [
      activeConversationId,
      confirm,
      currentWorkspaceSlug,
      navigateToAi,
      t,
      token,
    ],
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
      if (!trimmedTitle || trimmedTitle === (conversation.title ?? '').trim()) {
        return;
      }
      try {
        const detail = await renameConversation(
          token,
          conversation.id,
          trimmedTitle,
          { workspaceSlug: currentWorkspaceSlug },
        );
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
        toast.error(
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.renameConversationFailed'),
        );
      }
    },
    [currentWorkspaceSlug, prompt, t, toast, token],
  );

  return (
    <>
      {confirmDialog}
      {promptDialog}
      <aside className="flex max-h-72 min-h-0 flex-col border-b border-app-border bg-app-surface-sidebar/70 lg:max-h-none lg:w-72 lg:shrink-0 lg:border-b-0 lg:border-r">
        <ConversationList
          conversations={state.conversations}
          error={state.error}
          activeConversationId={activeConversationId}
          onSelect={navigateToAi}
          onNewConversation={() => navigateToAi()}
          onDelete={handleDeleteConversation}
          onRename={handleRenameConversation}
          onLoadMore={loadMoreConversations}
          hasMore={Boolean(state.nextCursor)}
          isLoadingMore={state.isLoadingMore}
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
