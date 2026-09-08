import { describe, expect, it } from 'vitest';

import {
  appendDmMessage,
  applyDmRealtimeEvent,
  buildDmConversationListItemProjection,
  canMarkDmConversationRead,
  DM_MAX_ATTACHMENT_BYTES,
  DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH,
  DM_MESSAGE_BODY_MAX_LENGTH,
  DM_PARTICIPANT_IDS_MAX_LENGTH,
  DM_REALTIME_EVENT_TYPES,
  DM_REALTIME_EVENT_TYPE_VALUES,
  DM_ROUTE_ID_MAX_LENGTH,
  dmConversationDisplayName,
  dmConversationPreviewText,
  dmInitials,
  dmMessagePreviewText,
  dmRoutes,
  dmUnreadBadge,
  dmUserDisplayName,
  isDmAttachmentUploadFileAllowed,
  isDmComposerSendDisabled,
  isDmImageMimeType,
  isDmRouteId,
  normalizeDmAddParticipantsRequest,
  normalizeDmAttachmentUrlResponse,
  normalizeDmCreateConversationRequest,
  normalizeDmConversationListResponse,
  normalizeDmLimit,
  normalizeDmMessageListResponse,
  normalizeDmRealtimeEvent,
  normalizeDmSendMessageRequest,
  normalizeDmUpdateConversationRequest,
  normalizeDmUserListResponse,
  readyDmPendingAttachmentIds,
  normalizeDmMessageAttachment,
  resolveDmComposerSendCommand,
  shouldSubmitDmComposerKey,
  totalDmUnreadCount,
  uploadingDmPendingAttachmentCount,
  upsertDmConversation,
  type DmConversation,
  type DmMessage,
  type DmMessageAttachment,
  type DmUser,
} from './dm';

describe('DM realtime event type contract', () => {
  it('exports the API event names in subscription order', () => {
    expect(DM_REALTIME_EVENT_TYPES).toEqual({
      messageCreated: 'dm.message.created',
      conversationCreated: 'dm.conversation.created',
      conversationUpdated: 'dm.conversation.updated',
      conversationRead: 'dm.conversation.read',
      conversationRemoved: 'dm.conversation.removed',
    });
    expect(DM_REALTIME_EVENT_TYPE_VALUES).toEqual([
      'dm.message.created',
      'dm.conversation.created',
      'dm.conversation.updated',
      'dm.conversation.read',
      'dm.conversation.removed',
    ]);
  });
});

describe('dmRoutes', () => {
  it('builds encoded conversation paths from one shared contract', () => {
    expect(dmRoutes.conversation('conversation-1')).toBe(
      '/api/v1/dm/conversations/conversation-1',
    );
    expect(dmRoutes.conversationParticipants('c1')).toBe(
      '/api/v1/dm/conversations/c1/participants',
    );
    expect(dmRoutes.conversationParticipant('c1', 'u2')).toBe(
      '/api/v1/dm/conversations/c1/participants/u2',
    );
    expect(dmRoutes.leaveConversation('c1')).toBe(
      '/api/v1/dm/conversations/c1/participants/me',
    );
    expect(dmRoutes.markRead('c1')).toBe('/api/v1/dm/conversations/c1/read');
  });

  it('builds message and attachment paths', () => {
    expect(dmRoutes.messages('c1')).toBe(
      '/api/v1/dm/conversations/c1/messages',
    );
    expect(dmRoutes.listMessages('c1', { limit: 80 })).toBe(
      '/api/v1/dm/conversations/c1/messages?limit=80',
    );
    expect(
      dmRoutes.listMessages('c1', { before: '2026-05-20T01:02:03.000Z' }),
    ).toBe(
      '/api/v1/dm/conversations/c1/messages?limit=50&before=2026-05-20T01%3A02%3A03.000Z',
    );
    expect(dmRoutes.messageAttachments('c1')).toBe(
      '/api/v1/dm/conversations/c1/attachments',
    );
    expect(dmRoutes.attachmentDownload('attachment-1')).toBe(
      '/api/v1/dm/attachments/attachment-1/download',
    );
    expect(dmRoutes.attachmentPreview('attachment-1')).toBe(
      '/api/v1/dm/attachments/attachment-1/preview',
    );
  });

  it('rejects route IDs that are not short URL path segments', () => {
    expect(isDmRouteId('c1')).toBe(true);
    expect(isDmRouteId('a'.repeat(DM_ROUTE_ID_MAX_LENGTH))).toBe(true);
    expect(isDmRouteId('')).toBe(false);
    expect(isDmRouteId('a'.repeat(DM_ROUTE_ID_MAX_LENGTH + 1))).toBe(false);
    expect(isDmRouteId('space id')).toBe(false);
    expect(isDmRouteId('c/1')).toBe(false);
    expect(isDmRouteId('c\\1')).toBe(false);
    expect(isDmRouteId('%2e')).toBe(false);
    expect(() => dmRoutes.conversation('space id/with/slash')).toThrow(
      'DM route id',
    );
    expect(() => dmRoutes.attachmentDownload('a/b')).toThrow('DM route id');
    expect(() =>
      dmRoutes.messages('x'.repeat(DM_ROUTE_ID_MAX_LENGTH + 1)),
    ).toThrow('DM route id');
  });

  it('keeps DM query limits inside the API contract range', () => {
    expect(normalizeDmLimit(1)).toBe(1);
    expect(normalizeDmLimit(100)).toBe(100);
    expect(() => normalizeDmLimit(0)).toThrow(RangeError);
    expect(() => normalizeDmLimit(101)).toThrow(RangeError);
    expect(() => normalizeDmLimit(1.5)).toThrow(RangeError);
  });

  it('exposes the DM attachment upload size contract', () => {
    expect(DM_MAX_ATTACHMENT_BYTES).toBe(50 * 1024 * 1024);
    expect(isDmAttachmentUploadFileAllowed({ size: 0 })).toBe(true);
    expect(
      isDmAttachmentUploadFileAllowed({ size: DM_MAX_ATTACHMENT_BYTES }),
    ).toBe(true);
    expect(
      isDmAttachmentUploadFileAllowed({ size: DM_MAX_ATTACHMENT_BYTES + 1 }),
    ).toBe(false);
    expect(isDmAttachmentUploadFileAllowed({ size: Number.NaN })).toBe(false);
  });

  it('exposes DM request size contracts', () => {
    expect(DM_MESSAGE_BODY_MAX_LENGTH).toBe(120000);
    expect(DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH).toBe(10);
    expect(DM_PARTICIPANT_IDS_MAX_LENGTH).toBe(50);
  });

  it('keeps session-bound URLs out of attachment metadata and realtime projections', () => {
    const normalized = normalizeDmMessageAttachment({
      ...attachment(),
      download_url: '/api/v1/content#grant=private-session',
      preview_url: '/api/v1/dm/attachments/a/content?signature=old',
    });
    expect(normalized).toEqual(attachment());
    expect(normalized).not.toHaveProperty('download_url');
    expect(normalized).not.toHaveProperty('preview_url');
  });

  it('builds user search query parameters consistently', () => {
    expect(dmRoutes.users({ q: '김 개발', limit: 20 })).toBe(
      '/api/v1/dm/users?q=%EA%B9%80+%EA%B0%9C%EB%B0%9C&limit=20',
    );
  });
});

describe('DM shared view model projections', () => {
  const labels = {
    directFallback: 'DM',
    groupFallback: 'Group DM',
    emptyThread: 'No messages yet.',
    attachmentFile: (filename: string) => filename,
    attachmentCount: (count: number) => `${count} attachments`,
  };

  it('projects stable user, conversation, initials, preview, and unread labels', () => {
    const group = conversation({
      conversation_type: 'group',
      thread_type: 'group',
      title: null,
      display_name: '',
      unread_count: 12,
      last_message: message({
        sender_id: 'u2',
        sender_name: 'Alice',
        body: '',
        attachments: [
          attachment({ id: 'a1', filename: 'brief.pdf' }),
          attachment({ id: 'a2', filename: 'screen.png' }),
        ],
      }),
      participants: [
        participant(user({ id: 'u1', display_name: 'Me' })),
        participant(user({ id: 'u2', display_name: 'Alice' })),
        participant(user({ id: 'u3', display_name: 'Bob' })),
        participant(user({ id: 'u4', display_name: 'Cara' })),
      ],
    });

    expect(dmUserDisplayName(user({ display_name: 'Alice' }))).toBe('Alice');
    expect(dmUserDisplayName(user({ display_name: null, full_name: '' }))).toBe(
      'user@example.test',
    );
    expect(
      dmConversationDisplayName(group, { currentUserId: 'u1', labels }),
    ).toBe('Alice, Bob, Cara');
    expect(
      dmConversationDisplayName(
        { ...group, display_name: 'Server Group Name' },
        { currentUserId: 'u1', labels },
      ),
    ).toBe('Server Group Name');
    expect(
      dmConversationDisplayName(
        { ...group, display_name: 'Server Group Name' },
        {
          currentUserId: 'u1',
          groupDisplayName: 'participants',
          labels,
        },
      ),
    ).toBe('Alice, Bob, Cara');
    expect(dmInitials('jane.doe')).toBe('JD');
    expect(dmMessagePreviewText(message({ body: '' }), labels)).toBe(
      'No messages yet.',
    );
    expect(
      dmConversationPreviewText(group, { currentUserId: 'u1', labels }),
    ).toBe('Alice: 2 attachments');
    expect(dmUnreadBadge(0)).toBeNull();
    expect(dmUnreadBadge(10)).toBe('9+');
    expect(totalDmUnreadCount([conversation({ unread_count: 2 }), group])).toBe(
      14,
    );

    expect(
      buildDmConversationListItemProjection({
        conversation: group,
        currentUserId: 'u1',
        labels,
        selectedConversationId: 'c1',
      }),
    ).toMatchObject({
      id: 'c1',
      initials: 'AB',
      name: 'Alice, Bob, Cara',
      preview: 'Alice: 2 attachments',
      selected: true,
      unreadBadge: '9+',
      unreadCount: 12,
    });
  });

  it('supports direct-thread preview prefix policies for web and desktop callers', () => {
    const direct = conversation({
      other_user: user({ id: 'u2', display_name: 'Open Work Hub Bot' }),
      last_message: message({
        sender_id: 'u2',
        sender_name: 'Open Work Hub Bot',
        body: '내 커뮤니티 글에 댓글이 달렸습니다',
      }),
    });

    expect(
      dmConversationPreviewText(direct, {
        currentUserId: 'u1',
        labels,
        senderPrefix: 'group',
      }),
    ).toBe('내 커뮤니티 글에 댓글이 달렸습니다');
    expect(
      dmConversationPreviewText(direct, {
        currentUserId: 'u1',
        labels,
        senderPrefix: 'incoming',
      }),
    ).toBe('Open Work Hub Bot: 내 커뮤니티 글에 댓글이 달렸습니다');
  });

  it('projects composer and pending attachment state consistently', () => {
    expect(
      resolveDmComposerSendCommand({
        authenticated: true,
        conversationId: 'c1',
        sending: false,
        uploadingAttachmentCount: 0,
        draft: ' hello ',
        readyAttachmentIds: ['a1'],
      }),
    ).toEqual({
      attachmentIds: ['a1'],
      body: 'hello',
      conversationId: 'c1',
      replyToMessageId: null,
    });
    expect(
      resolveDmComposerSendCommand({
        authenticated: true,
        conversationId: 'c1',
        sending: false,
        uploadingAttachmentCount: 0,
        draft: 'reply',
        readyAttachmentIds: [],
        replyToMessageId: 'm1',
      }),
    ).toMatchObject({
      body: 'reply',
      replyToMessageId: 'm1',
    });
    expect(
      resolveDmComposerSendCommand({
        authenticated: true,
        conversationId: 'c1',
        sending: false,
        uploadingAttachmentCount: 1,
        draft: 'hello',
        readyAttachmentIds: [],
      }),
    ).toBeNull();
    expect(
      isDmComposerSendDisabled({
        draft: '',
        readyAttachmentIds: [],
        sending: false,
        uploadingAttachmentCount: 0,
      }),
    ).toBe(true);
    expect(shouldSubmitDmComposerKey({ key: 'Enter', shiftKey: false })).toBe(
      true,
    );
    expect(shouldSubmitDmComposerKey({ key: 'Enter', shiftKey: true })).toBe(
      false,
    );
    expect(
      readyDmPendingAttachmentIds([
        { status: 'uploading', attachment: null },
        { status: 'ready', attachment: { id: 'a1' } },
      ]),
    ).toEqual(['a1']);
    expect(
      uploadingDmPendingAttachmentCount([
        { status: 'uploading' },
        { status: 'ready' },
      ]),
    ).toBe(1);
    expect(isDmImageMimeType({ type: 'image/png; charset=utf-8' })).toBe(true);
    expect(isDmImageMimeType({ type: 'application/pdf' })).toBe(false);
  });
});

describe('DM request normalizers', () => {
  it('normalizes create conversation requests with route-safe participant IDs', () => {
    expect(
      normalizeDmCreateConversationRequest({
        recipient_user_id: ' u1 ',
      }),
    ).toEqual({ recipient_user_id: 'u1' });
    expect(
      normalizeDmCreateConversationRequest({
        participant_user_ids: [' u1 ', 'u2'],
        title: '  Team  ',
      }),
    ).toEqual({
      participant_user_ids: ['u1', 'u2'],
      title: 'Team',
    });
    expect(
      normalizeDmCreateConversationRequest({
        participant_user_ids: ['u1'],
        title: '   ',
      }),
    ).toEqual({ participant_user_ids: ['u1'] });
    expect(
      normalizeDmCreateConversationRequest({
        recipient_user_id: 'u1',
        participant_user_ids: ['u2'],
      }),
    ).toBeNull();
    expect(normalizeDmCreateConversationRequest({ title: 'Team' })).toBeNull();
    expect(
      normalizeDmCreateConversationRequest({ recipient_user_id: 'u/1' }),
    ).toBeNull();
    expect(
      normalizeDmCreateConversationRequest({
        participant_user_ids: ['u1', 'u1'],
      }),
    ).toBeNull();
    expect(
      normalizeDmCreateConversationRequest({
        recipient_user_id: 'u1',
        debug: true,
      }),
    ).toBeNull();
  });

  it('normalizes conversation update and participant requests', () => {
    expect(normalizeDmUpdateConversationRequest({ title: '  Team  ' })).toEqual(
      {
        title: 'Team',
      },
    );
    expect(normalizeDmUpdateConversationRequest({ title: '   ' })).toEqual({
      title: null,
    });
    expect(
      normalizeDmUpdateConversationRequest({
        title: 'x'.repeat(141),
      }),
    ).toBeNull();
    expect(
      normalizeDmAddParticipantsRequest({ user_ids: [' u1 ', 'u2'] }),
    ).toEqual({ user_ids: ['u1', 'u2'] });
    expect(normalizeDmAddParticipantsRequest({ user_ids: [] })).toBeNull();
    expect(
      normalizeDmAddParticipantsRequest({
        user_ids: Array.from(
          { length: DM_PARTICIPANT_IDS_MAX_LENGTH + 1 },
          (_, index) => `u${index}`,
        ),
      }),
    ).toBeNull();
  });

  it('normalizes send message requests with body and attachment invariants', () => {
    expect(
      normalizeDmSendMessageRequest({
        body: '  hello  ',
        attachment_ids: [' a1 '],
        reply_to_message_id: ' m1 ',
      }),
    ).toEqual({
      body: 'hello',
      attachment_ids: ['a1'],
      reply_to_message_id: 'm1',
    });
    expect(
      normalizeDmSendMessageRequest({
        body: '   ',
        attachment_ids: ['a1'],
      }),
    ).toEqual({ body: '', attachment_ids: ['a1'] });
    expect(normalizeDmSendMessageRequest({ body: 'hello' })).toEqual({
      body: 'hello',
      attachment_ids: [],
    });
    expect(
      normalizeDmSendMessageRequest({
        body: 'x'.repeat(DM_MESSAGE_BODY_MAX_LENGTH),
      })?.body.length,
    ).toBe(DM_MESSAGE_BODY_MAX_LENGTH);
    expect(
      normalizeDmSendMessageRequest({ body: '   ', attachment_ids: [] }),
    ).toBeNull();
    expect(
      normalizeDmSendMessageRequest({
        body: 'x'.repeat(DM_MESSAGE_BODY_MAX_LENGTH + 1),
      }),
    ).toBeNull();
    expect(
      normalizeDmSendMessageRequest({
        body: 'hello',
        attachment_ids: ['a1', 'a1'],
      }),
    ).toBeNull();
    expect(
      normalizeDmSendMessageRequest({
        body: 'hello',
        attachment_ids: ['a/1'],
      }),
    ).toBeNull();
    expect(
      normalizeDmSendMessageRequest({
        body: 'hello',
        attachment_ids: Array.from(
          { length: DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH + 1 },
          (_, index) => `a${index}`,
        ),
      }),
    ).toBeNull();
    expect(
      normalizeDmSendMessageRequest({
        body: 'hello',
        reply_to_message_id: 'm/1',
      }),
    ).toBeNull();
  });
});

describe('DM response normalizers', () => {
  it('normalizes API response shapes used by web and desktop DM clients', () => {
    expect(
      normalizeDmUserListResponse([user({ display_name: undefined })]),
    ).toEqual([
      {
        id: 'u1',
        email: 'user@example.test',
        full_name: 'User One',
        display_name: null,
      },
    ]);
    expect(
      normalizeDmAttachmentUrlResponse({
        url: '/api/v1/dm/attachments/a1/download',
      }),
    ).toEqual({
      url: '/api/v1/dm/attachments/a1/download',
    });
    expect(normalizeDmMessageListResponse({ items: [message()] })).toEqual({
      items: [
        {
          ...message(),
          attachments: [],
        },
      ],
    });
    expect(
      normalizeDmConversationListResponse({ items: [conversation()] }),
    ).toEqual({
      items: [
        {
          ...conversation(),
          title: null,
          other_user: null,
          last_message: null,
          last_read_message_id: null,
          muted_at: null,
        },
      ],
    });
  });

  it('rejects malformed nested API response shapes before clients render them', () => {
    expect(
      normalizeDmUserListResponse([{ id: 'u1', email: 'user@example.test' }]),
    ).toBeNull();
    expect(normalizeDmAttachmentUrlResponse({ url: '' })).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [
          message({
            attachments: [{ id: 'attachment-1' }] as DmMessage['attachments'],
          }),
        ],
      }),
    ).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [
          message({
            read_state: { unread_count: -1, read_by_all: false },
          } as DmMessage),
        ],
      }),
    ).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [message({ reply_to: { id: 'm1' } as DmMessage['reply_to'] })],
      }),
    ).toBeNull();
    expect(
      normalizeDmConversationListResponse({
        items: [conversation({ updated_at: 'not-a-date' })],
      }),
    ).toBeNull();
    expect(
      normalizeDmConversationListResponse({
        items: [
          conversation({
            other_user: { id: 'u2' } as DmConversation['other_user'],
          }),
        ],
      }),
    ).toBeNull();
  });

  it('rejects response IDs that cannot be reused as DM route segments', () => {
    expect(normalizeDmUserListResponse([user({ id: 'u/1' })])).toBeNull();
    expect(
      normalizeDmMessageListResponse({ items: [message({ id: 'm/1' })] }),
    ).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [message({ conversation_id: 'c/1' })],
      }),
    ).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [message({ sender_id: 'u/1' })],
      }),
    ).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [message({ attachments: [attachment({ id: 'a/1' })] })],
      }),
    ).toBeNull();
    expect(
      normalizeDmMessageListResponse({
        items: [message({ attachments: [attachment({ message_id: 'm/1' })] })],
      }),
    ).toBeNull();
    expect(
      normalizeDmConversationListResponse({
        items: [conversation({ id: 'c/1' })],
      }),
    ).toBeNull();
    expect(
      normalizeDmConversationListResponse({
        items: [conversation({ created_by_id: 'u/1' })],
      }),
    ).toBeNull();
    expect(
      normalizeDmConversationListResponse({
        items: [conversation({ last_read_message_id: 'm/1' })],
      }),
    ).toBeNull();
    expect(
      normalizeDmConversationListResponse({
        items: [
          conversation({
            participants: [
              {
                user: user({ id: 'u/1' }),
                role: 'member',
                joined_at: '2026-05-20T00:00:00.000Z',
              },
            ],
          }),
        ],
      }),
    ).toBeNull();
  });
});

describe('DM realtime event normalizers', () => {
  it('normalizes nested realtime event payloads before state reducers consume them', () => {
    const nextConversation = conversation({ id: 'c2' });
    const nextMessage = message({
      id: 'm2',
      conversation_id: 'c2',
      thread_id: 'c2',
    });
    const normalizedConversation = {
      ...nextConversation,
      title: null,
      other_user: null,
      last_message: null,
      last_read_message_id: null,
      muted_at: null,
    };

    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.message.created',
        data: {
          conversation: nextConversation,
          thread: nextConversation,
          message: nextMessage,
          conversation_id: 'c2',
          thread_id: 'c2',
          user_id: 'u2',
        },
      }),
    ).toEqual({
      type: 'dm.message.created',
      data: {
        conversation: normalizedConversation,
        thread: normalizedConversation,
        message: {
          ...nextMessage,
          attachments: [],
        },
        conversation_id: 'c2',
        thread_id: 'c2',
        user_id: 'u2',
      },
    });

    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.conversation.removed',
        data: { thread_id: 'c2' },
      }),
    ).toEqual({
      type: 'dm.conversation.removed',
      data: { thread_id: 'c2' },
    });
    expect(
      normalizeDmRealtimeEvent({
        type: 'notification.created',
        data: { ignored: true },
      }),
    ).toEqual({
      type: 'notification.created',
    });
  });

  it('rejects malformed realtime event payloads for known DM event types', () => {
    expect(normalizeDmRealtimeEvent({ data: {} })).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.message.created',
        data: { conversation: conversation(), message: { id: 'm1' } },
      }),
    ).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.conversation.updated',
        data: { conversation: { id: 'c1' } },
      }),
    ).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.conversation.removed',
        data: {},
      }),
    ).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.conversation.removed',
        data: { conversation_id: 123, thread_id: 'c1' },
      }),
    ).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.conversation.removed',
        data: { conversation_id: 'c/1' },
      }),
    ).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.message.created',
        data: {
          conversation: conversation(),
          message: message(),
          user_id: 'u/1',
        },
      }),
    ).toBeNull();
    expect(
      normalizeDmRealtimeEvent({
        type: 'dm.message.created',
        data: {
          conversation: conversation(),
          thread: { id: 'c1' },
          message: message(),
        },
      }),
    ).toBeNull();
  });
});

describe('DM realtime state helpers', () => {
  it('upserts conversations by updated_at descending', () => {
    const oldConversation = conversation({
      id: 'c1',
      updated_at: '2026-05-20T00:00:00.000Z',
    });
    const newerConversation = conversation({
      id: 'c2',
      updated_at: '2026-05-20T01:00:00.000Z',
    });
    const updatedConversation = conversation({
      id: 'c1',
      updated_at: '2026-05-20T02:00:00.000Z',
      unread_count: 0,
    });

    expect(
      upsertDmConversation(
        [oldConversation, newerConversation],
        updatedConversation,
      ),
    ).toEqual([updatedConversation, newerConversation]);
  });

  it('appends messages once and keeps chronological order', () => {
    const first = message({ id: 'm1', created_at: '2026-05-20T00:00:00.000Z' });
    const second = message({
      id: 'm2',
      created_at: '2026-05-20T01:00:00.000Z',
    });

    expect(appendDmMessage([second], first)).toEqual([first, second]);
    expect(appendDmMessage([first, second], second)).toEqual([first, second]);
  });

  it('marks a selected incoming message read only when the app can mark read', () => {
    const nextConversation = conversation({ id: 'c1', unread_count: 1 });
    const nextMessage = message({
      id: 'm2',
      conversation_id: 'c1',
      sender_id: 'u2',
    });

    const visibleResult = applyDmRealtimeEvent(
      {
        conversations: [conversation({ id: 'c1', unread_count: 0 })],
        messages: [message({ id: 'm1', conversation_id: 'c1' })],
        selectedConversationId: 'c1',
        currentUserId: 'u1',
        canMarkRead: true,
      },
      {
        type: 'dm.message.created',
        data: { conversation: nextConversation, message: nextMessage },
      },
    );

    expect(visibleResult.conversations[0]).toBe(nextConversation);
    expect(visibleResult.messages.map((item) => item.id)).toEqual(['m1', 'm2']);
    expect(visibleResult.markReadConversationId).toBe('c1');

    const hiddenResult = applyDmRealtimeEvent(
      {
        ...visibleResult,
        currentUserId: 'u1',
        canMarkRead: false,
      },
      {
        type: 'dm.message.created',
        data: {
          conversation: nextConversation,
          message: message({
            id: 'm3',
            conversation_id: 'c1',
            sender_id: 'u2',
          }),
        },
      },
    );

    expect(hiddenResult.markReadConversationId).toBeNull();
    expect(hiddenResult.messages.map((item) => item.id)).toEqual([
      'm1',
      'm2',
      'm3',
    ]);
  });

  it('does not request read marking for outgoing realtime echoes', () => {
    const result = applyDmRealtimeEvent(
      {
        conversations: [],
        messages: [message({ id: 'm1', conversation_id: 'c1' })],
        selectedConversationId: 'c1',
        currentUserId: 'u1',
        canMarkRead: true,
      },
      {
        type: 'dm.message.created',
        data: {
          conversation: conversation({ id: 'c1' }),
          message: message({
            id: 'm1',
            conversation_id: 'c1',
            sender_id: 'u1',
          }),
        },
      },
    );

    expect(result.markReadConversationId).toBeNull();
    expect(result.messages.map((item) => item.id)).toEqual(['m1']);
  });

  it('applies conversation read snapshots and removed selected conversations', () => {
    const readConversation = conversation({
      id: 'c1',
      unread_count: 0,
      updated_at: '2026-05-20T03:00:00.000Z',
    });
    const readResult = applyDmRealtimeEvent(
      {
        conversations: [conversation({ id: 'c1', unread_count: 3 })],
        messages: [],
        selectedConversationId: 'c1',
        currentUserId: 'u1',
        canMarkRead: true,
      },
      {
        type: 'dm.conversation.read',
        data: { conversation: readConversation },
      },
    );

    expect(readResult.conversations).toEqual([readConversation]);

    const removedResult = applyDmRealtimeEvent(readResult, {
      type: 'dm.conversation.removed',
      data: { conversation_id: 'c1' },
    });

    expect(removedResult.conversations).toEqual([]);
    expect(removedResult.selectedConversationId).toBeNull();
    expect(removedResult.selectedConversationRemoved).toBe(true);
    expect(removedResult.removedConversationId).toBe('c1');
  });

  it('uses explicit visibility and focus inputs for read decisions', () => {
    expect(canMarkDmConversationRead({ visible: true, focused: true })).toBe(
      true,
    );
    expect(canMarkDmConversationRead({ visible: true, focused: false })).toBe(
      false,
    );
    expect(canMarkDmConversationRead({ visible: false, focused: true })).toBe(
      false,
    );
  });
});

function conversation(overrides: Partial<DmConversation> = {}): DmConversation {
  return {
    id: 'c1',
    conversation_type: 'direct',
    thread_type: 'direct',
    display_name: 'Direct',
    participants: [],
    participant_count: 2,
    unread_count: 0,
    created_by_id: 'u1',
    created_at: '2026-05-20T00:00:00.000Z',
    updated_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}

function user(overrides: Partial<DmUser> = {}): DmUser {
  return {
    id: 'u1',
    email: 'user@example.test',
    full_name: 'User One',
    display_name: null,
    ...overrides,
  };
}

function participant(
  userValue: DmUser,
): DmConversation['participants'][number] {
  return {
    user: userValue,
    role: 'member',
    joined_at: '2026-05-20T00:00:00.000Z',
    left_at: null,
    muted_at: null,
    last_read_message_id: null,
  };
}

function message(overrides: Partial<DmMessage> = {}): DmMessage {
  return {
    id: 'm1',
    conversation_id: 'c1',
    thread_id: 'c1',
    sequence: 1,
    sender_id: 'u1',
    sender_name: 'User',
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

function attachment(
  overrides: Partial<DmMessageAttachment> = {},
): DmMessageAttachment {
  return {
    id: 'a1',
    conversation_id: 'c1',
    message_id: null,
    filename: 'document.txt',
    content_type: 'text/plain',
    size_bytes: 12,
    is_image: false,
    created_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}
