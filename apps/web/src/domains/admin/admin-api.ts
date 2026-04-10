import type { AuthUser } from '@/src/domains/auth/auth-api';

export interface OrgUnitItem {
  id: string;
  name: string;
  slug: string;
  parent_id: string | null;
  active: boolean;
}

export interface AccessGroupItem {
  id: string;
  name: string;
  slug: string;
  description: string;
  group_kind: string;
  active: boolean;
  system_roles: string[];
  member_count: number;
}

export interface WorkspaceItem {
  id: string;
  key: string;
  name: string;
  description: string;
  active: boolean;
  team_count: number;
}

export interface WorkspaceBindingItem {
  subject_id: string;
  subject_type: 'user' | 'group';
  subject_label: string;
  role: string;
}

export interface TeamItem {
  id: string;
  workspace_id: string;
  workspace_key: string;
  key: string;
  name: string;
  description: string;
  active: boolean;
  member_count: number;
  current_user_role?: string | null;
}

export interface FeaturePolicyItem {
  id: string;
  code: string;
  name: string;
  description: string;
  enabled: boolean;
  allowed_workspace_keys: string[];
}

export interface AuditLogItem {
  id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  action: string;
  entity_kind: string;
  entity_id: string | null;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AdminUsersResponse {
  items: AuthUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUsersQuery {
  page?: number;
  page_size?: number;
  q?: string;
}

export interface CreatedUserResponse {
  user: AuthUser;
  temporary_password: string;
}

export interface ResetPasswordResponse {
  temporary_password: string;
}

class AdminApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function defaultAdminErrorMessage(path: string, status: number, method: string): string {
  if (method === 'DELETE' && path.startsWith('/api/v1/admin/teams/')) {
    return status >= 500
      ? '팀 스페이스를 휴지통으로 옮기지 못했습니다. 잠시 후 다시 시도해 주세요.'
      : '팀 스페이스를 휴지통으로 옮기지 못했습니다.';
  }

  return status >= 500
    ? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
    : `요청에 실패했습니다. (${status})`;
}

function resolveAdminErrorMessage(path: string, status: number, method: string, payload: unknown): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }

  return defaultAdminErrorMessage(path, status, method);
}

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('Authorization', `Bearer ${token}`);

  if (init.body) {
    headers.set('Content-Type', 'application/json');
  }

  const method = init.method ?? 'GET';
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      cache: 'no-store',
    });
  } catch {
    throw new AdminApiError(
      0,
      '관리자 API 서버에 연결하지 못했습니다. 서버 상태를 확인해 주세요.',
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AdminApiError(
      response.status,
      resolveAdminErrorMessage(path, response.status, method, payload),
    );
  }

  return payload as T;
}

export function listAdminUsers(
  token: string,
  query: AdminUsersQuery = {},
): Promise<AdminUsersResponse> {
  const params = new URLSearchParams();
  if (query.page !== undefined) {
    params.set('page', String(query.page));
  }
  if (query.page_size !== undefined) {
    params.set('page_size', String(query.page_size));
  }
  if (query.q?.trim()) {
    params.set('q', query.q.trim());
  }

  const queryString = params.toString();
  const suffix = queryString ? `?${queryString}` : '';
  return request<AdminUsersResponse>(token, `/api/v1/admin/users${suffix}`);
}

export function createAdminUser(
  token: string,
  payload: {
    email: string;
    full_name: string;
    display_name?: string;
    primary_org_unit_id?: string;
    group_ids?: string[];
  },
): Promise<CreatedUserResponse> {
  return request<CreatedUserResponse>(token, '/api/v1/admin/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(
  token: string,
  userId: string,
  payload: {
    full_name?: string;
    display_name?: string;
    primary_org_unit_id?: string;
    group_ids?: string[];
    status?: 'active' | 'invited' | 'suspended';
  },
): Promise<AuthUser> {
  return request<AuthUser>(token, `/api/v1/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteAdminUser(token: string, userId: string): Promise<void> {
  return request<void>(token, `/api/v1/admin/users/${userId}`, { method: 'DELETE' });
}

export function listOrgUnits(token: string): Promise<OrgUnitItem[]> {
  return request<OrgUnitItem[]>(token, '/api/v1/admin/org-units');
}

export function listGroups(token: string): Promise<AccessGroupItem[]> {
  return request<AccessGroupItem[]>(token, '/api/v1/admin/groups');
}

export function createGroup(
  token: string,
  payload: {
    name: string;
    description: string;
    system_roles?: string[];
  },
): Promise<AccessGroupItem> {
  return request<AccessGroupItem>(token, '/api/v1/admin/groups', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listWorkspaces(token: string): Promise<WorkspaceItem[]> {
  return request<WorkspaceItem[]>(token, '/api/v1/admin/workspaces');
}

export function createWorkspace(
  token: string,
  payload: {
    name: string;
    description: string;
  },
): Promise<WorkspaceItem> {
  return request<WorkspaceItem>(token, '/api/v1/admin/workspaces', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listWorkspaceBindings(
  token: string,
  workspaceId: string,
): Promise<WorkspaceBindingItem[]> {
  return request<WorkspaceBindingItem[]>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/bindings`,
  );
}

export function replaceWorkspaceBindings(
  token: string,
  workspaceId: string,
  payload: {
    users: Array<{ subject_id: string; role: string }>;
    groups: Array<{ subject_id: string; role: string }>;
  },
): Promise<WorkspaceBindingItem[]> {
  return request<WorkspaceBindingItem[]>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/bindings`,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function listTeams(token: string, workspaceId?: string): Promise<TeamItem[]> {
  const suffix = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
  return request<TeamItem[]>(token, `/api/v1/admin/teams${suffix}`);
}

export function createTeam(
  token: string,
  workspaceId: string,
  payload: {
    name: string;
    description: string;
  },
): Promise<TeamItem> {
  return request<TeamItem>(token, `/api/v1/admin/workspaces/${workspaceId}/teams`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTeam(
  token: string,
  teamId: string,
  payload: { name: string; description?: string },
): Promise<TeamItem> {
  return request<TeamItem>(token, `/api/v1/admin/teams/${teamId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteTeam(token: string, teamId: string): Promise<void> {
  return request<void>(token, `/api/v1/admin/teams/${teamId}`, { method: 'DELETE' });
}

export function listTeamMembers(token: string, teamId: string): Promise<AuthUser[]> {
  return request<AuthUser[]>(token, `/api/v1/admin/teams/${teamId}/members`);
}

export function replaceTeamMembers(
  token: string,
  teamId: string,
  userIds: string[],
): Promise<AuthUser[]> {
  return request<AuthUser[]>(token, `/api/v1/admin/teams/${teamId}/members`, {
    method: 'PUT',
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export function listFeaturePolicies(token: string): Promise<FeaturePolicyItem[]> {
  return request<FeaturePolicyItem[]>(token, '/api/v1/admin/feature-policies');
}

export function updateFeaturePolicies(
  token: string,
  items: Array<{
    id: string;
    enabled: boolean;
  }>,
): Promise<FeaturePolicyItem[]> {
  return request<FeaturePolicyItem[]>(token, '/api/v1/admin/feature-policies', {
    method: 'PUT',
    body: JSON.stringify({ items }),
  });
}

export function listAuditLogs(token: string): Promise<AuditLogItem[]> {
  return request<AuditLogItem[]>(token, '/api/v1/admin/audit-logs');
}

export function resetUserPassword(
  token: string,
  userId: string,
): Promise<ResetPasswordResponse> {
  return request<ResetPasswordResponse>(
    token,
    `/api/v1/admin/users/${userId}/reset-password`,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  );
}
