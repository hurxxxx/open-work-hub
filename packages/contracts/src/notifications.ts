import type { ApiSchema } from './api.js';

export const NOTIFICATION_REALTIME_EVENT_TYPES = {
  snapshot: 'notification.snapshot',
  created: 'notification.created',
  read: 'notification.read',
  readAll: 'notifications.read_all',
} as const;

export const NOTIFICATION_REALTIME_EVENT_TYPE_VALUES = [
  NOTIFICATION_REALTIME_EVENT_TYPES.snapshot,
  NOTIFICATION_REALTIME_EVENT_TYPES.created,
  NOTIFICATION_REALTIME_EVENT_TYPES.read,
  NOTIFICATION_REALTIME_EVENT_TYPES.readAll,
] as const;

export type NotificationRealtimeEventType =
  (typeof NOTIFICATION_REALTIME_EVENT_TYPE_VALUES)[number];

const NOTIFICATION_REALTIME_EVENT_TYPE_SET: ReadonlySet<string> = new Set(
  NOTIFICATION_REALTIME_EVENT_TYPE_VALUES,
);

export type NotificationRealtimeNotification =
  ApiSchema<'GlobalNotificationItem'>;

export interface NotificationRealtimeEventData {
  notification: NotificationRealtimeNotification | null;
  unread_count: number;
}

export interface NotificationRealtimeEvent {
  type: NotificationRealtimeEventType;
  data: NotificationRealtimeEventData;
}

export function isNotificationRealtimeEventType(
  value: unknown,
): value is NotificationRealtimeEventType {
  return (
    typeof value === 'string' && NOTIFICATION_REALTIME_EVENT_TYPE_SET.has(value)
  );
}

export function normalizeNotificationRealtimeEvent(
  value: unknown,
): NotificationRealtimeEvent | null {
  if (!isRecord(value) || !isNotificationRealtimeEventType(value.type)) {
    return null;
  }
  if (!isRecord(value.data)) {
    return null;
  }

  const unreadCount = value.data.unread_count;
  if (
    typeof unreadCount !== 'number' ||
    !Number.isInteger(unreadCount) ||
    unreadCount < 0
  ) {
    return null;
  }

  const notification = normalizeNotification(value.data.notification);
  if (notification === undefined) {
    return null;
  }

  return {
    type: value.type,
    data: {
      notification,
      unread_count: unreadCount,
    },
  };
}

function normalizeNotification(
  value: unknown,
): NotificationRealtimeNotification | null | undefined {
  if (value == null) {
    return null;
  }
  if (!isRecord(value)) {
    return undefined;
  }

  const actionUrl = value.action_url;
  if (
    typeof value.id !== 'string' ||
    typeof value.type !== 'string' ||
    typeof value.title !== 'string' ||
    typeof value.body !== 'string' ||
    typeof value.reference_type !== 'string' ||
    !isNullableString(value.reference_id) ||
    (actionUrl !== undefined &&
      actionUrl !== null &&
      typeof actionUrl !== 'string') ||
    typeof value.is_read !== 'boolean' ||
    typeof value.created_at !== 'string'
  ) {
    return undefined;
  }

  const notification: NotificationRealtimeNotification = {
    id: value.id,
    type: value.type,
    title: value.title,
    body: value.body,
    reference_type: value.reference_type,
    reference_id: value.reference_id,
    is_read: value.is_read,
    created_at: value.created_at,
  };
  if (actionUrl !== undefined) {
    notification.action_url = actionUrl;
  }
  return notification;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
