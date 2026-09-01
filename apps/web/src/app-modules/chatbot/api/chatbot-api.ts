import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { iterSseEvents } from './sse-parser';
import {
  HermesAgentApiError,
  HERMES_APPROVAL_TTL_MS,
  createHermesRun,
  createHermesSession,
  decodeHermesApprovalReference,
  encodeHermesApprovalReference,
  getHermesAgentStatus,
  getHermesRun,
  getHermesSession,
  hermesApprovalToolName,
  resolveHermesApproval,
  stopHermesRun,
  streamHermesRunEvents,
  type HermesRun,
} from './hermes-agent-api';

const HERMES_PROVIDER = 'openrouter';
const HERMES_MODEL = 'qwen/qwen3.8-flash';
const HERMES_POLICY = 'hermes';
const TERMINAL_RUN_STATUSES = new Set([
  'completed',
  'failed',
  'cancelled',
  'interrupted',
  'invalid_output',
]);

export type AiChatRole = ApiSchema<'ChatMessage'>['role'];
export type AiBackendMode =
  ApiSchema<'ConversationBoundChatRequest'>['backend_mode'];
export type AiChatMessage = ApiSchema<'ChatMessage'>;
type AiChatRequestContract = ApiSchema<'ConversationBoundChatRequest'>;
export type AiChatRequest = Omit<
  AiChatRequestContract,
  | 'allowed_app_ids'
  | 'backend_mode'
  | 'persist'
  | 'persist_user_turn'
  | 'replace_from_seq'
  | 'replace_from_turn_id'
  | 'replace_tail_seq'
  | 'replace_tail_turn_id'
  | 'temperature'
> & {
  allowed_app_ids?: string[];
  backend_mode?: AiBackendMode;
  persist?: boolean;
  persist_user_turn?: boolean;
  replace_from_seq?: number | null;
  replace_from_turn_id?: string | null;
  replace_tail_seq?: number | null;
  replace_tail_turn_id?: string | null;
  temperature?: number;
};
export type AiChatUsage = ApiSchema<'ChatUsage'>;
export type AiChatResponseArtifact = ApiSchema<'ChatArtifact'>;
export type AiChatResponse = Omit<
  ApiSchema<'ChatResponse'>,
  | 'chosen_pool'
  | 'decision_reason'
  | 'pii_hits'
  | 'policy'
  | 'requested_backend_mode'
  | 'usage'
> & {
  usage: AiChatUsage | null;
  requested_backend_mode: AiBackendMode;
  policy: string | null;
  chosen_pool: 'local' | 'external' | null;
  decision_reason: string | null;
  pii_hits: string[];
};
export type LlmPoolHealthResponse = Omit<
  ApiSchema<'LlmPoolHealthResponse'>,
  'detail' | 'pool'
> & {
  pool: 'local' | 'external';
  detail: string | null;
};
export type LlmHealthResponse = Omit<
  ApiSchema<'LlmDualHealthResponse'>,
  'external' | 'local'
> & {
  local: LlmPoolHealthResponse;
  external: LlmPoolHealthResponse | null;
};

export class AiApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'AiApiError';
  }
}

export async function getLlmHealth(
  token: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<LlmHealthResponse> {
  try {
    const status = await getHermesAgentStatus(token, options.workspaceSlug);
    const ready = status.enabled && status.profile_status === 'active';
    return {
      ready,
      local: {
        pool: 'local',
        provider: `${status.provider}/hermes`,
        base_url: 'hermes-headless',
        model: status.model,
        canonical_model: status.model,
        status: ready ? 'ready' : status.profile_status,
        ready,
        detail: ready ? null : status.profile_status,
      },
      external: null,
      external_providers: [],
    };
  } catch (error) {
    return raiseAiError(error);
  }
}

export async function sendAiChat(
  payload: AiChatRequest,
  token: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<AiChatResponse> {
  try {
    const started = await startHermesRun(
      payload,
      token,
      options.workspaceSlug,
    );
    const run = await waitForHermesRun(
      token,
      started.run.id,
      options.workspaceSlug,
    );
    return runToChatResponse(run, started.sessionId, payload.backend_mode);
  } catch (error) {
    return raiseAiError(error);
  }
}

export interface AiChatStreamRequest extends AiChatRequest {
  stream_reasoning?: boolean;
}

export interface StreamAiChatArgs {
  payload: AiChatStreamRequest;
  token: string;
  signal: AbortSignal;
  workspaceSlug?: string | null;
}

export type AiApprovalStatusResponse = ApiSchema<'ApprovalStatusResponse'>;
export type ResolveAiApprovalRequest = ApiSchema<'ApprovalResolveRequest'>;
export type AbandonAiApprovalRequest = ApiSchema<'ApprovalAbandonRequest'>;
export type ResumeAiChatRequest = Omit<
  ApiSchema<'ChatResumeRequest'>,
  'allowed_app_ids'
> & {
  allowed_app_ids?: string[];
};

export interface StreamAiResumeArgs {
  payload: ResumeAiChatRequest;
  token: string;
  signal: AbortSignal;
  workspaceSlug?: string | null;
}

export async function streamAiChat({
  payload,
  token,
  signal,
  workspaceSlug,
}: StreamAiChatArgs): Promise<Response> {
  try {
    const started = await startHermesRun(payload, token, workspaceSlug);
    const stopOnAbort = () => {
      void stopHermesRun(token, started.run.id, workspaceSlug).catch(() => undefined);
    };
    signal.addEventListener('abort', stopOnAbort, { once: true });
    const response = await legacyEventStreamResponse({
      afterSequence: 0,
      conversationId: started.sessionId,
      runId: started.run.id,
      signal,
      token,
      workspaceSlug,
    });
    return withAbortListenerCleanup(response, signal, stopOnAbort);
  } catch (error) {
    return raiseAiError(error);
  }
}

export async function getAiApprovalStatus(
  token: string,
  approvalId: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<AiApprovalStatusResponse> {
  const reference = requireApprovalReference(approvalId);
  try {
    const run = await getHermesRun(token, reference.runId, options.workspaceSlug);
    const payload = run.pending_approval ?? {};
    const argumentsValue =
      payload.arguments ?? payload.args ?? payload.command ?? payload.preview ?? {};
    const timestamp = eventTimestampMs(payload);
    return {
      id: approvalId,
      workspace_id: '',
      conversation_id: run.session_binding_id ?? '',
      agent_run_id: run.id,
      tool_call_id: stringValue(payload.call_id) || reference.requestId,
      tool_name: hermesApprovalToolName(payload),
      arguments_json:
        typeof argumentsValue === 'string'
          ? argumentsValue
          : JSON.stringify(argumentsValue, null, 2),
      resource_preview:
        stringValue(payload.preview ?? payload.command ?? payload.description) ||
        null,
      status: run.status === 'awaiting_approval' ? 'pending' : run.status,
      requested_by_user_id: '',
      resolved_by_user_id: null,
      reject_reason: null,
      resolved_at: null,
      expires_at: new Date(timestamp + HERMES_APPROVAL_TTL_MS).toISOString(),
      execution_result_json: null,
      error_message: run.error_message ?? null,
      created_at: run.created_at,
      snapshot_status: run.status,
    };
  } catch (error) {
    return raiseAiError(error);
  }
}

export async function resolveAiApproval(
  token: string,
  approvalId: string,
  payload: ResolveAiApprovalRequest,
  options: { workspaceSlug?: string | null } = {},
): Promise<AiApprovalStatusResponse> {
  const reference = requireApprovalReference(approvalId);
  try {
    await resolveHermesApproval(
      token,
      reference.runId,
      reference.requestId,
      payload.decision === 'approved' ? 'once' : 'deny',
      options.workspaceSlug,
    );
    const current = await getAiApprovalStatus(token, approvalId, options);
    return {
      ...current,
      status: payload.decision,
      reject_reason: payload.reason ?? null,
      resolved_at: new Date().toISOString(),
    };
  } catch (error) {
    return raiseAiError(error);
  }
}

export function abandonAiApproval(
  token: string,
  approvalId: string,
  payload: AbandonAiApprovalRequest = {},
  options: { workspaceSlug?: string | null } = {},
): Promise<AiApprovalStatusResponse> {
  return resolveAiApproval(
    token,
    approvalId,
    {
      decision: 'rejected',
      reason: payload.reason ?? 'Cancelled by the user.',
    },
    options,
  );
}

export async function streamAiChatResume({
  payload,
  token,
  signal,
  workspaceSlug,
}: StreamAiResumeArgs): Promise<Response> {
  const reference = requireApprovalReference(payload.approval_id);
  try {
    return await legacyEventStreamResponse({
      afterSequence: reference.sequence,
      conversationId: payload.conversation_id,
      runId: reference.runId,
      signal,
      token,
      workspaceSlug,
    });
  } catch (error) {
    return raiseAiError(error);
  }
}

interface StartedHermesRun {
  run: HermesRun;
  sessionId: string;
}

async function startHermesRun(
  payload: AiChatRequest,
  token: string,
  workspaceSlug?: string | null,
): Promise<StartedHermesRun> {
  const input = latestUserContent(payload);
  const shouldBranch = hasRewriteDirective(payload);
  let sessionId = payload.conversation_id ?? null;
  let scopeRef = payload.scope_ref ?? null;
  let scopeResourceId = payload.scope_resource_id ?? null;

  if (sessionId && shouldBranch) {
    const source = await getHermesSession(token, sessionId, workspaceSlug);
    scopeRef = source.scope_ref ?? scopeRef;
    scopeResourceId = source.scope_resource_id ?? scopeResourceId;
    sessionId = null;
  }

  if (!sessionId) {
    const session = await createHermesSession(
      token,
      {
        // Hermes derives and de-duplicates the title from the opening turn.
        // Supplying the first message here bypasses that official flow and can
        // fail session creation when another session already has that title.
        title: null,
        scope_ref: scopeRef,
        scope_resource_id: scopeResourceId,
      },
      workspaceSlug,
    );
    sessionId = session.id;
  }

  const systemInstructions = payload.messages
    .filter((message) => message.role === 'system' && message.content.trim())
    .map((message) => message.content.trim())
    .join('\n\n');
  const shouldSeedHistory = !payload.conversation_id || shouldBranch;
  const history = shouldSeedHistory
    ? payload.messages.slice(0, -1).map((message) => ({
        role: message.role,
        content: message.content,
      }))
    : [];
  const run = await createHermesRun(
    token,
    sessionId,
    {
      input,
      instructions: systemInstructions || null,
      conversation_history: history,
      allowed_app_ids: payload.allowed_app_ids ?? null,
    },
    workspaceSlug,
  );
  return { run, sessionId };
}

function hasRewriteDirective(payload: AiChatRequest): boolean {
  return (
    payload.replace_from_seq != null ||
    payload.replace_from_turn_id != null ||
    payload.replace_tail_seq != null ||
    payload.replace_tail_turn_id != null
  );
}

function latestUserContent(payload: AiChatRequest): string {
  for (let index = payload.messages.length - 1; index >= 0; index -= 1) {
    const message = payload.messages[index];
    if (message?.role === 'user' && message.content.trim()) {
      return message.content.trim();
    }
  }
  throw new AiApiError(422, i18n.t('apps:ai.errors.requestFailed', { status: 422 }));
}

async function waitForHermesRun(
  token: string,
  runId: string,
  workspaceSlug?: string | null,
): Promise<HermesRun> {
  const deadline = Date.now() + 60 * 60 * 1000;
  while (Date.now() < deadline) {
    const run = await getHermesRun(token, runId, workspaceSlug);
    if (TERMINAL_RUN_STATUSES.has(run.status) || run.status === 'awaiting_approval') {
      return run;
    }
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
  throw new AiApiError(504, i18n.t('apps:ai.errors.responseFailed'));
}

function runToChatResponse(
  run: HermesRun,
  sessionId: string,
  requestedBackendMode: AiBackendMode | undefined,
): AiChatResponse {
  return {
    model: HERMES_MODEL,
    content: run.output_text ?? '',
    usage: normalizeUsage(run.usage),
    finish_reason:
      run.status === 'completed'
        ? 'stop'
        : run.status === 'awaiting_approval'
          ? 'awaiting_approval'
          : run.status === 'cancelled' || run.status === 'interrupted'
            ? 'cancelled'
            : 'error',
    provider: HERMES_PROVIDER,
    backend: 'hermes',
    fallback_used: false,
    canonical_model: HERMES_MODEL,
    requested_backend_mode: requestedBackendMode ?? 'local',
    policy: HERMES_POLICY,
    chosen_pool: 'external',
    decision_reason: 'Executed by Hermes headless runtime.',
    forced_local: false,
    pii_hits: [],
    conversation_id: sessionId,
    artifacts: [],
  };
}

interface LegacyEventStreamArgs {
  afterSequence: number;
  conversationId: string;
  runId: string;
  signal: AbortSignal;
  token: string;
  workspaceSlug?: string | null;
}

async function legacyEventStreamResponse(
  args: LegacyEventStreamArgs,
): Promise<Response> {
  const sourceAbort = new AbortController();
  const forwardAbort = () => sourceAbort.abort();
  args.signal.addEventListener('abort', forwardAbort, { once: true });
  const source = await streamHermesRunEvents(args.token, args.runId, {
    afterSequence: args.afterSequence,
    signal: sourceAbort.signal,
    workspaceSlug: args.workspaceSlug,
  });
  if (!source.body) {
    throw new AiApiError(0, i18n.t('apps:ai.errors.emptySseBody'));
  }

  const encoder = new TextEncoder();
  const openTools: Array<{ id: string; name: string }> = [];
  let syntheticSequence = args.afterSequence;
  let contentSeen = false;
  let terminal = false;
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const emit = (type: string, data: unknown, sequence?: number) => {
        syntheticSequence = Math.max(syntheticSequence + 1, sequence ?? 0);
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({
              type,
              seq: syntheticSequence,
              timestamp_ms: Date.now(),
              data,
            })}\n\n`,
          ),
        );
      };

      emit('conversation_attached', { conversation_id: args.conversationId });
      try {
        for await (const message of iterSseEvents(
          source.body as ReadableStream<Uint8Array>,
          sourceAbort.signal,
        )) {
          const payload = parseRecord(message.data);
          if (!payload) continue;
          const eventType = stringValue(payload.event) || message.event;
          const sequence = Number.parseInt(message.id ?? '', 10);
          const resolvedSequence = Number.isFinite(sequence)
            ? sequence
            : undefined;

          if (eventType === 'message.delta') {
            const text = stringValue(payload.delta ?? payload.text);
            if (text) {
              contentSeen = true;
              emit('content_delta', { text }, resolvedSequence);
            }
          } else if (eventType === 'reasoning.available') {
            const text = stringValue(payload.text ?? payload.preview);
            if (text) emit('reasoning_delta', { text }, resolvedSequence);
          } else if (eventType === 'tool.started') {
            const name = stringValue(payload.tool ?? payload.name) || 'tool';
            const id =
              stringValue(payload.call_id) ||
              `hermes-tool-${args.runId}-${resolvedSequence ?? syntheticSequence + 1}`;
            openTools.push({ id, name });
            emit(
              'tool_call_started',
              {
                call_id: id,
                name,
                args_preview: stringValue(payload.preview) || null,
              },
              resolvedSequence,
            );
          } else if (eventType === 'tool.completed' || eventType === 'tool.failed') {
            const name = stringValue(payload.tool ?? payload.name) || 'tool';
            const matchingIndex = findOpenTool(openTools, name);
            const call =
              matchingIndex >= 0
                ? openTools.splice(matchingIndex, 1)[0]
                : { id: `hermes-tool-${args.runId}-${syntheticSequence + 1}`, name };
            const failed =
              eventType === 'tool.failed' || Boolean(payload.error === true);
            emit(
              'tool_result',
              {
                call_id: call.id,
                status: failed ? 'error' : 'ok',
                result_preview: stringValue(payload.preview ?? payload.result) || null,
                error: failed
                  ? stringValue(payload.message ?? payload.error) || 'Tool failed.'
                  : null,
              },
              resolvedSequence,
            );
          } else if (eventType === 'approval.request') {
            const requestId = stringValue(payload.request_id);
            if (!requestId) continue;
            const approvalSequence = resolvedSequence ?? syntheticSequence + 1;
            const tool = hermesApprovalToolName(payload);
            emit(
              'approval_required',
              {
                approval_id: encodeHermesApprovalReference({
                  runId: args.runId,
                  requestId,
                  sequence: approvalSequence,
                }),
                call_id: stringValue(payload.call_id) || requestId,
                tool,
                resource_preview:
                  stringValue(
                    payload.preview ?? payload.command ?? payload.description,
                  ) || null,
                expires_at_ms:
                  eventTimestampMs(payload) + HERMES_APPROVAL_TTL_MS,
              },
              approvalSequence,
            );
            emit('done', {
              finish_reason: 'awaiting_approval',
              audit_id: null,
              meta: doneMeta(args.runId),
            });
            terminal = true;
            break;
          } else if (eventType === 'run.completed') {
            const output = stringValue(payload.output);
            if (output && !contentSeen) {
              emit('content_delta', { text: output }, resolvedSequence);
            }
            const usage = normalizeUsage(payload.usage);
            if (usage) emit('usage', usage);
            emit('done', {
              finish_reason: 'stop',
              audit_id: null,
              meta: doneMeta(args.runId),
            });
            terminal = true;
            break;
          } else if (eventType === 'run.failed') {
            emit('error', {
              code: stringValue(payload.error_code) || 'hermes.run_failed',
              message:
                stringValue(payload.error ?? payload.message) ||
                i18n.t('apps:ai.errors.responseFailed'),
              retryable: false,
            });
            emit('done', {
              finish_reason: 'error',
              audit_id: null,
              meta: doneMeta(args.runId),
            });
            terminal = true;
            break;
          } else if (
            eventType === 'run.cancelled' ||
            eventType === 'run.interrupted'
          ) {
            emit('done', {
              finish_reason: 'cancelled',
              audit_id: null,
              meta: doneMeta(args.runId),
            });
            terminal = true;
            break;
          }
        }
        if (!terminal && !args.signal.aborted) {
          emit('error', {
            code: 'hermes.stream_closed',
            message: i18n.t('apps:ai.errors.streamFailed'),
            retryable: true,
          });
          emit('done', {
            finish_reason: 'error',
            audit_id: null,
            meta: doneMeta(args.runId),
          });
        }
        controller.close();
      } catch (error) {
        if (args.signal.aborted || sourceAbort.signal.aborted) {
          controller.close();
        } else {
          controller.error(error);
        }
      } finally {
        args.signal.removeEventListener('abort', forwardAbort);
        sourceAbort.abort();
        if (terminal && typeof window !== 'undefined') {
          window.dispatchEvent(new Event('corporate:ai:conversations-updated'));
        }
      }
    },
    cancel() {
      sourceAbort.abort();
      args.signal.removeEventListener('abort', forwardAbort);
    },
  });
  return new Response(stream, {
    status: 200,
    headers: {
      'Cache-Control': 'no-cache',
      'Content-Type': 'text/event-stream',
    },
  });
}

function withAbortListenerCleanup(
  response: Response,
  signal: AbortSignal,
  listener: () => void,
): Response {
  if (!response.body) return response;
  const reader = response.body.getReader();
  return new Response(
    new ReadableStream<Uint8Array>({
      async pull(controller) {
        const result = await reader.read();
        if (result.done) {
          signal.removeEventListener('abort', listener);
          controller.close();
          return;
        }
        controller.enqueue(result.value);
      },
      async cancel(reason) {
        signal.removeEventListener('abort', listener);
        await reader.cancel(reason);
      },
    }),
    { status: response.status, headers: response.headers },
  );
}

function findOpenTool(
  tools: Array<{ id: string; name: string }>,
  name: string,
): number {
  for (let index = tools.length - 1; index >= 0; index -= 1) {
    if (tools[index]?.name === name) return index;
  }
  return tools.length - 1;
}

function doneMeta(runId: string) {
  return {
    policy: HERMES_POLICY,
    chosen_pool: 'external' as const,
    decision_reason: 'Executed by Hermes headless runtime.',
    forced_local: false,
    pii_hits: [],
    model: HERMES_MODEL,
    chosen_model: HERMES_MODEL,
    canonical_model: HERMES_MODEL,
    provider: HERMES_PROVIDER,
    agent_run_id: runId,
  };
}

function normalizeUsage(value: unknown): AiChatUsage | null {
  if (!value || typeof value !== 'object') return null;
  const usage = value as Record<string, unknown>;
  const prompt = numberValue(usage.prompt_tokens ?? usage.input_tokens);
  const completion = numberValue(
    usage.completion_tokens ?? usage.output_tokens,
  );
  const total = numberValue(usage.total_tokens) ??
    (prompt != null || completion != null
      ? (prompt ?? 0) + (completion ?? 0)
      : null);
  if (prompt == null && completion == null && total == null) return null;
  return {
    prompt_tokens: prompt,
    completion_tokens: completion,
    total_tokens: total,
  };
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function parseRecord(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function eventTimestampMs(payload: Record<string, unknown>): number {
  const value = payload.timestamp;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value < 10_000_000_000 ? value * 1000 : value;
  }
  return Date.now();
}

function requireApprovalReference(approvalId: string) {
  const reference = decodeHermesApprovalReference(approvalId);
  if (!reference) {
    throw new AiApiError(404, i18n.t('apps:ai.approval.loadDetailsFailed'));
  }
  return reference;
}

function raiseAiError(error: unknown): never {
  if (error instanceof AiApiError) throw error;
  if (error instanceof HermesAgentApiError) {
    throw new AiApiError(error.status, error.message);
  }
  throw new AiApiError(
    0,
    error instanceof Error ? error.message : i18n.t('apps:ai.errors.connect'),
  );
}
