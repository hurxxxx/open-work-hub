export interface PmsProject {
  id: string;
  key: string;
  name: string;
  description: string;
  status: string;
  archived: boolean;
  role: string;
  progress: number;
  member_count: number;
  milestone_count: number;
  issue_count: number;
  overdue_issue_count: number;
  created_at: string;
  updated_at: string;
}

export interface PmsProjectsResponse {
  items: PmsProject[];
  total: number;
  page: number;
  page_size: number;
}

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

export interface PmsMilestone {
  id: string;
  project_id: string;
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
  project_id: string;
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

export interface PmsIssueDetail {
  issue: PmsIssue;
  comments: PmsComment[];
  dependencies: PmsDependency[];
  subtasks: PmsIssue[];
}

export interface PmsLabelsResponse {
  items: PmsLabel[];
  total: number;
  page: number;
  page_size: number;
}

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
  project_id: string;
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

class PmsApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
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

export function listPmsProjects(token: string): Promise<PmsProjectsResponse> {
  return request<PmsProjectsResponse>('/api/v1/pms/projects?page=1&page_size=20', token);
}

export function createPmsProject(
  token: string,
  payload: { key: string; name: string; description: string },
): Promise<PmsProject> {
  return request<PmsProject>('/api/v1/pms/projects', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

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
    `/api/v1/pms/projects/${projectId}/members?page=1&page_size=20`,
    token,
  );
}

export function listProjectMilestones(
  token: string,
  projectId: string,
): Promise<PmsMilestonesResponse> {
  return request<PmsMilestonesResponse>(
    `/api/v1/pms/projects/${projectId}/milestones?page=1&page_size=20`,
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
  return request<PmsMilestone>(`/api/v1/pms/projects/${projectId}/milestones`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listProjectIssues(
  token: string,
  projectId: string,
  params: {
    q?: string;
    status?: string[];
    priority?: string;
  } = {},
): Promise<PmsIssuesResponse> {
  const search = new URLSearchParams({
    page: '1',
    page_size: '100',
    sort_by: 'board_position',
    sort_dir: 'asc',
  });
  if (params.q) {
    search.set('q', params.q);
  }
  if (params.priority && params.priority !== 'all') {
    search.set('priority', params.priority);
  }
  params.status?.forEach((value) => search.append('status', value));

  return request<PmsIssuesResponse>(
    `/api/v1/pms/projects/${projectId}/issues?${search.toString()}`,
    token,
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
  return request<PmsIssue>(`/api/v1/pms/projects/${projectId}/issues`, token, {
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
  return request<PmsLabelsResponse>(`/api/v1/pms/projects/${projectId}/labels?page=1&page_size=100`, token);
}

export function createProjectLabel(
  token: string,
  projectId: string,
  payload: { name: string; color: string },
): Promise<PmsLabel> {
  return request<PmsLabel>(`/api/v1/pms/projects/${projectId}/labels`, token, {
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
