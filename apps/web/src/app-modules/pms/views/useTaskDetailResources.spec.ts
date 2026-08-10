import { describe, expect, it } from 'vitest';

import {
  INITIAL_TASK_DETAIL_RESOURCES_STATE,
  taskDetailResourcesReducer,
} from './useTaskDetailResources';
import type { PmsTask } from '../api/pms-api';

function buildTask(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    archived: false,
    assignee_id: null,
    assignee_ids: [],
    assignee_name: null,
    assignee_names: [],
    board_position: 1,
    checklist_done: 0,
    checklist_total: 0,
    comments_count: 0,
    description: '',
    description_blocks: null,
    due_date: null,
    follower_ids: [],
    follower_names: [],
    id: 'task-1',
    labels: [],
    list_id: 'list-1',
    milestone_id: null,
    milestone_title: null,
    parent_id: null,
    priority: 'medium',
    priority_label: 'Medium',
    progress: 0,
    recurrence_rule: null,
    reference: 'AID-1',
    reporter_id: 'user-1',
    reporter_name: 'Reporter',
    start_date: null,
    status: 'todo',
    status_label: 'Todo',
    subtask_count: 0,
    title: 'Task',
    updated_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

describe('taskDetailResourcesReducer', () => {
  it('loads task detail resources and filters archived subtasks', () => {
    const openSubtask = buildTask({ id: 'subtask-open' });
    const archivedSubtask = buildTask({
      archived: true,
      id: 'subtask-archived',
    });

    const state = taskDetailResourcesReducer(
      INITIAL_TASK_DETAIL_RESOURCES_STATE,
      {
        type: 'loaded',
        detail: {
          attachments: [],
          checklist_items: [],
          comments: [],
          linked_docs: [],
          subtasks: [openSubtask, archivedSubtask],
          task: buildTask(),
        },
        logs: {
          items: [],
          page: 1,
          page_size: 50,
          total: 0,
        },
      },
    );

    expect(state.subtasks).toEqual([openSubtask]);
  });

  it('applies resource updater functions without touching sibling state', () => {
    const state = taskDetailResourcesReducer(
      {
        ...INITIAL_TASK_DETAIL_RESOURCES_STATE,
        subtasks: [buildTask({ id: 'subtask-1' })],
      },
      {
        type: 'subtasks',
        value: (current) => [...current, buildTask({ id: 'subtask-2' })],
      },
    );

    expect(state.subtasks.map((task) => task.id)).toEqual([
      'subtask-1',
      'subtask-2',
    ]);
    expect(state.loading).toBe(true);
  });
});
