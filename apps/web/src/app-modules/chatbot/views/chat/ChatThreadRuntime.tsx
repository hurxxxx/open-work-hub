import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from '@assistant-ui/react';
import { useMemo, type ReactNode } from 'react';

import type { ChatTurn } from './chat-turn';
import type { LiveAssistant } from './ChatThread';

export function projectChatTurn(
  turn: ChatTurn,
  running = false,
): ThreadMessageLike {
  return {
    id: turn.id,
    role: turn.role,
    content:
      turn.role === 'user'
        ? turn.content
        : [
            ...(turn.reasoning
              ? [{ type: 'reasoning' as const, text: turn.reasoning }]
              : []),
            ...(turn.toolCalls ?? []).map((call, index) => ({
              type: 'tool-call' as const,
              toolCallId: call.call_id || `${turn.id}:tool:${index}`,
              toolName: call.name,
              argsText: call.argsBuffer || '{}',
              result:
                call.result ??
                (running && call.status === 'running'
                  ? undefined
                  : { status: call.status }),
              isError: call.status === 'error' || call.status === 'rejected',
            })),
            { type: 'text', text: turn.content },
          ],
    status:
      turn.role === 'user'
        ? undefined
        : running
          ? { type: 'running' }
          : turn.responseStatus === 'error'
            ? { type: 'incomplete', reason: 'error' }
            : turn.responseStatus === 'cancelled'
              ? { type: 'incomplete', reason: 'cancelled' }
              : { type: 'complete', reason: 'stop' },
    metadata: {
      custom: {
        turnId: turn.id,
        artifacts: turn.artifacts ?? [],
        approvals: turn.pendingApprovals ?? [],
      },
    },
  };
}

function textContent(message: AppendMessage): string {
  return message.content
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('\n');
}

const identityMessage = (message: ThreadMessageLike) => message;

export interface ChatThreadRuntimeProps {
  turns: ChatTurn[];
  liveAssistant: LiveAssistant | null;
  onSendMessage?: (content: string) => void;
  onEditMessage?: (turn: ChatTurn, content: string) => Promise<void>;
  onRetryTurn?: (turn: ChatTurn) => void;
  onAbort?: () => void;
  children: ReactNode;
}

/** A read projection of OWH state; the controller remains the execution owner. */
export function ChatThreadRuntime({
  turns,
  liveAssistant,
  onSendMessage,
  onEditMessage,
  onRetryTurn,
  onAbort,
  children,
}: ChatThreadRuntimeProps) {
  const messages = useMemo(
    () => [
      ...turns.map((turn) => projectChatTurn(turn)),
      ...(liveAssistant
        ? [
            projectChatTurn(
              {
                id: 'owh-live-assistant',
                role: 'assistant',
                content: liveAssistant.content,
                reasoning: liveAssistant.reasoning,
                toolCalls: liveAssistant.toolCalls,
                artifacts: liveAssistant.artifacts,
              },
              liveAssistant.status === 'streaming',
            ),
          ]
        : []),
    ],
    [turns, liveAssistant],
  );
  const runtime = useExternalStoreRuntime({
    messages,
    convertMessage: identityMessage,
    isRunning: liveAssistant?.status === 'streaming',
    isSendDisabled: !onSendMessage,
    onNew: async (message) => {
      onSendMessage?.(textContent(message));
    },
    onCancel: onAbort
      ? async () => {
          onAbort();
        }
      : undefined,
    onEdit: onEditMessage
      ? async (message) => {
          const turn = turns.find((item) => item.id === message.sourceId);
          if (turn?.role === 'user')
            await onEditMessage(turn, textContent(message));
        }
      : undefined,
    onReload: onRetryTurn
      ? async (parentId) => {
          const turn =
            turns[turns.findIndex((item) => item.id === parentId) + 1];
          if (turn?.role === 'assistant') onRetryTurn(turn);
        }
      : undefined,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
