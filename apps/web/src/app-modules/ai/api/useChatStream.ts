import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AiApiError,
  sendAiChat,
  streamAiChat,
  streamAiChatResume,
  type AiChatResponse,
  type AiChatStreamRequest,
  type AiChatUsage,
  type ResumeAiChatRequest,
} from './ai-api';
import type {
  ApprovalRequiredEvent,
  ApprovalResolvedEvent,
  ArtifactBuffer,
  ArtifactCompletedEvent,
  ArtifactDeltaEvent,
  ArtifactStartedEvent,
  ChatStreamStatus,
  ContentDeltaEvent,
  ConversationAttachedEvent,
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
} from './agent-events';
import { iterSseEvents } from './sse-parser';

export type ChatTransport = 'stream' | 'sync' | null;

export interface ChatStreamState {
  contentBuffer: string;
  reasoningBuffer: string;
  usage: AiChatUsage | null;
  doneMeta: DoneMeta | null;
  finishReason: 'stop' | 'length' | 'cancelled' | 'error' | 'awaiting_approval' | null;
  status: ChatStreamStatus;
  errorMessage: string | null;
  toolCalls: ToolCallBuffer[];
  pendingApprovals: PendingApproval[];
  artifacts: ArtifactBuffer[];
  transport: ChatTransport;
  streamOpened: boolean;
  /** Populated from the `conversation_attached` envelope that opens every
   *  persisted stream. The web client reads this on the `done` transition
   *  and threads it back on follow-up `send()` calls so the backend keeps
   *  appending to the same Conversation row. */
  conversationId: string | null;
}

export interface UseChatStreamApi {
  state: ChatStreamState;
  send: (payload: AiChatStreamRequest) => Promise<void>;
  resume: (
    payload: ResumeAiChatRequest,
    options?: { seedApproval?: PendingApproval | null },
  ) => Promise<void>;
  abort: () => void;
  reset: (options?: { keepPendingApprovals?: boolean }) => void;
  replacePendingApprovals: (approvals: PendingApproval[]) => void;
  upsertPendingApproval: (approval: PendingApproval) => void;
}

const AI_STREAM_ENABLED_STORAGE_KEY = 'aidoo.ai.streamEnabled';

const INITIAL_STATE: ChatStreamState = {
  contentBuffer: '',
  reasoningBuffer: '',
  usage: null,
  doneMeta: null,
  finishReason: null,
  status: 'idle',
  errorMessage: null,
  toolCalls: [],
  pendingApprovals: [],
  artifacts: [],
  transport: null,
  streamOpened: false,
  conversationId: null,
};

export function useChatStream(token: string | null): UseChatStreamApi {
  const [state, setState] = useState<ChatStreamState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef(0);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const setStateForRun = useCallback(
    (
      runId: number,
      next:
        | ChatStreamState
        | ((prev: ChatStreamState) => ChatStreamState),
    ) => {
      setState((prev) => {
        if (runIdRef.current !== runId) {
          return prev;
        }
        return typeof next === 'function'
          ? next(prev)
          : next;
      });
    },
    [],
  );

  const reset = useCallback((options?: { keepPendingApprovals?: boolean }) => {
    runIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setState((prev) =>
      options?.keepPendingApprovals
        ? { ...INITIAL_STATE, pendingApprovals: prev.pendingApprovals }
        : INITIAL_STATE,
    );
  }, []);

  const replacePendingApprovals = useCallback((approvals: PendingApproval[]) => {
    setState((prev) => ({ ...prev, pendingApprovals: approvals }));
  }, []);

  const upsertPendingApproval = useCallback((approval: PendingApproval) => {
    setState((prev) => ({
      ...prev,
      pendingApprovals: mergePendingApprovals(prev.pendingApprovals, [approval]),
    }));
  }, []);

  const send = useCallback(
    async (payload: AiChatStreamRequest) => {
      if (!token) {
        throw new AiApiError(401, '로그인이 필요합니다.');
      }

      abortRef.current?.abort();
      const runId = runIdRef.current + 1;
      runIdRef.current = runId;
      const controller = new AbortController();
      abortRef.current = controller;

      if (!shouldUseStreamingTransport()) {
        await sendViaSyncFallback({
          payload,
          token,
          runId,
          setStateForRun,
        });
        return;
      }

      setStateForRun(runId, {
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
        setStateForRun(runId, (prev) => ({
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
          setStateForRun(runId, (prev) => {
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
          setStateForRun(runId, (prev) => ({
            ...prev,
            status: 'cancelled',
            // Any artifacts still streaming are implicitly terminal now.
            // Flipping status prevents the card from rendering as
            // "생성 중…" forever in the finalized turn.
            artifacts: prev.artifacts.map((artifact) =>
              artifact.status === 'open'
                ? { ...artifact, status: 'closed' as const }
                : artifact,
            ),
          }));
          return;
        }

        if (!streamOpened) {
          // Auto-fallback to the sync endpoint when SSE never opened (proxy
          // buffering, transient gateway, etc.) so the user still gets a
          // reply. `/api/v1/ai/chat` now accepts the same persistence
          // fields as `/chat/stream`, so conversation history continues to
          // append even when the transport downgrades.
          await sendViaSyncFallback({
            payload,
            token,
            runId,
            setStateForRun,
            fallbackReason: error,
          });
          return;
        }

        setStateForRun(runId, (prev) => ({
          ...prev,
          status: 'error',
          errorMessage:
            error instanceof Error
              ? error.message
              : prev.errorMessage ?? 'AI 스트리밍에 실패했습니다.',
          // Same rationale as the AbortError branch: any artifact still in
          // the ``open`` state has no more deltas coming, so flip it to
          // closed before AIView finalizes the turn. Otherwise the saved
          // card sits as "생성 중…" forever.
          artifacts: prev.artifacts.map((artifact) =>
            artifact.status === 'open'
              ? { ...artifact, status: 'closed' as const }
              : artifact,
          ),
        }));
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [setStateForRun, token],
  );

  const resume = useCallback(
    async (
      payload: ResumeAiChatRequest,
      options?: { seedApproval?: PendingApproval | null },
    ) => {
      if (!token) {
        throw new AiApiError(401, '로그인이 필요합니다.');
      }

      abortRef.current?.abort();
      const runId = runIdRef.current + 1;
      runIdRef.current = runId;
      const controller = new AbortController();
      abortRef.current = controller;
      const seededApproval = options?.seedApproval ?? null;

      setStateForRun(runId, {
        ...INITIAL_STATE,
        status: 'streaming',
        transport: 'stream',
        pendingApprovals: seededApproval ? [seededApproval] : [],
      });

      try {
        const response = await streamAiChatResume({
          payload,
          token,
          signal: controller.signal,
        });
        if (!response.body) {
          throw new AiApiError(0, 'SSE 응답 본문이 비어 있습니다.');
        }

        setStateForRun(runId, (prev) => ({
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
          setStateForRun(runId, (prev) => {
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
          setStateForRun(runId, (prev) => ({
            ...prev,
            status: 'cancelled',
            artifacts: prev.artifacts.map((artifact) =>
              artifact.status === 'open'
                ? { ...artifact, status: 'closed' as const }
                : artifact,
            ),
          }));
          return;
        }

        setStateForRun(runId, (prev) => ({
          ...prev,
          status: 'error',
          errorMessage:
            error instanceof Error
              ? error.message
              : prev.errorMessage ?? 'AI 재개 스트리밍에 실패했습니다.',
          artifacts: prev.artifacts.map((artifact) =>
            artifact.status === 'open'
              ? { ...artifact, status: 'closed' as const }
              : artifact,
          ),
        }));
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [setStateForRun, token],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return {
    state,
    send,
    resume,
    abort,
    reset,
    replacePendingApprovals,
    upsertPendingApproval,
  };
}

async function sendViaSyncFallback({
  payload,
  token,
  runId,
  setStateForRun,
  fallbackReason,
}: {
  payload: AiChatStreamRequest;
  token: string;
  runId: number;
  setStateForRun: (
    runId: number,
    next:
      | ChatStreamState
      | ((prev: ChatStreamState) => ChatStreamState),
  ) => void;
  fallbackReason?: unknown;
}) {
  setStateForRun(runId, {
    ...INITIAL_STATE,
    status: 'streaming',
    transport: 'sync',
  });

  const {
    stream_reasoning: _streamReasoning,
    ...syncPayload
  } = payload;
  void _streamReasoning;

  try {
    const response = await sendAiChat(syncPayload, token);
    setStateForRun(runId, syncResponseToState(response));
  } catch (error) {
    const resolved = error instanceof Error ? error : fallbackReason;
    setStateForRun(runId, (prev) => ({
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
  // Trust the server's artifact parse result. The field is always present
  // on any backend that ships `<artifact>` markup at all — older servers
  // that predate Phase C never emit the markup, so there's nothing to
  // extract client-side. Re-parsing here would only diverge from the
  // server's fence/inline-code suppression rules during a rolling deploy.
  const serverArtifacts = response.artifacts ?? [];
  const content = response.content || '';
  const artifacts = serverArtifacts.map(
    (artifact): ArtifactBuffer => ({
      id: artifact.id,
      type: artifact.type,
      title: artifact.title ?? null,
      language: artifact.language ?? null,
      content: artifact.content,
      status: 'closed',
    }),
  );
  return {
    ...INITIAL_STATE,
    contentBuffer: content,
    artifacts,
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
    finishReason:
      response.finish_reason === 'stop' ||
      response.finish_reason === 'length' ||
      response.finish_reason === 'cancelled' ||
      response.finish_reason === 'error' ||
      response.finish_reason === 'awaiting_approval'
        ? response.finish_reason
        : null,
    status: 'done',
    transport: 'sync',
    streamOpened: false,
    conversationId: response.conversation_id ?? null,
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
        next: {
          ...prev,
          status,
          doneMeta: data.meta ?? null,
          finishReason: reason,
        },
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
        startedAtMs: event.timestamp_ms,
        completedAtMs: null,
        status: 'running',
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
      const nextStatus: ToolCallBuffer['status'] =
        data.status === 'ok'
          ? 'ok'
          : data.status === 'rejected'
            ? 'rejected'
            : 'error';
      const result = {
        status: data.status,
        preview: data.result_preview ?? null,
        error: data.error ?? null,
      };
      let matched = false;
      const next = prev.toolCalls.map((call) => {
        if (call.call_id !== data.call_id) {
          return call;
        }
        matched = true;
        return {
          ...call,
          completedAtMs: event.timestamp_ms,
          status: nextStatus,
          result,
        };
      });
      if (!matched) {
        const approval = prev.pendingApprovals.find(
          (item) => item.call_id === data.call_id,
        );
        next.push({
          call_id: data.call_id,
          name: approval?.tool ?? 'tool',
          args_preview: null,
          argsBuffer: '',
          startedAtMs: event.timestamp_ms,
          completedAtMs: event.timestamp_ms,
          status: nextStatus,
          result,
        });
      }
      return { next: { ...prev, toolCalls: next }, terminal: false };
    }
    case 'approval_required': {
      const data = (event as ApprovalRequiredEvent).data;
      const entry: PendingApproval = {
        approval_id: data.approval_id,
        call_id: data.call_id,
        tool: data.tool,
        resource_preview: data.resource_preview ?? null,
        expires_at_ms: data.expires_at_ms,
        decision: null,
        reason: null,
      };
      return {
        next: {
          ...prev,
          pendingApprovals: mergePendingApprovals(prev.pendingApprovals, [entry]),
        },
        terminal: false,
      };
    }
    case 'approval_resolved': {
      const data = (event as ApprovalResolvedEvent).data;
      const next = prev.pendingApprovals.map((item) =>
        item.approval_id === data.approval_id
          ? { ...item, decision: data.decision, reason: data.reason ?? null }
          : item,
      );
      return { next: { ...prev, pendingApprovals: next }, terminal: false };
    }
    case 'conversation_attached': {
      const data = (event as ConversationAttachedEvent).data;
      return {
        next: { ...prev, conversationId: data.conversation_id },
        terminal: false,
      };
    }
    case 'artifact_started': {
      const data = (event as ArtifactStartedEvent).data;
      const entry: ArtifactBuffer = {
        id: data.artifact_id,
        type: data.artifact_type,
        title: data.title ?? null,
        language: data.language ?? null,
        content: '',
        status: 'open',
      };
      // Artifacts arrive in order; append preserves that ordering for the
      // side panel's "next / previous" navigation.
      return {
        next: { ...prev, artifacts: [...prev.artifacts, entry] },
        terminal: false,
      };
    }
    case 'artifact_delta': {
      const data = (event as ArtifactDeltaEvent).data;
      const next = prev.artifacts.map((artifact) =>
        artifact.id === data.artifact_id
          ? { ...artifact, content: artifact.content + data.delta }
          : artifact,
      );
      return { next: { ...prev, artifacts: next }, terminal: false };
    }
    case 'artifact_completed': {
      const data = (event as ArtifactCompletedEvent).data;
      const next = prev.artifacts.map((artifact) =>
        artifact.id === data.artifact_id
          ? { ...artifact, status: 'closed' as const }
          : artifact,
      );
      return { next: { ...prev, artifacts: next }, terminal: false };
    }
    default:
      console.debug('[useChatStream] unknown envelope type', event.type);
      return { next: prev, terminal: false };
  }
}

function mergePendingApprovals(
  current: PendingApproval[],
  incoming: PendingApproval[],
): PendingApproval[] {
  const merged = new Map<string, PendingApproval>();
  for (const approval of [...current, ...incoming]) {
    merged.set(approval.approval_id, approval);
  }
  return Array.from(merged.values());
}
