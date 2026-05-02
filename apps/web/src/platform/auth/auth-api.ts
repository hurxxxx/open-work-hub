import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type ThemePreference = 'system' | 'light' | 'dark';

export type OrgUnitSummary = ApiSchema<'OrgUnitSummaryResponse'>;

export interface WorkspaceRole {
  workspace_id: string;
  key: string;
  name: string;
  role: string;
}

export type WorkspaceSummary = ApiSchema<'WorkspaceSummaryResponse'>;

const WORKSPACE_ROLE_RANK: Record<string, number> = {
  member: 20,
  admin: 40,
};

const TEAM_ROLE_RANK: Record<string, number> = {
  viewer: 10,
  member: 20,
  admin: 30,
  owner: 40,
};

export type AuthUser = Omit<
  ApiSchema<'AuthUserResponse'>,
  'created_at' | 'job_title' | 'last_login_at' | 'primary_org_unit' | 'theme_preference' | 'time_zone' | 'workspaces'
> & {
  job_title?: string | null;
  theme_preference: ThemePreference;
  time_zone: string;
  primary_org_unit: OrgUnitSummary | null;
  workspaces: WorkspaceSummary[];
  workspace_roles?: WorkspaceRole[];
  last_login_at?: string | null;
  created_at?: string;
};

export function getWorkspaceRoleByKey(
  user: Pick<AuthUser, 'workspaces' | 'workspace_roles'> | null | undefined,
  key: string,
): WorkspaceRole | null {
  const workspace = user?.workspaces.find((item) => item.slug === key);
  if (workspace) {
    return {
      workspace_id: workspace.id,
      key: workspace.slug,
      name: workspace.name,
      role: workspace.role,
    };
  }
  return user?.workspace_roles?.find((role) => role.key === key) ?? null;
}

export function workspaceRoleAllows(
  role: string | null | undefined,
  minRole: keyof typeof WORKSPACE_ROLE_RANK,
): boolean {
  const normalizedRole = role === 'owner'
    ? 'admin'
    : role === 'viewer'
      ? 'member'
      : role;
  if (!normalizedRole) {
    return false;
  }

  return (WORKSPACE_ROLE_RANK[normalizedRole] ?? -1) >= WORKSPACE_ROLE_RANK[minRole];
}

export function teamRoleAllows(
  role: string | null | undefined,
  minRole: keyof typeof TEAM_ROLE_RANK,
): boolean {
  if (!role) {
    return false;
  }

  return (TEAM_ROLE_RANK[role] ?? -1) >= TEAM_ROLE_RANK[minRole];
}

export function hasSystemRole(
  user: Pick<AuthUser, 'system_roles'> | null | undefined,
  role: string,
): boolean {
  return user?.system_roles?.includes(role) ?? false;
}

export function hasAnySystemRole(
  user: Pick<AuthUser, 'system_roles'> | null | undefined,
  roles: readonly string[],
): boolean {
  return roles.some((role) => hasSystemRole(user, role));
}

export function hasWorkspaceMembership(
  user: Pick<AuthUser, 'workspaces'> | null | undefined,
  workspaceSlug?: string | null,
): boolean {
  if (!workspaceSlug) {
    return (user?.workspaces?.length ?? 0) > 0;
  }
  return user?.workspaces?.some((workspace) => workspace.slug === workspaceSlug) ?? false;
}

export function hasWorkspaceAdminAccess(
  user: Pick<AuthUser, 'workspaces' | 'system_roles'> | null | undefined,
  workspaceSlug?: string | null,
): boolean {
  if (hasAnySystemRole(user, ['platform_admin'])) {
    return true;
  }
  const role = workspaceSlug
    ? user?.workspaces?.find((workspace) => workspace.slug === workspaceSlug)?.role
    : null;
  return workspaceRoleAllows(role, 'admin');
}

export function hasAdminConsoleAccess(
  user: Pick<AuthUser, 'system_roles'> | null | undefined,
): boolean {
  return hasAnySystemRole(user, ['platform_admin']);
}

export type BootstrapStatusResponse = ApiSchema<'BootstrapStatusResponse'>;

export type DevLoginAccount = ApiSchema<'DevLoginAccountResponse'>;

export type AuthSessionResponse = Omit<ApiSchema<'AuthSessionResponse'>, 'user'> & {
  user: AuthUser;
};

export type LoginPayload = ApiSchema<'LoginRequest'>;

export type SetupFirstUserPayload = ApiSchema<'SetupFirstUserRequest'>;

export type UpdatePreferencesPayload = Omit<ApiSchema<'UpdatePreferencesRequest'>, 'theme_preference' | 'time_zone'> & {
  theme_preference?: ThemePreference;
  time_zone?: string;
};

export type ChangePasswordPayload = ApiSchema<'ChangePasswordRequest'>;

export type AuthSessionItem = ApiSchema<'SessionListItemResponse'>;

export type AuthSessionsResponse = ApiSchema<'SessionListResponse'>;

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

  if (path === '/api/v1/auth/dev-login') {
    return status >= 500
      ? '개발용 계정 로그인을 처리하지 못했습니다. API 서버 상태를 확인해 주세요.'
      : '개발용 계정 바로 로그인을 실행하지 못했습니다.';
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
  try {
    return await apiFetchJson<T>(path, token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new AuthApiError(
        error.status,
        resolveAuthErrorMessage(path, error.status, error.payload),
      );
    }
    throw new AuthApiError(
      0,
      '인증 서버에 연결하지 못했습니다. API 서버가 실행 중인지 확인해 주세요.',
    );
  }
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

export function developmentAccountLogin(accountKey: string): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>('/api/v1/auth/dev-login', {
    method: 'POST',
    body: JSON.stringify({ account_key: accountKey }),
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
