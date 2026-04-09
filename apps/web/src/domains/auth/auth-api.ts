export type ThemePreference = 'system' | 'light' | 'dark';

export interface OrgUnitSummary {
  id: string;
  name: string;
  slug: string;
  parent_id: string | null;
}

export interface WorkspaceRole {
  workspace_id: string;
  key: string;
  name: string;
  role: string;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  display_name: string;
  job_title?: string | null;
  status: string;
  theme_preference: ThemePreference;
  primary_org_unit: OrgUnitSummary | null;
  workspace_roles: WorkspaceRole[];
  group_ids: string[];
  group_slugs: string[];
  permissions: string[];
  visible_features: string[];
  must_change_password: boolean;
  is_admin: boolean;
  last_login_at?: string | null;
  created_at?: string;
}

export function getWorkspaceRoleByKey(
  user: Pick<AuthUser, 'workspace_roles'> | null | undefined,
  key: string,
): WorkspaceRole | null {
  return user?.workspace_roles.find((role) => role.key === key) ?? null;
}

export interface BootstrapStatusResponse {
  requires_setup: boolean;
}

export interface AuthSessionResponse {
  token: string;
  user: AuthUser;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface SetupFirstUserPayload extends LoginPayload {
  full_name: string;
}

export interface UpdatePreferencesPayload {
  display_name?: string;
  full_name?: string;
  job_title?: string;
  theme_preference?: ThemePreference;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface AuthSessionItem {
  id: string;
  is_current: boolean;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  last_seen_at: string | null;
  user_agent: string | null;
  ip_address: string | null;
}

export interface AuthSessionsResponse {
  items: AuthSessionItem[];
}

export class AuthApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function defaultAuthErrorMessage(path: string, status: number): string {
  if (path === '/api/v1/auth/bootstrap-status') {
    return status >= 500
      ? '인증 서비스를 확인하지 못했습니다. API 서버 상태를 확인해 주세요.'
      : '초기 인증 상태를 확인하지 못했습니다.';
  }

  if (path === '/api/v1/auth/login') {
    return status >= 500
      ? '로그인 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
      : '로그인하지 못했습니다.';
  }

  if (path === '/api/v1/auth/dev-admin-login') {
    return status >= 500
      ? '개발용 관리자 로그인을 처리하지 못했습니다. API 서버 상태를 확인해 주세요.'
      : '개발용 관리자 바로 로그인을 실행하지 못했습니다.';
  }

  if (path === '/api/v1/auth/setup') {
    return status >= 500
      ? '최초 관리자 계정 생성을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
      : '최초 관리자 계정을 만들지 못했습니다.';
  }

  return status >= 500
    ? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
    : `요청에 실패했습니다. (${status})`;
}

function resolveAuthErrorMessage(path: string, status: number, payload: unknown): string {
  if (
    payload &&
    typeof payload === 'object' &&
    'detail' in payload
  ) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') {
            return item.msg;
          }
          return typeof item === 'string' ? item : null;
        })
        .filter((message): message is string => Boolean(message && message.trim()));

      if (messages.length > 0) {
        return messages.join(', ');
      }
    }
  }

  return defaultAuthErrorMessage(path, status);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (init.body) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      cache: 'no-store',
    });
  } catch {
    throw new AuthApiError(
      0,
      '인증 서버에 연결하지 못했습니다. API 서버가 실행 중인지 확인해 주세요.',
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AuthApiError(
      response.status,
      resolveAuthErrorMessage(path, response.status, payload),
    );
  }

  return payload as T;
}

export function getBootstrapStatus(): Promise<BootstrapStatusResponse> {
  return request<BootstrapStatusResponse>('/api/v1/auth/bootstrap-status');
}

export function login(payload: LoginPayload): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function developmentAdminLogin(): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>('/api/v1/auth/dev-admin-login', {
    method: 'POST',
  });
}

export function setupFirstUser(
  payload: SetupFirstUserPayload,
): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>('/api/v1/auth/setup', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getCurrentUser(token: string): Promise<AuthUser> {
  return request<AuthUser>('/api/v1/auth/me', {}, token);
}

export function logout(token: string): Promise<void> {
  return request<void>(
    '/api/v1/auth/logout',
    {
      method: 'POST',
    },
    token,
  );
}

export function updatePreferences(
  token: string,
  payload: UpdatePreferencesPayload,
): Promise<AuthUser> {
  return request<AuthUser>(
    '/api/v1/auth/preferences',
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function changePassword(
  token: string,
  payload: ChangePasswordPayload,
): Promise<void> {
  return request<void>(
    '/api/v1/auth/change-password',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listSessions(token: string): Promise<AuthSessionsResponse> {
  return request<AuthSessionsResponse>('/api/v1/auth/sessions', {}, token);
}

export function revokeSession(token: string, sessionId: string): Promise<void> {
  return request<void>(
    `/api/v1/auth/sessions/${sessionId}/revoke`,
    {
      method: 'POST',
    },
    token,
  );
}
