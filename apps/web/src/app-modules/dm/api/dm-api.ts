import {
  DM_MAX_ATTACHMENT_BYTES,
  dmRoutes,
  isDmAttachmentUploadFileAllowed,
  normalizeDmAddParticipantsRequest,
  normalizeDmAttachmentUrlResponse,
  normalizeDmCreateConversationRequest,
  normalizeDmConversation,
  normalizeDmConversationListResponse,
  normalizeDmMessage,
  normalizeDmMessageAttachment,
  normalizeDmMessageListResponse,
  normalizeDmSendMessageRequest,
  normalizeDmUpdateConversationRequest,
  normalizeDmUserListResponse,
} from '@ai-do/contracts/dm';
import type {
  DmAddParticipantsRequest,
  DmAttachmentUrlResponse,
  DmConversation,
  DmConversationListResponse,
  DmMessage,
  DmMessageAttachment,
  DmMessageListResponse,
  DmSendMessageRequest,
  DmUpdateConversationRequest,
  DmUser,
  DmCreateConversationRequest,
} from '@ai-do/contracts/dm';

import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';

export type {
  DmAttachmentUrlResponse,
  DmConversation,
  DmConversationListResponse,
  DmConversationParticipant,
  DmMessage,
  DmMessageAttachment,
  DmMessageListResponse,
  DmRealtimeEvent,
  DmUser,
} from '@ai-do/contracts/dm';

export type DmThread = DmConversation;
export type DmThreadListResponse = DmConversationListResponse;

type SearchDmUsersOptions = {
  includeCurrent?: boolean;
  limit?: number;
  workspaceKey?: string;
};

function dmUsersPath({
  includeCurrent,
  limit,
  q,
  workspaceKey,
}: {
  includeCurrent: boolean;
  limit: number;
  q: string;
  workspaceKey?: string;
}): string {
  let path = dmRoutes.users({ q, limit });
  if (includeCurrent) {
    const separator = path.includes('?') ? '&' : '?';
    path = `${path}${separator}include_current=true`;
  }
  if (workspaceKey) {
    const separator = path.includes('?') ? '&' : '?';
    path = `${path}${separator}workspace_key=${encodeURIComponent(workspaceKey)}`;
  }
  return path;
}

export function searchDmUsers(
  token: string,
  query: string,
  options: SearchDmUsersOptions = {},
): Promise<DmUser[]> {
  const { includeCurrent = false, limit = 30, workspaceKey } = options;
  const path = dmUsersPath({ includeCurrent, limit, q: query, workspaceKey });
  return fetchDmResponse(
    'dm:users',
    path,
    token,
    {},
    normalizeDmUserListResponse,
  );
}

export function listDmConversations(
  token: string,
): Promise<DmConversationListResponse> {
  return fetchDmResponse(
    'dm:conversations',
    dmRoutes.conversations(),
    token,
    {},
    normalizeDmConversationListResponse,
  );
}

export function createDirectDmConversation(
  token: string,
  recipientUserId: string,
): Promise<DmConversation> {
  const body = requireDmRequest(
    'dm:create-conversation',
    { recipient_user_id: recipientUserId },
    normalizeDmCreateConversationRequest,
  );
  return fetchDmResponse(
    'dm:create-conversation',
    dmRoutes.conversations(),
    token,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    normalizeDmConversation,
  );
}

export function createGroupDmConversation(
  token: string,
  participantUserIds: string[],
  title: string,
): Promise<DmConversation> {
  const body = requireDmRequest(
    'dm:create-conversation',
    {
      participant_user_ids: participantUserIds,
      title,
    },
    normalizeDmCreateConversationRequest,
  );
  return fetchDmResponse(
    'dm:create-conversation',
    dmRoutes.conversations(),
    token,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    normalizeDmConversation,
  );
}

export function updateDmConversationTitle(
  token: string,
  conversationId: string,
  title: string,
): Promise<DmConversation> {
  const body = requireDmRequest(
    'dm:update-conversation',
    { title },
    normalizeDmUpdateConversationRequest,
  );
  return fetchDmResponse(
    'dm:update-conversation',
    dmRoutes.conversation(conversationId),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
    normalizeDmConversation,
  );
}

export function addDmConversationParticipants(
  token: string,
  conversationId: string,
  userIds: string[],
): Promise<DmConversation> {
  const body = requireDmRequest(
    'dm:add-participants',
    { user_ids: userIds },
    normalizeDmAddParticipantsRequest,
  );
  return fetchDmResponse(
    'dm:add-participants',
    dmRoutes.conversationParticipants(conversationId),
    token,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    normalizeDmConversation,
  );
}

export function removeDmConversationParticipant(
  token: string,
  conversationId: string,
  userId: string,
): Promise<DmConversation> {
  return fetchDmResponse(
    'dm:remove-participant',
    dmRoutes.conversationParticipant(conversationId, userId),
    token,
    { method: 'DELETE' },
    normalizeDmConversation,
  );
}

export function leaveDmConversation(
  token: string,
  conversationId: string,
): Promise<void> {
  return apiFetchJson<void>(dmRoutes.leaveConversation(conversationId), token, {
    method: 'DELETE',
  });
}

export function listDmMessages(
  token: string,
  conversationId: string,
  limit = 50,
): Promise<DmMessageListResponse> {
  return fetchDmResponse(
    'dm:messages',
    dmRoutes.listMessages(conversationId, { limit }),
    token,
    {},
    normalizeDmMessageListResponse,
  );
}

export function uploadDmAttachment(
  token: string,
  conversationId: string,
  file: File,
): Promise<DmMessageAttachment> {
  const path = dmRoutes.messageAttachments(conversationId);
  assertDmAttachmentUploadFile(file);
  const formData = new FormData();
  formData.append('file', file, file.name || 'clipboard-file');
  return fetchDmResponse(
    'dm:upload-attachment',
    path,
    token,
    {
      method: 'POST',
      body: formData,
    },
    normalizeDmMessageAttachment,
  );
}

export function getDmAttachmentDownloadUrl(
  token: string,
  attachmentId: string,
): Promise<DmAttachmentUrlResponse> {
  return fetchDmResponse(
    'dm:attachment-download',
    dmRoutes.attachmentDownload(attachmentId),
    token,
    {},
    normalizeDmAttachmentUrlResponse,
  );
}

export function getDmAttachmentPreviewUrl(
  token: string,
  attachmentId: string,
): Promise<DmAttachmentUrlResponse> {
  return fetchDmResponse(
    'dm:attachment-preview',
    dmRoutes.attachmentPreview(attachmentId),
    token,
    {},
    normalizeDmAttachmentUrlResponse,
  );
}

export function sendDmMessage(
  token: string,
  conversationId: string,
  body: string,
  attachmentIds: string[] = [],
  replyToMessageId: string | null = null,
): Promise<DmMessage> {
  const payload = requireDmRequest(
    'dm:send-message',
    {
      body,
      attachment_ids: attachmentIds,
      ...(replyToMessageId ? { reply_to_message_id: replyToMessageId } : {}),
    },
    normalizeDmSendMessageRequest,
  );
  return fetchDmResponse(
    'dm:send-message',
    dmRoutes.messages(conversationId),
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    normalizeDmMessage,
  );
}

function markDmConversationRead(
  token: string,
  conversationId: string,
): Promise<DmConversation> {
  return fetchDmResponse(
    'dm:mark-read',
    dmRoutes.markRead(conversationId),
    token,
    { method: 'PATCH' },
    normalizeDmConversation,
  );
}

export const listDmThreads = listDmConversations;
export const createDmThread = createDirectDmConversation;
export const createGroupDmThread = createGroupDmConversation;
export const markDmThreadRead = markDmConversationRead;

function fetchDmResponse<T>(
  label: string,
  path: string,
  token: string,
  init: RequestInit,
  normalize: (value: unknown) => T | null,
): Promise<T> {
  return apiFetchJson<unknown>(path, token, init).then((value) => {
    const normalized = normalize(value);
    if (!normalized) {
      throw new ApiRequestError(
        502,
        `Invalid response format for ${label}.`,
        value,
      );
    }
    return normalized;
  });
}

function assertDmAttachmentUploadFile(file: Pick<File, 'size'>): void {
  if (!isDmAttachmentUploadFileAllowed(file)) {
    throw new ApiRequestError(
      400,
      `Attachments must be ${DM_MAX_ATTACHMENT_BYTES / (1024 * 1024)}MB or smaller.`,
      { size: file.size },
    );
  }
}

function requireDmRequest<
  T extends
    | DmAddParticipantsRequest
    | DmCreateConversationRequest
    | DmSendMessageRequest
    | DmUpdateConversationRequest,
>(label: string, value: unknown, normalize: (value: unknown) => T | null): T {
  const normalized = normalize(value);
  if (!normalized) {
    throw new ApiRequestError(
      400,
      `Invalid request format for ${label}.`,
      value,
    );
  }
  return normalized;
}
