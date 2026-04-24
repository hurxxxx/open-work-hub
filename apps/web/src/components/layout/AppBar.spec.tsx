import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import type { AuthUser } from '@/src/domains/auth/auth-api';
import { resolveShellWorkspaceSlug } from '@/src/domains/workspaces/workspace-utils';
import type { WorkspaceBootstrapApp } from '@/src/domains/workspaces/workspaces-api';
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

function buildWorkspaceApps(): WorkspaceBootstrapApp[] {
  return [
    { app_id: 'home', title: 'HOME', route_base: '/home', icon_key: 'home', enabled: true, nav_items: [] },
    { app_id: 'ai', title: 'AI', route_base: '/ai', icon_key: 'brain', enabled: true, nav_items: [] },
    { app_id: 'pms', title: 'PMS', route_base: '/pms', icon_key: 'folder-kanban', enabled: true, nav_items: [] },
    { app_id: 'docs', title: 'DOCS', route_base: '/docs', icon_key: 'files', enabled: true, nav_items: [] },
    { app_id: 'planner', title: 'Planner', route_base: '/planner', icon_key: 'calendar', enabled: true, nav_items: [] },
    { app_id: 'meeting', title: 'MEETING', route_base: '/meeting', icon_key: 'users', enabled: true, nav_items: [] },
  ];
}

function renderAppBar({
  activeAppId = 'home',
  currentPathname = '/',
  currentUser = buildUser(),
  shellWorkspaceSlug = 'hq',
  workspaceApps = buildWorkspaceApps(),
}: {
  activeAppId?: string;
  currentPathname?: string;
  currentUser?: AuthUser;
  shellWorkspaceSlug?: string | null;
  workspaceApps?: WorkspaceBootstrapApp[];
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
          workspaceApps={workspaceApps}
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
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledWith('test-token', 'hq');
    });
  });

  it('polls notifications using the shell workspace slug instead of the current URL workspace slug', async () => {
    renderAppBar({
      activeAppId: 'pms',
      currentPathname: '/w/delivery-hub/pms',
      shellWorkspaceSlug: 'hq',
    });

    await waitFor(() => {
      expect(mockGetUnreadNotificationCount).toHaveBeenCalledWith('test-token', 'hq');
    });
  });

  it('skips unread notification polling when no shell workspace is available', async () => {
    renderAppBar({
      activeAppId: 'settings',
      currentPathname: '/admin/general',
      currentUser: buildUser({
        workspaces: [],
        system_roles: ['platform_admin'],
      }),
      shellWorkspaceSlug: null,
    });

    await waitFor(() => {
      expect(mockGetUnreadNotificationCount).not.toHaveBeenCalled();
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

  it('opens workspace-scoped integrated search from the global AppBar button', async () => {
    renderAppBar({
      activeAppId: 'docs',
      currentPathname: '/w/hq/docs',
      shellWorkspaceSlug: 'hq',
    });

    fireEvent.click(screen.getByRole('button', { name: '통합검색' }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/tool/search?workspace=hq');
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

  it('hides app icons that are not enabled by the workspace bootstrap', () => {
    const { container } = renderAppBar({
      currentPathname: '/',
      workspaceApps: buildWorkspaceApps().filter((item) => item.app_id !== 'docs'),
    });

    expect(container.querySelector('a[href="/w/hq/docs"]')).toBeFalsy();
    expect(container.querySelector('a[href="/w/hq/ai"]')).toBeTruthy();
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
