import { authRoutes } from '@open-work-hub/contracts/auth';
import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import type {
  AuthSessionResponse,
  AuthUser,
} from '@/src/platform/auth/auth-api';
import { emitCommunityChannelsChanged } from '@/src/platform/community/community-channel-events';
import { i18n } from '@/src/platform/i18n';

export type WorkspaceItem = ApiSchema<'WorkspaceItemResponse'>;
export type WorkspaceBindingItem = ApiSchema<'WorkspaceBindingItemResponse'>;
export type WorkspaceMemberCandidate =
  ApiSchema<'WorkspaceMemberCandidateResponse'>;
export type WorkspaceMemberItem = ApiSchema<'WorkspaceMemberItemResponse'>;
export type WorkspaceMemberRoleCounts = ApiSchema<'WorkspaceMemberRoleCounts'>;
export type WorkspaceMembersResponse = ApiSchema<'WorkspaceMembersResponse'>;

export interface WorkspaceMembersListParams {
  q?: string;
  role?: string[];
  subjectType?: 'user';
  page?: number;
  pageSize?: number;
  pendingOnly?: boolean;
}

export type WorkspaceMemberBulkSubject =
  ApiSchema<'WorkspaceMemberBulkSubject'>;
export type WorkspaceMemberBulkResponse = Omit<
  ApiSchema<'WorkspaceMemberBulkResponse'>,
  'failed'
> & {
  failed: Array<{ subject_type: string; subject_id: string; detail: string }>;
};
export type TeamItem = ApiSchema<'TeamItemResponse'>;
export type AuditLogItem = ApiSchema<'AuditLogItemResponse'>;
export type AuditLogsResponse = ApiSchema<'AuditLogsResponse'>;
export type AdminUsageDashboard = ApiSchema<'AdminUsageDashboardResponse'>;
export interface AdminUsageExcludedUserItem {
  user_id: string;
  full_name: string;
  email: string;
  excluded_at: string;
}
export type AdminUsageTargetsResponse = ApiSchema<'AdminUsageTargetsResponse'>;
export type AdminUsersResponse = Omit<
  ApiSchema<'AdminUsersResponse'>,
  'items'
> & {
  items: AuthUser[];
};
export type AdminCommunityChannelItem = ApiSchema<'CommunityChannelOut'>;
export type AdminCommunityChannelInput =
  ApiSchema<'CommunityChannelCreateRequest'>;
export type AdminCommunityChannelsResponse =
  ApiSchema<'CommunityChannelsResponse'>;
export type PlatformAppVisibilityItem =
  ApiSchema<'PlatformAppVisibilityItemResponse'> & {
    availability_scope: 'platform' | 'workspace';
  };
export type PlatformAppVisibilityResponse = Omit<
  ApiSchema<'PlatformAppVisibilityResponse'>,
  'items'
> & { items: PlatformAppVisibilityItem[] };
export type WorkspaceAppVisibilityItem =
  ApiSchema<'WorkspaceAppVisibilityItemResponse'> & {
    availability_scope: 'workspace';
  };
export type WorkspaceAppVisibilityResponse = Omit<
  ApiSchema<'WorkspaceAppVisibilityResponse'>,
  'items'
> & { items: WorkspaceAppVisibilityItem[] };
export interface AdminAppBarCategoryAppItem {
  app_id: string;
  title: string;
  route_base: string;
  icon_key: string;
  coming_soon?: boolean | null;
  runtime_enabled: boolean;
}

export interface AdminAppBarCategory {
  id: string;
  key: string;
  title: string;
  icon_key: string;
  position: number;
  items: AdminAppBarCategoryAppItem[];
}

export interface AdminAppBarCategoriesResponse {
  categories: AdminAppBarCategory[];
  available_apps: AdminAppBarCategoryAppItem[];
  icon_keys: string[];
}

export type AiSecurityPolicyEffect =
  | 'inherit'
  | 'block_external'
  | 'mask_and_send'
  | 'audit_only';

export type AiSecurityExternalTransferBlocker =
  | 'internal_context'
  | 'blocking_sensitivity_label'
  | 'company_sensitive_entity'
  | 'policy_block_external'
  | 'pii'
  | 'credential'
  | 'internal_url'
  | 'security_document'
  | 'custom_block_term'
  | 'unknown_external_entity';

export type AiSecurityDataProtectionAction = 'block' | 'mask_and_send';
export type AiSecurityExternalAppAction = 'block' | 'mask_and_send';

export interface AiSecurityExternalAppCandidate {
  app_id: string;
  app_label?: string | null;
  task_kind: string;
  capability: string;
  provider: string;
  description: string;
}

export interface AiSecurityDataProtection {
  enforcement_enabled: boolean;
  enforcement_disabled_reason: string;
  custom_block_terms: string[];
  mandatory_blockers: string[];
  hard_blockers: AiSecurityExternalTransferBlocker[];
  exception_eligible_blockers: AiSecurityExternalTransferBlocker[];
  mask_eligible_blockers: AiSecurityExternalTransferBlocker[];
  blocker_actions: Partial<
    Record<AiSecurityExternalTransferBlocker, AiSecurityDataProtectionAction>
  >;
  external_app_actions: Partial<
    Record<
      string,
      Partial<
        Record<AiSecurityExternalTransferBlocker, AiSecurityExternalAppAction>
      >
    >
  >;
  privacy_filter_enabled: boolean;
  privacy_filter_ready?: boolean;
  privacy_filter_status?: string;
  privacy_filter_checkpoint?: string;
  privacy_filter_detail?: string | null;
  privacy_filter_device: string;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface AiSecurityPolicyRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  user_id?: string | null;
  user_name?: string | null;
  workspace_id?: string | null;
  workspace_name?: string | null;
  app_id?: string | null;
  task_kind?: string | null;
  task_kinds?: string[];
  capability?: string | null;
  provider?: string | null;
  effect: AiSecurityPolicyEffect;
  custom_block_terms: string[];
  created_at: string;
  updated_at: string;
}

export interface AiSecurityExternalTransferException {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  user_id?: string | null;
  user_name?: string | null;
  workspace_id?: string | null;
  workspace_name?: string | null;
  app_id?: string | null;
  task_kind?: string | null;
  task_kinds?: string[];
  capability?: string | null;
  provider?: string | null;
  allowed_blocker_types: AiSecurityExternalTransferBlocker[];
  reason: string;
  expires_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AiSecurityConditionOption {
  value: string;
  label?: string | null;
}

export interface AiSecurityConditionOptions {
  apps: AiSecurityConditionOption[];
  external_apps?: AiSecurityConditionOption[];
  task_kinds: AiSecurityConditionOption[];
  capabilities: AiSecurityConditionOption[];
  providers: AiSecurityConditionOption[];
  content_origins: AiSecurityConditionOption[];
}

export interface AiSecuritySummary {
  external_app_candidates?: AiSecurityExternalAppCandidate[];
  data_protection: AiSecurityDataProtection;
  rules: AiSecurityPolicyRule[];
  exceptions: AiSecurityExternalTransferException[];
  condition_options: AiSecurityConditionOptions;
  active_rule_count: number;
  active_exception_count: number;
  audit_log_count_24h: number;
}

export interface AiSecurityMonitoringTotals {
  security_event_count: number;
  blocked_event_count: number;
  forced_local_count: number;
  masked_event_count: number;
  external_exception_count: number;
  hard_blocker_count: number;
  unique_actor_count: number;
}

export interface AiSecurityMonitoringTrendPoint {
  date: string;
  blocked_count: number;
  forced_local_count: number;
  masked_count: number;
}

export interface AiSecurityMonitoringBreakdownItem {
  key: string;
  label: string;
  count: number;
}

export interface AiSecurityMonitoringUserItem {
  user_id: string;
  full_name: string;
  email: string;
  blocked_count: number;
  forced_local_count: number;
  masked_count: number;
  total_count: number;
  last_blocked_at?: string | null;
}

export interface AiSecurityDetectedValueStat {
  detector: string;
  entity_type: string;
  blocker_type: string;
  detected_value?: string | null;
  value_hash?: string | null;
  occurrence_count: number;
  event_count: number;
}

export interface AiSecurityDetectedValueGroup {
  detector: string;
  entity_type: string;
  blocker_type: string;
  occurrence_count: number;
  event_count: number;
  distinct_value_count: number;
  latest_at?: string | null;
  detail_available: boolean;
}

export interface AiSecurityDetectedValueGroupsResponse {
  items: AiSecurityDetectedValueGroup[];
  total: number;
  limit: number;
  offset: number;
}

export interface AiSecurityDetectedValueDetailsResponse {
  items: AiSecurityDetectedValueStat[];
  total: number;
  limit: number;
  offset: number;
}

export interface AiSecurityMonitoring {
  period_days: number;
  from_date: string;
  to_date: string;
  generated_at: string;
  totals: AiSecurityMonitoringTotals;
  daily_trends: AiSecurityMonitoringTrendPoint[];
  blocked_by_user: AiSecurityMonitoringUserItem[];
  blocked_by_reason: AiSecurityMonitoringBreakdownItem[];
  blocked_by_entity_type: AiSecurityMonitoringBreakdownItem[];
  detected_value_groups: AiSecurityDetectedValueGroup[];
  privacy_filter_groups: AiSecurityDetectedValueGroup[];
  detected_value_rankings: AiSecurityDetectedValueStat[];
  privacy_filter_rankings: AiSecurityDetectedValueStat[];
  blocked_events: AuditLogItem[];
}

export interface AiSecurityRulePayload {
  name: string;
  description: string;
  enabled: boolean;
  user_id?: string | null;
  workspace_id?: string | null;
  app_id?: string | null;
  task_kind?: string | null;
  task_kinds?: string[];
  capability?: string | null;
  provider?: string | null;
  effect: AiSecurityPolicyEffect;
  custom_block_terms: string[];
}

export interface AiSecurityExternalTransferExceptionPayload {
  name: string;
  description: string;
  enabled: boolean;
  user_id?: string | null;
  workspace_id?: string | null;
  app_id?: string | null;
  task_kind?: string | null;
  task_kinds?: string[];
  capability?: string | null;
  provider?: string | null;
  allowed_blocker_types: AiSecurityExternalTransferBlocker[];
  reason: string;
  expires_at: string;
}

export interface AiSecuritySimulationPayload {
  workspace_id?: string | null;
  actor_user_id?: string | null;
  app_id?: string | null;
  task_kind?: string | null;
  capability?: string | null;
  provider?: string | null;
  content_origin?: string | null;
  source_kinds: string[];
  sensitivity_labels: string[];
  sample_text?: string | null;
}

export interface AiSecuritySimulationResult {
  effect: AiSecurityPolicyEffect;
  rule_id?: string | null;
  rule_name?: string | null;
  reason_code: string;
  route_action:
    | 'unchanged'
    | 'blocked'
    | 'audit_only'
    | 'external_exception'
    | 'masked_external';
  allow_external: boolean;
  forced_local: boolean;
  blocked_entity_types: string[];
  external_transfer_blocker_types: AiSecurityExternalTransferBlocker[];
  hard_blocker_types: AiSecurityExternalTransferBlocker[];
  external_transfer_exception_allowed: boolean;
  external_transfer_exception_id?: string | null;
  external_transfer_exception_name?: string | null;
  external_transfer_exception_reason?: string | null;
  pii_hits: string[];
  sensitivity_labels: string[];
  content_origin: string;
  source_kinds: string[];
  custom_block_term_count: number;
  matched_scope: Record<string, string>;
  mask_applied: boolean;
  masked_entity_types: string[];
  masked_text_preview?: string | null;
  privacy_filter_status?: string | null;
}

export interface AdminUsersQuery {
  page?: number;
  page_size?: number;
  q?: string;
}

export interface AdminAuditLogsQuery {
  days?: number;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
  actor_user_id?: string;
  action?: string;
  entity_kind?: string;
  q?: string;
  ai_security_only?: boolean;
  ai_security_blocked_only?: boolean;
}

export type CreatedUserResponse = Omit<
  ApiSchema<'CreatedUserResponse'>,
  'user'
> & {
  user: AuthUser;
};
export type ResetPasswordResponse = ApiSchema<'ResetPasswordResponse'>;

class AdminApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function defaultAdminErrorMessage(
  path: string,
  status: number,
  method: string,
): string {
  if (method === 'DELETE' && path.startsWith('/api/v1/admin/teams/')) {
    return status >= 500
      ? i18n.t('apps:admin.errors.teamDeleteRetry')
      : i18n.t('apps:admin.errors.teamDelete');
  }

  return status >= 500
    ? i18n.t('common:feedback.requestFailedRetry')
    : i18n.t('common:feedback.requestFailed', { status });
}

function resolveAdminErrorMessage(
  path: string,
  status: number,
  method: string,
  payload: unknown,
): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }

  return defaultAdminErrorMessage(path, status, method);
}

async function request<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = init.method ?? 'GET';
  try {
    return await apiFetchJsonWithMappedError<T>(
      path,
      token,
      init,
      (error) =>
        new AdminApiError(
          error.status,
          resolveAdminErrorMessage(path, error.status, method, error.payload),
        ),
    );
  } catch (error) {
    if (error instanceof AdminApiError) {
      throw error;
    }
    throw new AdminApiError(0, i18n.t('apps:admin.errors.connection'));
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
    login_id?: string;
    email: string;
    full_name: string;
    display_name?: string;
    system_roles?: string[];
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
    system_roles?: string[];
    status?: 'active' | 'invited' | 'suspended';
    login_blocked?: boolean;
  },
): Promise<AuthUser> {
  return request<AuthUser>(token, `/api/v1/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteAdminUser(token: string, userId: string): Promise<void> {
  return request<void>(token, `/api/v1/admin/users/${userId}`, {
    method: 'DELETE',
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
  return request<WorkspaceItem>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
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

export function updateWorkspaceMemberRole(
  token: string,
  workspaceId: string,
  subjectType: 'user',
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
  subjectType: 'user',
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

export function listTeams(
  token: string,
  workspaceId?: string,
): Promise<TeamItem[]> {
  const suffix = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : '';
  return request<TeamItem[]>(token, `/api/v1/admin/teams${suffix}`);
}

export function listAuditLogs(
  token: string,
  query: AdminAuditLogsQuery = {},
): Promise<AuditLogsResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') {
      continue;
    }
    params.set(key, String(value));
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return request<AuditLogsResponse>(token, `/api/v1/admin/audit-logs${suffix}`);
}

export function getAdminUsageDashboard(
  token: string,
  query: {
    days?: number;
    from_date?: string;
    to_date?: string;
    limit?: number;
  } = {},
): Promise<AdminUsageDashboard> {
  const params = new URLSearchParams();
  if (query.days) {
    params.set('days', String(query.days));
  }
  if (query.from_date) {
    params.set('from_date', query.from_date);
  }
  if (query.to_date) {
    params.set('to_date', query.to_date);
  }
  if (query.limit) {
    params.set('limit', String(query.limit));
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return request<AdminUsageDashboard>(
    token,
    `/api/v1/admin/usage/dashboard${suffix}`,
  );
}

export function getAdminAiSecuritySummary(
  token: string,
): Promise<AiSecuritySummary> {
  return request<AiSecuritySummary>(token, '/api/v1/admin/ai-security/summary');
}

export function getAdminAiSecurityMonitoring(
  token: string,
  query: {
    days?: number;
    from_date?: string;
    to_date?: string;
    limit?: number;
  } = {},
): Promise<AiSecurityMonitoring> {
  const params = new URLSearchParams();
  if (query.days) {
    params.set('days', String(query.days));
  }
  if (query.from_date) {
    params.set('from_date', query.from_date);
  }
  if (query.to_date) {
    params.set('to_date', query.to_date);
  }
  if (query.limit) {
    params.set('limit', String(query.limit));
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return request<AiSecurityMonitoring>(
    token,
    `/api/v1/admin/ai-security/monitoring${suffix}`,
  );
}

export function getAdminAiSecurityDetectedValueGroups(
  token: string,
  query: {
    days?: number;
    from_date?: string;
    to_date?: string;
    limit?: number;
    offset?: number;
    q?: string;
    privacy_filter?: boolean;
  } = {},
): Promise<AiSecurityDetectedValueGroupsResponse> {
  const params = new URLSearchParams();
  if (query.days) {
    params.set('days', String(query.days));
  }
  if (query.from_date) {
    params.set('from_date', query.from_date);
  }
  if (query.to_date) {
    params.set('to_date', query.to_date);
  }
  if (query.limit) {
    params.set('limit', String(query.limit));
  }
  if (query.offset) {
    params.set('offset', String(query.offset));
  }
  if (query.q?.trim()) {
    params.set('q', query.q.trim());
  }
  if (query.privacy_filter) {
    params.set('privacy_filter', 'true');
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return request<AiSecurityDetectedValueGroupsResponse>(
    token,
    `/api/v1/admin/ai-security/detected-values/groups${suffix}`,
  );
}

export function getAdminAiSecurityDetectedValueDetails(
  token: string,
  query: {
    detector: string;
    entity_type: string;
    blocker_type: string;
    days?: number;
    from_date?: string;
    to_date?: string;
    limit?: number;
    offset?: number;
    q?: string;
  },
): Promise<AiSecurityDetectedValueDetailsResponse> {
  const params = new URLSearchParams();
  params.set('detector', query.detector);
  params.set('entity_type', query.entity_type);
  params.set('blocker_type', query.blocker_type);
  if (query.days) {
    params.set('days', String(query.days));
  }
  if (query.from_date) {
    params.set('from_date', query.from_date);
  }
  if (query.to_date) {
    params.set('to_date', query.to_date);
  }
  if (query.limit) {
    params.set('limit', String(query.limit));
  }
  if (query.offset) {
    params.set('offset', String(query.offset));
  }
  if (query.q?.trim()) {
    params.set('q', query.q.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return request<AiSecurityDetectedValueDetailsResponse>(
    token,
    `/api/v1/admin/ai-security/detected-values/details${suffix}`,
  );
}

export function updateAdminAiSecurityDataProtection(
  token: string,
  payload: {
    custom_block_terms: string[];
    blocker_actions: Partial<
      Record<AiSecurityExternalTransferBlocker, AiSecurityDataProtectionAction>
    >;
    external_app_actions: Partial<
      Record<
        string,
        Partial<
          Record<AiSecurityExternalTransferBlocker, AiSecurityExternalAppAction>
        >
      >
    >;
  },
): Promise<AiSecurityDataProtection> {
  return request<AiSecurityDataProtection>(
    token,
    '/api/v1/admin/ai-security/data-protection',
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function updateAdminAiSecurityEnforcement(
  token: string,
  payload: {
    enforcement_enabled: boolean;
    enforcement_disabled_reason?: string;
  },
): Promise<AiSecurityDataProtection> {
  return request<AiSecurityDataProtection>(
    token,
    '/api/v1/admin/ai-security/enforcement',
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function createAdminAiSecurityRule(
  token: string,
  payload: AiSecurityRulePayload,
): Promise<AiSecurityPolicyRule> {
  return request<AiSecurityPolicyRule>(
    token,
    '/api/v1/admin/ai-security/rules',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateAdminAiSecurityRule(
  token: string,
  ruleId: string,
  payload: AiSecurityRulePayload,
): Promise<AiSecurityPolicyRule> {
  return request<AiSecurityPolicyRule>(
    token,
    `/api/v1/admin/ai-security/rules/${encodeURIComponent(ruleId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteAdminAiSecurityRule(
  token: string,
  ruleId: string,
): Promise<void> {
  return request<void>(
    token,
    `/api/v1/admin/ai-security/rules/${encodeURIComponent(ruleId)}`,
    { method: 'DELETE' },
  );
}

export function createAdminAiSecurityExternalTransferException(
  token: string,
  payload: AiSecurityExternalTransferExceptionPayload,
): Promise<AiSecurityExternalTransferException> {
  return request<AiSecurityExternalTransferException>(
    token,
    '/api/v1/admin/ai-security/exceptions',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateAdminAiSecurityExternalTransferException(
  token: string,
  exceptionId: string,
  payload: AiSecurityExternalTransferExceptionPayload,
): Promise<AiSecurityExternalTransferException> {
  return request<AiSecurityExternalTransferException>(
    token,
    `/api/v1/admin/ai-security/exceptions/${encodeURIComponent(exceptionId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteAdminAiSecurityExternalTransferException(
  token: string,
  exceptionId: string,
): Promise<void> {
  return request<void>(
    token,
    `/api/v1/admin/ai-security/exceptions/${encodeURIComponent(exceptionId)}`,
    { method: 'DELETE' },
  );
}

export function simulateAdminAiSecurityPolicy(
  token: string,
  payload: AiSecuritySimulationPayload,
): Promise<AiSecuritySimulationResult> {
  return request<AiSecuritySimulationResult>(
    token,
    '/api/v1/admin/ai-security/simulate',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function listAdminUsageExcludedUsers(
  token: string,
): Promise<AdminUsageExcludedUserItem[]> {
  return request<AdminUsageExcludedUserItem[]>(
    token,
    '/api/v1/admin/usage/excluded-users',
  );
}

export function replaceAdminUsageExcludedUsers(
  token: string,
  userIds: string[],
): Promise<AdminUsageExcludedUserItem[]> {
  return request<AdminUsageExcludedUserItem[]>(
    token,
    '/api/v1/admin/usage/excluded-users',
    {
      method: 'PUT',
      body: JSON.stringify({ user_ids: userIds }),
    },
  );
}

export function getAdminUsageTargets(
  token: string,
): Promise<AdminUsageTargetsResponse> {
  return request<AdminUsageTargetsResponse>(
    token,
    '/api/v1/admin/usage/targets',
  );
}

export function replaceAdminUsageTargets(
  token: string,
  payload: { user_ids: string[] },
): Promise<AdminUsageTargetsResponse> {
  return request<AdminUsageTargetsResponse>(
    token,
    '/api/v1/admin/usage/targets',
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function listPlatformAppVisibility(
  token: string,
): Promise<PlatformAppVisibilityResponse> {
  return request<PlatformAppVisibilityResponse>(
    token,
    '/api/v1/admin/app-visibility',
  );
}

export function updatePlatformAppVisibility(
  token: string,
  payload: {
    items: Array<{ app_id: string; visible: boolean }>;
  },
): Promise<PlatformAppVisibilityResponse> {
  return request<PlatformAppVisibilityResponse>(
    token,
    '/api/v1/admin/app-visibility',
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function listWorkspaceAppVisibility(
  token: string,
  workspaceId: string,
): Promise<WorkspaceAppVisibilityResponse> {
  return request<WorkspaceAppVisibilityResponse>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/app-visibility`,
  );
}

export function updateWorkspaceAppVisibility(
  token: string,
  workspaceId: string,
  payload: {
    items: Array<{ app_id: string; visibility_override: boolean | null }>;
  },
): Promise<WorkspaceAppVisibilityResponse> {
  return request<WorkspaceAppVisibilityResponse>(
    token,
    `/api/v1/admin/workspaces/${workspaceId}/app-visibility`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function listAdminAppBarCategories(
  token: string,
): Promise<AdminAppBarCategoriesResponse> {
  return request<AdminAppBarCategoriesResponse>(
    token,
    '/api/v1/admin/app-bar-categories',
  );
}

export function createAdminAppBarCategory(
  token: string,
  payload: { title: string; icon_key: string },
): Promise<AdminAppBarCategoriesResponse> {
  return request<AdminAppBarCategoriesResponse>(
    token,
    '/api/v1/admin/app-bar-categories',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateAdminAppBarCategory(
  token: string,
  categoryId: string,
  payload: { title?: string; icon_key?: string },
): Promise<AdminAppBarCategoriesResponse> {
  return request<AdminAppBarCategoriesResponse>(
    token,
    `/api/v1/admin/app-bar-categories/${encodeURIComponent(categoryId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteAdminAppBarCategory(
  token: string,
  categoryId: string,
): Promise<AdminAppBarCategoriesResponse> {
  return request<AdminAppBarCategoriesResponse>(
    token,
    `/api/v1/admin/app-bar-categories/${encodeURIComponent(categoryId)}`,
    { method: 'DELETE' },
  );
}

export function updateAdminAppBarCategoryLayout(
  token: string,
  payload: {
    categories: Array<{
      id: string;
      title: string;
      icon_key: string;
      app_ids: string[];
    }>;
  },
): Promise<AdminAppBarCategoriesResponse> {
  return request<AdminAppBarCategoriesResponse>(
    token,
    '/api/v1/admin/app-bar-categories/layout',
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function listCommunityAdminChannels(
  token: string,
): Promise<AdminCommunityChannelsResponse> {
  return request<AdminCommunityChannelsResponse>(
    token,
    '/api/v1/community/admin/channels',
  );
}

export function createCommunityAdminChannel(
  token: string,
  payload: AdminCommunityChannelInput,
): Promise<AdminCommunityChannelItem> {
  return request<AdminCommunityChannelItem>(
    token,
    '/api/v1/community/admin/channels',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  ).then((channel) => {
    emitCommunityChannelsChanged();
    return channel;
  });
}

export function updateCommunityAdminChannel(
  token: string,
  channelKey: string,
  payload: AdminCommunityChannelInput,
): Promise<AdminCommunityChannelItem> {
  return request<AdminCommunityChannelItem>(
    token,
    `/api/v1/community/admin/channels/${encodeURIComponent(channelKey)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  ).then((channel) => {
    emitCommunityChannelsChanged();
    return channel;
  });
}

export function deleteCommunityAdminChannel(
  token: string,
  channelKey: string,
): Promise<void> {
  return request<void>(
    token,
    `/api/v1/community/admin/channels/${encodeURIComponent(channelKey)}`,
    { method: 'DELETE' },
  ).then((result) => {
    emitCommunityChannelsChanged();
    return result;
  });
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

export function impersonateAdminUser(
  token: string,
  userId: string,
): Promise<AuthSessionResponse> {
  return request<AuthSessionResponse>(
    token,
    authRoutes.impersonateUser(userId),
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  );
}
