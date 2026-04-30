import { apiFetchJson } from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export interface WorkspaceNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  reference_type: string;
  reference_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface WorkspaceNotificationsResponse {
  items: WorkspaceNotification[];
  total: number;
  page: number;
  page_size: number;
}

export interface WorkspaceUnreadCountResponse {
  count: number;
}

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
