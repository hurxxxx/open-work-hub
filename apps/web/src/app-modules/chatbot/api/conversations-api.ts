import { i18n } from '@/src/platform/i18n';
import {
  HERMES_APPROVAL_TTL_MS,
  HermesAgentApiError,
  createHermesSession,
  deleteHermesSession,
  encodeHermesApprovalReference,
  getHermesSession,
  getHermesSessionMessages,
  hermesApprovalToolName,
  listHermesRuns,
  listHermesSessions,
  updateHermesSession,
  type HermesRun,
  type HermesSession,
} from './hermes-agent-api';

export interface ConversationArtifact {
  id: string;
  type: string;
  title?: string | null;
  language?: string | null;
  content: string;
  status?: string | null;
}

export interface ConversationTurn {
  id: string;
  seq: number;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string | null;
  reasoningStatus?: string | null;
  finishReason?: string | null;
  responseStatus?: string | null;
  provider?: string | null;
  policy?: string | null;
  chosenPool?: 'local' | 'external' | null;
  decisionReason?: string | null;
  forcedLocal?: boolean | null;
  piiHits?: string[];
  toolCalls?: Record<string, unknown>[];
  pendingApprovals?: Record<string, unknown>[];
  artifacts?: ConversationArtifact[];
  createdAt: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  scopeRef?: string | null;
  scopeResourceId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationLivePendingApproval {
  approvalId: string;
  agentRunId: string;
  callId: string;
  tool: string;
  resourcePreview?: string | null;
  expiresAtMs: number;
  status: 'pending' | 'approved' | 'rejected';
  reason?: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  livePendingApproval?: ConversationLivePendingApproval | null;
  turns: ConversationTurn[];
}

export interface ConversationListResponse {
  items: ConversationSummary[];
  nextCursor?: string | null;
}

export class ConversationsApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ConversationsApiError';
  }
}

function mapError(error: unknown): never {
  if (error instanceof HermesAgentApiError) {
    throw new ConversationsApiError(error.status, error.message);
  }
  throw new ConversationsApiError(
    0,
    error instanceof Error
      ? error.message
      : i18n.t('apps:ai.errors.conversationConnect'),
  );
}

/** Fired after Hermes persists a turn so recent sessions refresh in place. */
export const CONVERSATIONS_UPDATED_EVENT = 'corporate:ai:conversations-updated';

export async function listConversations(
  token: string,
  params: {
    limit?: number;
    cursor?: string | null;
    scopeRef?: string;
    scopeResourceId?: string;
  } = {},
): Promise<ConversationListResponse> {
  const limit = params.limit ?? 50;
  const parsedOffset = Number.parseInt(params.cursor ?? '0', 10);
  const offset = Number.isFinite(parsedOffset) ? Math.max(0, parsedOffset) : 0;
  try {
    const response = await listHermesSessions(token, {
      limit,
      offset,
      scopeRef: params.scopeRef,
      scopeResourceId: params.scopeResourceId,
    });
    return {
      items: response.data.map(sessionToSummary),
      nextCursor: response.has_more ? String(offset + limit) : null,
    };
  } catch (error) {
    return mapError(error);
  }
}

export async function getConversation(
  token: string,
  conversationId: string,
  options: Record<string, never> = {},
): Promise<ConversationDetail> {
  try {
    const [session, messages, runs] = await Promise.all([
      getHermesSession(token, conversationId),
      getHermesSessionMessages(token, conversationId),
      listHermesRuns(token, {
        sessionId: conversationId,
        limit: 1,
      }),
    ]);
    return {
      ...sessionToSummary(session),
      turns: messages.data
        .map((message, index) => messageToTurn(message, index, session.id))
        .filter((turn): turn is ConversationTurn => turn !== null),
      livePendingApproval: runToPendingApproval(runs.data[0]),
    };
  } catch (error) {
    return mapError(error);
  }
}

export async function createConversation(
  token: string,
  init: {
    title?: string;
    scopeRef?: string;
    scopeResourceId?: string;
  } = {},
): Promise<ConversationDetail> {
  try {
    const session = await createHermesSession(token, {
      title: init.title || null,
      scope_ref: init.scopeRef || null,
      scope_resource_id: init.scopeResourceId || null,
    });
    return {
      ...sessionToSummary(session),
      turns: [],
      livePendingApproval: null,
    };
  } catch (error) {
    return mapError(error);
  }
}

export async function renameConversation(
  token: string,
  conversationId: string,
  title: string,
  options: Record<string, never> = {},
): Promise<ConversationDetail> {
  try {
    const session = await updateHermesSession(token, conversationId, { title });
    const detail = await getConversation(token, conversationId, options);
    return { ...detail, ...sessionToSummary(session) };
  } catch (error) {
    return mapError(error);
  }
}

export async function deleteConversation(
  token: string,
  conversationId: string,
  options: Record<string, never> = {},
): Promise<void> {
  try {
    await deleteHermesSession(token, conversationId);
  } catch (error) {
    return mapError(error);
  }
}

function sessionToSummary(session: HermesSession): ConversationSummary {
  return {
    id: session.id,
    title: session.title?.trim() || '',
    scopeRef: session.scope_ref ?? null,
    scopeResourceId: session.scope_resource_id ?? null,
    createdAt: session.created_at,
    updatedAt: session.updated_at,
  };
}

function messageToTurn(
  message: Record<string, unknown>,
  index: number,
  sessionId: string,
): ConversationTurn | null {
  const role = message.role;
  if (role !== 'user' && role !== 'assistant') return null;
  const reasoning = stringValue(message.reasoning_content ?? message.reasoning);
  const timestamp = timestampToIso(message.timestamp);
  return {
    id: stringValue(message.id) || `${sessionId}:${index + 1}`,
    seq: index + 1,
    role,
    content: displayContent(message),
    reasoning,
    reasoningStatus: reasoning ? 'done' : null,
    finishReason: stringValue(message.finish_reason) || null,
    responseStatus: role === 'assistant' ? 'done' : null,
    provider: role === 'assistant' ? 'openrouter' : null,
    policy: role === 'assistant' ? 'hermes' : null,
    chosenPool: role === 'assistant' ? 'external' : null,
    decisionReason: role === 'assistant' ? 'Hermes headless agent' : null,
    forcedLocal: false,
    piiHits: [],
    toolCalls:
      role === 'assistant'
        ? mapStoredToolCalls(message.tool_calls, timestamp)
        : [],
    pendingApprovals: [],
    artifacts: [],
    createdAt: timestamp,
  };
}

function displayContent(message: Record<string, unknown>): string {
  const display = stringValue(message.display_content);
  return display || stringValue(message.content);
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function timestampToIso(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return new Date(
      value < 10_000_000_000 ? value * 1000 : value,
    ).toISOString();
  }
  if (typeof value === 'string') {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return new Date(parsed).toISOString();
  }
  return new Date().toISOString();
}

function mapStoredToolCalls(value: unknown, timestamp: string) {
  if (!Array.isArray(value)) return [];
  const startedAtMs = Date.parse(timestamp);
  return value.flatMap((entry, index) => {
    if (!entry || typeof entry !== 'object') return [];
    const row = entry as Record<string, unknown>;
    const fn =
      row.function && typeof row.function === 'object'
        ? (row.function as Record<string, unknown>)
        : {};
    const name = stringValue(fn.name ?? row.name);
    if (!name) return [];
    return [
      {
        call_id: stringValue(row.id) || `stored-tool-${index}`,
        name,
        args_preview: stringValue(fn.arguments ?? row.arguments) || null,
        argsBuffer: stringValue(fn.arguments ?? row.arguments),
        startedAtMs,
        completedAtMs: startedAtMs,
        status: 'ok',
        result: null,
      },
    ];
  });
}

function runToPendingApproval(
  run: HermesRun | undefined,
): ConversationLivePendingApproval | null {
  const payload = run?.pending_approval;
  if (!run || run.status !== 'awaiting_approval' || !payload) return null;
  const requestId = stringValue(payload.request_id);
  if (!requestId) return null;
  const sequenceValue = payload.sequence;
  const sequence =
    typeof sequenceValue === 'number' && Number.isFinite(sequenceValue)
      ? sequenceValue
      : 0;
  const timestamp =
    typeof payload.timestamp === 'number'
      ? payload.timestamp * 1000
      : Date.now();
  return {
    approvalId: encodeHermesApprovalReference({
      runId: run.id,
      requestId,
      sequence,
    }),
    agentRunId: run.id,
    callId: stringValue(payload.call_id) || requestId,
    tool: hermesApprovalToolName(payload),
    resourcePreview:
      stringValue(payload.preview ?? payload.command ?? payload.description) ||
      null,
    expiresAtMs: timestamp + HERMES_APPROVAL_TTL_MS,
    status: 'pending',
    reason: null,
  };
}
