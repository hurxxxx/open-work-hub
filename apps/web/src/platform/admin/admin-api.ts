import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { AuthUser } from '@/src/platform/auth/auth-api';

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
  workspace_bindings: GroupWorkspaceBindingItem[];
}

export interface GroupWorkspaceBindingItem {
  workspace_id: string;
  workspace_key: string;
  workspace_name: string;
  role: string;
}

export interface WorkspaceItem {
  id: string;
  key: string;
  name: string;
  description: string;
  active: boolean;
  team_count: number;
  member_count: number;
  meeting_count: number;
  doc_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface WorkspaceBindingItem {
  subject_id: string;
  subject_type: 'user' | 'group';
  subject_label: string;
  subject_secondary?: string | null;
  role: string;
}

export interface WorkspaceMemberCandidate {
  id: string;
  email: string;
  full_name: string;
  display_name: string;
  status: string;
}

export interface WorkspaceMemberItem {
  subject_id: string;
  subject_type: 'user' | 'group';
  subject_label: string;
  subject_secondary: string | null;
  role: string;
  user_status: string | null;
  last_login_at: string | null;
  created_at: string | null;
}

export interface WorkspaceMemberRoleCounts {
  admin: number;
  member: number;
}

export interface WorkspaceMembersResponse {
  items: WorkspaceMemberItem[];
  total: number;
  page: number;
  page_size: number;
  role_counts: WorkspaceMemberRoleCounts;
  user_count: number;
  group_count: number;
  pending_count: number;
}

export interface WorkspaceMembersListParams {
  q?: string;
  role?: string[];
  subjectType?: 'user' | 'group';
  page?: number;
  pageSize?: number;
  pendingOnly?: boolean;
}

export interface WorkspaceMemberBulkSubject {
  subject_type: 'user' | 'group';
  subject_id: string;
  role?: string;
}

export interface WorkspaceMemberBulkResponse {
  succeeded: number;
  failed: Array<{ subject_type: string; subject_id: string; detail: string }>;
}

export interface UserTeamMembershipItem {
  id: string;
  workspace_id: string;
  workspace_key: string;
  workspace_name: string;
  key: string;
  name: string;
  description: string;
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
  const method = init.method ?? 'GET';
  try {
    return await apiFetchJson<T>(path, token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new AdminApiError(
        error.status,
        resolveAdminErrorMessage(path, error.status, method, error.payload),
      );
    }
    throw new AdminApiError(
      0,
      '관리자 API 서버에 연결하지 못했습니다. 서버 상태를 확인해 주세요.',
    );
  }
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

export function updateGroup(
  token: string,
  groupId: string,
  payload: {
    name: string;
    description: string;
    system_roles?: string[];
    slug?: string;
    group_kind?: string;
    active?: boolean;
  },
): Promise<AccessGroupItem> {
  return request<AccessGroupItem>(token, `/api/v1/admin/groups/${groupId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function replaceGroupWorkspaceBindings(
  token: string,
  groupId: string,
  items: Array<{ workspace_id: string; role: string }>,
): Promise<AccessGroupItem> {
  return request<AccessGroupItem>(token, `/api/v1/admin/groups/${groupId}/workspace-bindings`, {
    method: 'PUT',
    body: JSON.stringify({ items }),
  });
}

export function replaceGroupMembers(
  token: string,
  groupId: string,
  userIds: string[],
): Promise<AccessGroupItem> {
  return request<AccessGroupItem>(token, `/api/v1/admin/groups/${groupId}/members`, {
    method: 'PUT',
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export function listWorkspaces(
  token: string,
  options: { includeArchived?: boolean } = {},
): Promise<WorkspaceItem[]> {
  const suffix = options.includeArchived ? '?include_archived=true' : '';
  return request<WorkspaceItem[]>(token, `/api/v1/admin/workspaces${suffix}`);
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

export function updateWorkspace(
  token: string,
  workspaceId: string,
  payload: {
    key?: string;
    name: string;
    description: string;
    active?: boolean;
  },
): Promise<WorkspaceItem> {
  return request<WorkspaceItem>(token, `/api/v1/admin/workspaces/${workspaceId}`, {
    method: 'PATCH',
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

export function addWorkspaceMember(
  token: string,
  workspaceId: string,
  payload: {
    subject_id: string;
    subject_type: 'user' | 'group';
    role: string;
  },
): Promise<WorkspaceBindingItem> {
  return request<WorkspaceBindingItem>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/members`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateWorkspaceMemberRole(
  token: string,
  workspaceId: string,
  subjectType: 'user' | 'group',
  subjectId: string,
  role: string,
): Promise<WorkspaceBindingItem> {
  return request<WorkspaceBindingItem>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/members/${subjectType}/${encodeURIComponent(subjectId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    },
  );
}

export function removeWorkspaceMember(
  token: string,
  workspaceId: string,
  subjectType: 'user' | 'group',
  subjectId: string,
): Promise<void> {
  return request<void>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/members/${subjectType}/${encodeURIComponent(subjectId)}`,
    {
      method: 'DELETE',
    },
  );
}

export function deleteWorkspace(token: string, workspaceId: string): Promise<void> {
  return request<void>(token, `/api/v1/admin/workspaces/${workspaceId}`, {
    method: 'DELETE',
  });
}

export function listWorkspaceMembers(
  token: string,
  workspaceId: string,
  params: WorkspaceMembersListParams = {},
): Promise<WorkspaceMembersResponse> {
  const search = new URLSearchParams();
  if (params.q?.trim()) search.set('q', params.q.trim());
  if (params.subjectType) search.set('subject_type', params.subjectType);
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('page_size', String(params.pageSize));
  if (params.pendingOnly) search.set('pending_only', 'true');
  if (params.role && params.role.length > 0) {
    for (const role of params.role) search.append('role', role);
  }
  const suffix = search.toString() ? `?${search.toString()}` : '';
  return request<WorkspaceMembersResponse>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/members${suffix}`,
  );
}

export function bulkWorkspaceMembers(
  token: string,
  workspaceId: string,
  payload: {
    action: 'add' | 'remove' | 'update_role';
    subjects: WorkspaceMemberBulkSubject[];
  },
): Promise<WorkspaceMemberBulkResponse> {
  return request<WorkspaceMemberBulkResponse>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/members/bulk`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function listWorkspaceMemberCandidates(
  token: string,
  workspaceId: string,
  query?: string,
): Promise<WorkspaceMemberCandidate[]> {
  const suffix = query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
  return request<WorkspaceMemberCandidate[]>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/member-candidates${suffix}`,
  );
}

export function listUserTeamMemberships(
  token: string,
  userId: string,
): Promise<UserTeamMembershipItem[]> {
  return request<UserTeamMembershipItem[]>(token, `/api/v1/admin/users/${userId}/teams`);
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
