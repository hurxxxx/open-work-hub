import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';

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
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      path,
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
): Promise<HermesAgentStatus> {
  return request('/api/v1/agent/status', token, undefined);
}

export function listHermesSessions(
  token: string,
  params: {
    limit?: number;
    offset?: number;
    scopeRef?: string;
    scopeResourceId?: string;
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
): Promise<HermesSession> {
  return request('/api/v1/agent/sessions', token, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getHermesSession(
  token: string,
  sessionId: string,
): Promise<HermesSession> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`,
    token,
    undefined,
  );
}

export function updateHermesSession(
  token: string,
  sessionId: string,
  body: { title?: string; pinned?: boolean; archived?: boolean },
): Promise<HermesSession> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
}

export function deleteHermesSession(
  token: string,
  sessionId: string,
): Promise<void> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`,
    token,
    { method: 'DELETE' },
  );
}

export function getHermesSessionMessages(
  token: string,
  sessionId: string,
): Promise<HermesSessionMessages> {
  return request(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/messages?limit=500&offset=0`,
    token,
    undefined,
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
  );
}

export function getHermesRun(token: string, runId: string): Promise<HermesRun> {
  return request(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}`,
    token,
    undefined,
  );
}

export function listHermesRuns(
  token: string,
  params: {
    limit?: number;
    offset?: number;
    sessionId?: string;
    status?: string;
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
  );
}

export async function streamHermesRunEvents(
  token: string,
  runId: string,
  options: {
    afterSequence?: number;
    signal: AbortSignal;
  },
): Promise<Response> {
  const response = await fetch(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}/events`,
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
): Promise<HermesRun> {
  return request(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}/stop`,
    token,
    { method: 'POST', body: '{}' },
  );
}

export function resolveHermesApproval(
  token: string,
  runId: string,
  requestId: string,
  choice: 'once' | 'deny',
): Promise<HermesRun> {
  return request(
    `/api/v1/agent/runs/${encodeURIComponent(runId)}/approval`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId, choice }),
    },
  );
}

export function listHermesJobs(token: string): Promise<HermesJobList> {
  return request('/api/v1/agent/jobs', token, undefined);
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
): Promise<HermesJob> {
  return request('/api/v1/agent/jobs', token, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function runHermesJobAction(
  token: string,
  jobId: string,
  action: 'pause' | 'resume' | 'run',
): Promise<HermesJob> {
  return request(
    `/api/v1/agent/jobs/${encodeURIComponent(jobId)}/${action}`,
    token,
    { method: 'POST', body: '{}' },
  );
}

export function deleteHermesJob(token: string, jobId: string): Promise<void> {
  return request(`/api/v1/agent/jobs/${encodeURIComponent(jobId)}`, token, {
    method: 'DELETE',
  });
}

export type HermesFile = ApiSchema<'HermesFileResponse'>;
export type HermesFileRevision = ApiSchema<'HermesFileRevisionResponse'>;
export function listHermesFileRevisions(
  token: string,
  sessionId: string,
  fileId?: string,
  offset = 0,
) {
  const query = new URLSearchParams({
    offset: String(offset),
    limit: '100',
  });
  if (fileId) query.set('file_id', fileId);
  return request<ApiSchema<'HermesFileRevisionListResponse'>>(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/file-revisions?${query}`,
    token,
  );
}
export function getHermesFileRevision(token: string, revisionId: string) {
  return request<HermesFileRevision>(
    `/api/v1/agent/file-revisions/${encodeURIComponent(revisionId)}`,
    token,
  );
}

export function hermesFileRevisionContentPath(revisionId: string) {
  return `/api/v1/agent/file-revisions/${encodeURIComponent(revisionId)}/content`;
}

export async function previewHermesFileRevision(
  token: string,
  revision: HermesFileRevision,
  limit: number,
  signal: AbortSignal,
): Promise<Blob> {
  if (revision.size_bytes > limit)
    throw new Error(i18n.t('apps:ai.filePreview.tooLarge'));
  return readPreviewBytes(
    token,
    hermesFileRevisionContentPath(revision.id),
    limit,
    signal,
    revision.size_bytes,
    revision.media_type,
  );
}

export async function previewHermesAsset(
  token: string,
  revisionId: string,
  path: string,
  signal: AbortSignal,
): Promise<Uint8Array> {
  const query = new URLSearchParams({ path });
  const blob = await readPreviewBytes(
    token,
    `/api/v1/agent/file-revisions/${encodeURIComponent(revisionId)}/preview-asset?${query}`,
    2 * 1024 * 1024,
    signal,
  );
  return new Uint8Array(await blob.arrayBuffer());
}

async function readPreviewBytes(
  token: string,
  path: string,
  limit: number,
  signal: AbortSignal,
  expectedSize?: number,
  mediaType = 'application/octet-stream',
): Promise<Blob> {
  const response = await fetch(path, {
    headers: jsonHeaders(token, { Accept: '*/*' }),
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
  });
  if (!response.ok || !response.body)
    throw new HermesAgentApiError(
      response.status,
      i18n.t('apps:ai.filePreview.unavailable'),
    );
  const reader = response.body.getReader();
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit || (expectedSize !== undefined && size > expectedSize))
        throw new Error(i18n.t('apps:ai.filePreview.tooLarge'));
      chunks.push(new Uint8Array(value));
    }
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
  if (expectedSize !== undefined && size !== expectedSize)
    throw new Error(i18n.t('apps:ai.filePreview.unavailable'));
  return new Blob(chunks, { type: mediaType });
}
export function listHermesFiles(token: string, sessionId: string) {
  return request<ApiSchema<'HermesFileListResponse'>>(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/files`,
    token,
    undefined,
  );
}
export function uploadHermesFile(token: string, sessionId: string, file: File) {
  return request<HermesFile>(
    `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/files`,
    token,
    {
      method: 'POST',
      body: file,
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-File-Name': encodeURIComponent(file.name),
      },
    },
  );
}
