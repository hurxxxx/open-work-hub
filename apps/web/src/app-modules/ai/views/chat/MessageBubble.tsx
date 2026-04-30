import { Bot, User } from 'lucide-react';

import { ArtifactCard } from './ArtifactCard';
import { ThinkingPanel } from './ThinkingPanel';
import type {
  ArtifactBuffer,
  ChatStreamStatus,
  PendingApproval,
  ToolCallBuffer,
} from '../../api/agent-events';

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  reasoningStatus?: ChatStreamStatus;
  finishReason?: 'stop' | 'length' | 'cancelled' | 'error' | 'awaiting_approval' | null;
  provider?: string;
  policy?: string | null;
  chosenPool?: 'local' | 'external' | null;
  decisionReason?: string | null;
  forcedLocal?: boolean;
  piiHits?: string[];
  responseStatus?: Exclude<ChatStreamStatus, 'idle' | 'streaming'>;
  toolCalls?: ToolCallBuffer[];
  pendingApprovals?: PendingApproval[];
  artifacts?: ArtifactBuffer[];
}

export interface MessageBubbleProps {
  turn: ChatTurn;
  activeArtifactId?: string | null;
  onOpenArtifact?: (artifactId: string) => void;
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

export function MessageBubble({
  turn,
  activeArtifactId = null,
  onOpenArtifact,
}: MessageBubbleProps) {
  const isUser = turn.role === 'user';
  const metaParts: string[] = [];
  if (!isUser) {
    if (turn.finishReason === 'length') {
      metaParts.push('토큰 한도 도달');
    }
    if (turn.responseStatus === 'error') {
      metaParts.push('응답 실패');
    }
    if (turn.responseStatus === 'cancelled') {
      metaParts.push('응답 중단');
    }
    if (turn.chosenPool) {
      metaParts.push(`${poolLabel(turn.chosenPool)} · ${turn.policy ?? 'policy_unknown'}`);
    }
    if (turn.decisionReason) {
      metaParts.push(turn.decisionReason);
    }
    if (turn.forcedLocal) {
      metaParts.push('local 강제');
    }
    if (turn.piiHits && turn.piiHits.length > 0) {
      metaParts.push(`PII: ${turn.piiHits.join(', ')}`);
    }
  }
  const showMeta =
    !isUser && metaParts.length > 0;

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
            {metaParts.join(' · ')}
          </div>
        )}
        {!isUser && turn.artifacts && turn.artifacts.length > 0
          ? turn.artifacts.map((artifact) => (
              <ArtifactCard
                key={artifact.id}
                artifact={artifact}
                isActive={activeArtifactId === artifact.id}
                onOpen={(id) => onOpenArtifact?.(id)}
              />
            ))
          : null}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-gray-500">
          <User size={16} />
        </div>
      )}
    </div>
  );
}
