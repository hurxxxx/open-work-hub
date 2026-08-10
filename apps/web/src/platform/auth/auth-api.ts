import { authRoutes } from '@open-alm/contracts/auth';
import { hasCoreWorkspaceMembership } from '@open-alm/core-web/workspace-access';

import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { WorkspaceShellAppId } from '@/src/app/shell/navigation-types';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';

export type ThemePreference = 'system' | 'light' | 'dark';
export type LocalePreference = 'ko-KR' | 'en-US';
export type DateFormatPreference =
  | 'korean'
  | 'iso'
  | 'us'
  | 'european'
  | 'locale';
export type AppBarAppId = WorkspaceShellAppId;

export interface AppBarLayoutPreference {
  pinned_app_ids: AppBarAppId[];
}

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
  | 'created_at'
  | 'default_workspace_id'
  | 'employee_code'
  | 'job_title'
  | 'last_login_at'
  | 'auth_provider'
  | 'login_blocked'
  | 'primary_org_unit'
  | 'theme_preference'
  | 'locale'
  | 'time_zone'
  | 'date_format'
  | 'workspaces'
> & {
  default_workspace_id?: string | null;
  app_bar_layout?: AppBarLayoutPreference | null;
  employee_code?: string | null;
  job_title?: string | null;
  auth_provider?: string;
  login_blocked?: boolean;
  theme_preference: ThemePreference;
  locale: LocalePreference;
  time_zone: string;
  date_format: DateFormatPreference;
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
  const normalizedRole =
    role === 'owner' ? 'admin' : role === 'viewer' ? 'member' : role;
  return roleRankAllows(WORKSPACE_ROLE_RANK, normalizedRole, minRole);
}

export function teamRoleAllows(
  role: string | null | undefined,
  minRole: keyof typeof TEAM_ROLE_RANK,
): boolean {
  return roleRankAllows(TEAM_ROLE_RANK, role, minRole);
}

function roleRankAllows<TRole extends string>(
  ranks: Record<TRole, number>,
  role: string | null | undefined,
  minRole: TRole,
): boolean {
  if (!role) {
    return false;
  }

  return ((ranks as Record<string, number>)[role] ?? -1) >= ranks[minRole];
}

function hasSystemRole(
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
  return hasCoreWorkspaceMembership(user, workspaceSlug);
}

export function hasWorkspaceAdminAccess(
  user: Pick<AuthUser, 'workspaces' | 'system_roles'> | null | undefined,
  workspaceSlug?: string | null,
): boolean {
  if (hasAnySystemRole(user, ['platform_admin'])) {
    return true;
  }
  const role = workspaceSlug
    ? user?.workspaces?.find((workspace) => workspace.slug === workspaceSlug)
        ?.role
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

export type AuthSessionResponse = Omit<
  ApiSchema<'AuthSessionResponse'>,
  'user'
> & {
  user: AuthUser;
};

export type LoginPayload = ApiSchema<'LoginRequest'>;

export type SetupFirstUserPayload = ApiSchema<'SetupFirstUserRequest'>;

export type SignupPayload = ApiSchema<'SignupRequest'>;

export type UpdatePreferencesPayload = Omit<
  ApiSchema<'UpdatePreferencesRequest'>,
  'theme_preference' | 'locale' | 'time_zone' | 'date_format'
> & {
  app_bar_layout?: AppBarLayoutPreference | null;
  default_workspace_id?: string | null;
  theme_preference?: ThemePreference;
  locale?: LocalePreference;
  time_zone?: string;
  date_format?: DateFormatPreference;
};

export type ChangePasswordPayload = ApiSchema<'ChangePasswordRequest'>;

export type AuthSessionItem = ApiSchema<'SessionListItemResponse'>;

export type AuthSessionsResponse = ApiSchema<'SessionListResponse'>;

export interface DesktopSessionLinkResponse {
  code: string;
  expires_at: string;
}

export class AuthApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function defaultAuthErrorMessage(path: string, status: number): string {
  if (path === authRoutes.bootstrapStatus()) {
    return status >= 500
      ? i18n.t('auth:errors.bootstrapServer')
      : i18n.t('auth:errors.bootstrap');
  }

  if (path === authRoutes.login()) {
    return status >= 500
      ? i18n.t('auth:errors.loginServer')
      : i18n.t('auth:errors.login');
  }

  if (path === authRoutes.signup()) {
    return status >= 500
      ? i18n.t('auth:errors.signupServer')
      : i18n.t('auth:errors.signup');
  }

  if (path === authRoutes.developmentAdminLogin()) {
    return status >= 500
      ? i18n.t('auth:errors.devAdminLoginServer')
      : i18n.t('auth:errors.devAdminLogin');
  }

  if (path === authRoutes.developmentAccountLogin()) {
    return status >= 500
      ? i18n.t('auth:errors.devLoginServer')
      : i18n.t('auth:errors.devLogin');
  }

  if (path === authRoutes.setup()) {
    return status >= 500
      ? i18n.t('auth:errors.setupServer')
      : i18n.t('auth:errors.setup');
  }

  return status >= 500
    ? i18n.t('common:feedback.requestFailedRetry')
    : i18n.t('common:feedback.requestFailed', { status });
}

function resolveAuthErrorMessage(
  path: string,
  status: number,
  payload: unknown,
): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (
            item &&
            typeof item === 'object' &&
            'msg' in item &&
            typeof item.msg === 'string'
          ) {
            return item.msg;
          }
          return typeof item === 'string' ? item : null;
        })
        .filter((message): message is string =>
          Boolean(message && message.trim()),
        );

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
    return await apiFetchJsonWithMappedError<T>(
      path,
      token,
      init,
      (error) =>
        new AuthApiError(
          error.status,
          resolveAuthErrorMessage(path, error.status, error.payload),
        ),
    );
  } catch (error) {
    if (error instanceof AuthApiError) {
      throw error;
    }
    throw new AuthApiError(0, i18n.t('auth:errors.connection'));
  }
}

export function getBootstrapStatus(): Promise<BootstrapStatusResponse> {
  return request<BootstrapStatusResponse>(authRoutes.bootstrapStatus());
}

export function login(payload: LoginPayload): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>(authRoutes.login(), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function signup(payload: SignupPayload): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>(authRoutes.signup(), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function developmentAdminLogin(): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>(authRoutes.developmentAdminLogin(), {
    method: 'POST',
  });
}

export function developmentAccountLogin(
  accountKey: string,
): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>(authRoutes.developmentAccountLogin(), {
    method: 'POST',
    body: JSON.stringify({ account_key: accountKey }),
  });
}

export function setupFirstUser(
  payload: SetupFirstUserPayload,
): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>(authRoutes.setup(), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getCurrentUser(token: string): Promise<AuthUser> {
  return request<AuthUser>(authRoutes.currentUser(), {}, token);
}

export function logout(token: string): Promise<void> {
  return request<void>(
    authRoutes.logout(),
    {
      method: 'POST',
    },
    token,
  );
}

export function createDesktopSessionLink(
  token: string,
): Promise<DesktopSessionLinkResponse> {
  return request<DesktopSessionLinkResponse>(
    authRoutes.desktopSessionLinks(),
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
    authRoutes.preferences(),
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
    authRoutes.changePassword(),
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listSessions(token: string): Promise<AuthSessionsResponse> {
  return request<AuthSessionsResponse>(authRoutes.sessions(), {}, token);
}

export function revokeSession(token: string, sessionId: string): Promise<void> {
  return request<void>(
    authRoutes.revokeSession(sessionId),
    {
      method: 'POST',
    },
    token,
  );
}
