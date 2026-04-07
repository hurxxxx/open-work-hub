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

  const response = await fetch(path, {
    ...init,
    headers,
    cache: 'no-store',
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    let message: string;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail.map((d: { msg?: string }) => d.msg ?? String(d)).join(', ');
    } else {
      message = `Request failed with ${response.status}.`;
    }
    throw new AuthApiError(response.status, message);
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
