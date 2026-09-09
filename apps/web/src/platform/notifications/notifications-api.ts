import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type NotificationItem = ApiSchema<'GlobalNotificationItem'>;
export type NotificationsResponse = ApiSchema<'GlobalNotificationListResponse'>;
export type UnreadCountResponse = ApiSchema<'GlobalUnreadCountResponse'>;

export function listNotifications(
  token: string,
  page = 1,
): Promise<NotificationsResponse> {
  return apiFetchJson<NotificationsResponse>(
    `/api/v1/notifications?page=${page}&page_size=20`,
    token,
  );
}

export function getUnreadNotificationCount(
  token: string,
): Promise<UnreadCountResponse> {
  return apiFetchJson<UnreadCountResponse>(
    '/api/v1/notifications/unread-count',
    token,
  );
}

export function markNotificationRead(
  token: string,
  notificationId: string,
): Promise<NotificationItem> {
  return apiFetchJson<NotificationItem>(
    `/api/v1/notifications/${notificationId}/read`,
    token,
    { method: 'PATCH' },
  );
}

export function markAllNotificationsRead(token: string): Promise<void> {
  return apiFetchJson<void>('/api/v1/notifications/read-all', token, {
    method: 'PATCH',
  });
}
