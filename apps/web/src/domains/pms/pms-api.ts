import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

export interface PmsProject {
  id: string;
  key: string;
  name: string;
  description: string;
  status: string;
  archived: boolean;
  team_id: string | null;
  team_name: string | null;
  folder_id: string | null;
  folder_name: string | null;
  role: string;
  progress: number;
  member_count: number;
  milestone_count: number;
  issue_count: number;
  overdue_issue_count: number;
  created_at: string;
  updated_at: string;
}

export type PmsList = PmsProject;

export interface PmsProjectsResponse {
  items: PmsProject[];
  total: number;
  page: number;
  page_size: number;
}

export type PmsListsResponse = PmsProjectsResponse;

export interface PmsProjectMember {
  user_id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  role: string;
  joined_at: string;
}

export interface PmsProjectMembersResponse {
  items: PmsProjectMember[];
  total: number;
  page: number;
  page_size: number;
}

export interface PmsSpace {
  id: string;
  workspace_id: string;
  workspace_key: string;
  key: string;
  name: string;
  description: string;
  member_count: number;
  current_user_role: string | null;
  created_at: string;
  updated_at: string;
}

export interface PmsSpaceMember {
  user_id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  role: string;
  joined_at: string;
}

export interface PmsSpaceMembersResponse {
  items: PmsSpaceMember[];
  total: number;
  page: number;
  page_size: number;
}

export interface PmsUserSummary {
  id: string;
  email: string;
  full_name: string;
}

export interface PmsMilestone {
  id: string;
  list_id: string;
  title: string;
  description: string;
  status: string;
  start_date: string | null;
  due_date: string | null;
  sort_order: number;
  progress: number;
  issue_count: number;
  completed_issue_count: number;
  updated_at: string;
}

export interface PmsMilestonesResponse {
  items: PmsMilestone[];
  total: number;
  page: number;
  page_size: number;
}

export interface PmsLabel {
  id: string;
  name: string;
  color: string;
}

export interface PmsIssue {
  id: string;
  list_id: string;
  reference: string;
  title: string;
  description: string;
  description_blocks: Record<string, unknown>[] | null;
  parent_id: string | null;
  subtask_count: number;
  status: string;
  status_label: string;
  priority: string;
  priority_label: string;
  assignee_id: string | null;
  assignee_name: string | null;
  reporter_id: string;
  reporter_name: string;
  milestone_id: string | null;
  milestone_title: string | null;
  start_date: string | null;
  due_date: string | null;
  board_position: number;
  archived: boolean;
  progress: number | null;
  comments_count: number;
  checklist_total: number;
  checklist_done: number;
  estimate_hours: number | null;
  time_spent_minutes: number;
  recurrence_rule: string | null;
  assignee_ids: string[];
  assignee_names: string[];
  labels: PmsLabel[];
  updated_at: string;
}

export interface PmsIssuesResponse {
  items: PmsIssue[];
  total: number;
  page: number;
  page_size: number;
}

export interface PmsDependency {
  id: string;
  predecessor_kind: string;
  predecessor_id: string;
  successor_kind: string;
  successor_id: string;
  relation_type: string;
}

export interface PmsComment {
  id: string;
  issue_id: string;
  author_id: string;
  author_name: string;
  body: string;
  body_blocks: Record<string, unknown>[] | null;
  created_at: string;
}

export interface PmsActivityLog {
  id: string;
  issue_id: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  field_name: string | null;
  from_value: string | null;
  to_value: string | null;
  message: string;
  created_at: string;
}

export interface PmsActivityLogsResponse {
  items: PmsActivityLog[];
  total: number;
  page: number;
  page_size: number;
}

export interface PmsAttachment {
  id: string;
  issue_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  download_url: string;
  uploaded_by_id: string;
  uploaded_by_name: string;
  created_at: string;
}

export interface PmsChecklistItem {
  id: string;
  issue_id: string;
  text: string;
  completed: boolean;
  sort_order: number;
  created_at: string;
}

export interface PmsTimeEntry {
  id: string;
  issue_id: string;
  user_id: string;
  user_name: string;
  duration_minutes: number;
  description: string;
  entry_date: string;
  created_at: string;
}

export interface PmsIssueDetail {
  issue: PmsIssue;
  comments: PmsComment[];
  dependencies: PmsDependency[];
  subtasks: PmsIssue[];
  attachments: PmsAttachment[];
  checklist_items: PmsChecklistItem[];
  time_entries: PmsTimeEntry[];
}

export interface PmsLabelsResponse {
  items: PmsLabel[];
  total: number;
  page: number;
  page_size: number;
}

export type IssueArchivedState = 'active' | 'archived' | 'all';

export interface PmsDashboardStatusCount {
  status: string;
  label: string;
  count: number;
}

export interface PmsDashboardPriorityCount {
  priority: string;
  label: string;
  count: number;
}

export interface PmsDashboardProject {
  list_id: string;
  key: string;
  name: string;
  progress: number;
  open_issue_count: number;
  overdue_issue_count: number;
  next_due_date: string | null;
}

export interface PmsDashboardRecentActivity {
  id: string;
  issue_id: string;
  issue_reference: string;
  message: string;
  actor_name: string | null;
  created_at: string;
}

export interface PmsDashboardSummary {
  project_count: number;
  active_issue_count: number;
  overdue_issue_count: number;
  my_issue_count: number;
  milestone_due_soon_count: number;
  status_counts: PmsDashboardStatusCount[];
  priority_counts: PmsDashboardPriorityCount[];
  projects: PmsDashboardProject[];
  recent_activity: PmsDashboardRecentActivity[];
}

export interface PmsSpaceDoc {
  id: string;
  team_id: string;
  title: string;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  trashed_at: string | null;
}

export interface PmsSpaceDocsResponse {
  items: PmsSpaceDoc[];
}

export interface PmsSpaceDocPage {
  id: string;
  team_id: string;
  space_doc_id: string;
  parent_id: string | null;
  title: string;
  content_blocks: Record<string, unknown>[] | null;
  sort_order: number;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  trashed_at: string | null;
}

export interface PmsSpaceDocPagesResponse {
  items: PmsSpaceDocPage[];
}

// ── Folders ─────────────────────────────────────────────────────────

export interface PmsFolder {
  id: string;
  team_id: string | null;
  name: string;
  sort_order: number;
  project_count: number;
}

export interface PmsFoldersResponse {
  items: PmsFolder[];
}

// ── Task Templates ──────────────────────────────────────────────────

export interface PmsTaskTemplate {
  id: string;
  list_id: string;
  name: string;
  description: string;
  default_status: string;
  default_priority: string;
  checklist_items: { text: string }[] | null;
  created_at: string;
}

export interface PmsTaskTemplatesResponse {
  items: PmsTaskTemplate[];
}

// ── Custom Fields ───────────────────────────────────────────────────

export interface PmsCustomField {
  id: string;
  list_id: string;
  name: string;
  field_type: 'text' | 'number' | 'date' | 'select';
  options: string[] | null;
  sort_order: number;
}

export interface PmsCustomFieldsResponse {
  items: PmsCustomField[];
}

export interface PmsCustomFieldValue {
  field_id: string;
  value: string;
}

// ── Project Custom Statuses ─────────────────────────────────────────

export interface PmsProjectStatus {
  id: string;
  slug: string;
  name: string;
  color: string;
  category: 'backlog' | 'active' | 'done' | 'canceled';
  sort_order: number;
}

export interface PmsProjectStatusesResponse {
  items: PmsProjectStatus[];
}

class PmsApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  const response = await fetch(resolvePmsPath(path, workspaceSlug), {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new PmsApiError(
      response.status,
      payload?.detail ?? `Request failed with ${response.status}.`,
    );
  }

  return payload as T;
}

function resolvePmsPath(path: string, workspaceSlug?: string | null): string {
  return rewriteWorkspaceApiPath(path, workspaceSlug);
}

export function listPmsProjects(
  token: string,
  teamId?: string,
  workspaceSlug?: string | null,
): Promise<PmsProjectsResponse> {
  const params = new URLSearchParams({ page: '1', page_size: '50' });
  if (teamId) params.set('team_id', teamId);
  return request<PmsProjectsResponse>(`/api/v1/pms/lists?${params}`, token, {}, workspaceSlug);
}

export function listSpaces(token: string): Promise<PmsSpace[]> {
  return request<PmsSpace[]>('/api/v1/pms/spaces', token);
}

export function listPmsUsers(token: string): Promise<PmsUserSummary[]> {
  return request<PmsUserSummary[]>('/api/v1/pms/users', token);
}

export function createSpace(
  token: string,
  payload: { name: string; description?: string },
): Promise<PmsSpace> {
  return request<PmsSpace>('/api/v1/pms/spaces', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateSpace(
  token: string,
  spaceId: string,
  payload: { name?: string; description?: string },
): Promise<PmsSpace> {
  return request<PmsSpace>(`/api/v1/pms/spaces/${spaceId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteSpace(token: string, spaceId: string): Promise<void> {
  return request<void>(`/api/v1/pms/spaces/${spaceId}`, token, { method: 'DELETE' });
}

export function listSpaceMembers(
  token: string,
  spaceId: string,
  workspaceSlug?: string | null,
): Promise<PmsSpaceMembersResponse> {
  return request<PmsSpaceMembersResponse>(
    `/api/v1/pms/spaces/${spaceId}/members?page=1&page_size=50`,
    token,
    {},
    workspaceSlug,
  );
}

export function addSpaceMember(
  token: string,
  spaceId: string,
  payload: { user_id: string; role: string },
  workspaceSlug?: string | null,
): Promise<PmsSpaceMember> {
  return request<PmsSpaceMember>(`/api/v1/pms/spaces/${spaceId}/members`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, workspaceSlug);
}

export function updateSpaceMemberRole(
  token: string,
  spaceId: string,
  userId: string,
  role: string,
  workspaceSlug?: string | null,
): Promise<PmsSpaceMember> {
  return request<PmsSpaceMember>(`/api/v1/pms/spaces/${spaceId}/members/${userId}`, token, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  }, workspaceSlug);
}

export function removeSpaceMember(
  token: string,
  spaceId: string,
  userId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `/api/v1/pms/spaces/${spaceId}/members/${userId}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function getPmsList(token: string, projectId: string): Promise<PmsProject> {
  return request<PmsProject>(`/api/v1/pms/lists/${projectId}`, token);
}

export function createPmsProject(
  token: string,
  payload: { key?: string; name: string; description?: string; team_id?: string | null; folder_id?: string | null },
): Promise<PmsProject> {
  return request<PmsProject>('/api/v1/pms/lists', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export const listPmsLists = listPmsProjects;
export const createPmsList = createPmsProject;

export function getPmsDashboardSummary(
  token: string,
  projectId?: string,
): Promise<PmsDashboardSummary> {
  const suffix = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  return request<PmsDashboardSummary>(`/api/v1/pms/dashboard/summary${suffix}`, token);
}

export function listProjectMembers(
  token: string,
  projectId: string,
): Promise<PmsProjectMembersResponse> {
  return request<PmsProjectMembersResponse>(
    `/api/v1/pms/lists/${projectId}/members?page=1&page_size=20`,
    token,
  );
}

export function updateMemberRole(
  token: string,
  projectId: string,
  userId: string,
  role: string,
): Promise<PmsProjectMember> {
  return request<PmsProjectMember>(`/api/v1/pms/lists/${projectId}/members/${userId}/role`, token, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
}

export function removeProjectMember(token: string, projectId: string, userId: string): Promise<void> {
  return request<void>(`/api/v1/pms/lists/${projectId}/members/${userId}`, token, { method: 'DELETE' });
}

export function listProjectMilestones(
  token: string,
  projectId: string,
): Promise<PmsMilestonesResponse> {
  return request<PmsMilestonesResponse>(
    `/api/v1/pms/lists/${projectId}/milestones?page=1&page_size=20`,
    token,
  );
}

export function createProjectMilestone(
  token: string,
  projectId: string,
  payload: {
    title: string;
    description: string;
    status: string;
    due_date: string | null;
  },
): Promise<PmsMilestone> {
  return request<PmsMilestone>(`/api/v1/pms/lists/${projectId}/milestones`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface IssueFilterParams {
  q?: string;
  status?: string[];
  priority?: string;
  assignee_id?: string;
  label_id?: string;
  milestone_id?: string;
  due_date_from?: string;
  due_date_to?: string;
  start_date_from?: string;
  start_date_to?: string;
  archived_state?: IssueArchivedState;
}

export function listProjectIssues(
  token: string,
  projectId: string,
  params: IssueFilterParams = {},
  workspaceSlug?: string | null,
): Promise<PmsIssuesResponse> {
  const search = new URLSearchParams({
    page: '1',
    page_size: '100',
    sort_by: 'board_position',
    sort_dir: 'asc',
  });
  if (params.q) search.set('q', params.q);
  if (params.priority && params.priority !== 'all') search.set('priority', params.priority);
  if (params.assignee_id) search.set('assignee_id', params.assignee_id);
  if (params.label_id) search.set('label_id', params.label_id);
  if (params.milestone_id) search.set('milestone_id', params.milestone_id);
  if (params.due_date_from) search.set('due_date_from', params.due_date_from);
  if (params.due_date_to) search.set('due_date_to', params.due_date_to);
  if (params.start_date_from) search.set('start_date_from', params.start_date_from);
  if (params.start_date_to) search.set('start_date_to', params.start_date_to);
  if (params.archived_state === 'active') search.set('archived', 'false');
  if (params.archived_state === 'archived') search.set('archived', 'true');
  params.status?.forEach((value) => search.append('status', value));

  return request<PmsIssuesResponse>(
    `/api/v1/pms/lists/${projectId}/issues?${search.toString()}`,
    token,
    {},
    workspaceSlug,
  );
}

export function createProjectIssue(
  token: string,
  projectId: string,
  payload: {
    title: string;
    description: string;
    description_blocks?: Record<string, unknown>[] | null;
    status: string;
    priority: string;
    assignee_id: string | null;
    milestone_id: string | null;
    due_date: string | null;
    parent_id?: string | null;
  },
): Promise<PmsIssue> {
  return request<PmsIssue>(`/api/v1/pms/lists/${projectId}/issues`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getIssueDetail(token: string, issueId: string): Promise<PmsIssueDetail> {
  return request<PmsIssueDetail>(`/api/v1/pms/issues/${issueId}`, token);
}

export function updateIssue(
  token: string,
  issueId: string,
  payload: Record<string, unknown>,
): Promise<PmsIssue> {
  return request<PmsIssue>(`/api/v1/pms/issues/${issueId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function createIssueComment(
  token: string,
  issueId: string,
  body: string,
  bodyBlocks?: Record<string, unknown>[] | null,
): Promise<PmsComment> {
  return request<PmsComment>(`/api/v1/pms/issues/${issueId}/comments`, token, {
    method: 'POST',
    body: JSON.stringify({ body, body_blocks: bodyBlocks ?? null }),
  });
}

export function listProjectLabels(token: string, projectId: string): Promise<PmsLabelsResponse> {
  return request<PmsLabelsResponse>(`/api/v1/pms/lists/${projectId}/labels?page=1&page_size=100`, token);
}

export function createProjectLabel(
  token: string,
  projectId: string,
  payload: { name: string; color: string },
): Promise<PmsLabel> {
  return request<PmsLabel>(`/api/v1/pms/lists/${projectId}/labels`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateLabel(
  token: string,
  labelId: string,
  payload: { name?: string; color?: string },
): Promise<PmsLabel> {
  return request<PmsLabel>(`/api/v1/pms/labels/${labelId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteLabel(token: string, labelId: string): Promise<void> {
  return request<void>(`/api/v1/pms/labels/${labelId}`, token, {
    method: 'DELETE',
  });
}

export function deleteIssue(token: string, issueId: string): Promise<void> {
  return request<void>(`/api/v1/pms/issues/${issueId}`, token, {
    method: 'DELETE',
  });
}

export function listIssueActivityLogs(
  token: string,
  issueId: string,
): Promise<PmsActivityLogsResponse> {
  return request<PmsActivityLogsResponse>(
    `/api/v1/pms/issues/${issueId}/activity-logs?page=1&page_size=50`,
    token,
  );
}

export async function uploadAttachment(
  token: string,
  issueId: string,
  file: File,
): Promise<PmsAttachment> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(resolvePmsPath(`/api/v1/pms/issues/${issueId}/attachments`), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new PmsApiError(response.status, payload?.detail ?? `Upload failed with ${response.status}.`);
  }
  return payload as PmsAttachment;
}

export function deleteAttachment(token: string, attachmentId: string): Promise<void> {
  return request<void>(`/api/v1/pms/attachments/${attachmentId}`, token, { method: 'DELETE' });
}

// ── Dependencies ────────────────────────────────────────────────────

export function createDependency(
  token: string,
  payload: { predecessor_id: string; successor_id: string },
): Promise<PmsDependency> {
  return request<PmsDependency>('/api/v1/pms/dependencies', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteDependency(token: string, dependencyId: string): Promise<void> {
  return request<void>(`/api/v1/pms/dependencies/${dependencyId}`, token, { method: 'DELETE' });
}

// ── Bulk Operations ─────────────────────────────────────────────────

export interface BulkUpdatePayload {
  issue_ids: string[];
  status?: string;
  priority?: string;
  assignee_id?: string | null;
  add_label_ids?: string[];
  remove_label_ids?: string[];
  archived?: boolean;
  delete?: boolean;
}

export interface BulkUpdateResult {
  updated_count: number;
  deleted_count: number;
}

export function bulkUpdateIssues(
  token: string,
  projectId: string,
  payload: BulkUpdatePayload,
): Promise<BulkUpdateResult> {
  return request<BulkUpdateResult>(`/api/v1/pms/lists/${projectId}/issues/bulk`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

// ── Checklist ───────────────────────────────────────────────────────

export function createChecklistItem(
  token: string,
  issueId: string,
  payload: { text: string; sort_order?: number },
): Promise<PmsChecklistItem> {
  return request<PmsChecklistItem>(`/api/v1/pms/issues/${issueId}/checklist`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateChecklistItem(
  token: string,
  itemId: string,
  payload: { text?: string; completed?: boolean; sort_order?: number },
): Promise<PmsChecklistItem> {
  return request<PmsChecklistItem>(`/api/v1/pms/checklist/${itemId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteChecklistItem(token: string, itemId: string): Promise<void> {
  return request<void>(`/api/v1/pms/checklist/${itemId}`, token, { method: 'DELETE' });
}

// ── Time Tracking ───────────────────────────────────────────────────

export function createTimeEntry(
  token: string,
  issueId: string,
  payload: { duration_minutes: number; description: string; entry_date: string },
): Promise<PmsTimeEntry> {
  return request<PmsTimeEntry>(`/api/v1/pms/issues/${issueId}/time-entries`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTimeEntry(
  token: string,
  entryId: string,
  payload: { duration_minutes?: number; description?: string; entry_date?: string },
): Promise<PmsTimeEntry> {
  return request<PmsTimeEntry>(`/api/v1/pms/time-entries/${entryId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteTimeEntry(token: string, entryId: string): Promise<void> {
  return request<void>(`/api/v1/pms/time-entries/${entryId}`, token, { method: 'DELETE' });
}

// ── Notifications ───────────────────────────────────────────────────

export interface PmsNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  reference_type: string;
  reference_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface PmsNotificationsResponse {
  items: PmsNotification[];
  total: number;
  page: number;
  page_size: number;
}

export interface PmsUnreadCountResponse {
  count: number;
}

export function listNotifications(token: string, page = 1): Promise<PmsNotificationsResponse> {
  return request<PmsNotificationsResponse>(`/api/v1/pms/notifications?page=${page}&page_size=20`, token);
}

export function getUnreadNotificationCount(token: string): Promise<PmsUnreadCountResponse> {
  return request<PmsUnreadCountResponse>('/api/v1/pms/notifications/unread-count', token);
}

export function markNotificationRead(token: string, notificationId: string): Promise<PmsNotification> {
  return request<PmsNotification>(`/api/v1/pms/notifications/${notificationId}/read`, token, { method: 'PATCH' });
}

export function markAllNotificationsRead(token: string): Promise<void> {
  return request<void>('/api/v1/pms/notifications/read-all', token, { method: 'PATCH' });
}

// ── Project Statuses (Custom Workflow) ─────────────────────────────

export function listProjectStatuses(
  token: string,
  projectId: string,
): Promise<PmsProjectStatusesResponse> {
  return request<PmsProjectStatusesResponse>(
    `/api/v1/pms/lists/${projectId}/statuses`,
    token,
  );
}

export function createProjectStatus(
  token: string,
  projectId: string,
  payload: { name: string; color?: string; category?: string; sort_order?: number },
): Promise<PmsProjectStatus> {
  return request<PmsProjectStatus>(`/api/v1/pms/lists/${projectId}/statuses`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateProjectStatus(
  token: string,
  statusId: string,
  payload: { name?: string; color?: string; category?: string; sort_order?: number },
): Promise<PmsProjectStatus> {
  return request<PmsProjectStatus>(`/api/v1/pms/project-statuses/${statusId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteProjectStatus(token: string, statusId: string): Promise<void> {
  return request<void>(`/api/v1/pms/project-statuses/${statusId}`, token, { method: 'DELETE' });
}

// ── Export ──────────────────────────────────────────────────────────

export async function exportProjectCsv(token: string, projectId: string): Promise<void> {
  const response = await fetch(resolvePmsPath(`/api/v1/pms/lists/${projectId}/export?format=csv`), {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new PmsApiError(response.status, 'Export failed.');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `issues_export.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Task Templates ─────────────────────────────────────────────────

export function listTaskTemplates(
  token: string,
  projectId: string,
): Promise<PmsTaskTemplatesResponse> {
  return request<PmsTaskTemplatesResponse>(`/api/v1/pms/lists/${projectId}/templates`, token);
}

export function createTaskTemplate(
  token: string,
  projectId: string,
  payload: {
    name: string;
    description?: string;
    default_status?: string;
    default_priority?: string;
    checklist_items?: { text: string }[];
  },
): Promise<PmsTaskTemplate> {
  return request<PmsTaskTemplate>(`/api/v1/pms/lists/${projectId}/templates`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteTaskTemplate(token: string, templateId: string): Promise<void> {
  return request<void>(`/api/v1/pms/templates/${templateId}`, token, { method: 'DELETE' });
}

// ── Custom Fields ──────────────────────────────────────────────────

export function listCustomFields(
  token: string,
  projectId: string,
): Promise<PmsCustomFieldsResponse> {
  return request<PmsCustomFieldsResponse>(`/api/v1/pms/lists/${projectId}/custom-fields`, token);
}

export function createCustomField(
  token: string,
  projectId: string,
  payload: { name: string; field_type: string; options?: string[]; sort_order?: number },
): Promise<PmsCustomField> {
  return request<PmsCustomField>(`/api/v1/pms/lists/${projectId}/custom-fields`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteCustomField(token: string, fieldId: string): Promise<void> {
  return request<void>(`/api/v1/pms/custom-fields/${fieldId}`, token, { method: 'DELETE' });
}

export function listIssueCustomFieldValues(
  token: string,
  issueId: string,
): Promise<PmsCustomFieldValue[]> {
  return request<PmsCustomFieldValue[]>(`/api/v1/pms/issues/${issueId}/custom-field-values`, token);
}

export function setIssueCustomFieldValue(
  token: string,
  issueId: string,
  payload: { field_id: string; value: string },
): Promise<PmsCustomFieldValue> {
  return request<PmsCustomFieldValue>(`/api/v1/pms/issues/${issueId}/custom-field-values`, token, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

// ── Issue Assignees (Multiple) ─────────────────────────────────────

export interface PmsIssueAssignee {
  user_id: string;
  full_name: string;
}

export function setIssueAssignees(
  token: string,
  issueId: string,
  userIds: string[],
): Promise<PmsIssueAssignee[]> {
  return request<PmsIssueAssignee[]>(`/api/v1/pms/issues/${issueId}/assignees`, token, {
    method: 'PUT',
    body: JSON.stringify({ user_ids: userIds }),
  });
}

// ── Folders ─────────────────────────────────────────────────────────

export function listFolders(token: string, teamId?: string): Promise<PmsFoldersResponse> {
  const params = teamId ? `?team_id=${encodeURIComponent(teamId)}` : '';
  return request<PmsFoldersResponse>(`/api/v1/pms/folders${params}`, token);
}

export function createFolder(
  token: string,
  payload: { name: string; team_id?: string | null; sort_order?: number },
): Promise<PmsFolder> {
  return request<PmsFolder>('/api/v1/pms/folders', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateFolder(
  token: string,
  folderId: string,
  payload: { name?: string; sort_order?: number },
): Promise<PmsFolder> {
  return request<PmsFolder>(`/api/v1/pms/folders/${folderId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteFolder(token: string, folderId: string): Promise<void> {
  return request<void>(`/api/v1/pms/folders/${folderId}`, token, { method: 'DELETE' });
}

// ── Space Docs (collections) ────────────────────────────────────────

export function listSpaceDocs(token: string, spaceId: string): Promise<PmsSpaceDocsResponse> {
  return request<PmsSpaceDocsResponse>(`/api/v1/pms/spaces/${spaceId}/docs`, token);
}

export function createSpaceDoc(
  token: string,
  spaceId: string,
  payload: { title: string },
): Promise<PmsSpaceDoc> {
  return request<PmsSpaceDoc>(`/api/v1/pms/spaces/${spaceId}/docs`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateSpaceDoc(
  token: string,
  docId: string,
  payload: { title?: string },
): Promise<PmsSpaceDoc> {
  return request<PmsSpaceDoc>(`/api/v1/pms/space-docs/${docId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteSpaceDoc(token: string, docId: string): Promise<void> {
  return request<void>(`/api/v1/pms/space-docs/${docId}`, token, { method: 'DELETE' });
}

// ── Space Doc Pages ─────────────────────────────────────────────────

export function listSpaceDocPages(token: string, spaceId: string, spaceDocId: string): Promise<PmsSpaceDocPagesResponse> {
  const params = `?space_doc_id=${encodeURIComponent(spaceDocId)}`;
  return request<PmsSpaceDocPagesResponse>(`/api/v1/pms/spaces/${spaceId}/docs/pages${params}`, token);
}

export function createSpaceDocPage(
  token: string,
  spaceId: string,
  payload: { title: string; parent_id?: string | null; space_doc_id: string; content_blocks?: Record<string, unknown>[] | null; sort_order?: number | null },
): Promise<PmsSpaceDocPage> {
  return request<PmsSpaceDocPage>(`/api/v1/pms/spaces/${spaceId}/docs/pages`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getSpaceDocPage(token: string, pageId: string): Promise<PmsSpaceDocPage> {
  return request<PmsSpaceDocPage>(`/api/v1/pms/space-doc-pages/${pageId}`, token);
}

export function updateSpaceDocPage(
  token: string,
  pageId: string,
  payload: { title?: string; parent_id?: string | null; content_blocks?: Record<string, unknown>[] | null; sort_order?: number | null },
): Promise<PmsSpaceDocPage> {
  return request<PmsSpaceDocPage>(`/api/v1/pms/space-doc-pages/${pageId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteSpaceDocPage(token: string, pageId: string): Promise<void> {
  return request<void>(`/api/v1/pms/space-doc-pages/${pageId}`, token, { method: 'DELETE' });
}

// ── Docs Hub (cross-space aggregation) ──────────────────────────

export interface DocsHubItem {
  id: string;
  team_id: string;
  space_name: string;
  title: string;
  page_count: number;
  created_by_id: string;
  created_by_name: string;
  is_favorite: boolean;
  is_private: boolean;
  last_viewed_at: string | null;
  created_at: string;
  updated_at: string;
  trashed_at: string | null;
}

export interface DocsHubResponse {
  items: DocsHubItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface RecentPageItem {
  page_id: string;
  page_title: string;
  doc_id: string;
  doc_title: string;
  team_id: string;
  last_viewed_at: string;
}

export interface FavoriteDocItem {
  id: string;
  title: string;
  team_id: string;
}

export function listDocsHub(
  token: string,
  params: {
    category?: string;
    q?: string;
    sort_by?: string;
    sort_dir?: string;
    page?: number;
    page_size?: number;
  } = {},
): Promise<DocsHubResponse> {
  const qs = new URLSearchParams();
  if (params.category) qs.set('category', params.category);
  if (params.q) qs.set('q', params.q);
  if (params.sort_by) qs.set('sort_by', params.sort_by);
  if (params.sort_dir) qs.set('sort_dir', params.sort_dir);
  if (params.page) qs.set('page', String(params.page));
  if (params.page_size) qs.set('page_size', String(params.page_size));
  return request<DocsHubResponse>(`/api/v1/pms/docs-hub?${qs}`, token);
}

export function toggleDocFavorite(token: string, docId: string): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(`/api/v1/pms/docs-hub/${docId}/favorite`, token, {
    method: 'PATCH',
  });
}

export function toggleDocPrivate(token: string, docId: string): Promise<{ is_private: boolean }> {
  return request<{ is_private: boolean }>(`/api/v1/pms/docs-hub/${docId}/private`, token, {
    method: 'PATCH',
  });
}

export function recordDocView(token: string, docId: string): Promise<void> {
  return request<void>(`/api/v1/pms/docs-hub/${docId}/view`, token, { method: 'POST' });
}

export function listRecentPages(token: string, limit = 10): Promise<RecentPageItem[]> {
  return request<RecentPageItem[]>(`/api/v1/pms/docs-hub/recent-pages?limit=${limit}`, token);
}

export function listFavoriteDocs(token: string): Promise<FavoriteDocItem[]> {
  return request<FavoriteDocItem[]>(`/api/v1/pms/docs-hub/favorites`, token);
}
