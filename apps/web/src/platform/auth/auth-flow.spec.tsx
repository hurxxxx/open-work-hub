import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import {
  AuthProvider,
  LoginRoute,
  RequireAuth,
  useAuth,
} from './auth-provider';
import { AUTH_TOKEN_STORAGE_KEY } from './auth-storage';
import { LOCALE_STORAGE_KEY, syncLocale } from '@/src/platform/i18n';
import type { AuthUser } from './auth-api';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@ai-do.local',
    full_name: 'AI-DO Member',
    display_name: 'AI-DO Member',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    primary_org_unit: null,
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'AI-DO HQ',
        role: 'admin',
      },
    ],
    workspace_roles: [
      {
        workspace_id: 'workspace-pms',
        key: 'pms',
        name: 'PMS Workspace',
        role: 'admin',
      },
    ],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    ...overrides,
  };
}

function ProtectedArea() {
  const auth = useAuth();
  const location = useLocation();

  return (
    <div>
      <h2>Protected Shell</h2>
      <p>{auth.user?.email}</p>
      <p data-testid="location">{location.pathname}</p>
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
    syncLocale('ko-KR');
    vi.restoreAllMocks();
  });

  it('shows initial setup when bootstrap requires the first user', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: true, dev_admin_login_available: true }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/setup' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'setup-token',
            user: buildUser({
              email: 'admin@ai-do.local',
              full_name: 'AI-DO Admin',
              display_name: 'AI-DO Admin',
              system_roles: ['platform_admin'],
              workspaces: [],
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
      target: { value: 'AI-DO Admin' },
    });
    fireEvent.change(screen.getByLabelText('이메일'), {
      target: { value: 'admin@ai-do.local' },
    });
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'supersecret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '관리자 계정 만들기' }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('admin@ai-do.local')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('setup-token');
  });

  it('logs in and redirects back to the requested route', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false, dev_admin_login_available: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/login' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'login-token',
            user: buildUser({ locale: 'en-US' }),
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
      target: { value: 'member@ai-do.local' },
    });
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'supersecret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '로그인' }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('member@ai-do.local')).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toBe('/docs');
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('login-token');
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en-US');
    expect(document.documentElement.lang).toBe('en-US');
  });

  it('logs in through the development admin shortcut button', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false, dev_admin_login_available: true }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/dev-admin-login' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'dev-admin-token',
            user: buildUser({
              email: 'admin@ai-do.local',
              full_name: 'AI-DO Admin',
              display_name: 'AI-DO Admin',
              system_roles: ['platform_admin'],
              workspaces: [],
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
    expect(screen.getByText('admin@ai-do.local')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('dev-admin-token');
  });

  it('renders seeded development account buttons and logs in with the selected account', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(
          JSON.stringify({
            requires_setup: false,
            dev_admin_login_available: true,
            dev_login_accounts: [
              {
                account_key: 'platform-admin',
                label: 'Platform Admin',
                email: 'platform-admin@ai-do.local',
                description: '전역 관리자 권한으로 모든 워크스페이스와 설정을 관리합니다.',
                category: 'Administrators',
              },
              {
                account_key: 'delivery-hub-member',
                label: 'Delivery Hub Member',
                email: 'delivery-hub-member@ai-do.local',
                description: 'Delivery Hub 워크스페이스 멤버 계정입니다. 기본 Team Space 멤버 권한이 함께 제공됩니다.',
                category: 'Workspaces',
              },
            ],
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        );
      }

      if (path === '/api/v1/auth/dev-login' && method === 'POST') {
        return new Response(
          JSON.stringify({
            token: 'dev-account-token',
            user: buildUser({
              email: 'delivery-hub-member@ai-do.local',
              full_name: 'Delivery Hub Member',
              display_name: 'Delivery Hub Member',
              workspace_roles: [
                {
                  workspace_id: 'workspace-pms',
                  key: 'delivery-hub',
                  name: 'Delivery Hub',
                  role: 'member',
                },
              ],
              workspaces: [
                {
                  id: 'workspace-delivery-hub',
                  slug: 'delivery-hub',
                  name: 'Delivery Hub',
                  role: 'member',
                },
              ],
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
    await screen.findByText('Platform Admin');
    await screen.findByText('Delivery Hub Member');
    fireEvent.click(screen.getByRole('button', { name: /Delivery Hub Member/ }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('delivery-hub-member@ai-do.local')).toBeTruthy();
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('dev-account-token');
  });

  it('restores an existing session from localStorage', async () => {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'saved-token');

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false, dev_admin_login_available: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/me') {
        return new Response(
          JSON.stringify(
            buildUser({
              id: 'user-2',
              email: 'saved@ai-do.local',
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
    expect(screen.getByText('saved@ai-do.local')).toBeTruthy();
  });

  it('clears session state on logout and returns to login', async () => {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'saved-token');

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false, dev_admin_login_available: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/me') {
        return new Response(
          JSON.stringify(
            buildUser({
              id: 'user-2',
              email: 'saved@ai-do.local',
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

  it('redirects to home after an explicit logout and next login', async () => {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'saved-token');

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false, dev_admin_login_available: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      if (path === '/api/v1/auth/me') {
        return new Response(
          JSON.stringify(
            buildUser({
              id: 'user-2',
              email: 'saved@ai-do.local',
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

    renderAuthFlow(['/planner']);

    await screen.findByText('Protected Shell');
    expect(screen.getByTestId('location').textContent).toBe('/planner');

    fireEvent.click(screen.getByRole('button', { name: 'Logout' }));

    await waitFor(() => {
      expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
    });
    await screen.findByRole('heading', { name: '로그인' });

    fireEvent.change(screen.getByLabelText('이메일'), {
      target: { value: 'member@ai-do.local' },
    });
    fireEvent.change(screen.getByLabelText('비밀번호'), {
      target: { value: 'supersecret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '로그인' }));

    await screen.findByText('Protected Shell');
    expect(screen.getByText('member@ai-do.local')).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toBe('/');
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('login-token');
  });

  it('shows a friendly bootstrap error when the auth API is unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(null, {
          status: 500,
          statusText: 'Internal Server Error',
        });
      }

      throw new Error(`Unhandled request: GET ${path}`);
    });

    renderAuthFlow(['/login']);

    await screen.findByRole('heading', { name: '로그인' });
    await screen.findByText('인증 서비스를 확인하지 못했습니다. API 서버 상태를 확인해 주세요.');
  });

  it('hides the development admin shortcut when the backend disables it', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);

      if (path === '/api/v1/auth/bootstrap-status') {
        return new Response(JSON.stringify({ requires_setup: false, dev_admin_login_available: false }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        });
      }

      throw new Error(`Unhandled request: GET ${path}`);
    });

    renderAuthFlow(['/login']);

    await screen.findByRole('heading', { name: '로그인' });
    expect(screen.queryByRole('button', { name: '개발용 관리자 바로 로그인' })).toBeNull();
    expect(screen.getByText('로컬 계정으로 로그인합니다.')).toBeTruthy();
  });
});
