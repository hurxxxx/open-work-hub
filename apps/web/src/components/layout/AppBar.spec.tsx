import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import type { AuthUser } from '@/src/domains/auth/auth-api';
import { AppBar } from './AppBar';

const mockGetUnreadNotificationCount = vi.fn();

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/domains/pms/pms-api', () => ({
  getUnreadNotificationCount: (...args: unknown[]) => mockGetUnreadNotificationCount(...args),
}));

vi.mock('./NotificationPanel', () => ({
  NotificationPanel: ({
    onNavigateToIssue,
  }: {
    onNavigateToIssue?: (issueId: string) => void;
  }) => (
    <button onClick={() => onNavigateToIssue?.('issue-123')} type="button">
      Open issue notification
    </button>
  ),
}));

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspace_roles: [],
    group_ids: [],
    group_slugs: [],
    permissions: [],
    visible_features: ['nav.ai', 'nav.docs', 'nav.pms', 'nav.planner'],
    must_change_password: false,
    is_admin: false,
    last_login_at: null,
    created_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

describe('AppBar', () => {
  beforeEach(() => {
    mockGetUnreadNotificationCount.mockResolvedValue({ count: 0 });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the settings app for users with admin section permissions and links to the first allowed section', async () => {
    const onOpenAccount = vi.fn();

    render(
      <MemoryRouter>
        <AppBar
          activeAppId="settings"
          currentUser={buildUser({
            permissions: ['group.read'],
            visible_features: [],
          })}
          onOpenAccount={onOpenAccount}
        />
      </MemoryRouter>,
    );

    const settingsLink = screen.getByText('Settings').closest('a');
    expect(settingsLink).toBeTruthy();
    expect(settingsLink?.getAttribute('href')).toBe('/admin/security');
    await waitFor(() => {
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledWith('test-token');
    });
  });

  it('routes notification clicks to the requested issue in PMS', async () => {
    render(
      <MemoryRouter initialEntries={['/ai']}>
        <AppBar
          activeAppId="ai"
          currentUser={buildUser()}
          onOpenAccount={vi.fn()}
        />
        <LocationDisplay />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '알림' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open issue notification' }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/pms?issue=issue-123');
    });
  });
});
