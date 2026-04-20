import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

export interface ConversationArtifact {
  id: string;
  type: string;
  title: string | null;
  content: string;
  status?: string | null;
}

// Mirrors ConversationTurnOut on the server — the backend flattens its stored
// `meta` dict into top-level camelCase fields so MessageBubble/ThinkingPanel/
// ToolCallCard/ArtifactCard can render a reloaded turn without a second
// translation pass.
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
  toolCalls?: Array<Record<string, unknown>>;
  pendingApprovals?: Array<Record<string, unknown>>;
  artifacts?: ConversationArtifact[];
  createdAt: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationDetail extends ConversationSummary {
  turns: ConversationTurn[];
}

export interface ConversationListResponse {
  items: ConversationSummary[];
  nextCursor: string | null;
}

export class ConversationsApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ConversationsApiError';
  }
}

async function request<T>(
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
    throw new ConversationsApiError(
      0,
      '대화 내역 서버에 연결하지 못했습니다.',
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      payload && typeof payload === 'object' && 'detail' in payload &&
      typeof (payload as { detail?: unknown }).detail === 'string'
        ? ((payload as { detail: string }).detail)
        : `대화 요청에 실패했습니다. (${response.status})`;
    throw new ConversationsApiError(response.status, message);
  }
  return payload as T;
}

/**
 * Window custom event fired by the chat view whenever a turn finishes
 * persisting. The sidebar listens for it to refresh the "최근 대화" list —
 * `updated_at` bumps on follow-up replies don't change the URL, so the
 * sidebar's `location.search` dependency alone won't catch them.
 */
export const CONVERSATIONS_UPDATED_EVENT = 'doowon:ai:conversations-updated';

export function listConversations(
  token: string,
  params: { limit?: number; cursor?: string | null } = {},
): Promise<ConversationListResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit != null) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.cursor) {
    searchParams.set('cursor', params.cursor);
  }
  const qs = searchParams.toString();
  const suffix = qs ? `?${qs}` : '';
  return request<ConversationListResponse>(
    `/api/v1/conversations${suffix}`,
    token,
  );
}

export function getConversation(
  token: string,
  conversationId: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
    token,
  );
}

export function createConversation(
  token: string,
  init: { title?: string } = {},
): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/v1/conversations`, token, {
    method: 'POST',
    body: JSON.stringify({ title: init.title ?? '' }),
  });
}

export function renameConversation(
  token: string,
  conversationId: string,
  title: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify({ title }) },
  );
}

export function deleteConversation(
  token: string,
  conversationId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
    token,
    { method: 'DELETE' },
  );
}
