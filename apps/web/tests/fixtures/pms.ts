import type {
  PmsTask,
  PmsTaskListStatus,
} from '../../src/app-modules/pms/api/pms-api';

export function createPmsTask(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    id: 'task-1',
    list_id: 'list-1',
    reference: 'TASK-1',
    title: 'Task',
    description: '',
    description_blocks: null,
    parent_id: null,
    subtask_count: 0,
    status: 'todo',
    status_label: 'To do',
    priority: 'medium',
    priority_label: 'Medium',
    assignee_id: null,
    assignee_name: null,
    assignee_ids: [],
    assignee_names: [],
    follower_ids: [],
    follower_names: [],
    reporter_id: 'user-1',
    reporter_name: 'Member',
    milestone_id: null,
    milestone_title: null,
    start_date: null,
    due_date: null,
    completed_date: null,
    board_position: 1000,
    archived: false,
    progress: 0,
    comments_count: 0,
    checklist_total: 0,
    checklist_done: 0,
    recurrence_rule: null,
    labels: [],
    updated_at: '2026-09-08T00:00:00Z',
    ...overrides,
  };
}

export function createPmsStatus(
  overrides: Partial<PmsTaskListStatus> = {},
): PmsTaskListStatus {
  return {
    id: 'status-1',
    slug: 'todo',
    name: 'To do',
    category: 'not_started',
    color: '#94a3b8',
    sort_order: 0,
    ...overrides,
  };
}
