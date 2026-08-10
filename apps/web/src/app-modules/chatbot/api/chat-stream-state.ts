import type { AiChatResponse, AiChatUsage } from './chatbot-api';
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

export type ChatTransport = 'stream' | 'sync' | null;

export interface ChatStreamState {
  contentBuffer: string;
  reasoningBuffer: string;
  /**
   * Latest user prompt for the active run. Unlike the route-local transcript,
   * this survives an SPA route unmount so the question can be rendered while
   * the persisted conversation is being hydrated again.
   */
  pendingUserContent: string | null;
  usage: AiChatUsage | null;
  doneMeta: DoneMeta | null;
  finishReason:
    | 'stop'
    | 'length'
    | 'cancelled'
    | 'error'
    | 'awaiting_approval'
    | null;
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

export interface ChatStreamTransition {
  next: ChatStreamState;
  terminal: boolean;
}

export const CHAT_STREAM_INITIAL_STATE: ChatStreamState = {
  contentBuffer: '',
  reasoningBuffer: '',
  pendingUserContent: null,
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

export function createChatStreamStartState({
  transport,
  pendingApprovals = [],
  pendingUserContent = null,
}: {
  transport: Exclude<ChatTransport, null>;
  pendingApprovals?: PendingApproval[];
  pendingUserContent?: string | null;
}): ChatStreamState {
  return {
    ...CHAT_STREAM_INITIAL_STATE,
    status: 'streaming',
    transport,
    pendingApprovals: [...pendingApprovals],
    pendingUserContent,
  };
}

export function resetChatStreamState(
  prev: ChatStreamState,
  options?: { keepPendingApprovals?: boolean },
): ChatStreamState {
  return options?.keepPendingApprovals
    ? { ...CHAT_STREAM_INITIAL_STATE, pendingApprovals: prev.pendingApprovals }
    : CHAT_STREAM_INITIAL_STATE;
}

export function replaceChatStreamPendingApprovals(
  prev: ChatStreamState,
  approvals: PendingApproval[],
): ChatStreamState {
  return { ...prev, pendingApprovals: approvals };
}

export function upsertChatStreamPendingApproval(
  prev: ChatStreamState,
  approval: PendingApproval,
): ChatStreamState {
  return {
    ...prev,
    pendingApprovals: mergePendingApprovals(prev.pendingApprovals, [approval]),
  };
}

export function markChatStreamOpened(prev: ChatStreamState): ChatStreamState {
  return { ...prev, streamOpened: true };
}

export function cancelChatStreamState(prev: ChatStreamState): ChatStreamState {
  return {
    ...prev,
    status: 'cancelled',
    artifacts: closeOpenArtifacts(prev.artifacts),
  };
}

export function failChatStreamState(
  prev: ChatStreamState,
  errorMessage: string,
): ChatStreamState {
  return {
    ...prev,
    status: 'error',
    errorMessage,
    artifacts: closeOpenArtifacts(prev.artifacts),
  };
}

export function syncResponseToChatStreamState(
  response: AiChatResponse,
): ChatStreamState {
  // Trust the server's artifact parse result. The field is always present
  // on any backend that ships `<artifact>` markup at all; older servers
  // that predate Phase C never emit the markup, so there's nothing to
  // extract client-side. Re-parsing here would only diverge from the
  // server's fence/inline-code suppression rules during a rolling deploy.
  return {
    ...CHAT_STREAM_INITIAL_STATE,
    contentBuffer: response.content || '',
    artifacts: syncResponseArtifacts(response),
    usage: response.usage,
    doneMeta: syncResponseDoneMeta(response),
    finishReason: syncResponseFinishReason(response.finish_reason),
    status: 'done',
    transport: 'sync',
    streamOpened: false,
    conversationId: response.conversation_id ?? null,
  };
}

export function applyChatStreamEvent(
  prev: ChatStreamState,
  event: RawAgentEvent,
): ChatStreamTransition {
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
      return {
        next: {
          ...prev,
          toolCalls: [
            ...prev.toolCalls,
            toolCallFromStartedEvent(event as ToolCallStartedEvent),
          ],
        },
        terminal: false,
      };
    }
    case 'tool_call_args_delta': {
      const data = (event as ToolCallArgsDeltaEvent).data;
      return {
        next: {
          ...prev,
          toolCalls: appendToolCallArgs(
            prev.toolCalls,
            data.call_id,
            data.delta,
          ),
        },
        terminal: false,
      };
    }
    case 'tool_result': {
      return {
        next: {
          ...prev,
          toolCalls: applyToolResult(prev, event as ToolResultEvent),
        },
        terminal: false,
      };
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
          pendingApprovals: mergePendingApprovals(prev.pendingApprovals, [
            entry,
          ]),
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
      // Artifacts arrive in order; append preserves that ordering for the
      // side panel's "next / previous" navigation.
      return {
        next: {
          ...prev,
          artifacts: [
            ...prev.artifacts,
            artifactFromStartedEvent(event as ArtifactStartedEvent),
          ],
        },
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
      return { next: prev, terminal: false };
  }
}

export function mergePendingApprovals(
  current: PendingApproval[],
  incoming: PendingApproval[],
): PendingApproval[] {
  const merged = new Map<string, PendingApproval>();
  for (const approval of [...current, ...incoming]) {
    merged.set(approval.approval_id, approval);
  }
  return Array.from(merged.values());
}

function syncResponseArtifacts(response: AiChatResponse): ArtifactBuffer[] {
  return (response.artifacts ?? []).map(
    (artifact): ArtifactBuffer => ({
      id: artifact.id,
      type: artifact.type,
      title: artifact.title ?? null,
      language: artifact.language ?? null,
      content: artifact.content,
      status: 'closed',
    }),
  );
}

function syncResponseDoneMeta(response: AiChatResponse): DoneMeta {
  return {
    policy: response.policy,
    chosen_pool: response.chosen_pool,
    decision_reason: response.decision_reason,
    forced_local: response.forced_local,
    pii_hits: response.pii_hits,
    model: response.model,
    chosen_model: response.model,
    canonical_model: response.canonical_model,
    provider: response.provider,
  };
}

function syncResponseFinishReason(
  finishReason: AiChatResponse['finish_reason'],
): ChatStreamState['finishReason'] {
  if (
    finishReason === 'stop' ||
    finishReason === 'length' ||
    finishReason === 'cancelled' ||
    finishReason === 'error' ||
    finishReason === 'awaiting_approval'
  ) {
    return finishReason;
  }
  return null;
}

function toolCallFromStartedEvent(event: ToolCallStartedEvent): ToolCallBuffer {
  const data = event.data;
  return {
    call_id: data.call_id,
    name: data.name,
    args_preview: data.args_preview ?? null,
    argsBuffer: '',
    startedAtMs: event.timestamp_ms,
    completedAtMs: null,
    status: 'running',
    result: null,
  };
}

function appendToolCallArgs(
  toolCalls: ToolCallBuffer[],
  callId: string,
  delta: string,
): ToolCallBuffer[] {
  return toolCalls.map((call) =>
    call.call_id === callId
      ? { ...call, argsBuffer: call.argsBuffer + delta }
      : call,
  );
}

function applyToolResult(
  prev: ChatStreamState,
  event: ToolResultEvent,
): ToolCallBuffer[] {
  const data = event.data;
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
      status: toolResultStatus(data.status),
      result,
    };
  });
  if (!matched) {
    next.push(fallbackToolCallFromResult(prev, event));
  }
  return next;
}

function fallbackToolCallFromResult(
  prev: ChatStreamState,
  event: ToolResultEvent,
): ToolCallBuffer {
  const data = event.data;
  const approval = prev.pendingApprovals.find(
    (item) => item.call_id === data.call_id,
  );
  return {
    call_id: data.call_id,
    name: approval?.tool ?? 'tool',
    args_preview: null,
    argsBuffer: '',
    startedAtMs: event.timestamp_ms,
    completedAtMs: event.timestamp_ms,
    status: toolResultStatus(data.status),
    result: {
      status: data.status,
      preview: data.result_preview ?? null,
      error: data.error ?? null,
    },
  };
}

function toolResultStatus(
  status: ToolResultEvent['data']['status'],
): ToolCallBuffer['status'] {
  if (status === 'ok') {
    return 'ok';
  }
  if (status === 'rejected') {
    return 'rejected';
  }
  return 'error';
}

function artifactFromStartedEvent(event: ArtifactStartedEvent): ArtifactBuffer {
  const data = event.data;
  return {
    id: data.artifact_id,
    type: data.artifact_type,
    title: data.title ?? null,
    language: data.language ?? null,
    content: '',
    status: 'open',
  };
}

function closeOpenArtifacts(artifacts: ArtifactBuffer[]): ArtifactBuffer[] {
  return artifacts.map((artifact) =>
    artifact.status === 'open'
      ? { ...artifact, status: 'closed' as const }
      : artifact,
  );
}
