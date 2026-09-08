import { ArrowDown, Bot, Loader2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { MarkdownContent } from '@/src/components/artifacts/MarkdownContent';

import type { ArtifactBuffer, ChatStreamStatus } from '../../api/agent-events';
import type { ChatbotArtifactRenderer } from '../chatbot-experience';
import { AiRunProgress, type AiRunProgressValue } from './AiRunProgress';
import { ArtifactCard } from './ArtifactCard';
import { MessageBubble, type ChatTurn } from './MessageBubble';
import { ThinkingPanel } from './ThinkingPanel';

export interface LiveAssistant {
  content: string;
  reasoning: string;
  status: ChatStreamStatus;
  artifacts?: ArtifactBuffer[];
  progress?: AiRunProgressValue;
}

export interface ChatThreadProps {
  turns: ChatTurn[];
  liveAssistant: LiveAssistant | null;
  typingLabel: string;
  jumpToBottomLabel: string;
  activeArtifactId?: string | null;
  onOpenArtifact?: (artifactId: string) => void;
  onCopyTurn?: (turn: ChatTurn) => Promise<void> | void;
  onEditTurn?: (turn: ChatTurn) => void;
  onRetryTurn?: (turn: ChatTurn) => void;
  editingTurnId?: string | null;
  editValue?: string;
  onEditValueChange?: (value: string) => void;
  onSubmitEdit?: () => void;
  onCancelEdit?: () => void;
  forceFollowKey?: number;
  sourceArtifactTypes?: readonly string[];
  artifactRenderers?: readonly ChatbotArtifactRenderer[];
  resolvedArtifacts?: readonly ArtifactBuffer[];
}

function hasPersistedTurnId(turn: ChatTurn): boolean {
  return !turn.id.startsWith('user-') && !turn.id.startsWith('assistant-');
}

type ScrollFollowState = {
  forceFollowKey: number;
  isAtBottom: boolean;
};

export function ChatThread({
  turns,
  liveAssistant,
  typingLabel,
  jumpToBottomLabel,
  activeArtifactId = null,
  onOpenArtifact,
  onCopyTurn,
  onEditTurn,
  onRetryTurn,
  editingTurnId = null,
  editValue,
  onEditValueChange,
  onSubmitEdit,
  onCancelEdit,
  forceFollowKey = 0,
  sourceArtifactTypes = [],
  artifactRenderers = [],
  resolvedArtifacts = [],
}: ChatThreadProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const shouldFollowRef = useRef(true);
  const [scrollFollowState, setScrollFollowState] = useState<ScrollFollowState>(
    {
      forceFollowKey,
      isAtBottom: true,
    },
  );
  const isAtBottom =
    scrollFollowState.forceFollowKey === forceFollowKey
      ? scrollFollowState.isAtBottom
      : true;

  useEffect(() => {
    shouldFollowRef.current = true;
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'auto',
    });
  }, [forceFollowKey]);

  useEffect(() => {
    if (!shouldFollowRef.current) {
      return;
    }
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'auto',
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
    (liveAssistant.artifacts?.length ?? 0) === 0 &&
    !liveAssistant.progress;

  return (
    <div className="relative min-h-0 flex-1 bg-app-bg">
      <div
        ref={scrollRef}
        onScroll={(event) => {
          const target = event.currentTarget;
          const distanceFromBottom =
            target.scrollHeight - target.scrollTop - target.clientHeight;
          const nextAtBottom = distanceFromBottom < 96;
          shouldFollowRef.current = nextAtBottom;
          setScrollFollowState({
            forceFollowKey,
            isAtBottom: nextAtBottom,
          });
        }}
        className="custom-scrollbar h-full space-y-4 overflow-y-auto p-5"
      >
        {turns.map((turn) => (
          <MessageBubble
            key={turn.id}
            turn={turn}
            activeArtifactId={activeArtifactId}
            onOpenArtifact={onOpenArtifact}
            onCopy={onCopyTurn}
            onEdit={hasPersistedTurnId(turn) ? onEditTurn : undefined}
            onRetry={hasPersistedTurnId(turn) ? onRetryTurn : undefined}
            editValue={editingTurnId === turn.id ? editValue : undefined}
            onEditValueChange={onEditValueChange}
            onSubmitEdit={onSubmitEdit}
            onCancelEdit={onCancelEdit}
            sourceArtifactTypes={sourceArtifactTypes}
            artifactRenderers={artifactRenderers}
            resolvedArtifacts={resolvedArtifacts}
          />
        ))}
        {liveAssistant && !showTypingHint && (
          <div className="flex gap-3 justify-start">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
              <Bot size={16} />
            </div>
            <div className="max-w-[min(720px,80%)] rounded-lg border border-app-border bg-app-surface px-4 py-3 app-text-body-sm leading-relaxed text-app-ink">
              {liveAssistant.content ? (
                <MarkdownContent
                  content={liveAssistant.content}
                  className="chat-message-markdown"
                />
              ) : null}
              {liveAssistant.progress ? (
                <AiRunProgress value={liveAssistant.progress} />
              ) : null}
              {liveAssistant.status === 'streaming' && (
                <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-app-accent align-baseline" />
              )}
              <ThinkingPanel
                reasoning={liveAssistant.reasoning}
                status={liveAssistant.status}
              />
              {liveAssistant.artifacts && liveAssistant.artifacts.length > 0
                ? liveAssistant.artifacts
                    .filter(
                      (artifact) =>
                        !sourceArtifactTypes.includes(artifact.type),
                    )
                    .map((artifact) => (
                      <ArtifactCard
                        key={artifact.id}
                        artifact={artifact}
                        isActive={activeArtifactId === artifact.id}
                        onOpen={(id) => onOpenArtifact?.(id)}
                        renderers={artifactRenderers}
                      />
                    ))
                : null}
            </div>
          </div>
        )}
        {showTypingHint && (
          <div className="flex items-center gap-3 text-app-ink/55">
            <div className="flex size-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
              <Loader2 size={16} className="animate-spin" />
            </div>
            <span className="app-text-body-sm">{typingLabel}</span>
          </div>
        )}
      </div>
      {!isAtBottom ? (
        <button
          type="button"
          aria-label={jumpToBottomLabel}
          onClick={() => {
            shouldFollowRef.current = true;
            setScrollFollowState({
              forceFollowKey,
              isAtBottom: true,
            });
            scrollRef.current?.scrollTo({
              top: scrollRef.current.scrollHeight,
              behavior: 'smooth',
            });
          }}
          className="absolute bottom-4 left-1/2 flex size-9 -translate-x-1/2 items-center justify-center rounded-full border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:border-app-accent"
        >
          <ArrowDown size={16} />
        </button>
      ) : null}
    </div>
  );
}
