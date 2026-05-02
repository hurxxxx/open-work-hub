import { useEffect, useState } from 'react';
import { MessageSquare, Plus, Sparkles, Trash2 } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useConfirm } from '@aidoo/ui/feedback/confirm-dialog';

import { aiManifest } from './manifest';
import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import {
  CONVERSATIONS_UPDATED_EVENT,
  deleteConversation,
  listConversations,
  type ConversationSummary,
} from './api/conversations-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  resolveToolInvocationHref,
} from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import { i18n } from '@/src/platform/i18n';

interface AiSidebarSectionProps {
  currentWorkspaceSlug: string;
}

interface AiConversationsSectionProps {
  conversations: ConversationSummary[];
  error: string | null;
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
  onDelete: (conversationId: string) => void | Promise<void>;
}

const MAX_VISIBLE = 8;

function AiConversationsSection({
  conversations,
  error,
  activeConversationId,
  onSelect,
  onNewConversation,
  onDelete,
}: AiConversationsSectionProps) {
  const { t } = useTranslation(['apps', 'common']);
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? conversations : conversations.slice(0, MAX_VISIBLE);
  const hasMore = conversations.length > MAX_VISIBLE;

  return (
    <div className="space-y-1 px-1 pb-4 border-b border-app-border">
      <button
        type="button"
        onClick={onNewConversation}
        className="sidebar-submenu-item group flex w-full items-center gap-2 rounded-lg border border-dashed border-app-border px-3 py-2 text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
      >
        <Plus size={14} className="text-gray-500 group-hover:text-app-accent" />
        <span className="sidebar-submenu-label">{t('apps:ai.sidebar.newConversation')}</span>
      </button>

      <div className="pt-1">
        <span className="sidebar-section-label block px-3 py-1 text-gray-500">
          {t('apps:ai.sidebar.recentConversations')}
        </span>
        {error ? (
          <div className="px-3 py-1 app-text-micro text-amber-600 dark:text-amber-400">
            {error}
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-3 py-1 app-text-micro text-gray-500">
            {t('apps:ai.sidebar.noConversations')}
          </div>
        ) : (
          <ul className="space-y-0.5">
            {visible.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              const isScoped = conversation.scopeRef === 'meeting';
              const Icon = isScoped ? Sparkles : MessageSquare;
              return (
                <li key={conversation.id} className="group/conversation relative">
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    title={isScoped ? t('apps:ai.sidebar.boundMeetingConversation') : undefined}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-3 py-1.5 pr-8 text-left transition-colors',
                      isActive
                        ? 'bg-app-surface-hover text-app-accent'
                        : 'text-app-ink hover:bg-app-surface-hover',
                    )}
                  >
                    <Icon
                      size={13}
                      aria-label={isScoped ? t('apps:ai.sidebar.meetingContext') : undefined}
                      className={cn(
                        'shrink-0',
                        isActive || isScoped
                          ? 'text-app-accent'
                          : 'text-gray-500 dark:text-gray-400',
                      )}
                    />
                    <span className="sidebar-submenu-label truncate">
                      {conversation.title || t('apps:ai.sidebar.untitledConversation')}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={t('apps:ai.sidebar.deleteConversation')}
                    onClick={(event) => {
                      event.stopPropagation();
                      void onDelete(conversation.id);
                    }}
                    className="absolute right-1 top-1/2 hidden -translate-y-1/2 rounded p-1 text-gray-400 transition-colors hover:text-red-500 group-hover/conversation:inline-flex"
                  >
                    <Trash2 size={12} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {hasMore ? (
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            className="mt-1 w-full rounded-md px-3 py-1 text-left app-text-micro text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
          >
            {expanded
              ? t('apps:ai.sidebar.collapse')
              : t('apps:ai.sidebar.more', { count: conversations.length - MAX_VISIBLE })}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function AiSidebarSection({ currentWorkspaceSlug }: AiSidebarSectionProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { confirm, confirmDialog } = useConfirm();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handler = () => {
      setRefreshKey((current) => current + 1);
    };
    window.addEventListener(CONVERSATIONS_UPDATED_EVENT, handler);
    return () => {
      window.removeEventListener(CONVERSATIONS_UPDATED_EVENT, handler);
    };
  }, []);

  useEffect(() => {
    if (!token || !currentWorkspaceSlug) {
      setConversations([]);
      setError(null);
      return;
    }
    let cancelled = false;
    listConversations(token, { limit: 20 })
      .then((response) => {
        if (cancelled) return;
        setConversations(response.items);
        setError(null);
      })
      .catch((caughtError: unknown) => {
        if (cancelled) return;
        setConversations([]);
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : t('apps:ai.sidebar.loadConversationsFailed'),
        );
      });
    return () => {
      cancelled = true;
    };
  }, [currentWorkspaceSlug, location.search, refreshKey, t, token]);

  return (
    <>
      {confirmDialog}
      <AiConversationsSection
        conversations={conversations}
        error={error}
        activeConversationId={new URLSearchParams(location.search).get('c')}
        onSelect={(conversationId) => {
          navigate(
            `${buildWorkspaceAppPath(
              currentWorkspaceSlug,
              'ai',
            )}?c=${encodeURIComponent(conversationId)}`,
          );
        }}
        onNewConversation={() => {
          navigate(buildWorkspaceAppPath(currentWorkspaceSlug, 'ai'));
        }}
        onDelete={async (conversationId) => {
          if (!token) return;
          const confirmed = await confirm({
            title: t('apps:ai.sidebar.deleteConversation'),
            description: t('apps:ai.sidebar.deleteConversationDescription'),
            confirmLabel: t('common:actions.delete'),
            variant: 'danger',
          });
          if (!confirmed) return;
          await deleteConversation(token, conversationId);
          setConversations((current) =>
            current.filter((item) => item.id !== conversationId),
          );
          const activeId = new URLSearchParams(location.search).get('c');
          if (activeId === conversationId) {
            navigate(buildWorkspaceAppPath(currentWorkspaceSlug, 'ai'));
          }
        }}
      />
    </>
  );
}

export const aiSidebarConfig: AppSidebarConfig = {
  createActions: ({ currentWorkspaceSlug, navigate, user }) => [
    {
      id: 'ai-search',
      label: i18n.t('apps:ai.sidebar.search'),
      icon: Sparkles,
      run: () => {
        const searchItem = aiManifest.navItems.find((item) => item.id === 'search');
        navigate(
          searchItem
            ? resolveToolInvocationHref(searchItem, currentWorkspaceSlug, user)
            : '/tool/search',
        );
      },
    },
  ],
  beforeCategories: ({ currentWorkspaceSlug }) =>
    currentWorkspaceSlug ? (
      <AiSidebarSection currentWorkspaceSlug={currentWorkspaceSlug} />
    ) : null,
};
