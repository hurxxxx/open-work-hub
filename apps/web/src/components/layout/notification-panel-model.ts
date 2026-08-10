import type { WorkspaceNotification } from '@/src/platform/notifications/notifications-api';

export type NotificationPanelState = {
  loading: boolean;
  notifications: WorkspaceNotification[];
};

export type NotificationPanelAction =
  | { type: 'loading' }
  | { type: 'loaded'; notifications: WorkspaceNotification[] }
  | { type: 'mark-read'; notificationId: string }
  | { type: 'mark-all-read' }
  | { type: 'signed-out' };

export type NotificationAction =
  | { kind: 'dm'; threadId: string | null }
  | { kind: 'route'; to: string }
  | { kind: 'issue'; taskId: string }
  | { kind: 'none' };

export const INITIAL_NOTIFICATION_PANEL_STATE: NotificationPanelState = {
  loading: true,
  notifications: [],
};

export function notificationPanelReducer(
  state: NotificationPanelState,
  action: NotificationPanelAction,
): NotificationPanelState {
  switch (action.type) {
    case 'loading':
      return {
        ...state,
        loading: true,
      };
    case 'loaded':
      return {
        loading: false,
        notifications: action.notifications,
      };
    case 'mark-read':
      return {
        ...state,
        notifications: state.notifications.map((item) =>
          item.id === action.notificationId ? { ...item, is_read: true } : item,
        ),
      };
    case 'mark-all-read':
      return {
        ...state,
        notifications: state.notifications.map((notification) => ({
          ...notification,
          is_read: true,
        })),
      };
    case 'signed-out':
      return {
        loading: false,
        notifications: [],
      };
  }
}

export function countUnreadNotifications(
  notifications: readonly WorkspaceNotification[],
): number {
  return notifications.filter((notification) => !notification.is_read).length;
}

export function resolveNotificationAction(
  notification: WorkspaceNotification,
): NotificationAction {
  const dmThreadId = resolveDmNotificationThreadId(notification.action_url);
  if (dmThreadId !== undefined) {
    return { kind: 'dm', threadId: dmThreadId };
  }
  if (notification.action_url?.startsWith('/')) {
    return { kind: 'route', to: notification.action_url };
  }
  if (notification.reference_id) {
    return { kind: 'issue', taskId: notification.reference_id };
  }
  return { kind: 'none' };
}

export function resolveDmNotificationThreadId(
  actionUrl: string | null | undefined,
): string | null | undefined {
  if (!actionUrl?.startsWith('/')) {
    return undefined;
  }
  const parsed = new URL(actionUrl, 'https://ai-do.local');
  if (parsed.pathname === '/dm') {
    return parsed.searchParams.get('thread');
  }
  const globalMatch = parsed.pathname.match(
    /^\/dm\/(?:conversations\/)?([^/]+)\/?$/,
  );
  if (globalMatch?.[1]) {
    return decodeURIComponent(globalMatch[1]);
  }
  if (/^\/w\/[^/]+\/dm\/?$/.test(parsed.pathname)) {
    return parsed.searchParams.get('thread');
  }
  return undefined;
}
