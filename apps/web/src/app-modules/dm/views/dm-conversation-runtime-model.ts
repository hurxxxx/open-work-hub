import type { DmRealtimeStateResult } from '@open-work-hub/contracts/dm';
import {
  appendDmMessage,
  applyDmRealtimeEvent,
  canMarkDmConversationRead,
  isDmComposerSendDisabled,
  normalizeDmRealtimeEvent,
  resolveDmComposerSendCommand,
  shouldSubmitDmComposerKey as shouldSubmitContractDmComposerKey,
  upsertDmConversation,
} from '@open-work-hub/contracts/dm';

import type { DmMessage, DmThread } from '../api/dm-api';

export interface DmMessagesState {
  items: DmMessage[];
  loading: boolean;
}

export type DmMessagesAction =
  | { type: 'clear' }
  | { type: 'loading'; loading: boolean }
  | { type: 'loaded'; items: DmMessage[] }
  | { type: 'replace'; items: DmMessage[] };

export const DM_MESSAGES_INITIAL_STATE: DmMessagesState = {
  items: [],
  loading: false,
};

export function dmMessagesReducer(
  state: DmMessagesState,
  action: DmMessagesAction,
): DmMessagesState {
  if (action.type === 'clear') return { ...state, items: [] };
  if (action.type === 'loading') return { ...state, loading: action.loading };
  if (action.type === 'loaded') return { items: action.items, loading: false };
  return { ...state, items: action.items };
}

export interface DmReadPresenceInput {
  visible: boolean;
  focused: boolean;
}

export interface VisibleDmThreadReadInput extends DmReadPresenceInput {
  authenticated: boolean;
  selectedThreadId: string | null | undefined;
}

export function canMarkVisibleDmConversationRead(
  input: DmReadPresenceInput,
): boolean {
  return canMarkDmConversationRead(input);
}

export function visibleDmThreadReadConversationId(
  input: VisibleDmThreadReadInput,
): string | null {
  if (!input.authenticated || !input.selectedThreadId) {
    return null;
  }
  return canMarkVisibleDmConversationRead(input)
    ? input.selectedThreadId
    : null;
}

export function upsertDmThreadList(
  items: DmThread[],
  thread: DmThread,
): DmThread[] {
  return upsertDmConversation(items, thread);
}

export function appendDmThreadMessage(
  items: DmMessage[],
  message: DmMessage,
): DmMessage[] {
  return appendDmMessage(items, message);
}

export interface DmConversationRuntimeRealtimeInput
  extends DmReadPresenceInput {
  conversations: DmThread[];
  currentUserId?: string | null;
  event: unknown;
  messages: DmMessage[];
  selectedConversationId: string | null;
}

export function applyDmConversationRuntimeRealtimeEvent(
  input: DmConversationRuntimeRealtimeInput,
): DmRealtimeStateResult | null {
  const event = normalizeDmRealtimeEvent(input.event);
  if (!event) {
    return null;
  }
  return applyDmRealtimeEvent(
    {
      conversations: input.conversations,
      messages: input.messages,
      selectedConversationId: input.selectedConversationId,
      currentUserId: input.currentUserId,
      canMarkRead: canMarkVisibleDmConversationRead(input),
    },
    event,
  );
}

export interface DmSendDraftCommand {
  attachmentIds: string[];
  body: string;
  replyToMessageId: string | null;
  threadId: string;
}

export interface DmSendDraftInput {
  authenticated: boolean;
  draft: string;
  readyAttachmentIds: readonly string[];
  sending: boolean;
  threadId: string | null | undefined;
  uploadingAttachmentCount: number;
  replyToMessageId?: string | null;
}

export function resolveDmSendDraftCommand(
  input: DmSendDraftInput,
): DmSendDraftCommand | null {
  const command = resolveDmComposerSendCommand({
    authenticated: input.authenticated,
    conversationId: input.threadId,
    draft: input.draft,
    readyAttachmentIds: input.readyAttachmentIds,
    replyToMessageId: input.replyToMessageId,
    sending: input.sending,
    uploadingAttachmentCount: input.uploadingAttachmentCount,
  });
  if (!command) {
    return null;
  }
  return {
    attachmentIds: command.attachmentIds,
    body: command.body,
    replyToMessageId: command.replyToMessageId,
    threadId: command.conversationId,
  };
}

export function isDmSendActionDisabled(input: {
  draft: string;
  readyAttachmentIds: readonly string[];
  sending: boolean;
  uploadingAttachmentCount: number;
}): boolean {
  return isDmComposerSendDisabled(input);
}

export function shouldSubmitDmComposerKey(input: {
  key: string;
  shiftKey: boolean;
}): boolean {
  return shouldSubmitContractDmComposerKey(input);
}

export function shouldNavigateAfterDmThreadRemoved(input: {
  activeRouteThreadId: string | null | undefined;
  selectedConversationRemoved: boolean;
}): boolean {
  return Boolean(
    input.activeRouteThreadId && input.selectedConversationRemoved,
  );
}
