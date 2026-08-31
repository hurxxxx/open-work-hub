import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type WorkspaceNotification = ApiSchema<'GlobalNotificationItem'>;
export type WorkspaceNotificationsResponse =
  ApiSchema<'GlobalNotificationListResponse'>;
export type WorkspaceUnreadCountResponse =
  ApiSchema<'GlobalUnreadCountResponse'>;

export function listNotifications(
  token: string,
  page = 1,
  workspaceSlug?: string | null,
): Promise<WorkspaceNotificationsResponse> {
  void workspaceSlug;
  return apiFetchJson<WorkspaceNotificationsResponse>(
    `/api/v1/notifications?page=${page}&page_size=20`,
    token,
  );
}

export function getUnreadNotificationCount(
  token: string,
  workspaceSlug?: string | null,
): Promise<WorkspaceUnreadCountResponse> {
  void workspaceSlug;
  return apiFetchJson<WorkspaceUnreadCountResponse>(
    '/api/v1/notifications/unread-count',
    token,
  );
}

export function markNotificationRead(
  token: string,
  notificationId: string,
  workspaceSlug?: string | null,
): Promise<WorkspaceNotification> {
  void workspaceSlug;
  return apiFetchJson<WorkspaceNotification>(
    `/api/v1/notifications/${notificationId}/read`,
    token,
    { method: 'PATCH' },
  );
}

export function markAllNotificationsRead(
  token: string,
  workspaceSlug?: string | null,
): Promise<void> {
  void workspaceSlug;
  return apiFetchJson<void>('/api/v1/notifications/read-all', token, {
    method: 'PATCH',
  });
}
