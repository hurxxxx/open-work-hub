import { describe, expect, it } from 'vitest';

import type { DmMessage, DmThread } from '../api/dm-api';
import {
  DM_MESSAGES_INITIAL_STATE,
  applyDmConversationRuntimeRealtimeEvent,
  appendDmThreadMessage,
  dmMessagesReducer,
  isDmSendActionDisabled,
  resolveDmSendDraftCommand,
  shouldSubmitDmComposerKey,
  shouldNavigateAfterDmThreadRemoved,
  upsertDmThreadList,
  visibleDmThreadReadConversationId,
} from './dm-conversation-runtime-model';

describe('dm conversation runtime model', () => {
  it('moves message state through loading, loaded, replace, and clear actions', () => {
    const loading = dmMessagesReducer(DM_MESSAGES_INITIAL_STATE, {
      type: 'loading',
      loading: true,
    });
    const loaded = dmMessagesReducer(loading, {
      type: 'loaded',
      items: [message({ id: 'm1' })],
    });
    const replaced = dmMessagesReducer(loaded, {
      type: 'replace',
      items: [message({ id: 'm2' })],
    });
    const cleared = dmMessagesReducer(replaced, { type: 'clear' });

    expect(loading).toEqual({ items: [], loading: true });
    expect(loaded).toMatchObject({ items: [{ id: 'm1' }], loading: false });
    expect(replaced).toMatchObject({ items: [{ id: 'm2' }], loading: false });
    expect(cleared).toMatchObject({ items: [], loading: false });
  });

  it('marks only an authenticated visible and focused selected thread as read', () => {
    expect(
      visibleDmThreadReadConversationId({
        authenticated: true,
        selectedThreadId: 'c1',
        visible: true,
        focused: true,
      }),
    ).toBe('c1');
    expect(
      visibleDmThreadReadConversationId({
        authenticated: true,
        selectedThreadId: 'c1',
        visible: false,
        focused: true,
      }),
    ).toBeNull();
    expect(
      visibleDmThreadReadConversationId({
        authenticated: false,
        selectedThreadId: 'c1',
        visible: true,
        focused: true,
      }),
    ).toBeNull();
  });

  it('upserts threads and appends messages with stable ordering and dedupe', () => {
    const oldThread = conversation({
      id: 'c1',
      title: 'Old',
      updated_at: '2026-05-20T00:00:00.000Z',
    });
    const secondThread = conversation({
      id: 'c2',
      title: 'Second',
      updated_at: '2026-05-21T00:00:00.000Z',
    });
    const updatedThread = conversation({
      id: 'c1',
      title: 'Updated',
      updated_at: '2026-05-22T00:00:00.000Z',
    });

    expect(
      upsertDmThreadList([oldThread, secondThread], updatedThread).map(
        (thread) => thread.title,
      ),
    ).toEqual(['Updated', 'Second']);
    expect(
      appendDmThreadMessage(
        [message({ id: 'm2', created_at: '2026-05-22T00:00:00.000Z' })],
        message({ id: 'm1', created_at: '2026-05-21T00:00:00.000Z' }),
      ).map((item) => item.id),
    ).toEqual(['m1', 'm2']);
    expect(
      appendDmThreadMessage([message({ id: 'm1' })], message({ id: 'm1' })),
    ).toHaveLength(1);
  });

  it('normalizes realtime events and applies read policy from visibility', () => {
    const conversationUpdate = conversation({ id: 'c1', unread_count: 1 });
    const incomingMessage = message({
      id: 'm2',
      conversation_id: 'c1',
      sender_id: 'u2',
    });
    const visibleResult = applyDmConversationRuntimeRealtimeEvent({
      event: {
        type: 'dm.message.created',
        data: { conversation: conversationUpdate, message: incomingMessage },
      },
      conversations: [conversation({ id: 'c1', unread_count: 0 })],
      currentUserId: 'u1',
      focused: true,
      messages: [message({ id: 'm1', conversation_id: 'c1' })],
      selectedConversationId: 'c1',
      visible: true,
    });
    const hiddenResult = applyDmConversationRuntimeRealtimeEvent({
      event: {
        type: 'dm.message.created',
        data: { conversation: conversationUpdate, message: incomingMessage },
      },
      conversations: [conversation({ id: 'c1', unread_count: 0 })],
      currentUserId: 'u1',
      focused: true,
      messages: [],
      selectedConversationId: 'c1',
      visible: false,
    });

    expect(visibleResult?.messages.map((item) => item.id)).toEqual([
      'm1',
      'm2',
    ]);
    expect(visibleResult?.markReadConversationId).toBe('c1');
    expect(hiddenResult?.markReadConversationId).toBeNull();
    expect(
      applyDmConversationRuntimeRealtimeEvent({
        event: {
          type: 'dm.conversation.removed',
          data: { conversation_id: 'c/1' },
        },
        conversations: [conversation({ id: 'c1' })],
        currentUserId: 'u1',
        focused: true,
        messages: [],
        selectedConversationId: 'c1',
        visible: true,
      }),
    ).toBeNull();
  });

  it('reports selected conversation removal from realtime events', () => {
    const result = applyDmConversationRuntimeRealtimeEvent({
      event: {
        type: 'dm.conversation.removed',
        data: { conversation_id: 'c1' },
      },
      conversations: [conversation({ id: 'c1' })],
      currentUserId: 'u1',
      focused: true,
      messages: [],
      selectedConversationId: 'c1',
      visible: true,
    });

    expect(result).toMatchObject({
      conversations: [],
      selectedConversationId: null,
      selectedConversationRemoved: true,
    });
  });

  it('resolves send commands from draft and attachment state', () => {
    expect(
      resolveDmSendDraftCommand({
        authenticated: true,
        draft: '  hello  ',
        readyAttachmentIds: ['a1'],
        replyToMessageId: 'm1',
        sending: false,
        threadId: 'c1',
        uploadingAttachmentCount: 0,
      }),
    ).toEqual({
      attachmentIds: ['a1'],
      body: 'hello',
      replyToMessageId: 'm1',
      threadId: 'c1',
    });
    expect(
      resolveDmSendDraftCommand({
        authenticated: true,
        draft: '',
        readyAttachmentIds: ['a1'],
        sending: false,
        threadId: 'c1',
        uploadingAttachmentCount: 0,
      }),
    ).toEqual({
      attachmentIds: ['a1'],
      body: '',
      replyToMessageId: null,
      threadId: 'c1',
    });
    expect(
      resolveDmSendDraftCommand({
        authenticated: true,
        draft: '   ',
        readyAttachmentIds: [],
        sending: false,
        threadId: 'c1',
        uploadingAttachmentCount: 0,
      }),
    ).toBeNull();
    expect(
      resolveDmSendDraftCommand({
        authenticated: true,
        draft: 'hello',
        readyAttachmentIds: [],
        sending: true,
        threadId: 'c1',
        uploadingAttachmentCount: 0,
      }),
    ).toBeNull();
    expect(
      resolveDmSendDraftCommand({
        authenticated: true,
        draft: 'hello',
        readyAttachmentIds: ['a1'],
        sending: false,
        threadId: 'c1',
        uploadingAttachmentCount: 1,
      }),
    ).toBeNull();
  });

  it('derives send button and removed-thread navigation state', () => {
    expect(
      isDmSendActionDisabled({
        draft: '',
        readyAttachmentIds: [],
        sending: false,
        uploadingAttachmentCount: 0,
      }),
    ).toBe(true);
    expect(
      isDmSendActionDisabled({
        draft: '',
        readyAttachmentIds: ['a1'],
        sending: false,
        uploadingAttachmentCount: 1,
      }),
    ).toBe(true);
    expect(
      isDmSendActionDisabled({
        draft: 'hello',
        readyAttachmentIds: [],
        sending: false,
        uploadingAttachmentCount: 0,
      }),
    ).toBe(false);
    expect(
      shouldNavigateAfterDmThreadRemoved({
        activeRouteThreadId: 'c1',
        selectedConversationRemoved: true,
      }),
    ).toBe(true);
    expect(shouldSubmitDmComposerKey({ key: 'Enter', shiftKey: false })).toBe(
      true,
    );
    expect(shouldSubmitDmComposerKey({ key: 'Enter', shiftKey: true })).toBe(
      false,
    );
    expect(shouldSubmitDmComposerKey({ key: 'Tab', shiftKey: false })).toBe(
      false,
    );
  });
});

function message(overrides: Partial<DmMessage> = {}): DmMessage {
  return {
    id: 'm1',
    conversation_id: 'c1',
    thread_id: 'c1',
    sequence: 1,
    sender_id: 'u1',
    sender_name: 'User One',
    read_state: {
      unread_count: 0,
      read_by_all: true,
    },
    reply_to: null,
    body: 'hello',
    attachments: [],
    created_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}

function conversation(overrides: Partial<DmThread> = {}): DmThread {
  return {
    id: 'c1',
    conversation_type: 'direct',
    thread_type: 'direct',
    title: null,
    display_name: 'User One',
    other_user: null,
    participants: [],
    participant_count: 2,
    last_message: null,
    unread_count: 0,
    last_read_message_id: null,
    muted_at: null,
    created_by_id: 'u1',
    created_at: '2026-05-20T00:00:00.000Z',
    updated_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}
