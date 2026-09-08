import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AuthSessionResponse, AuthUser } from './auth-api';
import { AUTH_TOKEN_STORAGE_KEY } from './auth-storage';
import { AuthProvider, useAuth } from './auth-provider';

const apiMocks = vi.hoisted(() => ({
  getBootstrapStatus: vi.fn(),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  updatePreferences: vi.fn(),
}));

vi.mock('./auth-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./auth-api')>()),
  getBootstrapStatus: apiMocks.getBootstrapStatus,
  getCurrentUser: apiMocks.getCurrentUser,
  login: apiMocks.login,
  logout: apiMocks.logout,
  updatePreferences: apiMocks.updatePreferences,
}));

vi.mock('./desktop-session-sync', () => ({
  syncDesktopLoginSession: vi.fn().mockResolvedValue(undefined),
  syncDesktopLogoutSession: vi.fn(),
}));

vi.mock('@/src/platform/analytics/matomo', () => ({
  clearMatomoUser: vi.fn(),
  identifyMatomoUser: vi.fn(),
}));

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    app_bar_layout: { pinned_app_ids: [] },
    date_format: 'korean',
    display_name: 'Member',
    email: 'member@open-work-hub.local',
    full_name: 'Open Work Hub Member',
    id: 'user-1',
    last_login_at: null,
    locale: 'ko-KR',
    login_id: 'member',
    must_change_password: false,
    status: 'active',
    system_roles: [],
    group_ids: [],
    managed_organization_unit_ids: [],
    theme_preference: 'system',
    time_zone: 'Asia/Seoul',
    workspaces: [],
    workspace_roles: [],
    ...overrides,
  };
}

function session(): AuthSessionResponse {
  return { token: 'login-token', user: user() };
}

function AuthHarness() {
  const auth = useAuth();
  return (
    <div>
      <p>{auth.status}</p>
      <p data-testid="access-projection">
        {auth.user?.locale ?? 'none'}|
        {auth.user?.workspaces.map((workspace) => workspace.slug).join(',') ??
          'none'}
      </p>
      <button
        onClick={() =>
          void auth.login({ login_id: 'member', password: 'password123' })
        }
        type="button"
      >
        login
      </button>
      <button onClick={() => void auth.logout()} type="button">
        logout
      </button>
      <button onClick={() => void auth.refreshAccessUser()} type="button">
        refresh access
      </button>
      <button
        onClick={() => void auth.updatePreferences({ locale: 'en-US' })}
        type="button"
      >
        update preferences
      </button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  apiMocks.getBootstrapStatus.mockResolvedValue({
    dev_admin_login_available: false,
    dev_login_accounts: [],
    requires_setup: false,
  });
  apiMocks.login.mockResolvedValue(session());
  apiMocks.logout.mockReset();
  apiMocks.getCurrentUser.mockReset();
  apiMocks.updatePreferences.mockReset();
});

describe('AuthProvider logout', () => {
  it('removes authenticated content before the server revoke finishes or fails', async () => {
    let rejectLogout!: (reason: unknown) => void;
    apiMocks.logout.mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectLogout = reject;
        }),
    );

    render(
      <AuthProvider>
        <AuthHarness />
      </AuthProvider>,
    );
    await screen.findByText('unauthenticated');

    fireEvent.click(screen.getByRole('button', { name: 'login' }));
    await screen.findByText('authenticated');
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe(
      'login-token',
    );

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));
    expect(screen.getByText('unauthenticated')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
    expect(apiMocks.logout).toHaveBeenCalledWith('login-token');

    rejectLogout(new Error('server unavailable'));
    await waitFor(() =>
      expect(screen.getByText('unauthenticated')).toBeTruthy(),
    );
  });
});

describe('AuthProvider concurrent account updates', () => {
  it('does not let an older preference response restore stale workspace access', async () => {
    let resolvePreferences!: (value: AuthUser) => void;
    apiMocks.updatePreferences.mockImplementation(
      () =>
        new Promise<AuthUser>((resolve) => {
          resolvePreferences = resolve;
        }),
    );
    apiMocks.getCurrentUser.mockResolvedValue(
      user({
        workspaces: [
          {
            id: 'workspace-1',
            name: 'Workspace One',
            role: 'member',
            slug: 'workspace-one',
          },
        ],
      }),
    );

    render(
      <AuthProvider>
        <AuthHarness />
      </AuthProvider>,
    );
    await screen.findByText('unauthenticated');
    fireEvent.click(screen.getByRole('button', { name: 'login' }));
    await screen.findByText('authenticated');

    fireEvent.click(screen.getByRole('button', { name: 'update preferences' }));
    fireEvent.click(screen.getByRole('button', { name: 'refresh access' }));
    await waitFor(() =>
      expect(screen.getByTestId('access-projection').textContent).toBe(
        'ko-KR|workspace-one',
      ),
    );

    resolvePreferences(user({ locale: 'en-US', workspaces: [] }));
    await waitFor(() =>
      expect(screen.getByTestId('access-projection').textContent).toBe(
        'en-US|workspace-one',
      ),
    );
  });
});
