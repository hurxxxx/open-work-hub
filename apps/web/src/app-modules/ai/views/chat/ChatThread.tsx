import { useEffect, useRef } from 'react';
import { Bot, Loader2 } from 'lucide-react';

import { ArtifactCard } from './ArtifactCard';
import {
  MessageBubble,
  type ChatTurn,
} from './MessageBubble';
import { ThinkingPanel } from './ThinkingPanel';
import type {
  ArtifactBuffer,
  ChatStreamStatus,
} from '../../api/agent-events';

export interface LiveAssistant {
  content: string;
  reasoning: string;
  status: ChatStreamStatus;
  artifacts?: ArtifactBuffer[];
}

export interface ChatThreadProps {
  turns: ChatTurn[];
  liveAssistant: LiveAssistant | null;
  activeArtifactId?: string | null;
  onOpenArtifact?: (artifactId: string) => void;
}

export function ChatThread({
  turns,
  liveAssistant,
  activeArtifactId = null,
  onOpenArtifact,
}: ChatThreadProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [
    turns,
    liveAssistant?.content.length,
    liveAssistant?.reasoning.length,
    liveAssistant?.artifacts?.length,
    liveAssistant?.status,
  ]);

  const showTypingHint =
    liveAssistant !== null &&
    liveAssistant.status === 'streaming' &&
    liveAssistant.content.length === 0 &&
    liveAssistant.reasoning.length === 0 &&
    (liveAssistant.artifacts?.length ?? 0) === 0;

  return (
    <div
      ref={scrollRef}
      className="custom-scrollbar flex-1 space-y-4 overflow-y-auto bg-app-bg px-5 py-5"
    >
      {turns.map((turn) => (
        <MessageBubble
          key={turn.id}
          turn={turn}
          activeArtifactId={activeArtifactId}
          onOpenArtifact={onOpenArtifact}
        />
      ))}
      {liveAssistant && !showTypingHint && (
        <div className="flex gap-3 justify-start">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
            <Bot size={16} />
          </div>
          <div className="max-w-[min(720px,80%)] rounded-lg border border-app-border bg-app-surface px-4 py-3 app-text-body-sm leading-relaxed text-app-ink">
            <p className="m-0 whitespace-pre-wrap break-words">
              {liveAssistant.content}
              {liveAssistant.status === 'streaming' && (
                <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-app-accent align-baseline" />
              )}
            </p>
            <ThinkingPanel
              reasoning={liveAssistant.reasoning}
              status={liveAssistant.status}
            />
            {liveAssistant.artifacts && liveAssistant.artifacts.length > 0
              ? liveAssistant.artifacts.map((artifact) => (
                  <ArtifactCard
                    key={artifact.id}
                    artifact={artifact}
                    isActive={activeArtifactId === artifact.id}
                    onOpen={(id) => onOpenArtifact?.(id)}
                  />
                ))
              : null}
          </div>
        </div>
      )}
      {showTypingHint && (
        <div className="flex items-center gap-3 text-gray-500">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
            <Loader2 size={16} className="animate-spin" />
          </div>
          <span className="app-text-body-sm">답변 작성 중</span>
        </div>
      )}
    </div>
  );
}
