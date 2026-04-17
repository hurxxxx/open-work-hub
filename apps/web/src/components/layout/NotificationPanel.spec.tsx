import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { NotificationPanel } from './NotificationPanel';

const mockListNotifications = vi.fn();
const mockMarkNotificationRead = vi.fn();
const mockMarkAllNotificationsRead = vi.fn();

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/domains/pms/pms-api', () => ({
  listNotifications: (...args: unknown[]) => mockListNotifications(...args),
  markNotificationRead: (...args: unknown[]) => mockMarkNotificationRead(...args),
  markAllNotificationsRead: (...args: unknown[]) => mockMarkAllNotificationsRead(...args),
}));

describe('NotificationPanel', () => {
  beforeEach(() => {
    mockListNotifications.mockResolvedValue({
      items: [
        {
          id: 'notif-1',
          type: 'issue_assigned',
          title: 'Assigned',
          body: 'You were assigned',
          reference_type: 'issue',
          reference_id: 'issue-123',
          is_read: false,
          created_at: '2026-04-17T00:00:00Z',
        },
      ],
    });
    mockMarkNotificationRead.mockResolvedValue(undefined);
    mockMarkAllNotificationsRead.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('uses the explicit workspace slug for notification fetch and read actions', async () => {
    render(
      <NotificationPanel
        onClose={vi.fn()}
        onCountChange={vi.fn()}
        workspaceSlug="hq"
      />,
    );

    await waitFor(() => {
      expect(mockListNotifications).toHaveBeenCalledWith('test-token', 1, 'hq');
    });

    fireEvent.click(screen.getByTitle('Mark as read'));

    await waitFor(() => {
      expect(mockMarkNotificationRead).toHaveBeenCalledWith('test-token', 'notif-1', 'hq');
    });

    fireEvent.click(screen.getByTitle('Mark all as read'));

    await waitFor(() => {
      expect(mockMarkAllNotificationsRead).toHaveBeenCalledWith('test-token', 'hq');
    });
  });

  it('does not request notifications when no shell workspace is available', async () => {
    render(
      <NotificationPanel
        onClose={vi.fn()}
        workspaceSlug={null}
      />,
    );

    await waitFor(() => {
      expect(mockListNotifications).not.toHaveBeenCalled();
    });
    expect(screen.getByText('No notifications')).toBeTruthy();
  });
});
