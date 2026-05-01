import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type WorkspaceNotification = ApiSchema<'NotificationItem'>;
export type WorkspaceNotificationsResponse = ApiSchema<'NotificationListResponse'>;
export type WorkspaceUnreadCountResponse = ApiSchema<'UnreadCountResponse'>;

export function listNotifications(
  token: string,
  page = 1,
  workspaceSlug?: string | null,
): Promise<WorkspaceNotificationsResponse> {
  return apiFetchJson<WorkspaceNotificationsResponse>(
    rewriteWorkspaceApiPath(`/api/v1/pms/notifications?page=${page}&page_size=20`, workspaceSlug),
    token,
  );
}

export function getUnreadNotificationCount(
  token: string,
  workspaceSlug?: string | null,
): Promise<WorkspaceUnreadCountResponse> {
  return apiFetchJson<WorkspaceUnreadCountResponse>(
    rewriteWorkspaceApiPath('/api/v1/pms/notifications/unread-count', workspaceSlug),
    token,
  );
}

export function markNotificationRead(
  token: string,
  notificationId: string,
  workspaceSlug?: string | null,
): Promise<WorkspaceNotification> {
  return apiFetchJson<WorkspaceNotification>(
    rewriteWorkspaceApiPath(`/api/v1/pms/notifications/${notificationId}/read`, workspaceSlug),
    token,
    { method: 'PATCH' },
  );
}

export function markAllNotificationsRead(
  token: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return apiFetchJson<void>(
    rewriteWorkspaceApiPath('/api/v1/pms/notifications/read-all', workspaceSlug),
    token,
    { method: 'PATCH' },
  );
}
