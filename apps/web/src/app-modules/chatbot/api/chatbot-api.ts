import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { resolveWorkspaceChatbotApiPath } from './workspace-chatbot-api-path';

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

async function chatbotRequest<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      resolveWorkspaceChatbotApiPath(path, workspaceSlug),
      token,
      init,
      (error) =>
        new AiApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.errors.requestFailed', { status: error.status }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof AiApiError) {
      throw error;
    }
    throw new AiApiError(0, i18n.t('apps:ai.errors.connect'));
  }
}

export function getLlmHealth(
  token: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<LlmHealthResponse> {
  return chatbotRequest<LlmHealthResponse>(
    '/api/v1/chatbot/health',
    token,
    undefined,
    options.workspaceSlug,
  );
}

export function sendAiChat(
  payload: AiChatRequest,
  token: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<AiChatResponse> {
  return chatbotRequest<AiChatResponse>(
    '/api/v1/chatbot/chat',
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    options.workspaceSlug,
  );
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
  return streamAiRequest(
    '/api/v1/chatbot/chat/stream',
    payload,
    token,
    signal,
    workspaceSlug,
  );
}

export function getAiApprovalStatus(
  token: string,
  approvalId: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<AiApprovalStatusResponse> {
  return chatbotRequest<AiApprovalStatusResponse>(
    `/api/v1/chatbot/approvals/${encodeURIComponent(approvalId)}`,
    token,
    undefined,
    options.workspaceSlug,
  );
}

export function resolveAiApproval(
  token: string,
  approvalId: string,
  payload: ResolveAiApprovalRequest,
  options: { workspaceSlug?: string | null } = {},
): Promise<AiApprovalStatusResponse> {
  return chatbotRequest<AiApprovalStatusResponse>(
    `/api/v1/chatbot/approvals/${encodeURIComponent(approvalId)}/resolve`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    options.workspaceSlug,
  );
}

export function abandonAiApproval(
  token: string,
  approvalId: string,
  payload: AbandonAiApprovalRequest = {},
  options: { workspaceSlug?: string | null } = {},
): Promise<AiApprovalStatusResponse> {
  return chatbotRequest<AiApprovalStatusResponse>(
    `/api/v1/chatbot/approvals/${encodeURIComponent(approvalId)}/abandon`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    options.workspaceSlug,
  );
}

export async function streamAiChatResume({
  payload,
  token,
  signal,
  workspaceSlug,
}: StreamAiResumeArgs): Promise<Response> {
  return streamAiRequest(
    '/api/v1/chatbot/chat/resume',
    payload,
    token,
    signal,
    workspaceSlug,
  );
}

async function streamAiRequest(
  path: string,
  payload: unknown,
  token: string,
  signal: AbortSignal,
  workspaceSlug?: string | null,
): Promise<Response> {
  const url = resolveWorkspaceChatbotApiPath(path, workspaceSlug);
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      signal,
      cache: 'no-store',
      headers: {
        ...jsonHeaders(token),
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if ((error as Error).name === 'AbortError') {
      throw error;
    }
    throw new AiApiError(0, i18n.t('apps:ai.errors.connect'));
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
