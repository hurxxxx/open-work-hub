import type { Dispatch, SetStateAction } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AiApiError,
  sendAiChat,
  streamAiChat,
  type AiChatResponse,
  type AiChatStreamRequest,
  type AiChatUsage,
} from '@/src/domains/ai/ai-api';
import type {
  ApprovalRequiredEvent,
  ApprovalResolvedEvent,
  ChatStreamStatus,
  ContentDeltaEvent,
  DoneEvent,
  DoneMeta,
  ErrorEvent,
  PendingApproval,
  RawAgentEvent,
  ReasoningDeltaEvent,
  ToolCallArgsDeltaEvent,
  ToolCallBuffer,
  ToolCallStartedEvent,
  ToolResultEvent,
  UsageEvent,
} from '@/src/domains/ai/agent-events';
import { iterSseEvents } from '@/src/domains/ai/sse-parser';

export type ChatTransport = 'stream' | 'sync' | null;

export interface ChatStreamState {
  contentBuffer: string;
  reasoningBuffer: string;
  usage: AiChatUsage | null;
  doneMeta: DoneMeta | null;
  status: ChatStreamStatus;
  errorMessage: string | null;
  toolCalls: ToolCallBuffer[];
  pendingApprovals: PendingApproval[];
  transport: ChatTransport;
  streamOpened: boolean;
}

export interface UseChatStreamApi {
  state: ChatStreamState;
  send: (payload: AiChatStreamRequest) => Promise<void>;
  abort: () => void;
  reset: () => void;
}

const AI_STREAM_ENABLED_STORAGE_KEY = 'aidoo.ai.streamEnabled';

const INITIAL_STATE: ChatStreamState = {
  contentBuffer: '',
  reasoningBuffer: '',
  usage: null,
  doneMeta: null,
  status: 'idle',
  errorMessage: null,
  toolCalls: [],
  pendingApprovals: [],
  transport: null,
  streamOpened: false,
};

export function useChatStream(token: string | null): UseChatStreamApi {
  const [state, setState] = useState<ChatStreamState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  const send = useCallback(
    async (payload: AiChatStreamRequest) => {
      if (!token) {
        throw new AiApiError(401, '로그인이 필요합니다.');
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      if (!shouldUseStreamingTransport()) {
        await sendViaSyncFallback({
          payload,
          token,
          setState,
        });
        return;
      }

      setState({
        ...INITIAL_STATE,
        status: 'streaming',
        transport: 'stream',
      });

      let streamOpened = false;
      try {
        const response = await streamAiChat({
          payload,
          token,
          signal: controller.signal,
        });
        if (!response.body) {
          throw new AiApiError(0, 'SSE 응답 본문이 비어 있습니다.');
        }

        streamOpened = true;
        setState((prev) => ({
          ...prev,
          streamOpened: true,
        }));

        for await (const message of iterSseEvents(
          response.body,
          controller.signal,
        )) {
          const parsed = parseMessage(message.data);
          if (!parsed) {
            continue;
          }
          let shouldBreak = false;
          setState((prev) => {
            const { next, terminal } = applyEnvelope(prev, parsed);
            if (terminal) {
              shouldBreak = true;
            }
            return next;
          });
          if (shouldBreak) {
            break;
          }
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          setState((prev) => ({
            ...prev,
            status: 'cancelled',
          }));
          return;
        }

        if (!streamOpened) {
          await sendViaSyncFallback({
            payload,
            token,
            setState,
            fallbackReason: error,
          });
          return;
        }

        setState((prev) => ({
          ...prev,
          status: 'error',
          errorMessage:
            error instanceof Error
              ? error.message
              : prev.errorMessage ?? 'AI 스트리밍에 실패했습니다.',
        }));
      }
    },
    [token],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return { state, send, abort, reset };
}

async function sendViaSyncFallback({
  payload,
  token,
  setState,
  fallbackReason,
}: {
  payload: AiChatStreamRequest;
  token: string;
  setState: Dispatch<SetStateAction<ChatStreamState>>;
  fallbackReason?: unknown;
}) {
  setState({
    ...INITIAL_STATE,
    status: 'streaming',
    transport: 'sync',
  });

  try {
    const response = await sendAiChat(payload, token);
    setState(syncResponseToState(response));
  } catch (error) {
    const resolved = error instanceof Error ? error : fallbackReason;
    setState((prev) => ({
      ...prev,
      status: 'error',
      errorMessage:
        resolved instanceof Error
          ? resolved.message
          : 'AI 응답에 실패했습니다.',
    }));
  }
}

function syncResponseToState(response: AiChatResponse): ChatStreamState {
  return {
    ...INITIAL_STATE,
    contentBuffer: response.content || '',
    usage: response.usage,
    doneMeta: {
      policy: response.policy,
      chosen_pool: response.chosen_pool,
      decision_reason: response.decision_reason,
      forced_local: response.forced_local,
      pii_hits: response.pii_hits,
      model: response.model,
      chosen_model: response.model,
      canonical_model: response.canonical_model,
      provider: response.provider,
    },
    status: 'done',
    transport: 'sync',
    streamOpened: false,
  };
}

function shouldUseStreamingTransport(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  try {
    const stored = window.localStorage.getItem(AI_STREAM_ENABLED_STORAGE_KEY);
    if (stored === '0' || stored === 'false' || stored === 'off') {
      return false;
    }
  } catch {
    return true;
  }
  return supportsStreamingTransport();
}

function supportsStreamingTransport(): boolean {
  return (
    typeof fetch === 'function' &&
    typeof AbortController !== 'undefined' &&
    typeof ReadableStream !== 'undefined' &&
    typeof TextDecoder !== 'undefined'
  );
}

function parseMessage(data: string): RawAgentEvent | null {
  try {
    return JSON.parse(data) as RawAgentEvent;
  } catch (error) {
    console.debug('[useChatStream] failed to parse SSE data', error);
    return null;
  }
}

function applyEnvelope(
  prev: ChatStreamState,
  event: RawAgentEvent,
): { next: ChatStreamState; terminal: boolean } {
  switch (event.type) {
    case 'content_delta': {
      const data = (event as ContentDeltaEvent).data;
      return {
        next: { ...prev, contentBuffer: prev.contentBuffer + data.text },
        terminal: false,
      };
    }
    case 'reasoning_delta': {
      const data = (event as ReasoningDeltaEvent).data;
      return {
        next: { ...prev, reasoningBuffer: prev.reasoningBuffer + data.text },
        terminal: false,
      };
    }
    case 'usage': {
      const data = (event as UsageEvent).data;
      return {
        next: {
          ...prev,
          usage: {
            prompt_tokens: data.prompt_tokens ?? null,
            completion_tokens: data.completion_tokens ?? null,
            total_tokens: data.total_tokens ?? null,
          },
        },
        terminal: false,
      };
    }
    case 'done': {
      const data = (event as DoneEvent).data;
      const reason = data.finish_reason;
      const status: ChatStreamStatus =
        reason === 'error'
          ? 'error'
          : reason === 'cancelled'
            ? 'cancelled'
            : 'done';
      return {
        next: { ...prev, status, doneMeta: data.meta ?? null },
        terminal: true,
      };
    }
    case 'error': {
      const data = (event as ErrorEvent).data;
      return {
        next: { ...prev, errorMessage: data.message },
        terminal: false,
      };
    }
    case 'tool_call_started': {
      const data = (event as ToolCallStartedEvent).data;
      const entry: ToolCallBuffer = {
        call_id: data.call_id,
        name: data.name,
        args_preview: data.args_preview ?? null,
        argsBuffer: '',
        result: null,
      };
      return {
        next: { ...prev, toolCalls: [...prev.toolCalls, entry] },
        terminal: false,
      };
    }
    case 'tool_call_args_delta': {
      const data = (event as ToolCallArgsDeltaEvent).data;
      const next = prev.toolCalls.map((call) =>
        call.call_id === data.call_id
          ? { ...call, argsBuffer: call.argsBuffer + data.delta }
          : call,
      );
      return { next: { ...prev, toolCalls: next }, terminal: false };
    }
    case 'tool_result': {
      const data = (event as ToolResultEvent).data;
      const next = prev.toolCalls.map((call) =>
        call.call_id === data.call_id
          ? {
              ...call,
              result: {
                status: data.status,
                preview: data.result_preview ?? null,
                error: data.error ?? null,
              },
            }
          : call,
      );
      return { next: { ...prev, toolCalls: next }, terminal: false };
    }
    case 'approval_required': {
      const data = (event as ApprovalRequiredEvent).data;
      const entry: PendingApproval = {
        approval_id: data.approval_id,
        tool: data.tool,
        resource_preview: data.resource_preview ?? null,
        decision: null,
      };
      return {
        next: {
          ...prev,
          pendingApprovals: [...prev.pendingApprovals, entry],
        },
        terminal: false,
      };
    }
    case 'approval_resolved': {
      const data = (event as ApprovalResolvedEvent).data;
      const next = prev.pendingApprovals.map((item) =>
        item.approval_id === data.approval_id
          ? { ...item, decision: data.decision }
          : item,
      );
      return { next: { ...prev, pendingApprovals: next }, terminal: false };
    }
    default:
      console.debug('[useChatStream] unknown envelope type', event.type);
      return { next: prev, terminal: false };
  }
}
