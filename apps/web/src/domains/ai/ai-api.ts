import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

export type AiChatRole = 'system' | 'user' | 'assistant';
export type AiBackendMode = 'auto' | 'local';

export interface AiChatMessage {
  role: AiChatRole;
  content: string;
}

export interface AiChatRequest {
  messages: AiChatMessage[];
  backend_mode?: AiBackendMode;
  max_tokens?: number;
  temperature?: number;
  reasoning_effort?: 'none' | 'low' | 'medium' | 'high';
}

export interface AiChatUsage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
}

export interface AiChatResponse {
  model: string;
  content: string;
  usage: AiChatUsage | null;
  provider: string;
  backend: string;
  fallback_used: boolean;
  canonical_model: string;
  requested_backend_mode: AiBackendMode;
  policy: string | null;
  chosen_pool: 'local' | 'external' | null;
  decision_reason: string | null;
  forced_local: boolean;
  pii_hits: string[];
}

export interface LlmPoolHealthResponse {
  pool: 'local' | 'external';
  provider: string;
  base_url: string;
  model: string;
  canonical_model: string;
  status: string;
  ready: boolean;
  detail: string | null;
}

export interface LlmTaskReadinessResponse {
  task_kind: string;
  description: string;
  policy: string;
  chosen_pool: 'local' | 'external' | null;
  ready: boolean;
  detail: string | null;
}

export interface LlmHealthResponse {
  ready: boolean;
  local: LlmPoolHealthResponse;
  external: LlmPoolHealthResponse | null;
}

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
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('Authorization', `Bearer ${token}`);

  if (init.body) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(rewriteWorkspaceApiPath(path), {
      ...init,
      headers,
      cache: 'no-store',
    });
  } catch {
    throw new AiApiError(
      0,
      'AI 서버에 연결하지 못했습니다. API 서버가 실행 중인지 확인해 주세요.',
    );
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AiApiError(
      response.status,
      resolveErrorMessage(
        payload,
        `AI 요청에 실패했습니다. (${response.status})`,
      ),
    );
  }

  return payload as T;
}

export function getLlmHealth(token: string): Promise<LlmHealthResponse> {
  return aiRequest<LlmHealthResponse>('/api/v1/ai/health', token);
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
