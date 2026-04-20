import { useState } from 'react';
import { MessageSquare, Plus, Trash2 } from 'lucide-react';

import type { ConversationSummary } from '@/src/domains/ai/conversations-api';
import { cn } from '@/src/lib/utils';

export interface AiConversationsSectionProps {
  conversations: ConversationSummary[];
  error: string | null;
  activeConversationId: string | null;
  workspaceSlug: string;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
  onDelete: (conversationId: string) => void | Promise<void>;
}

const MAX_VISIBLE = 8;

export function AiConversationsSection({
  conversations,
  error,
  activeConversationId,
  onSelect,
  onNewConversation,
  onDelete,
}: AiConversationsSectionProps) {
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
        <span className="sidebar-submenu-label">새 대화</span>
      </button>

      <div className="pt-1">
        <span className="sidebar-section-label block px-3 py-1 text-gray-500">
          최근 대화
        </span>
        {error ? (
          <div className="px-3 py-1 app-text-micro text-amber-600 dark:text-amber-400">
            {error}
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-3 py-1 app-text-micro text-gray-500">
            아직 저장된 대화가 없습니다.
          </div>
        ) : (
          <ul className="space-y-0.5">
            {visible.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <li key={conversation.id} className="group/conversation relative">
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-3 py-1.5 pr-8 text-left transition-colors',
                      isActive
                        ? 'bg-app-surface-hover text-app-accent'
                        : 'text-app-ink hover:bg-app-surface-hover',
                    )}
                  >
                    <MessageSquare
                      size={13}
                      className={cn(
                        'shrink-0',
                        isActive
                          ? 'text-app-accent'
                          : 'text-gray-500 dark:text-gray-400',
                      )}
                    />
                    <span className="sidebar-submenu-label truncate">
                      {conversation.title || '제목 없는 대화'}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label="대화 삭제"
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
              ? '줄이기'
              : `더 보기 (${conversations.length - MAX_VISIBLE}개 더)`}
          </button>
        ) : null}
      </div>
    </div>
  );
}
