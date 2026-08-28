import { describe, expect, it } from 'vitest';

import {
  NOTIFICATION_REALTIME_EVENT_TYPES,
  NOTIFICATION_REALTIME_EVENT_TYPE_VALUES,
  isNotificationRealtimeEventType,
  normalizeNotificationRealtimeEvent,
} from './notifications';

describe('notification realtime event type contract', () => {
  it('exports the shared notification event names', () => {
    expect(NOTIFICATION_REALTIME_EVENT_TYPES).toEqual({
      snapshot: 'notification.snapshot',
      created: 'notification.created',
      read: 'notification.read',
      readAll: 'notifications.read_all',
    });
    expect(NOTIFICATION_REALTIME_EVENT_TYPE_VALUES).toEqual([
      'notification.snapshot',
      'notification.created',
      'notification.read',
      'notifications.read_all',
    ]);
  });

  it('guards notification realtime event types', () => {
    for (const eventType of NOTIFICATION_REALTIME_EVENT_TYPE_VALUES) {
      expect(isNotificationRealtimeEventType(eventType)).toBe(true);
    }

    expect(isNotificationRealtimeEventType('notification.deleted')).toBe(false);
    expect(isNotificationRealtimeEventType('notification.read ')).toBe(false);
    expect(isNotificationRealtimeEventType('')).toBe(false);
    expect(isNotificationRealtimeEventType(null)).toBe(false);
  });

  it('normalizes notification realtime events', () => {
    expect(
      normalizeNotificationRealtimeEvent({
        type: NOTIFICATION_REALTIME_EVENT_TYPES.snapshot,
        data: {
          notification: null,
          unread_count: 3,
        },
      }),
    ).toEqual({
      type: 'notification.snapshot',
      data: {
        notification: null,
        unread_count: 3,
      },
    });

    expect(
      normalizeNotificationRealtimeEvent({
        type: NOTIFICATION_REALTIME_EVENT_TYPES.created,
        data: {
          notification: {
            id: 'notification-1',
            type: 'dm.message',
            title: 'New message',
            body: 'A teammate sent a message.',
            reference_type: 'dm_conversation',
            reference_id: 'conversation-1',
            action_url: '/apps/community/posts/post-1',
            is_read: false,
            created_at: '2026-05-31T00:00:00Z',
          },
          unread_count: 4,
        },
      }),
    ).toEqual({
      type: 'notification.created',
      data: {
        notification: {
          id: 'notification-1',
          type: 'dm.message',
          title: 'New message',
          body: 'A teammate sent a message.',
          reference_type: 'dm_conversation',
          reference_id: 'conversation-1',
          action_url: '/apps/community/posts/post-1',
          is_read: false,
          created_at: '2026-05-31T00:00:00Z',
        },
        unread_count: 4,
      },
    });
  });

  it('rejects malformed notification realtime events', () => {
    expect(normalizeNotificationRealtimeEvent(null)).toBeNull();
    expect(normalizeNotificationRealtimeEvent({ data: {} })).toBeNull();
    expect(
      normalizeNotificationRealtimeEvent({
        type: 'notification.deleted',
        data: { notification: null, unread_count: 1 },
      }),
    ).toBeNull();
    expect(
      normalizeNotificationRealtimeEvent({
        type: NOTIFICATION_REALTIME_EVENT_TYPES.read,
        data: { notification: null },
      }),
    ).toBeNull();
    expect(
      normalizeNotificationRealtimeEvent({
        type: NOTIFICATION_REALTIME_EVENT_TYPES.read,
        data: { notification: null, unread_count: -1 },
      }),
    ).toBeNull();
    expect(
      normalizeNotificationRealtimeEvent({
        type: NOTIFICATION_REALTIME_EVENT_TYPES.created,
        data: {
          notification: {
            id: 'notification-1',
            type: 'dm.message',
            title: 'New message',
            body: 'A teammate sent a message.',
            reference_type: 'dm_conversation',
            reference_id: 'conversation-1',
            is_read: 'false',
            created_at: '2026-05-31T00:00:00Z',
          },
          unread_count: 1,
        },
      }),
    ).toBeNull();
  });
});
