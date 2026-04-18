import { Bot, User } from 'lucide-react';

import { ThinkingPanel } from '@/src/components/views/chat/ThinkingPanel';
import type {
  ChatStreamStatus,
  PendingApproval,
  ToolCallBuffer,
} from '@/src/domains/ai/agent-events';

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  reasoningStatus?: ChatStreamStatus;
  provider?: string;
  policy?: string | null;
  chosenPool?: 'local' | 'external' | null;
  decisionReason?: string | null;
  forcedLocal?: boolean;
  piiHits?: string[];
  responseStatus?: Exclude<ChatStreamStatus, 'idle' | 'streaming'>;
  toolCalls?: ToolCallBuffer[];
  pendingApprovals?: PendingApproval[];
}

export interface MessageBubbleProps {
  turn: ChatTurn;
}

function poolLabel(pool: ChatTurn['chosenPool']): string {
  if (pool === 'external') {
    return 'external 풀';
  }
  if (pool === 'local') {
    return 'local 풀';
  }
  return '';
}

export function MessageBubble({ turn }: MessageBubbleProps) {
  const isUser = turn.role === 'user';
  const showMeta =
    !isUser &&
    (turn.chosenPool ||
      turn.responseStatus === 'error' ||
      turn.responseStatus === 'cancelled');

  return (
    <div
      className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
          <Bot size={16} />
        </div>
      )}
      <div
        className={`max-w-[min(720px,80%)] rounded-lg border px-4 py-3 app-text-body-sm leading-relaxed ${
          isUser
            ? 'border-app-accent bg-app-accent text-app-accent-fg'
            : 'border-app-border bg-app-surface text-app-ink'
        }`}
      >
        <p className="m-0 whitespace-pre-wrap break-words">{turn.content}</p>
        {!isUser && turn.reasoning ? (
          <ThinkingPanel
            reasoning={turn.reasoning}
            status={turn.reasoningStatus ?? 'done'}
          />
        ) : null}
        {showMeta && (
          <div className="mt-2 app-text-micro text-gray-500">
            {turn.responseStatus === 'error' ? '응답 실패' : ''}
            {turn.responseStatus === 'cancelled' ? '응답 중단' : ''}
            {turn.chosenPool
              ? `${turn.responseStatus ? ' · ' : ''}${poolLabel(turn.chosenPool)} · ${turn.policy ?? 'policy_unknown'}`
              : ''}
            {turn.decisionReason ? ` · ${turn.decisionReason}` : ''}
            {turn.forcedLocal ? ' · local 강제' : ''}
            {turn.piiHits && turn.piiHits.length > 0
              ? ` · PII: ${turn.piiHits.join(', ')}`
              : ''}
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-gray-500">
          <User size={16} />
        </div>
      )}
    </div>
  );
}
