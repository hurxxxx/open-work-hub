import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { resolveWorkspaceAgentApiPath } from './workspace-chatbot-api-path';

export type HermesAgentStatus = ApiSchema<'HermesAgentStatusResponse'>;
export type HermesSession = ApiSchema<'HermesSessionResponse'>;
export type HermesSessionList = ApiSchema<'HermesSessionListResponse'>;
export type HermesSessionMessages = ApiSchema<'HermesSessionMessagesResponse'>;
export type HermesRun = ApiSchema<'HermesRunResponse'>;
export type HermesRunList = ApiSchema<'HermesRunListResponse'>;
export type HermesJob = ApiSchema<'HermesJobResponse'>;
export type HermesJobList = ApiSchema<'HermesJobListResponse'>;

export interface HermesApprovalReference {
  runId: string;
  requestId: string;
  sequence: number;
}

const HERMES_APPROVAL_PREFIX = 'hermes:';
export const HERMES_APPROVAL_TTL_MS = 5 * 60 * 1000;

export function hermesApprovalToolName(
  payload: Record<string, unknown>,
): string {
  const explicit = payload.tool ?? payload.name;
  if (typeof explicit === 'string' && explicit.trim()) {
    return explicit.trim();
  }
  const command = payload.command;
  if (typeof command !== 'string') return 'tool';
  const match = command.match(
    /^MCP tool '([^']+)' on UNTRUSTED server 'owh-mcp-[0-9a-f]{20}-internal' wants to run\./,
  );
  return match?.[1]?.trim() || 'tool';
}

export function encodeHermesApprovalReference(
  reference: HermesApprovalReference,
): string {
  return `${HERMES_APPROVAL_PREFIX}${reference.runId}:${reference.sequence}:${encodeURIComponent(reference.requestId)}`;
}

export function decodeHermesApprovalReference(
  value: string,
): HermesApprovalReference | null {
  if (!value.startsWith(HERMES_APPROVAL_PREFIX)) return null;
  const [runId, sequenceValue, ...requestParts] = value
    .slice(HERMES_APPROVAL_PREFIX.length)
    .split(':');
  const sequence = Number.parseInt(sequenceValue ?? '', 10);
  if (!runId || !Number.isFinite(sequence) || requestParts.length === 0) {
    return null;
  }
  try {
    return {
      runId,
      sequence,
      requestId: decodeURIComponent(requestParts.join(':')),
    };
  } catch {
    return null;
  }
}

export class HermesAgentApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'HermesAgentApiError';
  }
}

function resolveErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) {
    return fallback;
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (
    detail &&
    typeof detail === 'object' &&
    'message' in detail &&
    typeof detail.message === 'string' &&
    detail.message.trim()
  ) {
    return detail.message;
  }
  return fallback;
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      resolveWorkspaceAgentApiPath(path, workspaceSlug),
      token,
      init,
      (error) =>
        new HermesAgentApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.errors.requestFailed', { status: error.status }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof HermesAgentApiError) {
      throw error;
    }
    throw new HermesAgentApiError(0, i18n.t('apps:ai.errors.connect'));
  }
}

export function getHermesAgentStatus(
  token: string,
  workspaceSlug?: string | null,
): Promise<HermesAgentStatus> {
  return request('/api/v1/agent/status', token, undefined, workspaceSlug);
}

export function listHermesSessions(
  token: string,
  params: {
    limit?: number;
    offset?: number;
    scopeRef?: string;
    scopeResourceId?: string;
    workspaceSlug?: string | null;
  } = {},
): Promise<HermesSessionList> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set('limit', String(params.limit));
  if (params.offset != null) search.set('offset', String(params.offset));
  if (params.scopeRef) search.set('scope_ref', params.scopeRef);
  if (params.scopeResourceId) {
    search.set('scope_resource_id', params.scopeResourceId);
  }
  const query = search.toString();
  return request(
    `/api/v1/agent/sessions${query ? `?${query}` : ''}`,
    token,
    undefined,
    params.workspaceSlug,
  );
}

export function createHermesSession(
  token: string,
  body: {
    title?: string | null;
    system_prompt?: string | null;
    scope_ref?: string | null;
    scope_resource_id?: string | null;
  },
  workspaceSlug?: string | null,
): Promise<HermesSession> {
  return request(
    '/api/v1/agent/sessions',
    token,
    { method: 'POST', body: JSON.stringify(body) },
    workspaceSlug,
  );
}

export function getHermesSession(
  token: string,
  sessionId: string,
  workspaceSlug?: string | null,
): Promise<HermesSession> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`,
    token,
    undefined,
    workspaceSlug,
  );
}

export function updateHermesSession(
  token: string,
  sessionId: string,
  body: { title?: string; pinned?: boolean; archived?: boolean },
  workspaceSlug?: string | null,
): Promise<HermesSession> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify(body) },
    workspaceSlug,
  );
}

export function deleteHermesSession(
  token: string,
  sessionId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function getHermesSessionMessages(
  token: string,
  sessionId: string,
  workspaceSlug?: string | null,
): Promise<HermesSessionMessages> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/messages?limit=500&offset=0`,
    token,
    undefined,
    workspaceSlug,
  );
}

export function createHermesRun(
  token: string,
  sessionId: string,
  body: {
    input: string;
    instructions?: string | null;
    conversation_history?: Record<string, unknown>[];
    allowed_app_ids?: string[] | null;
  },
  workspaceSlug?: string | null,
  idempotencyKey?: string,
): Promise<HermesRun> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/runs`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(body),
      headers: idempotencyKey
        ? { 'Idempotency-Key': idempotencyKey }
        : undefined,
    },
    workspaceSlug,
  );
}

export function getHermesRun(
  token: string,
  runId: string,
  workspaceSlug?: string | null,
): Promise<HermesRun> {
  return request(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}`,
    token,
    undefined,
    workspaceSlug,
  );
}

export function listHermesRuns(
  token: string,
  params: {
    limit?: number;
    offset?: number;
    sessionId?: string;
    status?: string;
    workspaceSlug?: string | null;
  } = {},
): Promise<HermesRunList> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set('limit', String(params.limit));
  if (params.offset != null) search.set('offset', String(params.offset));
  if (params.sessionId) search.set('session_id', params.sessionId);
  if (params.status) search.set('status', params.status);
  const query = search.toString();
  return request(
    `/api/v1/agent/runs${query ? `?${query}` : ''}`,
    token,
    undefined,
    params.workspaceSlug,
  );
}

export async function streamHermesRunEvents(
  token: string,
  runId: string,
  options: {
    afterSequence?: number;
    signal: AbortSignal;
    workspaceSlug?: string | null;
  },
): Promise<Response> {
  const response = await fetch(
    resolveWorkspaceAgentApiPath(
      `/api/v1/agent/runs/${encodeURIComponent(runId)}/events`,
      options.workspaceSlug,
    ),
    {
      cache: 'no-store',
      headers: {
        ...jsonHeaders(token),
        Accept: 'text/event-stream',
        ...(options.afterSequence != null
          ? { 'Last-Event-ID': String(options.afterSequence) }
          : {}),
      },
      signal: options.signal,
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new HermesAgentApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t('apps:ai.errors.streamStartFailed', {
          status: response.status,
        }),
      ),
    );
  }
  if (!response.body) {
    throw new HermesAgentApiError(0, i18n.t('apps:ai.errors.emptySseBody'));
  }
  return response;
}

export function stopHermesRun(
  token: string,
  runId: string,
  workspaceSlug?: string | null,
): Promise<HermesRun> {
  return request(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}/stop`,
    token,
    { method: 'POST', body: '{}' },
    workspaceSlug,
  );
}

export function resolveHermesApproval(
  token: string,
  runId: string,
  requestId: string,
  choice: 'once' | 'deny',
  workspaceSlug?: string | null,
): Promise<HermesRun> {
  return request(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}/approval`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId, choice }),
    },
    workspaceSlug,
  );
}

export function listHermesJobs(
  token: string,
  workspaceSlug?: string | null,
): Promise<HermesJobList> {
  return request('/api/v1/agent/jobs', token, undefined, workspaceSlug);
}

export function createHermesJob(
  token: string,
  body: {
    name: string;
    schedule: string;
    prompt: string;
    skills?: string[];
    repeat?: number | null;
  },
  workspaceSlug?: string | null,
): Promise<HermesJob> {
  return request(
    '/api/v1/agent/jobs',
    token,
    { method: 'POST', body: JSON.stringify(body) },
    workspaceSlug,
  );
}

export function runHermesJobAction(
  token: string,
  jobId: string,
  action: 'pause' | 'resume' | 'run',
  workspaceSlug?: string | null,
): Promise<HermesJob> {
  return request(
    `/api/v1/agent/jobs/${encodeURIComponent(jobId)}/${action}`,
    token,
    { method: 'POST', body: '{}' },
    workspaceSlug,
  );
}

export function deleteHermesJob(
  token: string,
  jobId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request(
    `/api/v1/agent/jobs/${encodeURIComponent(jobId)}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}
