import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type AiChatRole = ApiSchema<'ChatMessage'>['role'];
export type AiBackendMode = ApiSchema<'ConversationBoundChatRequest'>['backend_mode'];
export type AiChatMessage = ApiSchema<'ChatMessage'>;
type AiChatRequestContract = ApiSchema<'ConversationBoundChatRequest'>;
export type AiChatRequest = Omit<
  AiChatRequestContract,
  'allowed_app_ids' | 'backend_mode' | 'persist' | 'temperature'
> & {
  allowed_app_ids?: string[];
  backend_mode?: AiBackendMode;
  persist?: boolean;
  temperature?: number;
};
export type AiChatUsage = ApiSchema<'ChatUsage'>;
export type AiChatResponseArtifact = ApiSchema<'ChatArtifact'>;
export type AiChatResponse = Omit<
  ApiSchema<'ChatResponse'>,
  'chosen_pool' | 'decision_reason' | 'pii_hits' | 'policy' | 'requested_backend_mode' | 'usage'
> & {
  usage: AiChatUsage | null;
  requested_backend_mode: AiBackendMode;
  policy: string | null;
  chosen_pool: 'local' | 'external' | null;
  decision_reason: string | null;
  pii_hits: string[];
};
export type LlmPoolHealthResponse = Omit<ApiSchema<'LlmPoolHealthResponse'>, 'detail' | 'pool'> & {
  pool: 'local' | 'external';
  detail: string | null;
};
export type LlmHealthResponse = Omit<ApiSchema<'LlmDualHealthResponse'>, 'external' | 'local'> & {
  local: LlmPoolHealthResponse;
  external: LlmPoolHealthResponse | null;
};

export class AiApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function resolveErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;

    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }

    if (
      detail &&
      typeof detail === 'object' &&
      'message' in detail &&
      typeof detail.message === 'string'
    ) {
      return detail.message;
    }
  }

  return fallback;
}

async function aiRequest<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJson<T>(rewriteWorkspaceApiPath(path), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new AiApiError(
        error.status,
        resolveErrorMessage(
          error.payload,
          i18n.t('apps:ai.errors.requestFailed', { status: error.status }),
        ),
      );
    }
    throw new AiApiError(
      0,
      i18n.t('apps:ai.errors.connect'),
    );
  }
}

export function getLlmHealth(token: string): Promise<LlmHealthResponse> {
  return aiRequest<LlmHealthResponse>('/api/v1/ai/health', token);
}

export interface ToolInvokeEnvelope<T> {
  tool: string;
  owner_domain: string;
  approval_required: boolean;
  result: T;
}

/**
 * Invoke an AI tool via POST /api/v1/ai/tools/{tool}/invoke and unwrap
 * the ``ToolInvokeResponse`` envelope. Tool arguments must use the
 * backend Pydantic field names (snake_case). Errors come back as
 * ``AiApiError`` with ``.status`` preserved, so callers can branch on
 * specific HTTP codes (e.g. 409 for "summary not available yet").
 */
export function invokeAiTool<T>(
  toolName: string,
  args: Record<string, unknown>,
  token: string,
): Promise<T> {
  return aiRequest<ToolInvokeEnvelope<T>>(
    `/api/v1/ai/tools/${encodeURIComponent(toolName)}/invoke`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ arguments: args }),
    },
  ).then((envelope) => envelope.result);
}

export function sendAiChat(
  payload: AiChatRequest,
  token: string,
): Promise<AiChatResponse> {
  return aiRequest<AiChatResponse>('/api/v1/ai/chat', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface AiChatStreamRequest extends AiChatRequest {
  stream_reasoning?: boolean;
}

export interface StreamAiChatArgs {
  payload: AiChatStreamRequest;
  token: string;
  signal: AbortSignal;
}

export type AiApprovalStatusResponse = ApiSchema<'ApprovalStatusResponse'>;
export type ResolveAiApprovalRequest = ApiSchema<'ApprovalResolveRequest'>;
export type AbandonAiApprovalRequest = ApiSchema<'ApprovalAbandonRequest'>;
export type ResumeAiChatRequest = Omit<ApiSchema<'ChatResumeRequest'>, 'allowed_app_ids'> & {
  allowed_app_ids?: string[];
};

export interface StreamAiResumeArgs {
  payload: ResumeAiChatRequest;
  token: string;
  signal: AbortSignal;
}

/**
 * Open an SSE stream to ``/api/v1/ai/chat/stream``. Returns the raw
 * ``Response`` — the caller consumes ``response.body`` via ``iterSseEvents``
 * and cancels with the ``AbortSignal``.
 */
export async function streamAiChat({
  payload,
  token,
  signal,
}: StreamAiChatArgs): Promise<Response> {
  return streamAiRequest('/api/v1/ai/chat/stream', payload, token, signal);
}

export function getAiApprovalStatus(
  token: string,
  approvalId: string,
): Promise<AiApprovalStatusResponse> {
  return aiRequest<AiApprovalStatusResponse>(
    `/api/v1/ai/approvals/${encodeURIComponent(approvalId)}`,
    token,
  );
}

export function resolveAiApproval(
  token: string,
  approvalId: string,
  payload: ResolveAiApprovalRequest,
): Promise<AiApprovalStatusResponse> {
  return aiRequest<AiApprovalStatusResponse>(
    `/api/v1/ai/approvals/${encodeURIComponent(approvalId)}/resolve`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function abandonAiApproval(
  token: string,
  approvalId: string,
  payload: AbandonAiApprovalRequest = {},
): Promise<AiApprovalStatusResponse> {
  return aiRequest<AiApprovalStatusResponse>(
    `/api/v1/ai/approvals/${encodeURIComponent(approvalId)}/abandon`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export async function streamAiChatResume({
  payload,
  token,
  signal,
}: StreamAiResumeArgs): Promise<Response> {
  return streamAiRequest('/api/v1/ai/chat/resume', payload, token, signal);
}

async function streamAiRequest(
  path: string,
  payload: unknown,
  token: string,
  signal: AbortSignal,
): Promise<Response> {
  const url = rewriteWorkspaceApiPath(path);
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      signal,
      cache: 'no-store',
      headers: {
        'Accept': 'text/event-stream',
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if ((error as Error).name === 'AbortError') {
      throw error;
    }
    throw new AiApiError(
      0,
      i18n.t('apps:ai.errors.connect'),
    );
  }

  if (!response.ok) {
    const errPayload = await response.json().catch(() => null);
    throw new AiApiError(
      response.status,
      resolveErrorMessage(
        errPayload,
        i18n.t('apps:ai.errors.streamStartFailed', { status: response.status }),
      ),
    );
  }
  if (!response.body) {
    throw new AiApiError(0, i18n.t('apps:ai.errors.emptySseBody'));
  }
  return response;
}
