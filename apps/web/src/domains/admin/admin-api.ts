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
  permissions: string[];
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
}

export interface FeaturePolicyItem {
  id: string;
  code: string;
  name: string;
  description: string;
  enabled: boolean;
  required_permissions: string[];
  allowed_workspace_keys: string[];
  allowed_group_slugs: string[];
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

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('Authorization', `Bearer ${token}`);

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
    throw new AdminApiError(
      response.status,
      payload?.detail ?? `Request failed with ${response.status}.`,
    );
  }

  return payload as T;
}

export function listAdminUsers(token: string): Promise<AdminUsersResponse> {
  return request<AdminUsersResponse>(token, '/api/v1/admin/users');
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
    permissions: string[];
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
    required_permissions: string[];
    allowed_workspace_keys: string[];
    allowed_group_slugs: string[];
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
