import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';

export type PmsTaskList = Omit<
  ApiSchema<'TaskListItem'>,
  'folder_id' | 'folder_name'
> & {
  folder_id: string | null;
  folder_name: string | null;
  status_mode: 'inherit' | 'custom';
};

export type PmsTaskListsResponse = Omit<
  ApiSchema<'TaskListsResponse'>,
  'items'
> & {
  items: PmsTaskList[];
};

export type PmsSpace = ApiSchema<'SpaceItem'>;

export type PmsSpaceMember = ApiSchema<'SpaceMemberItem'>;

export type PmsTaskListMember = PmsSpaceMember;

export type PmsSpaceMembersResponse = Omit<
  ApiSchema<'SpaceMemberListResponse'>,
  'items'
> & {
  items: PmsSpaceMember[];
};

export type PmsUserSummary = ApiSchema<'SpaceUserItem'>;

export type PmsMilestone = ApiSchema<'MilestoneItem'>;

export type PmsMilestonesResponse = Omit<
  ApiSchema<'MilestoneListResponse'>,
  'items'
> & {
  items: PmsMilestone[];
};

export type PmsLabel = ApiSchema<'LabelItem'>;

export type PmsTask = Omit<
  ApiSchema<'TaskItem'>,
  'description_blocks' | 'labels' | 'parent_id' | 'recurrence_rule'
> & {
  description_blocks: Record<string, unknown>[] | null;
  parent_id: string | null;
  recurrence_rule: string | null;
  labels: PmsLabel[];
};

export type PmsTasksResponse = Omit<ApiSchema<'TaskItemsResponse'>, 'items'> & {
  items: PmsTask[];
};

export type PersonalPmsTask = PmsTask;
export type PersonalPmsAssignedTasksResponse = PmsTasksResponse;

export type PmsTaskDocLink = ApiSchema<'TaskDocLinkItem'>;

export type PmsTaskDocLinksResponse = Omit<
  ApiSchema<'TaskDocLinksResponse'>,
  'items'
> & {
  items: PmsTaskDocLink[];
};

export type PmsComment = Omit<ApiSchema<'TaskCommentItem'>, 'body_blocks'> & {
  body_blocks: Record<string, unknown>[] | null;
};

export type PmsActivityLog = ApiSchema<'ActivityLogItem'>;

export type PmsActivityLogsResponse = Omit<
  ApiSchema<'ActivityLogListResponse'>,
  'items'
> & {
  items: PmsActivityLog[];
};

export type PmsAttachment = ApiSchema<'AttachmentItem'>;

export type PmsChecklistItem = ApiSchema<'ChecklistItemResponse'>;

export type PmsTaskDetail = Omit<
  ApiSchema<'TaskDetailResponse'>,
  | 'attachments'
  | 'checklist_items'
  | 'comments'
  | 'linked_docs'
  | 'task'
  | 'subtasks'
> & {
  task: PmsTask;
  comments: PmsComment[];
  linked_docs: PmsTaskDocLink[];
  subtasks: PmsTask[];
  attachments: PmsAttachment[];
  checklist_items: PmsChecklistItem[];
};

export type PmsLabelsResponse = Omit<
  ApiSchema<'LabelListResponse'>,
  'items'
> & {
  items: PmsLabel[];
};

export type TaskArchivedState = 'active' | 'archived' | 'all';

export type PmsDashboardStatusCount = ApiSchema<'StatusCountItem'>;

export type PmsDashboardPriorityCount = ApiSchema<'PriorityCountItem'>;

export type PmsDashboardTaskList = ApiSchema<'DashboardTaskListItem'>;

export type PmsDashboardRecentActivity = ApiSchema<'RecentActivityItem'>;

export type PmsDashboardSummary = Omit<
  ApiSchema<'DashboardSummaryResponse'>,
  'lists' | 'priority_counts' | 'recent_activity' | 'status_counts'
> & {
  status_counts: PmsDashboardStatusCount[];
  priority_counts: PmsDashboardPriorityCount[];
  lists: PmsDashboardTaskList[];
  recent_activity: PmsDashboardRecentActivity[];
};

// ── Folders ─────────────────────────────────────────────────────────

export type PmsFolder = ApiSchema<'FolderItem'>;

export type PmsFoldersResponse = Omit<
  ApiSchema<'FolderListResponse'>,
  'items'
> & {
  items: PmsFolder[];
};

// ── Task Templates ──────────────────────────────────────────────────

export type PmsTaskTemplate = Omit<
  ApiSchema<'TaskTemplateItem'>,
  'checklist_items'
> & {
  checklist_items: { text: string }[] | null;
};

export type PmsTaskTemplatesResponse = Omit<
  ApiSchema<'TaskTemplateListResponse'>,
  'items'
> & {
  items: PmsTaskTemplate[];
};

// ── Custom Fields ───────────────────────────────────────────────────

export type PmsCustomField = Omit<
  ApiSchema<'CustomFieldItem'>,
  'field_type'
> & {
  field_type: 'text' | 'number' | 'date' | 'select';
};

export type PmsCustomFieldsResponse = Omit<
  ApiSchema<'CustomFieldListResponse'>,
  'items'
> & {
  items: PmsCustomField[];
};

export type PmsCustomFieldValue = ApiSchema<'CustomFieldValueItem'>;

// ── Task List Custom Statuses ───────────────────────────────────────

export type PmsStatusCategory = 'not_started' | 'active' | 'done' | 'closed';

export type PmsTaskListStatus = Omit<
  ApiSchema<'TaskListStatusItem'>,
  'category'
> & {
  category: PmsStatusCategory;
};

export type PmsTaskListStatusesResponse = {
  mode: 'inherit' | 'custom';
  source: 'space' | 'list';
  items: PmsTaskListStatus[];
};

export type PmsSpaceStatusesResponse = {
  items: PmsTaskListStatus[];
};

export type PmsViewPreferences = ApiSchema<'PmsViewPreferencesResponse'>;

export type PmsTaskListGroupBy = PmsViewPreferences['task_list_group_by'];

export type PmsTaskSortField =
  | 'board_position'
  | 'completed_date'
  | 'created_at'
  | 'due_date'
  | 'start_date';
export type PmsTaskSortDirection = 'asc' | 'desc';
export type PmsTaskSort = {
  field: PmsTaskSortField;
  direction: PmsTaskSortDirection;
};

export const DEFAULT_PMS_TASK_SORT: PmsTaskSort = {
  direction: 'asc',
  field: 'board_position',
};

const PMS_MAX_PAGE_SIZE = 100;
const PMS_ASSIGNED_PAGE_SIZE = 50;

type PmsPageOptions = {
  page?: number;
  pageSize?: number;
};

type PmsTaskListQueryOptions = PmsPageOptions & {
  archived?: boolean;
};

type PmsTaskListPageOptions = PmsPageOptions & {
  sort?: PmsTaskSort;
};

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
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    resolvePmsPath(path),
    token,
    init,
    (error) => new PmsApiError(error.status, error.message),
  );
}

function resolvePmsPath(path: string): string {
  return path;
}

export function listPmsTaskLists(
  token: string,
  teamId?: string,
  options: PmsTaskListQueryOptions = {},
): Promise<PmsTaskListsResponse> {
  const params = new URLSearchParams({
    archived: String(options.archived ?? false),
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 50),
  });
  if (teamId) params.set('team_id', teamId);
  return request<PmsTaskListsResponse>(
    `/api/v1/pms/lists?${params}`,
    token,
    {},
  );
}

export async function listAllPmsTaskLists(
  token: string,
  teamId?: string,
  options: Pick<PmsTaskListQueryOptions, 'archived'> = {},
): Promise<PmsTaskListsResponse> {
  const items: PmsTaskList[] = [];
  let page = 1;
  let lastResponse: PmsTaskListsResponse | null = null;
  do {
    lastResponse = await listPmsTaskLists(token, teamId, {
      archived: options.archived,
      page,
      pageSize: PMS_MAX_PAGE_SIZE,
    });
    items.push(...lastResponse.items);
    if (items.length >= lastResponse.total || lastResponse.items.length === 0) {
      break;
    }
    page += 1;
  } while (lastResponse);

  return {
    items,
    total: lastResponse?.total ?? 0,
    page: 1,
    page_size: PMS_MAX_PAGE_SIZE,
  };
}

export function listSpaces(token: string): Promise<PmsSpace[]> {
  return request<PmsSpace[]>('/api/v1/pms/spaces', token, {});
}

export function listPmsUsers(token: string): Promise<PmsUserSummary[]> {
  return request<PmsUserSummary[]>('/api/v1/pms/users', token, {});
}

export function getPmsViewPreferences(
  token: string,
): Promise<PmsViewPreferences> {
  return request<PmsViewPreferences>('/api/v1/pms/view-preferences', token, {});
}

export function updatePmsViewPreferences(
  token: string,
  payload: PmsViewPreferences,
): Promise<PmsViewPreferences> {
  return request<PmsViewPreferences>('/api/v1/pms/view-preferences', token, {
    body: JSON.stringify(payload),
    method: 'PATCH',
  });
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
  return request<void>(`/api/v1/pms/spaces/${spaceId}`, token, {
    method: 'DELETE',
  });
}

export function listSpaceMembers(
  token: string,
  spaceId: string,
): Promise<PmsSpaceMembersResponse> {
  return request<PmsSpaceMembersResponse>(
    `/api/v1/pms/spaces/${spaceId}/members?page=1&page_size=50`,
    token,
    {},
  );
}

export function addSpaceMember(
  token: string,
  spaceId: string,
  payload: { user_id: string; role: string },
): Promise<PmsSpaceMember> {
  return request<PmsSpaceMember>(
    `/api/v1/pms/spaces/${spaceId}/members`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateSpaceMemberRole(
  token: string,
  spaceId: string,
  userId: string,
  role: string,
): Promise<PmsSpaceMember> {
  return request<PmsSpaceMember>(
    `/api/v1/pms/spaces/${spaceId}/members/${userId}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    },
  );
}

export function removeSpaceMember(
  token: string,
  spaceId: string,
  userId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/pms/spaces/${spaceId}/members/${userId}`,
    token,
    { method: 'DELETE' },
  );
}

export function getPmsTaskList(
  token: string,
  taskListId: string,
): Promise<PmsTaskList> {
  return request<PmsTaskList>(`/api/v1/pms/lists/${taskListId}`, token);
}

export function createPmsTaskList(
  token: string,
  payload: {
    key?: string;
    name: string;
    description?: string;
    team_id?: string | null;
    folder_id?: string | null;
  },
): Promise<PmsTaskList> {
  return request<PmsTaskList>('/api/v1/pms/lists', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updatePmsTaskList(
  token: string,
  taskListId: string,
  payload: {
    name?: string;
    description?: string;
    status?: string;
    archived?: boolean;
    folder_id?: string | null;
    sort_order?: number;
  },
): Promise<PmsTaskList> {
  return request<PmsTaskList>(`/api/v1/pms/lists/${taskListId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deletePmsTaskList(
  token: string,
  taskListId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/lists/${taskListId}`, token, {
    method: 'DELETE',
  });
}

export function reorderPmsTaskLists(
  token: string,
  spaceId: string,
  payload: {
    items: Array<{
      id: string;
      folder_id: string | null;
      sort_order: number;
    }>;
  },
): Promise<void> {
  return request<void>(`/api/v1/pms/spaces/${spaceId}/lists/reorder`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function getPmsDashboardSummary(
  token: string,
  taskListId?: string,
): Promise<PmsDashboardSummary> {
  const suffix = taskListId ? `?list_id=${encodeURIComponent(taskListId)}` : '';
  return request<PmsDashboardSummary>(
    `/api/v1/pms/dashboard/summary${suffix}`,
    token,
  );
}

export function listTaskListMilestones(
  token: string,
  taskListId: string,
): Promise<PmsMilestonesResponse> {
  return request<PmsMilestonesResponse>(
    `/api/v1/pms/lists/${taskListId}/milestones?page=1&page_size=20`,
    token,
  );
}

export function createTaskListMilestone(
  token: string,
  taskListId: string,
  payload: {
    title: string;
    description: string;
    status: string;
    due_date: string | null;
  },
): Promise<PmsMilestone> {
  return request<PmsMilestone>(
    `/api/v1/pms/lists/${taskListId}/milestones`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export interface TaskFilterParams {
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
  archived_state?: TaskArchivedState;
}

export function listTaskListTasks(
  token: string,
  taskListId: string,
  params: TaskFilterParams = {},
  options: PmsTaskListPageOptions = {},
): Promise<PmsTasksResponse> {
  const sort = options.sort ?? DEFAULT_PMS_TASK_SORT;
  const search = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? PMS_MAX_PAGE_SIZE),
    sort_by: sort.field,
    sort_dir: sort.direction,
  });
  if (params.q) search.set('q', params.q);
  if (params.priority && params.priority !== 'all')
    search.set('priority', params.priority);
  if (params.assignee_id) search.set('assignee_id', params.assignee_id);
  if (params.label_id) search.set('label_id', params.label_id);
  if (params.milestone_id) search.set('milestone_id', params.milestone_id);
  if (params.due_date_from) search.set('due_date_from', params.due_date_from);
  if (params.due_date_to) search.set('due_date_to', params.due_date_to);
  if (params.start_date_from)
    search.set('start_date_from', params.start_date_from);
  if (params.start_date_to) search.set('start_date_to', params.start_date_to);
  if (params.archived_state === 'active') search.set('archived', 'false');
  if (params.archived_state === 'archived') search.set('archived', 'true');
  params.status?.forEach((value) => search.append('status', value));

  return request<PmsTasksResponse>(
    `/api/v1/pms/lists/${taskListId}/tasks?${search.toString()}`,
    token,
    {},
  );
}

export async function listAllTaskListTasks(
  token: string,
  taskListId: string,
  params: TaskFilterParams = {},
  options: Pick<PmsTaskListPageOptions, 'sort'> = {},
): Promise<PmsTasksResponse> {
  if (params.status && params.status.length === 0) {
    return { items: [], total: 0, page: 1, page_size: PMS_MAX_PAGE_SIZE };
  }
  const items: PmsTask[] = [];
  let page = 1;
  let lastResponse: PmsTasksResponse | null = null;
  do {
    lastResponse = await listTaskListTasks(token, taskListId, params, {
      page,
      pageSize: PMS_MAX_PAGE_SIZE,
      sort: options.sort,
    });
    items.push(...lastResponse.items);
    if (items.length >= lastResponse.total || lastResponse.items.length === 0) {
      break;
    }
    page += 1;
  } while (lastResponse);

  return {
    items,
    total: lastResponse?.total ?? 0,
    page: 1,
    page_size: PMS_MAX_PAGE_SIZE,
  };
}

export function listAssignedTasks(
  token: string,
  options: {
    limit?: number;
  } & PmsPageOptions = {},
): Promise<PmsTasksResponse> {
  const search = new URLSearchParams();
  if (options.page !== undefined) {
    search.set('page', String(options.page));
    search.set('page_size', String(options.pageSize ?? PMS_ASSIGNED_PAGE_SIZE));
  } else if (options.limit !== undefined) {
    search.set('limit', String(options.limit));
  }
  const query = search.toString();
  return request<PmsTasksResponse>(
    `/api/v1/pms/tasks/assigned${query ? `?${query}` : ''}`,
    token,
    {},
  );
}

export async function listAllAssignedTasks(
  token: string,
): Promise<PmsTasksResponse> {
  const items: PmsTask[] = [];
  let page = 1;
  let lastResponse: PmsTasksResponse | null = null;
  do {
    lastResponse = await listAssignedTasks(token, {
      page,
      pageSize: PMS_ASSIGNED_PAGE_SIZE,
    });
    items.push(...lastResponse.items);
    if (items.length >= lastResponse.total || lastResponse.items.length === 0) {
      break;
    }
    page += 1;
  } while (lastResponse);

  return {
    items,
    total: lastResponse?.total ?? 0,
    page: 1,
    page_size: PMS_ASSIGNED_PAGE_SIZE,
  };
}

export async function listPersonalPmsAssignedTasks(
  token: string,
): Promise<PersonalPmsAssignedTasksResponse> {
  const items: PersonalPmsTask[] = [];
  let page = 1;
  let lastResponse: PersonalPmsAssignedTasksResponse | null = null;
  do {
    lastResponse = await request<PersonalPmsAssignedTasksResponse>(
      `/api/v1/personal-widgets/pms/tasks/assigned?page=${page}&page_size=${PMS_ASSIGNED_PAGE_SIZE}`,
      token,
    );
    items.push(...lastResponse.items);
    if (items.length >= lastResponse.total || lastResponse.items.length === 0) {
      break;
    }
    page += 1;
  } while (lastResponse);

  return {
    items,
    total: lastResponse?.total ?? 0,
    page: 1,
    page_size: PMS_ASSIGNED_PAGE_SIZE,
  };
}

export function listTodayOverdueTasks(
  token: string,
  today: string,
  options: PmsPageOptions = {},
): Promise<PmsTasksResponse> {
  const search = new URLSearchParams({
    today,
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? PMS_ASSIGNED_PAGE_SIZE),
  });
  return request<PmsTasksResponse>(
    `/api/v1/pms/tasks/today-overdue?${search.toString()}`,
    token,
    {},
  );
}

export async function listAllTodayOverdueTasks(
  token: string,
  today: string,
): Promise<PmsTasksResponse> {
  const items: PmsTask[] = [];
  let page = 1;
  let lastResponse: PmsTasksResponse | null = null;
  do {
    lastResponse = await listTodayOverdueTasks(token, today, {
      page,
      pageSize: PMS_ASSIGNED_PAGE_SIZE,
    });
    items.push(...lastResponse.items);
    if (items.length >= lastResponse.total || lastResponse.items.length === 0) {
      break;
    }
    page += 1;
  } while (lastResponse);

  return {
    items,
    total: lastResponse?.total ?? 0,
    page: 1,
    page_size: PMS_ASSIGNED_PAGE_SIZE,
  };
}

export function createTaskListTask(
  token: string,
  taskListId: string,
  payload: {
    title: string;
    description: string;
    description_blocks?: Record<string, unknown>[] | null;
    status: string;
    priority: string;
    assignee_id: string | null;
    milestone_id: string | null;
    start_date?: string | null;
    due_date: string | null;
    parent_id?: string | null;
  },
): Promise<PmsTask> {
  return request<PmsTask>(`/api/v1/pms/lists/${taskListId}/tasks`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getTaskDetail(
  token: string,
  taskId: string,
): Promise<PmsTaskDetail> {
  return request<PmsTaskDetail>(`/api/v1/pms/tasks/${taskId}`, token, {});
}

export function updateTask(
  token: string,
  taskId: string,
  payload: Record<string, unknown>,
): Promise<PmsTask> {
  return request<PmsTask>(`/api/v1/pms/tasks/${taskId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function createTaskComment(
  token: string,
  taskId: string,
  body: string,
  bodyBlocks?: Record<string, unknown>[] | null,
): Promise<PmsComment> {
  return request<PmsComment>(`/api/v1/pms/tasks/${taskId}/comments`, token, {
    method: 'POST',
    body: JSON.stringify({ body, body_blocks: bodyBlocks ?? null }),
  });
}

export function listTaskListLabels(
  token: string,
  taskListId: string,
): Promise<PmsLabelsResponse> {
  return request<PmsLabelsResponse>(
    `/api/v1/pms/lists/${taskListId}/labels?page=1&page_size=100`,
    token,
  );
}

export function createTaskListLabel(
  token: string,
  taskListId: string,
  payload: { name: string; color: string },
): Promise<PmsLabel> {
  return request<PmsLabel>(`/api/v1/pms/lists/${taskListId}/labels`, token, {
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

export function deleteTask(token: string, taskId: string): Promise<void> {
  return request<void>(`/api/v1/pms/tasks/${taskId}`, token, {
    method: 'DELETE',
  });
}

export function listTaskActivityLogs(
  token: string,
  taskId: string,
): Promise<PmsActivityLogsResponse> {
  return request<PmsActivityLogsResponse>(
    `/api/v1/pms/tasks/${taskId}/activity-logs?page=1&page_size=50`,
    token,
    {},
  );
}

export async function uploadAttachment(
  token: string,
  taskId: string,
  file: File,
): Promise<PmsAttachment> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetchJsonWithMappedError<PmsAttachment>(
    resolvePmsPath(`/api/v1/pms/tasks/${taskId}/attachments`),
    token,
    {
      method: 'POST',
      body: formData,
    },
    (error) => new PmsApiError(error.status, error.message),
  );
}

export function deleteAttachment(
  token: string,
  attachmentId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/attachments/${attachmentId}`, token, {
    method: 'DELETE',
  });
}

// ── Linked Docs ─────────────────────────────────────────────────────

export function listTaskDocs(
  token: string,
  taskId: string,
): Promise<PmsTaskDocLinksResponse> {
  return request<PmsTaskDocLinksResponse>(
    `/api/v1/pms/tasks/${taskId}/docs`,
    token,
    {},
  );
}

export function attachTaskDoc(
  token: string,
  taskId: string,
  docId: string,
): Promise<PmsTaskDocLinksResponse> {
  return request<PmsTaskDocLinksResponse>(
    `/api/v1/pms/tasks/${taskId}/docs`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ doc_id: docId }),
    },
  );
}

export function detachTaskDoc(
  token: string,
  taskId: string,
  docId: string,
): Promise<PmsTaskDocLinksResponse> {
  return request<PmsTaskDocLinksResponse>(
    `/api/v1/pms/tasks/${taskId}/docs/${docId}`,
    token,
    { method: 'DELETE' },
  );
}

// ── Bulk Operations ─────────────────────────────────────────────────

export type BulkUpdatePayload = Omit<
  ApiSchema<'BulkUpdateRequest'>,
  'delete' | 'priority' | 'status'
> & {
  status?: string;
  priority?: string;
  delete?: boolean;
};

export type BulkUpdateResult = ApiSchema<'BulkUpdateResponse'>;

export type TaskReorderPayload = Omit<
  ApiSchema<'TaskReorderRequest'>,
  'items'
> & {
  items: ApiSchema<'TaskReorderItem'>[];
};

export type TaskReorderResult = Omit<
  ApiSchema<'TaskReorderResponse'>,
  'items'
> & {
  items: PmsTask[];
};

export function bulkUpdateTasks(
  token: string,
  taskListId: string,
  payload: BulkUpdatePayload,
): Promise<BulkUpdateResult> {
  return request<BulkUpdateResult>(
    `/api/v1/pms/lists/${taskListId}/tasks/bulk`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function reorderTaskListTasks(
  token: string,
  taskListId: string,
  payload: TaskReorderPayload,
): Promise<TaskReorderResult> {
  return request<TaskReorderResult>(
    `/api/v1/pms/lists/${taskListId}/tasks/reorder`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

// ── Checklist ───────────────────────────────────────────────────────

export function createChecklistItem(
  token: string,
  taskId: string,
  payload: { text: string; sort_order?: number },
): Promise<PmsChecklistItem> {
  return request<PmsChecklistItem>(
    `/api/v1/pms/tasks/${taskId}/checklist`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
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

export function deleteChecklistItem(
  token: string,
  itemId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/checklist/${itemId}`, token, {
    method: 'DELETE',
  });
}

// ── Task List Statuses (Custom Workflow) ───────────────────────────

export function listTaskListStatuses(
  token: string,
  taskListId: string,
): Promise<PmsTaskListStatusesResponse> {
  return request<PmsTaskListStatusesResponse>(
    `/api/v1/pms/lists/${taskListId}/statuses`,
    token,
    {},
  );
}

export function updateTaskListStatusMode(
  token: string,
  taskListId: string,
  mode: 'inherit' | 'custom',
): Promise<PmsTaskListStatusesResponse> {
  return request<PmsTaskListStatusesResponse>(
    `/api/v1/pms/lists/${taskListId}/status-mode`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ mode }),
    },
  );
}

export function listSpaceStatuses(
  token: string,
  spaceId: string,
): Promise<PmsSpaceStatusesResponse> {
  return request<PmsSpaceStatusesResponse>(
    `/api/v1/pms/spaces/${spaceId}/statuses`,
    token,
  );
}

export function createSpaceStatus(
  token: string,
  spaceId: string,
  payload: {
    name: string;
    color?: string;
    category?: PmsStatusCategory;
    sort_order?: number;
  },
): Promise<PmsTaskListStatus> {
  return request<PmsTaskListStatus>(
    `/api/v1/pms/spaces/${spaceId}/statuses`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateSpaceStatus(
  token: string,
  statusId: string,
  payload: {
    name?: string;
    color?: string;
    category?: PmsStatusCategory;
    sort_order?: number;
  },
): Promise<PmsTaskListStatus> {
  return request<PmsTaskListStatus>(
    `/api/v1/pms/space-statuses/${statusId}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteSpaceStatus(
  token: string,
  statusId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/space-statuses/${statusId}`, token, {
    method: 'DELETE',
  });
}

export function createTaskListStatus(
  token: string,
  taskListId: string,
  payload: {
    name: string;
    color?: string;
    category?: PmsStatusCategory;
    sort_order?: number;
  },
): Promise<PmsTaskListStatus> {
  return request<PmsTaskListStatus>(
    `/api/v1/pms/lists/${taskListId}/statuses`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateTaskListStatus(
  token: string,
  statusId: string,
  payload: {
    name?: string;
    color?: string;
    category?: PmsStatusCategory;
    sort_order?: number;
  },
): Promise<PmsTaskListStatus> {
  return request<PmsTaskListStatus>(
    `/api/v1/pms/task-list-statuses/${statusId}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteTaskListStatus(
  token: string,
  statusId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/task-list-statuses/${statusId}`, token, {
    method: 'DELETE',
  });
}

// ── Export ──────────────────────────────────────────────────────────

export async function exportTaskListCsv(
  token: string,
  taskListId: string,
): Promise<void> {
  const response = await fetch(
    resolvePmsPath(`/api/v1/pms/lists/${taskListId}/export?format=csv`),
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!response.ok)
    throw new PmsApiError(
      response.status,
      i18n.t('apps:pms.errors.exportFailed'),
    );
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `tasks_export.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Task Templates ─────────────────────────────────────────────────

export function listTaskTemplates(
  token: string,
  taskListId: string,
): Promise<PmsTaskTemplatesResponse> {
  return request<PmsTaskTemplatesResponse>(
    `/api/v1/pms/lists/${taskListId}/templates`,
    token,
    {},
  );
}

export function createTaskTemplate(
  token: string,
  taskListId: string,
  payload: {
    name: string;
    description?: string;
    default_status?: string;
    default_priority?: string;
    checklist_items?: { text: string }[];
  },
): Promise<PmsTaskTemplate> {
  return request<PmsTaskTemplate>(
    `/api/v1/pms/lists/${taskListId}/templates`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteTaskTemplate(
  token: string,
  templateId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/templates/${templateId}`, token, {
    method: 'DELETE',
  });
}

// ── Custom Fields ──────────────────────────────────────────────────

export function listCustomFields(
  token: string,
  taskListId: string,
): Promise<PmsCustomFieldsResponse> {
  return request<PmsCustomFieldsResponse>(
    `/api/v1/pms/lists/${taskListId}/custom-fields`,
    token,
  );
}

export function createCustomField(
  token: string,
  taskListId: string,
  payload: {
    name: string;
    field_type: string;
    options?: string[];
    sort_order?: number;
  },
): Promise<PmsCustomField> {
  return request<PmsCustomField>(
    `/api/v1/pms/lists/${taskListId}/custom-fields`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteCustomField(
  token: string,
  fieldId: string,
): Promise<void> {
  return request<void>(`/api/v1/pms/custom-fields/${fieldId}`, token, {
    method: 'DELETE',
  });
}

export function listTaskCustomFieldValues(
  token: string,
  taskId: string,
): Promise<PmsCustomFieldValue[]> {
  return request<PmsCustomFieldValue[]>(
    `/api/v1/pms/tasks/${taskId}/custom-field-values`,
    token,
  );
}

export function setTaskCustomFieldValue(
  token: string,
  taskId: string,
  payload: { field_id: string; value: string },
): Promise<PmsCustomFieldValue> {
  return request<PmsCustomFieldValue>(
    `/api/v1/pms/tasks/${taskId}/custom-field-values`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

// ── Task Assignees (Multiple) ─────────────────────────────────────

export type PmsTaskAssignee = ApiSchema<'TaskAssigneeItem'>;

export function setTaskAssignees(
  token: string,
  taskId: string,
  userIds: string[],
): Promise<PmsTaskAssignee[]> {
  return request<PmsTaskAssignee[]>(
    `/api/v1/pms/tasks/${taskId}/assignees`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify({ user_ids: userIds }),
    },
  );
}

export type PmsTaskFollower = ApiSchema<'TaskFollowerItem'>;

export function setTaskFollowers(
  token: string,
  taskId: string,
  userIds: string[],
): Promise<PmsTaskFollower[]> {
  return request<PmsTaskFollower[]>(
    `/api/v1/pms/tasks/${taskId}/followers`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify({ user_ids: userIds }),
    },
  );
}

// ── Folders ─────────────────────────────────────────────────────────

export function listFolders(
  token: string,
  teamId?: string,
): Promise<PmsFoldersResponse> {
  const params = teamId ? `?team_id=${encodeURIComponent(teamId)}` : '';
  return request<PmsFoldersResponse>(`/api/v1/pms/folders${params}`, token, {});
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
  return request<void>(`/api/v1/pms/folders/${folderId}`, token, {
    method: 'DELETE',
  });
}
