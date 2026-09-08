import type { ApiSchema } from './api.js';
import { isDmRouteId } from './dm-routes.js';

export {
  DEFAULT_DM_MESSAGE_LIMIT,
  DEFAULT_DM_USER_SEARCH_LIMIT,
  DM_API_PREFIX,
  DM_MAX_ATTACHMENT_BYTES,
  DM_QUERY_LIMIT_MAX,
  DM_QUERY_LIMIT_MIN,
  DM_ROUTE_ID_ALLOWED_PATTERN,
  DM_ROUTE_ID_MAX_LENGTH,
  dmRoutes,
  isDmAttachmentUploadFileAllowed,
  isDmRouteId,
  normalizeDmLimit,
} from './dm-routes.js';
export type { DmAttachmentUploadFile } from './dm-routes.js';

export type DmUser = ApiSchema<'DmUserItem'>;
export type DmConversationParticipant =
  ApiSchema<'DmConversationParticipantItem'>;
export type DmMessageAttachment = ApiSchema<'DmMessageAttachmentItem'>;
export type DmMessageReadState = ApiSchema<'DmMessageReadStateItem'>;
export type DmMessageReplyTo = ApiSchema<'DmMessageReplyToItem'>;
export type DmMessage = ApiSchema<'DmMessageItem'>;
export type DmConversation = ApiSchema<'DmConversationItem'>;
export type DmConversationListResponse =
  ApiSchema<'DmConversationListResponse'>;
export type DmMessageListResponse = ApiSchema<'DmMessageListResponse'>;
export type DmAttachmentUrlResponse = ApiSchema<'DmAttachmentUrlResponse'>;
export type DmCreateConversationRequest =
  ApiSchema<'DmCreateConversationRequest'>;
export type DmUpdateConversationRequest =
  ApiSchema<'DmUpdateConversationRequest'>;
export type DmAddParticipantsRequest = ApiSchema<'DmAddParticipantsRequest'>;
export type DmSendMessageRequest = ApiSchema<'DmSendMessageRequest'>;

export const DM_REALTIME_EVENT_TYPES = {
  messageCreated: 'dm.message.created',
  conversationCreated: 'dm.conversation.created',
  conversationUpdated: 'dm.conversation.updated',
  conversationRead: 'dm.conversation.read',
  conversationRemoved: 'dm.conversation.removed',
} as const;

export const DM_REALTIME_EVENT_TYPE_VALUES = [
  DM_REALTIME_EVENT_TYPES.messageCreated,
  DM_REALTIME_EVENT_TYPES.conversationCreated,
  DM_REALTIME_EVENT_TYPES.conversationUpdated,
  DM_REALTIME_EVENT_TYPES.conversationRead,
  DM_REALTIME_EVENT_TYPES.conversationRemoved,
] as const;

export type DmRealtimeEventType =
  (typeof DM_REALTIME_EVENT_TYPE_VALUES)[number];

const DM_REALTIME_EVENT_TYPE_SET: ReadonlySet<string> = new Set(
  DM_REALTIME_EVENT_TYPE_VALUES,
);

export interface DmRealtimeEvent {
  type: DmRealtimeEventType | string;
  data?: {
    message?: DmMessage;
    conversation?: DmConversation;
    thread?: DmConversation;
    conversation_id?: string;
    thread_id?: string;
    user_id?: string;
  };
}

export interface DmReadVisibility {
  visible: boolean;
  focused: boolean;
}

export interface DmRealtimeState {
  conversations: DmConversation[];
  messages: DmMessage[];
  selectedConversationId: string | null;
  currentUserId?: string | null;
  canMarkRead: boolean;
}

export interface DmRealtimeStateResult {
  conversations: DmConversation[];
  messages: DmMessage[];
  selectedConversationId: string | null;
  markReadConversationId: string | null;
  removedConversationId: string | null;
  selectedConversationRemoved: boolean;
}

export type DmPreviewLabels = {
  emptyThread: string;
  attachmentFile: (filename: string) => string;
  attachmentCount: (count: number) => string;
};

export type DmDisplayLabels = DmPreviewLabels & {
  directFallback: string;
  groupFallback: string;
};

export type DmConversationPreviewSenderPrefix = 'group' | 'incoming' | 'never';
export type DmGroupDisplayNamePreference = 'display_name' | 'participants';

export type DmConversationListItemProjection = {
  id: string;
  name: string;
  initials: string;
  preview: string;
  selected: boolean;
  unreadBadge: string | null;
  unreadCount: number | null;
};

export type DmComposerSendCommand = {
  attachmentIds: string[];
  body: string;
  conversationId: string;
  replyToMessageId: string | null;
};

export const DM_MESSAGE_BODY_MAX_LENGTH = 120000;
export const DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH = 10;
export const DM_PARTICIPANT_IDS_MAX_LENGTH = 50;
export const DM_CONVERSATION_TITLE_MAX_LENGTH = 140;

export function normalizeDmCreateConversationRequest(
  value: unknown,
): DmCreateConversationRequest | null {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ['recipient_user_id', 'participant_user_ids', 'title'])
  ) {
    return null;
  }
  const recipientUserId = optionalNullableDmRequestId(value.recipient_user_id);
  const participantUserIds = optionalDmRequestIdList(
    value.participant_user_ids,
    DM_PARTICIPANT_IDS_MAX_LENGTH,
    true,
  );
  const title = optionalNullableDmTitle(value.title);
  if (
    recipientUserId === undefined ||
    participantUserIds === null ||
    title === undefined ||
    (Boolean(recipientUserId) && participantUserIds.length > 0) ||
    (!recipientUserId && participantUserIds.length === 0)
  ) {
    return null;
  }
  return {
    ...(recipientUserId ? { recipient_user_id: recipientUserId } : {}),
    ...(participantUserIds.length > 0
      ? { participant_user_ids: participantUserIds }
      : {}),
    ...(title ? { title } : {}),
  };
}

export function normalizeDmUpdateConversationRequest(
  value: unknown,
): DmUpdateConversationRequest | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ['title'])) {
    return null;
  }
  const title = optionalNullableDmTitle(value.title);
  if (title === undefined) {
    return null;
  }
  return {
    title,
  };
}

export function normalizeDmAddParticipantsRequest(
  value: unknown,
): DmAddParticipantsRequest | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ['user_ids'])) {
    return null;
  }
  const userIds = optionalDmRequestIdList(
    value.user_ids,
    DM_PARTICIPANT_IDS_MAX_LENGTH,
    false,
  );
  return userIds ? { user_ids: userIds } : null;
}

export function normalizeDmSendMessageRequest(
  value: unknown,
): DmSendMessageRequest | null {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ['body', 'attachment_ids', 'reply_to_message_id'])
  ) {
    return null;
  }
  if (typeof value.body !== 'string') {
    return null;
  }
  const body = value.body.trim();
  if (body.length > DM_MESSAGE_BODY_MAX_LENGTH) {
    return null;
  }
  const attachmentIds = optionalDmRequestIdList(
    value.attachment_ids,
    DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH,
    true,
  );
  if (!attachmentIds || (!body && attachmentIds.length === 0)) {
    return null;
  }
  const replyToMessageId = optionalNullableDmRequestId(
    value.reply_to_message_id,
  );
  if (replyToMessageId === undefined) {
    return null;
  }
  return {
    body,
    attachment_ids: attachmentIds,
    ...(replyToMessageId ? { reply_to_message_id: replyToMessageId } : {}),
  };
}

export function normalizeDmUser(value: unknown): DmUser | null {
  if (
    !isRecord(value) ||
    !isDmResponseId(value.id) ||
    typeof value.email !== 'string' ||
    typeof value.full_name !== 'string'
  ) {
    return null;
  }
  const displayName = optionalNullableString(value.display_name);
  if (displayName === undefined) {
    return null;
  }
  return {
    id: value.id,
    email: value.email,
    full_name: value.full_name,
    display_name: displayName,
  };
}

export function normalizeDmUserListResponse(value: unknown): DmUser[] | null {
  return normalizeArray(value, normalizeDmUser);
}

export function normalizeDmMessageAttachment(
  value: unknown,
): DmMessageAttachment | null {
  if (
    !isRecord(value) ||
    !isDmResponseId(value.id) ||
    !isDmResponseId(value.conversation_id) ||
    typeof value.filename !== 'string' ||
    typeof value.content_type !== 'string' ||
    !isNonNegativeInteger(value.size_bytes) ||
    typeof value.is_image !== 'boolean' ||
    !isDateTimeString(value.created_at)
  ) {
    return null;
  }
  const messageId = optionalNullableDmResponseId(value.message_id);
  if (messageId === undefined) {
    return null;
  }
  return {
    id: value.id,
    conversation_id: value.conversation_id,
    message_id: messageId,
    filename: value.filename,
    content_type: value.content_type,
    size_bytes: value.size_bytes,
    is_image: value.is_image,
    created_at: value.created_at,
  };
}

export function normalizeDmAttachmentUrlResponse(
  value: unknown,
): DmAttachmentUrlResponse | null {
  if (!isRecord(value) || typeof value.url !== 'string' || !value.url.trim()) {
    return null;
  }
  return {
    url: value.url,
  };
}

export function normalizeDmMessageReadState(
  value: unknown,
): DmMessageReadState | null {
  if (
    !isRecord(value) ||
    !isNonNegativeInteger(value.unread_count) ||
    typeof value.read_by_all !== 'boolean'
  ) {
    return null;
  }
  return {
    unread_count: value.unread_count,
    read_by_all: value.read_by_all,
  };
}

export function normalizeDmMessageReplyTo(
  value: unknown,
): DmMessageReplyTo | null {
  if (
    !isRecord(value) ||
    !isDmResponseId(value.id) ||
    !isDmResponseId(value.sender_id) ||
    typeof value.sender_name !== 'string' ||
    typeof value.body_preview !== 'string' ||
    !isNonNegativeInteger(value.attachment_count) ||
    !isDateTimeString(value.created_at)
  ) {
    return null;
  }
  return {
    id: value.id,
    sender_id: value.sender_id,
    sender_name: value.sender_name,
    body_preview: value.body_preview,
    attachment_count: value.attachment_count,
    created_at: value.created_at,
  };
}

export function normalizeDmMessage(value: unknown): DmMessage | null {
  if (
    !isRecord(value) ||
    !isDmResponseId(value.id) ||
    !isDmResponseId(value.conversation_id) ||
    !isDmResponseId(value.thread_id) ||
    !isNonNegativeInteger(value.sequence) ||
    !isDmResponseId(value.sender_id) ||
    typeof value.sender_name !== 'string' ||
    typeof value.body !== 'string' ||
    !isDateTimeString(value.created_at)
  ) {
    return null;
  }
  const attachments = normalizeOptionalArray(
    value.attachments,
    normalizeDmMessageAttachment,
  );
  const readState = normalizeDmMessageReadState(value.read_state);
  const replyTo =
    value.reply_to == null ? null : normalizeDmMessageReplyTo(value.reply_to);
  if (!attachments || !readState || (value.reply_to != null && !replyTo)) {
    return null;
  }
  return {
    id: value.id,
    conversation_id: value.conversation_id,
    thread_id: value.thread_id,
    sequence: value.sequence,
    sender_id: value.sender_id,
    sender_name: value.sender_name,
    read_state: readState,
    reply_to: replyTo,
    body: value.body,
    attachments,
    created_at: value.created_at,
  };
}

export function normalizeDmConversation(value: unknown): DmConversation | null {
  if (
    !isRecord(value) ||
    !isDmResponseId(value.id) ||
    !isDmConversationType(value.conversation_type) ||
    !isDmConversationType(value.thread_type) ||
    typeof value.display_name !== 'string' ||
    !isNonNegativeInteger(value.participant_count) ||
    !isNonNegativeInteger(value.unread_count) ||
    !isDmResponseId(value.created_by_id) ||
    !isDateTimeString(value.created_at) ||
    !isDateTimeString(value.updated_at)
  ) {
    return null;
  }
  const title = optionalNullableString(value.title);
  const otherUser =
    value.other_user == null ? null : normalizeDmUser(value.other_user);
  const participants = normalizeArray(
    value.participants,
    normalizeDmConversationParticipant,
  );
  const lastMessage =
    value.last_message == null ? null : normalizeDmMessage(value.last_message);
  const lastReadMessageId = optionalNullableDmResponseId(
    value.last_read_message_id,
  );
  const mutedAt = optionalNullableDateTimeString(value.muted_at);
  if (
    title === undefined ||
    (value.other_user != null && !otherUser) ||
    !participants ||
    (value.last_message != null && !lastMessage) ||
    lastReadMessageId === undefined ||
    mutedAt === undefined
  ) {
    return null;
  }
  return {
    id: value.id,
    conversation_type: value.conversation_type,
    thread_type: value.thread_type,
    title,
    display_name: value.display_name,
    other_user: otherUser,
    participants,
    participant_count: value.participant_count,
    last_message: lastMessage,
    unread_count: value.unread_count,
    last_read_message_id: lastReadMessageId,
    muted_at: mutedAt,
    created_by_id: value.created_by_id,
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}

export function normalizeDmConversationListResponse(
  value: unknown,
): DmConversationListResponse | null {
  if (!isRecord(value)) {
    return null;
  }
  const items = normalizeArray(value.items, normalizeDmConversation);
  return items ? { items } : null;
}

export function normalizeDmMessageListResponse(
  value: unknown,
): DmMessageListResponse | null {
  if (!isRecord(value)) {
    return null;
  }
  const items = normalizeArray(value.items, normalizeDmMessage);
  return items ? { items } : null;
}

export function normalizeDmRealtimeEvent(
  value: unknown,
): DmRealtimeEvent | null {
  if (
    !isRecord(value) ||
    typeof value.type !== 'string' ||
    !value.type.trim()
  ) {
    return null;
  }
  if (!isDmRealtimeEventType(value.type)) {
    return { type: value.type };
  }
  if (!isRecord(value.data)) {
    return null;
  }
  if (value.type === DM_REALTIME_EVENT_TYPES.messageCreated) {
    const message = normalizeDmMessage(value.data.message);
    const conversation = normalizeDmConversation(value.data.conversation);
    if (!message || !conversation) {
      return null;
    }
    const data = normalizeDmRealtimeData(value.data, { message, conversation });
    if (!data) {
      return null;
    }
    return {
      type: value.type,
      data,
    };
  }
  if (
    value.type === DM_REALTIME_EVENT_TYPES.conversationCreated ||
    value.type === DM_REALTIME_EVENT_TYPES.conversationUpdated ||
    value.type === DM_REALTIME_EVENT_TYPES.conversationRead
  ) {
    const conversation = normalizeDmConversation(value.data.conversation);
    if (!conversation) {
      return null;
    }
    const data = normalizeDmRealtimeData(value.data, { conversation });
    if (!data) {
      return null;
    }
    return {
      type: value.type,
      data,
    };
  }
  const conversationId = optionalRealtimeDmResponseId(
    value.data.conversation_id,
  );
  const threadId = optionalRealtimeDmResponseId(value.data.thread_id);
  if (!conversationId && !threadId) {
    return null;
  }
  const data = normalizeDmRealtimeData(value.data, {});
  if (!data) {
    return null;
  }
  return {
    type: value.type,
    data,
  };
}

export function canMarkDmConversationRead(input: DmReadVisibility): boolean {
  return input.visible && input.focused;
}

export function totalDmUnreadCount(
  conversations: readonly DmConversation[],
): number {
  return conversations.reduce(
    (sum, conversation) => sum + Math.max(0, conversation.unread_count),
    0,
  );
}

export function dmUserDisplayName(
  user: DmUser | null | undefined,
  fallback = 'DM',
): string {
  if (!user) {
    return fallback;
  }
  return user.display_name || user.full_name || user.email || fallback;
}

export function dmConversationDisplayName(
  conversation: DmConversation,
  input: {
    currentUserId?: string | null;
    labels: Pick<DmDisplayLabels, 'directFallback' | 'groupFallback'>;
    groupDisplayName?: DmGroupDisplayNamePreference;
  },
): string {
  if (conversation.conversation_type === 'direct') {
    return dmUserDisplayName(
      conversation.other_user,
      input.labels.directFallback,
    );
  }
  if (conversation.title) {
    return conversation.title;
  }
  if (
    conversation.display_name &&
    (input.groupDisplayName ?? 'display_name') === 'display_name'
  ) {
    return conversation.display_name;
  }
  const names = conversation.participants
    .filter((participant) => participant.user.id !== input.currentUserId)
    .map((participant) =>
      dmUserDisplayName(participant.user, input.labels.groupFallback),
    );
  return (
    names.slice(0, 3).join(', ') ||
    conversation.display_name ||
    input.labels.groupFallback
  );
}

export function dmInitials(value: string, fallback = 'DM'): string {
  const result = value
    .trim()
    .split(/[\s._-]+/u)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return result || fallback;
}

export function dmMessagePreviewText(
  message: Pick<DmMessage, 'attachments' | 'body'>,
  labels: DmPreviewLabels,
): string {
  if (message.body.trim()) {
    return message.body;
  }
  const attachments = message.attachments ?? [];
  if (attachments.length === 1) {
    return labels.attachmentFile(attachments[0].filename);
  }
  if (attachments.length > 1) {
    return labels.attachmentCount(attachments.length);
  }
  return labels.emptyThread;
}

export function dmConversationPreviewText(
  conversation: DmConversation,
  input: {
    currentUserId?: string | null;
    labels: DmPreviewLabels;
    senderPrefix?: DmConversationPreviewSenderPrefix;
  },
): string {
  const message = conversation.last_message;
  if (!message) {
    return input.labels.emptyThread;
  }
  const preview = dmMessagePreviewText(message, input.labels);
  if (
    shouldPrefixDmConversationPreview({
      conversationType: conversation.conversation_type,
      currentUserId: input.currentUserId,
      senderId: message.sender_id,
      senderPrefix: input.senderPrefix ?? 'group',
    })
  ) {
    return `${message.sender_name}: ${preview}`;
  }
  return preview;
}

export function dmUnreadBadge(count: number, max = 9): string | null {
  if (count <= 0) {
    return null;
  }
  return count > max ? `${max}+` : String(count);
}

export function buildDmConversationListItemProjection(input: {
  conversation: DmConversation;
  currentUserId?: string | null;
  labels: DmDisplayLabels;
  groupDisplayName?: DmGroupDisplayNamePreference;
  selectedConversationId?: string | null;
  senderPrefix?: DmConversationPreviewSenderPrefix;
  unreadBadgeMax?: number;
}): DmConversationListItemProjection {
  const name = dmConversationDisplayName(input.conversation, {
    currentUserId: input.currentUserId,
    labels: input.labels,
    groupDisplayName: input.groupDisplayName,
  });
  const unreadBadge = dmUnreadBadge(
    input.conversation.unread_count,
    input.unreadBadgeMax ?? 9,
  );
  return {
    id: input.conversation.id,
    name,
    initials: dmInitials(name),
    preview: dmConversationPreviewText(input.conversation, {
      currentUserId: input.currentUserId,
      labels: input.labels,
      senderPrefix: input.senderPrefix,
    }),
    selected: input.conversation.id === input.selectedConversationId,
    unreadBadge,
    unreadCount: unreadBadge ? input.conversation.unread_count : null,
  };
}

export function resolveDmComposerSendCommand(input: {
  authenticated?: boolean;
  conversationId: string | null | undefined;
  sending: boolean;
  uploadingAttachmentCount?: number;
  draft: string;
  readyAttachmentIds: readonly string[];
  replyToMessageId?: string | null;
}): DmComposerSendCommand | null {
  if (
    input.authenticated === false ||
    !input.conversationId ||
    input.sending ||
    (input.uploadingAttachmentCount ?? 0) > 0
  ) {
    return null;
  }
  const body = input.draft.trim();
  if (!body && input.readyAttachmentIds.length === 0) {
    return null;
  }
  return {
    attachmentIds: [...input.readyAttachmentIds],
    body,
    conversationId: input.conversationId,
    replyToMessageId: input.replyToMessageId ?? null,
  };
}

export function isDmComposerSendDisabled(input: {
  draft: string;
  readyAttachmentIds: readonly string[];
  sending: boolean;
  uploadingAttachmentCount: number;
}): boolean {
  return (
    input.sending ||
    input.uploadingAttachmentCount > 0 ||
    (!input.draft.trim() && input.readyAttachmentIds.length === 0)
  );
}

export function shouldSubmitDmComposerKey(input: {
  key: string;
  shiftKey: boolean;
}): boolean {
  return input.key === 'Enter' && !input.shiftKey;
}

export function readyDmPendingAttachmentIds<T extends { id: string }>(
  items: readonly {
    status: string;
    attachment: T | null;
  }[],
): string[] {
  return items.flatMap((item) =>
    item.status === 'ready' && item.attachment ? [item.attachment.id] : [],
  );
}

export function uploadingDmPendingAttachmentCount(
  items: readonly { status: string }[],
): number {
  return items.filter((item) => item.status === 'uploading').length;
}

export function isDmImageMimeType(input: { type: string }): boolean {
  return input.type.split(';', 1)[0].toLowerCase().startsWith('image/');
}

export function upsertDmConversation(
  items: DmConversation[],
  conversation: DmConversation,
): DmConversation[] {
  return [
    conversation,
    ...items.filter((item) => item.id !== conversation.id),
  ].sort(
    (left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at),
  );
}

export function appendDmMessage(
  items: DmMessage[],
  message: DmMessage,
): DmMessage[] {
  if (items.some((item) => item.id === message.id)) {
    return items;
  }
  return [...items, message].sort(
    (left, right) => Date.parse(left.created_at) - Date.parse(right.created_at),
  );
}

export function applyDmRealtimeEvent(
  state: DmRealtimeState,
  event: DmRealtimeEvent,
): DmRealtimeStateResult {
  let conversations = state.conversations;
  let messages = state.messages;
  let selectedConversationId = state.selectedConversationId;
  let markReadConversationId: string | null = null;
  let removedConversationId: string | null = null;
  let selectedConversationRemoved = false;

  if (
    event.type === DM_REALTIME_EVENT_TYPES.messageCreated &&
    event.data?.message &&
    event.data.conversation
  ) {
    const nextMessage = event.data.message;
    conversations = upsertDmConversation(
      conversations,
      event.data.conversation,
    );
    if (selectedConversationId === nextMessage.conversation_id) {
      messages = appendDmMessage(messages, nextMessage);
      if (nextMessage.sender_id !== state.currentUserId && state.canMarkRead) {
        markReadConversationId = nextMessage.conversation_id;
      }
    }
  } else if (
    (event.type === DM_REALTIME_EVENT_TYPES.conversationCreated ||
      event.type === DM_REALTIME_EVENT_TYPES.conversationUpdated ||
      event.type === DM_REALTIME_EVENT_TYPES.conversationRead) &&
    event.data?.conversation
  ) {
    conversations = upsertDmConversation(
      conversations,
      event.data.conversation,
    );
  } else if (event.type === DM_REALTIME_EVENT_TYPES.conversationRemoved) {
    removedConversationId =
      event.data?.conversation_id ?? event.data?.thread_id ?? null;
    if (removedConversationId) {
      conversations = conversations.filter(
        (item) => item.id !== removedConversationId,
      );
      if (selectedConversationId === removedConversationId) {
        selectedConversationId = null;
        selectedConversationRemoved = true;
      }
    }
  }

  return {
    conversations,
    messages,
    selectedConversationId,
    markReadConversationId,
    removedConversationId,
    selectedConversationRemoved,
  };
}

function shouldPrefixDmConversationPreview(input: {
  conversationType: DmConversation['conversation_type'];
  currentUserId?: string | null;
  senderId: string;
  senderPrefix: DmConversationPreviewSenderPrefix;
}): boolean {
  if (input.senderPrefix === 'never') {
    return false;
  }
  if (input.senderPrefix === 'group') {
    return input.conversationType === 'group';
  }
  return input.senderId !== input.currentUserId;
}

function normalizeDmRealtimeData(
  data: Record<string, unknown>,
  normalized: {
    message?: DmMessage;
    conversation?: DmConversation;
  },
): NonNullable<DmRealtimeEvent['data']> | null {
  const thread =
    data.thread === undefined
      ? normalized.conversation
      : normalizeDmConversation(data.thread);
  const conversationId = optionalRealtimeDmResponseId(data.conversation_id);
  const threadId = optionalRealtimeDmResponseId(data.thread_id);
  const userId = optionalRealtimeDmResponseId(data.user_id);
  if (
    thread === null ||
    conversationId === null ||
    threadId === null ||
    userId === null
  ) {
    return null;
  }
  return {
    ...normalized,
    ...(thread ? { thread } : {}),
    ...(conversationId ? { conversation_id: conversationId } : {}),
    ...(threadId ? { thread_id: threadId } : {}),
    ...(userId ? { user_id: userId } : {}),
  };
}

function normalizeDmConversationParticipant(
  value: unknown,
): DmConversationParticipant | null {
  if (
    !isRecord(value) ||
    !isDmConversationParticipantRole(value.role) ||
    !isDateTimeString(value.joined_at)
  ) {
    return null;
  }
  const user = normalizeDmUser(value.user);
  const leftAt = optionalNullableDateTimeString(value.left_at);
  const mutedAt = optionalNullableDateTimeString(value.muted_at);
  const lastReadMessageId = optionalNullableDmResponseId(
    value.last_read_message_id,
  );
  if (
    !user ||
    leftAt === undefined ||
    mutedAt === undefined ||
    lastReadMessageId === undefined
  ) {
    return null;
  }
  return {
    user,
    role: value.role,
    joined_at: value.joined_at,
    left_at: leftAt,
    muted_at: mutedAt,
    last_read_message_id: lastReadMessageId,
  };
}

function normalizeArray<T>(
  value: unknown,
  normalize: (item: unknown) => T | null,
): T[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const items: T[] = [];
  for (const item of value) {
    const normalized = normalize(item);
    if (!normalized) {
      return null;
    }
    items.push(normalized);
  }
  return items;
}

function normalizeOptionalArray<T>(
  value: unknown,
  normalize: (item: unknown) => T | null,
): T[] | null {
  return value === undefined ? [] : normalizeArray(value, normalize);
}

function optionalNullableString(value: unknown): string | null | undefined {
  if (value == null) {
    return null;
  }
  return typeof value === 'string' ? value : undefined;
}

function optionalNullableDmResponseId(
  value: unknown,
): string | null | undefined {
  if (value == null) {
    return null;
  }
  return isDmResponseId(value) ? value : undefined;
}

function optionalNullableDmRequestId(
  value: unknown,
): string | null | undefined {
  if (value == null) {
    return null;
  }
  if (typeof value !== 'string') {
    return undefined;
  }
  const normalized = value.trim();
  return isDmRouteId(normalized) ? normalized : undefined;
}

function optionalDmRequestIdList(
  value: unknown,
  maxLength: number,
  allowEmpty: boolean,
): string[] | null {
  if (value == null) {
    return allowEmpty ? [] : null;
  }
  if (!Array.isArray(value) || value.length > maxLength) {
    return null;
  }
  const ids: string[] = [];
  for (const item of value) {
    const id = optionalNullableDmRequestId(item);
    if (!id) {
      return null;
    }
    ids.push(id);
  }
  return (allowEmpty || ids.length > 0) && new Set(ids).size === ids.length
    ? ids
    : null;
}

function optionalNullableDmTitle(value: unknown): string | null | undefined {
  if (value == null) {
    return null;
  }
  if (typeof value !== 'string') {
    return undefined;
  }
  const normalized = value.trim();
  return normalized.length <= DM_CONVERSATION_TITLE_MAX_LENGTH
    ? normalized || null
    : undefined;
}

function optionalNullableDateTimeString(
  value: unknown,
): string | null | undefined {
  if (value == null) {
    return null;
  }
  return isDateTimeString(value) ? value : undefined;
}

function isDmConversationType(
  value: unknown,
): value is DmConversation['conversation_type'] {
  return value === 'direct' || value === 'group';
}

function isDmConversationParticipantRole(
  value: unknown,
): value is DmConversationParticipant['role'] {
  return value === 'owner' || value === 'admin' || value === 'member';
}

function isDmRealtimeEventType(value: string): value is DmRealtimeEventType {
  return DM_REALTIME_EVENT_TYPE_SET.has(value);
}

function optionalRealtimeDmResponseId(
  value: unknown,
): string | undefined | null {
  if (value === undefined) {
    return undefined;
  }
  return isDmResponseId(value) ? value : null;
}

function isDmResponseId(value: unknown): value is string {
  return typeof value === 'string' && isDmRouteId(value);
}

function hasOnlyKeys(
  record: Record<string, unknown>,
  allowedKeys: readonly string[],
): boolean {
  const allowed = new Set(allowedKeys);
  return Object.keys(record).every((key) => allowed.has(key));
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isDateTimeString(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
