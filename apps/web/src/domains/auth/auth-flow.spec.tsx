import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from './auth-provider';
import { AUTH_TOKEN_STORAGE_KEY } from './auth-storage';
import type { AuthUser } from './auth-api';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspace_roles: [
      {
        workspace_id: 'workspace-pms',
        key: 'pms',
        name: 'PMS Workspace',
        role: 'workspace_admin',
      },
    ],
    group_ids: [],
    group_slugs: [],
    permissions: [],
    visible_features: ['nav.ai', 'nav.docs', 'nav.pms', 'nav.planner'],
    must_change_password: false,
    is_admin: false,
    ...overrides,
  };
}

function ProtectedArea() {
  const auth = useAuth();

  return (
    <div>
      <h2>Protected Shell</h2>
      <p>{auth.user?.email}</p>
      <button
        onClick={() => {
          void auth.logout();
        }}
        type="button"
      >
        Logout
      </button>
    </div>
  );
}

function renderAuthFlow(initialEntries: string[]) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginRoute />} />
            <Route
              path="*"
              element={
                <RequireAuth>
                  <ProtectedArea />
                </RequireAuth>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </StrictMode>,
  );
}

describe('auth flow', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('shows initial setup when bootstrap requires the first user', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: true }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/setup' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'setup-token',
            user: buildUser({
              email: 'admin@aidoo.local',
              full_name: 'AIDOO Admin',
              display_name: 'AIDOO Admin',
              group_slugs: ['platform-admin'],
              permissions: ['admin.access'],
              is_admin: true,
            }),
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 201,
          },
        );
      }

      throw new Error(`Unhandled request: ${method} ${path}`);
    });

    renderAuthFlow(['/login']);

    await screen.findByRole('heading', { name: '최초 관리자 설정' });
    fireEvent.change(screen.getByLabelText('이름'), {
      target: { value: 'AIDOO Admin' },
    });
    fireEvent.change(screen.getByLabelText('이메일'), {
      target: { value: 'admin@aidoo.local' },
    });
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'supersecret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '관리자 계정 만들기' }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('admin@aidoo.local')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('setup-token');
  });

  it('logs in and redirects back to the requested route', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/login' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'login-token',
            user: buildUser(),
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        );
      }

      throw new Error(`Unhandled request: ${method} ${path}`);
    });

    renderAuthFlow(['/docs']);

    await screen.findByRole('heading', { name: '로그인' });
    fireEvent.change(screen.getByLabelText('이메일'), {
      target: { value: 'member@aidoo.local' },
    });
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'supersecret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '로그인' }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('member@aidoo.local')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('login-token');
  });

  it('logs in through the development admin shortcut button', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/dev-admin-login' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'dev-admin-token',
            user: buildUser({
              email: 'admin@aidoo.local',
              full_name: 'AIDOO Admin',
              display_name: 'AIDOO Admin',
              group_slugs: ['platform-admin'],
              permissions: ['admin.access'],
              is_admin: true,
            }),
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        );
      }

      throw new Error(`Unhandled request: ${method} ${path}`);
    });

    renderAuthFlow(['/login']);

    await screen.findByRole('heading', { name: '로그인' });
    fireEvent.click(screen.getByRole('button', { name: '개발용 관리자 바로 로그인' }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('admin@aidoo.local')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('dev-admin-token');
  });

  it('restores an existing session from localStorage', async () => {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'saved-token');

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/me') {
        return new Response(
          JSON.stringify(
            buildUser({
              id: 'user-2',
              email: 'saved@aidoo.local',
              full_name: 'Saved User',
              display_name: 'Saved User',
            }),
          ),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        );
      }

      throw new Error(`Unhandled request: GET ${path}`);
    });

    renderAuthFlow(['/ai']);

    await screen.findByText('Protected Shell');
    expect(screen.getByText('saved@aidoo.local')).toBeTruthy();
  });

  it('clears session state on logout and returns to login', async () => {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'saved-token');

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/me') {
        return new Response(
          JSON.stringify(
            buildUser({
              id: 'user-2',
              email: 'saved@aidoo.local',
              full_name: 'Saved User',
              display_name: 'Saved User',
            }),
          ),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        );
      }

      if (path === '/api/v1/auth/logout' && method === 'POST') {
        return new Response(null, { status: 204 });
      }

      throw new Error(`Unhandled request: ${method} ${path}`);
    });

    renderAuthFlow(['/planner']);

    await screen.findByText('Protected Shell');
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));

    await waitFor(() => {
      expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
    });
    await screen.findByRole('heading', { name: '로그인' });
  });
});
