import { describe, expect, it } from 'vitest';

import type { WorkspaceNotification } from '@/src/platform/notifications/notifications-api';
import {
  INITIAL_NOTIFICATION_PANEL_STATE,
  countUnreadNotifications,
  notificationPanelReducer,
  resolveNotificationAction,
} from './notification-panel-model';

describe('notification panel model', () => {
  it('moves from loading to loaded and signed-out states', () => {
    const loaded = notificationPanelReducer(INITIAL_NOTIFICATION_PANEL_STATE, {
      type: 'loaded',
      notifications: [notification('n1')],
    });
    const loading = notificationPanelReducer(loaded, { type: 'loading' });
    const signedOut = notificationPanelReducer(loading, { type: 'signed-out' });

    expect(loaded).toMatchObject({
      loading: false,
      notifications: [{ id: 'n1' }],
    });
    expect(loading.loading).toBe(true);
    expect(signedOut).toEqual({ loading: false, notifications: [] });
  });

  it('marks individual and all notifications as read', () => {
    const state = {
      loading: false,
      notifications: [
        notification('n1', { is_read: false }),
        notification('n2', { is_read: false }),
      ],
    };
    const oneRead = notificationPanelReducer(state, {
      type: 'mark-read',
      notificationId: 'n1',
    });
    const allRead = notificationPanelReducer(oneRead, {
      type: 'mark-all-read',
    });

    expect(oneRead.notifications.map((item) => item.is_read)).toEqual([
      true,
      false,
    ]);
    expect(countUnreadNotifications(oneRead.notifications)).toBe(1);
    expect(allRead.notifications.map((item) => item.is_read)).toEqual([
      true,
      true,
    ]);
    expect(countUnreadNotifications(allRead.notifications)).toBe(0);
  });

  it('resolves click actions in dm, route, issue, then none order', () => {
    expect(
      resolveNotificationAction(
        notification('route', {
          action_url: '/apps/pms/workspaces/hq/assigned',
          source_id: 'issue-1',
        }),
      ),
    ).toEqual({ kind: 'route', to: '/apps/pms/workspaces/hq/assigned' });
    expect(
      resolveNotificationAction(
        notification('dm', {
          action_url: '/dm/conversations/conversation-1',
          source_id: 'issue-1',
        }),
      ),
    ).toEqual({ kind: 'dm', threadId: 'conversation-1' });
    expect(
      resolveNotificationAction(
        notification('dm-query', {
          action_url: '/dm?thread=conversation-2',
        }),
      ),
    ).toEqual({ kind: 'dm', threadId: 'conversation-2' });
    expect(
      resolveNotificationAction(
        notification('issue', {
          action_url: 'https://example.test/unsafe',
          source_id: 'issue-1',
          source_type: 'pms_task',
        }),
      ),
    ).toEqual({ kind: 'issue', taskId: 'issue-1' });
    expect(
      resolveNotificationAction(
        notification('none', {
          action_url: 'https://example.test/unsafe',
          source_id: null,
        }),
      ),
    ).toEqual({ kind: 'none' });
  });
});

function notification(
  id: string,
  overrides: Partial<WorkspaceNotification> = {},
): WorkspaceNotification {
  return {
    action_url: null,
    body: 'Body',
    created_at: '2026-05-20T00:00:00.000Z',
    id,
    is_read: false,
    source_id: null,
    source_type: 'system',
    origin_app_id: 'shell',
    origin_workspace_id: null,
    title: 'Title',
    type: 'issue_assigned',
    ...overrides,
  } as WorkspaceNotification;
}
