import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  listNotifications,
  type NotificationsResponse,
} from '@/src/platform/notifications/notifications-api';
import { NotificationPanel } from './NotificationPanel';

const state = vi.hoisted(() => ({
  token: 'session-one' as string | null,
  t: (key: string) => key,
  i18n: { language: 'en-US', resolvedLanguage: 'en-US' },
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: state.token, user: { time_zone: 'UTC' } }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: state.t, i18n: state.i18n }),
}));
vi.mock('@/src/platform/notifications/notifications-api', () => ({
  listNotifications: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}));

const response = {
  items: [
    {
      id: 'notice-1',
      type: 'comment',
      title: 'Private notification',
      body: 'Private message',
      source_type: 'community_post',
      source_id: 'post-1',
      origin_app_id: 'community',
      is_read: false,
      created_at: '2026-09-08T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
} as NotificationsResponse;
const close = vi.fn();
const view = (refreshKey: number) => (
  <MemoryRouter>
    <NotificationPanel onClose={close} refreshKey={refreshKey} />
  </MemoryRouter>
);

beforeEach(() => {
  vi.clearAllMocks();
  state.token = 'session-one';
});

describe('notification authority refresh', () => {
  it('clears old rows during reauthorization and ignores a delayed earlier response', async () => {
    vi.mocked(listNotifications).mockResolvedValueOnce(response);
    const { rerender } = render(view(0));
    await screen.findByText('Private notification');
    let releaseOld!: (value: NotificationsResponse) => void;
    vi.mocked(listNotifications).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseOld = resolve;
        }),
    );
    rerender(view(1));
    expect(screen.queryByText('Private notification')).toBeNull();
    vi.mocked(listNotifications).mockResolvedValueOnce({
      ...response,
      items: [],
      total: 0,
    });
    rerender(view(2));
    await screen.findByText('notifications.empty');
    await act(async () => {
      releaseOld(response);
    });
    expect(screen.queryByText('Private notification')).toBeNull();
  });

  it('discards pending previous-account data on sign-out and handles a denied list without restoring rows', async () => {
    let releaseOld!: (value: NotificationsResponse) => void;
    vi.mocked(listNotifications).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseOld = resolve;
        }),
    );
    const { rerender } = render(view(0));
    state.token = null;
    rerender(view(0));
    await act(async () => {
      releaseOld(response);
    });
    expect(screen.queryByText('Private notification')).toBeNull();
    state.token = 'new-session';
    vi.mocked(listNotifications).mockRejectedValueOnce(
      new Error('Access denied'),
    );
    rerender(view(0));
    await screen.findByText('notifications.empty');
    expect(screen.queryByText('Private notification')).toBeNull();
  });
});
