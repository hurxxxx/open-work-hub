import { useEffect, useRef, useState } from 'react';
import { Bot, Check, Copy, Pencil, RotateCcw, User, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from '@open-work-hub/ui';

import { MarkdownContent } from '@/src/components/artifacts/MarkdownContent';
import type { ChatbotArtifactRenderer } from '../chatbot-experience';
import type { ArtifactBuffer } from '../../api/agent-events';

import { ArtifactCard } from './ArtifactCard';
import { ThinkingPanel } from './ThinkingPanel';
import type { ChatTurn } from './chat-turn';

export type { ChatTurn } from './chat-turn';

export interface MessageBubbleProps {
  turn: ChatTurn;
  activeArtifactId?: string | null;
  onOpenArtifact?: (artifactId: string) => void;
  onCopy?: (turn: ChatTurn) => Promise<void> | void;
  onEdit?: (turn: ChatTurn) => void;
  onRetry?: (turn: ChatTurn) => void;
  editValue?: string;
  onEditValueChange?: (value: string) => void;
  onSubmitEdit?: () => void;
  onCancelEdit?: () => void;
  sourceArtifactTypes?: readonly string[];
  artifactRenderers?: readonly ChatbotArtifactRenderer[];
  resolvedArtifacts?: readonly ArtifactBuffer[];
}

export function MessageBubble({
  turn,
  activeArtifactId = null,
  onOpenArtifact,
  onCopy,
  onEdit,
  onRetry,
  editValue,
  onEditValueChange,
  onSubmitEdit,
  onCancelEdit,
  sourceArtifactTypes = [],
  artifactRenderers = [],
  resolvedArtifacts = [],
}: MessageBubbleProps) {
  const { t } = useTranslation('apps');
  const isUser = turn.role === 'user';
  const isEditing = isUser && editValue !== undefined;
  const editRef = useRef<HTMLTextAreaElement | null>(null);
  const [copied, setCopied] = useState(false);
  const metaParts: string[] = [];
  if (!isUser) {
    if (turn.finishReason === 'length') {
      metaParts.push(t('ai.message.lengthLimit'));
    }
    if (turn.responseStatus === 'error') {
      metaParts.push(t('ai.message.responseFailed'));
    }
    if (turn.responseStatus === 'cancelled') {
      metaParts.push(t('ai.message.cancelled'));
    }
    if (turn.forcedLocal) {
      metaParts.push(t('ai.message.forcedLocal'));
    }
    if (turn.piiHits && turn.piiHits.length > 0) {
      metaParts.push(`PII: ${turn.piiHits.join(', ')}`);
    }
  }
  const showMeta = !isUser && metaParts.length > 0;
  const showFailedRetry =
    !isUser && turn.responseStatus === 'error' && Boolean(onRetry);
  const resolvedArtifactById = new Map(
    resolvedArtifacts.map((artifact) => [artifact.id, artifact]),
  );
  const actions = [
    !isEditing && onCopy
      ? {
          id: 'copy',
          label: copied ? t('ai.message.copySuccess') : t('ai.message.copy'),
          icon: copied ? Check : Copy,
          onClick: async () => {
            try {
              await onCopy(turn);
              setCopied(true);
            } catch {
              // The controller owns the user-facing error state.
            }
          },
        }
      : null,
    !isEditing && isUser && onEdit
      ? {
          id: 'edit',
          label: t('ai.message.edit'),
          icon: Pencil,
          onClick: () => onEdit(turn),
        }
      : null,
    !isEditing && !isUser && onRetry
      ? {
          id: 'retry',
          label: t('ai.message.retry'),
          icon: RotateCcw,
          onClick: () => onRetry(turn),
        }
      : null,
  ].filter(
    (
      action,
    ): action is {
      id: string;
      label: string;
      icon: typeof Copy;
      onClick: () => Promise<void> | void;
    } => action !== null,
  );

  useEffect(() => {
    setCopied(false);
  }, [turn.content, turn.id]);

  useEffect(() => {
    if (!isEditing) {
      return;
    }
    editRef.current?.focus();
    editRef.current?.select();
  }, [isEditing]);

  return (
    <div
      className={`group flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      {!isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-accent">
          <Bot size={16} />
        </div>
      )}
      <div
        className={`flex max-w-[min(720px,80%)] flex-col ${isUser ? 'items-end' : 'items-start'}`}
      >
        <div
          className={`rounded-lg border px-4 py-3 app-text-body-sm leading-relaxed ${
            isUser
              ? 'border-app-accent bg-app-accent text-app-accent-fg'
              : 'border-app-border bg-app-surface text-app-ink'
          }`}
        >
          {isEditing ? (
            <div className="space-y-2">
              <textarea
                ref={editRef}
                aria-label={t('ai.message.editPrompt')}
                className="min-h-[96px] w-full min-w-[min(520px,70vw)] resize-y rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none focus:border-app-accent"
                value={editValue}
                onChange={(event) => onEditValueChange?.(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    onCancelEdit?.();
                  }
                  if (
                    event.key === 'Enter' &&
                    (event.metaKey || event.ctrlKey)
                  ) {
                    event.preventDefault();
                    onSubmitEdit?.();
                  }
                }}
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onCancelEdit}
                  className="flex h-8 items-center gap-1 rounded-md border border-app-border bg-app-surface px-2 text-app-ink transition-colors hover:border-app-accent"
                >
                  <X size={14} />
                  {t('ai.message.cancelEdit')}
                </button>
                <button
                  type="button"
                  onClick={onSubmitEdit}
                  disabled={!editValue?.trim()}
                  className="flex h-8 items-center gap-1 rounded-md bg-app-accent px-2 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Check size={14} />
                  {t('ai.message.saveEdit')}
                </button>
              </div>
            </div>
          ) : isUser ? (
            <p className="m-0 whitespace-pre-wrap break-words">
              {turn.content}
            </p>
          ) : (
            <MarkdownContent
              content={turn.content}
              className="chat-message-markdown"
            />
          )}
          {!isUser && turn.reasoning ? (
            <ThinkingPanel
              reasoning={turn.reasoning}
              status={turn.reasoningStatus ?? 'done'}
            />
          ) : null}
          {showMeta && (
            <div className="mt-2 app-text-micro text-app-ink/55">
              {metaParts.join(' · ')}
            </div>
          )}
          {!isUser && turn.artifacts && turn.artifacts.length > 0
            ? turn.artifacts
                .filter(
                  (artifact) => !sourceArtifactTypes.includes(artifact.type),
                )
                .map((artifact) => (
                  <ArtifactCard
                    key={artifact.id}
                    artifact={resolvedArtifactById.get(artifact.id) ?? artifact}
                    isActive={activeArtifactId === artifact.id}
                    onOpen={(id) => onOpenArtifact?.(id)}
                    renderers={artifactRenderers}
                  />
                ))
            : null}
        </div>
        {actions.length > 0 ? (
          <div
            data-message-actions
            className={`mt-1 flex items-center gap-1 transition-opacity ${
              showFailedRetry
                ? 'opacity-100'
                : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'
            }`}
          >
            {actions.map((action) => {
              const Icon = action.icon;
              const showLabel = showFailedRetry && action.id === 'retry';
              return (
                <Tooltip key={action.id} content={action.label}>
                  <button
                    type="button"
                    aria-label={action.label}
                    onClick={() => {
                      void action.onClick();
                    }}
                    className={`flex h-7 items-center justify-center rounded-md border border-transparent text-app-ink/55 transition-colors hover:border-app-border hover:bg-app-surface hover:text-app-ink ${
                      showLabel ? 'gap-1 px-2' : 'w-7'
                    }`}
                  >
                    <Icon size={14} />
                    {showLabel ? (
                      <span className="app-text-micro">{action.label}</span>
                    ) : null}
                  </button>
                </Tooltip>
              );
            })}
          </div>
        ) : null}
      </div>
      {isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/55">
          <User size={16} />
        </div>
      )}
    </div>
  );
}
