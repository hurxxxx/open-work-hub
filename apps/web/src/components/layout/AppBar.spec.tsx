import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import type { AuthUser } from '@/src/domains/auth/auth-api';
import { resolveShellWorkspaceSlug } from '@/src/domains/workspaces/workspace-utils';
import { AppBar } from './AppBar';

const mockGetUnreadNotificationCount = vi.fn();
const mockHasPermission = vi.fn();

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    hasPermission: (permission: string) => mockHasPermission(permission),
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
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Aidoo HQ',
        role: 'owner',
      },
      {
        id: 'workspace-delivery-hub',
        slug: 'delivery-hub',
        name: 'Delivery Hub',
        role: 'member',
      },
      {
        id: 'workspace-innovation-lab',
        slug: 'innovation-lab',
        name: 'Innovation Lab',
        role: 'member',
      },
    ],
    workspace_roles: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    last_login_at: null,
    created_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderAppBar({
  activeAppId = 'home',
  currentPathname = '/',
  currentUser = buildUser(),
  shellWorkspaceSlug = 'hq',
}: {
  activeAppId?: string;
  currentPathname?: string;
  currentUser?: AuthUser;
  shellWorkspaceSlug?: string | null;
} = {}) {
  function Harness() {
    const [selectedShellWorkspaceSlug, setSelectedShellWorkspaceSlug] = useState(shellWorkspaceSlug);

    return (
      <>
        <AppBar
          activeAppId={activeAppId}
          currentPathname={currentPathname}
          currentUser={currentUser}
          onOpenAccount={vi.fn()}
          onShellWorkspaceChange={setSelectedShellWorkspaceSlug}
          shellWorkspaceSlug={selectedShellWorkspaceSlug}
        />
        <LocationDisplay />
      </>
    );
  }

  return render(
    <MemoryRouter initialEntries={[currentPathname]}>
      <Harness />
    </MemoryRouter>,
  );
}

describe('AppBar', () => {
  beforeEach(() => {
    mockGetUnreadNotificationCount.mockResolvedValue({ count: 0 });
    mockHasPermission.mockReturnValue(false);
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('shows the settings app for users with admin section permissions and links to the first allowed section', async () => {
    const { container } = renderAppBar({
      activeAppId: 'settings',
      currentUser: buildUser({
        system_roles: ['platform_admin'],
      }),
    });

    const settingsLink = container.querySelector('a[href="/admin/general"]');
    expect(settingsLink).toBeTruthy();
    await waitFor(() => {
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledWith('test-token');
    });
  });

  it('routes notification clicks to the requested issue in PMS', async () => {
    renderAppBar({
      activeAppId: 'ai',
      currentPathname: '/w/hq/ai',
      shellWorkspaceSlug: 'hq',
    });

    fireEvent.click(screen.getByRole('button', { name: '알림' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open issue notification' }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/w/hq/pms?issue=issue-123');
    });
  });

  it('renders the switcher on global routes using the persisted shell workspace and filters app icons by that workspace', () => {
    window.localStorage.setItem('aidoo:last-workspace-slug', 'innovation-lab');
    const currentUser = buildUser();
    const shellWorkspaceSlug = resolveShellWorkspaceSlug(currentUser, null);
    const { container } = renderAppBar({
      currentPathname: '/',
      currentUser,
      shellWorkspaceSlug,
    });

    expect(shellWorkspaceSlug).toBe('innovation-lab');
    expect(container.querySelector('a[href="/w/innovation-lab/docs"]')).toBeTruthy();
    expect(container.querySelector('a[href="/w/innovation-lab/ai"]')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '워크스페이스 전환' }));
    expect(screen.getByText('Innovation Lab')).toBeTruthy();
  });

  it('updates the selected workspace on home even when the route stays on home', async () => {
    const { container } = renderAppBar({
      currentPathname: '/',
      shellWorkspaceSlug: 'hq',
    });

    fireEvent.click(screen.getByRole('button', { name: '워크스페이스 전환' }));
    fireEvent.click(screen.getByRole('button', { name: /Innovation Lab/ }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/');
      expect(container.querySelector('a[href="/w/innovation-lab/docs"]')).toBeTruthy();
      expect(container.querySelector('a[href="/w/innovation-lab/ai"]')).toBeTruthy();
    });
  });

  it('switches from a docs detail route to the same app root when the next workspace supports it', async () => {
    renderAppBar({
      activeAppId: 'docs',
      currentPathname: '/w/hq/docs/123',
      shellWorkspaceSlug: 'hq',
    });

    fireEvent.click(screen.getByRole('button', { name: '워크스페이스 전환' }));
    fireEvent.click(screen.getByRole('button', { name: /Delivery Hub/ }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/w/delivery-hub/docs');
    });
  });

  it('keeps the current app when switching workspaces from an app detail route', async () => {
    renderAppBar({
      activeAppId: 'docs',
      currentPathname: '/w/hq/docs/123',
      currentUser: buildUser({
        workspaces: [
          {
            id: 'workspace-hq',
            slug: 'hq',
            name: 'Aidoo HQ',
            role: 'owner',
          },
          {
            id: 'workspace-ai-only',
            slug: 'ai-only',
            name: 'AI Only',
            role: 'member',
          },
        ],
      }),
      shellWorkspaceSlug: 'hq',
    });

    fireEvent.click(screen.getByRole('button', { name: '워크스페이스 전환' }));
    fireEvent.click(screen.getByRole('button', { name: /AI Only/ }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/w/ai-only/docs');
    });
  });

  it('uses the remembered app when switching from an admin route', async () => {
    window.localStorage.setItem('aidoo:last-workspace-app', 'meeting');

    renderAppBar({
      activeAppId: 'settings',
      currentPathname: '/admin/people',
      currentUser: buildUser({
        system_roles: ['platform_admin'],
      }),
      shellWorkspaceSlug: 'hq',
    });

    fireEvent.click(screen.getByRole('button', { name: '워크스페이스 전환' }));
    fireEvent.click(screen.getByRole('button', { name: /Delivery Hub/ }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/w/delivery-hub/meeting');
    });
  });

  it('hides footer actions when the user lacks workspace creation permission and workspace admin role', () => {
    renderAppBar({
      currentPathname: '/',
      currentUser: buildUser({
        workspaces: [
          {
            id: 'workspace-innovation-lab',
            slug: 'innovation-lab',
            name: 'Innovation Lab',
            role: 'member',
          },
        ],
      }),
      shellWorkspaceSlug: 'innovation-lab',
    });

    fireEvent.click(screen.getByRole('button', { name: '워크스페이스 전환' }));

    expect(screen.queryByText('새 워크스페이스')).toBeNull();
    expect(screen.queryByText('워크스페이스 설정')).toBeNull();
  });
});
