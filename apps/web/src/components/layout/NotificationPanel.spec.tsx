import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import { NotificationPanel } from './NotificationPanel';

const mockListNotifications = vi.fn();
const mockMarkNotificationRead = vi.fn();
const mockMarkAllNotificationsRead = vi.fn();

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/platform/notifications/notifications-api', () => ({
  listNotifications: (...args: unknown[]) => mockListNotifications(...args),
  markNotificationRead: (...args: unknown[]) => mockMarkNotificationRead(...args),
  markAllNotificationsRead: (...args: unknown[]) => mockMarkAllNotificationsRead(...args),
}));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname + location.search}</span>;
}

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
      <MemoryRouter>
        <NotificationPanel
          onClose={vi.fn()}
          onCountChange={vi.fn()}
          workspaceSlug="hq"
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockListNotifications).toHaveBeenCalledWith('test-token', 1, 'hq');
    });

    fireEvent.click(screen.getByTitle('읽음으로 표시'));

    await waitFor(() => {
      expect(mockMarkNotificationRead).toHaveBeenCalledWith('test-token', 'notif-1', 'hq');
    });

    fireEvent.click(screen.getByTitle('모두 읽음으로 표시'));

    await waitFor(() => {
      expect(mockMarkAllNotificationsRead).toHaveBeenCalledWith('test-token', 'hq');
    });
  });

  it('does not request notifications when no shell workspace is available', async () => {
    render(
      <MemoryRouter>
        <NotificationPanel
          onClose={vi.fn()}
          workspaceSlug={null}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockListNotifications).not.toHaveBeenCalled();
    });
    expect(screen.getByText('알림이 없습니다.')).toBeTruthy();
  });

  it('navigates to notification action URLs', async () => {
    mockListNotifications.mockResolvedValueOnce({
      items: [
        {
          id: 'notif-2',
          type: 'image_generation_succeeded',
          title: 'Image done',
          body: 'Your generated image is ready.',
          reference_type: 'image_generation',
          reference_id: 'gen-1',
          action_url: '/tool/image-wizard?workspace=hq&gen=gen-1&step=4',
          is_read: false,
          created_at: '2026-04-17T00:00:00Z',
        },
      ],
    });
    const onClose = vi.fn();

    render(
      <MemoryRouter initialEntries={['/w/hq/pms']}>
        <NotificationPanel
          onClose={onClose}
          workspaceSlug="hq"
        />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText('Image done'));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe(
        '/tool/image-wizard?workspace=hq&gen=gen-1&step=4',
      );
    });
    expect(mockMarkNotificationRead).toHaveBeenCalledWith('test-token', 'notif-2', 'hq');
    expect(onClose).toHaveBeenCalled();
  });
});
