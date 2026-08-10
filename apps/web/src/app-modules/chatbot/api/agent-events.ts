/**
 * Wire-level types for
 * ``POST /api/v1/workspaces/{workspace_slug}/chatbot/chat/stream`` SSE frames.
 * Mirrors ``apps/api/src/ai_do_api/domains/ai/events.py``.
 *
 * Unknown ``type`` values must be ignored by consumers so new server-side
 * event types roll out without a client release.
 */

export type ChatStreamStatus =
  | 'idle'
  | 'streaming'
  | 'done'
  | 'cancelled'
  | 'error';

export type AgentChosenPool = 'local' | 'external';

export interface DoneMeta {
  policy: string | null;
  chosen_pool: AgentChosenPool | null;
  decision_reason: string | null;
  forced_local: boolean;
  pii_hits: string[];
  model: string | null;
  chosen_model: string | null;
  canonical_model: string | null;
  provider: string | null;
  pending_approval_id?: string | null;
  pending_call_id?: string | null;
  agent_run_id?: string | null;
}

export interface UsageCounts {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface ContentDeltaEvent {
  type: 'content_delta';
  seq: number;
  timestamp_ms: number;
  data: { text: string };
}

export interface ReasoningDeltaEvent {
  type: 'reasoning_delta';
  seq: number;
  timestamp_ms: number;
  data: { text: string };
}

export interface UsageEvent {
  type: 'usage';
  seq: number;
  timestamp_ms: number;
  data: UsageCounts;
}

export interface DoneEvent {
  type: 'done';
  seq: number;
  timestamp_ms: number;
  data: {
    finish_reason:
      | 'stop'
      | 'length'
      | 'cancelled'
      | 'error'
      | 'awaiting_approval';
    audit_id: string | null;
    meta: DoneMeta | null;
  };
}

export interface ErrorEvent {
  type: 'error';
  seq: number;
  timestamp_ms: number;
  data: { code: string; message: string; retryable: boolean };
}

/**
 * Emitted once at stream open when the backend has bound the turns to a
 * persisted Conversation row. Always precedes the first content/reasoning
 * delta so the client can store the id before any rendering begins and
 * thread it back on follow-up requests.
 */
export interface ConversationAttachedEvent {
  type: 'conversation_attached';
  seq: number;
  timestamp_ms: number;
  data: { conversation_id: string };
}

/**
 * Artifact channel envelopes. Opens when the server detects an
 * ``<artifact type="..." title="...">`` tag inside the LLM output, streams
 * the body as deltas, then closes with ``artifact_completed``. Bodies are
 * rendered in a side panel rather than the chat bubble — see ArtifactCard /
 * ArtifactPanel.
 */
export interface ArtifactStartedEvent {
  type: 'artifact_started';
  seq: number;
  timestamp_ms: number;
  data: {
    artifact_id: string;
    artifact_type: string;
    title?: string | null;
    /** Optional language hint for ``type="code"`` artifacts. */
    language?: string | null;
  };
}

export interface ArtifactDeltaEvent {
  type: 'artifact_delta';
  seq: number;
  timestamp_ms: number;
  data: { artifact_id: string; delta: string };
}

export interface ArtifactCompletedEvent {
  type: 'artifact_completed';
  seq: number;
  timestamp_ms: number;
  data: { artifact_id: string };
}

/** Reserved P3 events (not emitted in Phase 2). */
export interface ToolCallStartedEvent {
  type: 'tool_call_started';
  seq: number;
  timestamp_ms: number;
  data: { call_id: string; name: string; args_preview?: string | null };
}

export interface ToolCallArgsDeltaEvent {
  type: 'tool_call_args_delta';
  seq: number;
  timestamp_ms: number;
  data: { call_id: string; delta: string };
}

export interface ToolResultEvent {
  type: 'tool_result';
  seq: number;
  timestamp_ms: number;
  data: {
    call_id: string;
    status: 'ok' | 'error' | 'rejected';
    result_preview?: string | null;
    error?: string | null;
  };
}

/** Reserved P4 events (not emitted in Phase 2). */
export interface ApprovalRequiredEvent {
  type: 'approval_required';
  seq: number;
  timestamp_ms: number;
  data: {
    approval_id: string;
    call_id: string;
    tool: string;
    resource_preview?: string | null;
    expires_at_ms: number;
  };
}

export interface ApprovalResolvedEvent {
  type: 'approval_resolved';
  seq: number;
  timestamp_ms: number;
  data: {
    approval_id: string;
    call_id: string;
    decision: 'approved' | 'rejected' | 'cancelled';
    reason?: string | null;
  };
}

export type AgentEventEnvelope =
  | ContentDeltaEvent
  | ReasoningDeltaEvent
  | UsageEvent
  | DoneEvent
  | ErrorEvent
  | ConversationAttachedEvent
  | ArtifactStartedEvent
  | ArtifactDeltaEvent
  | ArtifactCompletedEvent
  | ToolCallStartedEvent
  | ToolCallArgsDeltaEvent
  | ToolResultEvent
  | ApprovalRequiredEvent
  | ApprovalResolvedEvent;

/**
 * Raw SSE envelope *before* discrimination. Consumers JSON.parse into this
 * shape, then switch on ``type`` to narrow. Unknown ``type`` values fall
 * through and are ignored — forward-compat.
 */
export interface RawAgentEvent {
  type: string;
  seq: number;
  timestamp_ms: number;
  data: unknown;
}

export interface ToolCallBuffer {
  call_id: string;
  name: string;
  args_preview: string | null;
  argsBuffer: string;
  startedAtMs: number;
  completedAtMs: number | null;
  status: 'running' | 'ok' | 'error' | 'rejected';
  result: {
    status: 'ok' | 'error' | 'rejected';
    preview: string | null;
    error: string | null;
  } | null;
}

export interface PendingApproval {
  approval_id: string;
  call_id: string;
  tool: string;
  resource_preview: string | null;
  expires_at_ms: number;
  decision: 'approved' | 'rejected' | 'cancelled' | null;
  reason?: string | null;
}

/**
 * Accumulated artifact state during a stream. Mirrors the server-side
 * ``_AssistantTurnBuffer.artifact_records`` shape so a persisted turn's
 * ``artifacts[]`` array can hydrate straight into this shape on reload.
 */
export interface ArtifactBuffer {
  id: string;
  type: string;
  title: string | null;
  /** Optional language hint for ``type="code"`` artifacts. Other types
   *  leave it null and the renderer falls back to auto-detection. */
  language?: string | null;
  content: string;
  status: 'open' | 'closed';
  /** Durable artifact metadata is optional because older conversation turns
   *  and live SSE artifact frames only carry the presentation fields above. */
  kind?: string | null;
  graphRunId?: string | null;
  conversationId?: string | null;
  conversationTurnId?: string | null;
  createdAt?: string | null;
  completedAt?: string | null;
}
