import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { resolveWorkspaceChatbotApiPath } from './workspace-chatbot-api-path';

export type ConversationArtifact = ApiSchema<'ArtifactOut'>;

// Mirrors ConversationTurnOut on the server — the backend flattens its stored
// `meta` dict into top-level camelCase fields so MessageBubble/ThinkingPanel/
// ToolCallCard/ArtifactCard can render a reloaded turn without a second
// translation pass.
export type ConversationTurn = Omit<
  ApiSchema<'ConversationTurnOut'>,
  'chosenPool' | 'role'
> & {
  chosenPool?: 'local' | 'external' | null;
  role: 'user' | 'assistant';
};
export type ConversationSummary = ApiSchema<'ConversationSummary'>;
export type ConversationLivePendingApproval =
  ApiSchema<'ConversationLivePendingApproval'>;
export type ConversationDetail = Omit<
  ApiSchema<'ConversationDetail'>,
  'turns'
> & {
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
  workspaceSlug?: string | null,
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      resolveWorkspaceChatbotApiPath(path, workspaceSlug),
      token,
      init,
      (error) => {
        const message =
          error.payload &&
          typeof error.payload === 'object' &&
          'detail' in error.payload &&
          typeof (error.payload as { detail?: unknown }).detail === 'string'
            ? (error.payload as { detail: string }).detail
            : i18n.t('apps:ai.errors.conversationRequestFailed', {
                status: error.status,
              });
        return new ConversationsApiError(error.status, message);
      },
    );
  } catch (error) {
    if (error instanceof ConversationsApiError) {
      throw error;
    }
    throw new ConversationsApiError(
      0,
      i18n.t('apps:ai.errors.conversationConnect'),
    );
  }
}

/**
 * Window custom event fired by the chat view whenever a turn finishes
 * persisting. The conversation list listens for it to refresh recent threads —
 * `updated_at` bumps on follow-up replies don't change the URL, so the
 * route search params alone won't catch them.
 */
export const CONVERSATIONS_UPDATED_EVENT = 'corporate:ai:conversations-updated';

export function listConversations(
  token: string,
  params: {
    limit?: number;
    cursor?: string | null;
    scopeRef?: string;
    scopeResourceId?: string;
    workspaceSlug?: string | null;
  } = {},
): Promise<ConversationListResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit != null) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.cursor) {
    searchParams.set('cursor', params.cursor);
  }
  if (params.scopeRef) {
    searchParams.set('scope_ref', params.scopeRef);
  }
  if (params.scopeResourceId) {
    searchParams.set('scope_resource_id', params.scopeResourceId);
  }
  const qs = searchParams.toString();
  const suffix = qs ? `?${qs}` : '';
  return request<ConversationListResponse>(
    `/api/v1/chatbot/conversations${suffix}`,
    token,
    undefined,
    params.workspaceSlug,
  );
}

export function getConversation(
  token: string,
  conversationId: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/chatbot/conversations/${encodeURIComponent(conversationId)}`,
    token,
    undefined,
    options.workspaceSlug,
  );
}

export function createConversation(
  token: string,
  init: {
    title?: string;
    scopeRef?: string;
    scopeResourceId?: string;
    workspaceSlug?: string | null;
  } = {},
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/chatbot/conversations`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        title: init.title ?? '',
        scopeRef: init.scopeRef,
        scopeResourceId: init.scopeResourceId,
      }),
    },
    init.workspaceSlug,
  );
}

export function renameConversation(
  token: string,
  conversationId: string,
  title: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/v1/chatbot/conversations/${encodeURIComponent(conversationId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify({ title }) },
    options.workspaceSlug,
  );
}

export function deleteConversation(
  token: string,
  conversationId: string,
  options: { workspaceSlug?: string | null } = {},
): Promise<void> {
  return request<void>(
    `/api/v1/chatbot/conversations/${encodeURIComponent(conversationId)}`,
    token,
    { method: 'DELETE' },
    options.workspaceSlug,
  );
}
