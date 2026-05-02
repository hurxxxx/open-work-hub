import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type ConversationArtifact = ApiSchema<'ArtifactOut'>;

// Mirrors ConversationTurnOut on the server — the backend flattens its stored
// `meta` dict into top-level camelCase fields so MessageBubble/ThinkingPanel/
// ToolCallCard/ArtifactCard can render a reloaded turn without a second
// translation pass.
export type ConversationTurn = Omit<ApiSchema<'ConversationTurnOut'>, 'chosenPool' | 'role'> & {
  chosenPool?: 'local' | 'external' | null;
  role: 'user' | 'assistant';
};
export type ConversationSummary = ApiSchema<'ConversationSummary'>;
export type ConversationLivePendingApproval = ApiSchema<'ConversationLivePendingApproval'>;
export type ConversationDetail = Omit<ApiSchema<'ConversationDetail'>, 'turns'> & {
  turns: ConversationTurn[];
};
export type ConversationListResponse = ApiSchema<'ConversationListResponse'>;

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
  try {
    return await apiFetchJson<T>(rewriteWorkspaceApiPath(path), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      const message =
        error.payload && typeof error.payload === 'object' && 'detail' in error.payload &&
        typeof (error.payload as { detail?: unknown }).detail === 'string'
          ? ((error.payload as { detail: string }).detail)
          : i18n.t('apps:ai.errors.conversationRequestFailed', { status: error.status });
      throw new ConversationsApiError(error.status, message);
    }
    throw new ConversationsApiError(
      0,
      i18n.t('apps:ai.errors.conversationConnect'),
    );
  }
}

/**
 * Window custom event fired by the chat view whenever a turn finishes
 * persisting. The sidebar listens for it to refresh the recent conversation list —
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
    `/api/v1/ai/conversations${suffix}`,
    token,
  );
}

export function getConversation(
  token: string,
  conversationId: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/ai/conversations/${encodeURIComponent(conversationId)}`,
    token,
  );
}

export function createConversation(
  token: string,
  init: {
    title?: string;
    scopeRef?: 'meeting';
    scopeResourceId?: string;
  } = {},
): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/v1/ai/conversations`, token, {
    method: 'POST',
    body: JSON.stringify({
      title: init.title ?? '',
      scopeRef: init.scopeRef,
      scopeResourceId: init.scopeResourceId,
    }),
  });
}

export function renameConversation(
  token: string,
  conversationId: string,
  title: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/ai/conversations/${encodeURIComponent(conversationId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify({ title }) },
  );
}

export function deleteConversation(
  token: string,
  conversationId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/ai/conversations/${encodeURIComponent(conversationId)}`,
    token,
    { method: 'DELETE' },
  );
}
