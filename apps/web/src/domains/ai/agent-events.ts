/**
 * Wire-level types for ``POST /api/v1/ai/chat/stream`` SSE frames.
 * Mirrors ``apps/api/src/aidoo_api/domains/ai/events.py``.
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
    finish_reason: 'stop' | 'length' | 'cancelled' | 'error';
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
    status: 'ok' | 'error';
    result_preview?: string | null;
    error?: string | null;
  };
}

/** Reserved P4 events (not emitted in Phase 2). */
export interface ApprovalRequiredEvent {
  type: 'approval_required';
  seq: number;
  timestamp_ms: number;
  data: { approval_id: string; tool: string; resource_preview?: string | null };
}

export interface ApprovalResolvedEvent {
  type: 'approval_resolved';
  seq: number;
  timestamp_ms: number;
  data: { approval_id: string; decision: 'approved' | 'rejected' };
}

export type AgentEventEnvelope =
  | ContentDeltaEvent
  | ReasoningDeltaEvent
  | UsageEvent
  | DoneEvent
  | ErrorEvent
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
  result: { status: 'ok' | 'error'; preview: string | null; error: string | null } | null;
}

export interface PendingApproval {
  approval_id: string;
  tool: string;
  resource_preview: string | null;
  decision: 'approved' | 'rejected' | null;
}
