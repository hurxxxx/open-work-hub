import { describe, expect, it } from 'vitest';

import type { PmsTask, PmsTaskListStatus } from '../api/pms-api';
import {
  buildTaskBoardPresentationModel,
  buildTaskTablePresentationModel,
  getVisibleBoardStatusSlugs,
  resolveTaskStatusLabel,
} from './task-list-presentation-model';

describe('task list presentation model', () => {
  it('excludes closed board statuses while keeping active and done columns', () => {
    const customStatuses = [
      status({ slug: 'todo', name: 'Todo', category: 'not_started' }),
      status({ slug: 'doing', name: 'Doing', category: 'active' }),
      status({ slug: 'done', name: 'Done', category: 'done' }),
      status({ slug: 'canceled', name: 'Canceled', category: 'closed' }),
    ];

    expect(getVisibleBoardStatusSlugs(customStatuses)).toEqual([
      'todo',
      'doing',
      'done',
    ]);
    expect(getVisibleBoardStatusSlugs()).toEqual([
      'todo',
      'in_progress',
      'review',
      'done',
    ]);
  });

  it('orders tasks by hierarchy inside each board status', () => {
    const root = task({ id: 'root', title: 'Root task', board_position: 1000 });
    const child = task({
      id: 'child',
      title: 'Child task',
      board_position: 2000,
      parent_id: root.id,
    });
    const sibling = task({
      id: 'sibling',
      title: 'Sibling task',
      board_position: 3000,
    });

    const model = buildTaskBoardPresentationModel({
      taskListStatuses: [status()],
      tasks: [sibling, child, root],
    });

    expect(model.columns[0]?.tasks.map((item) => item.task.id)).toEqual([
      root.id,
      child.id,
      sibling.id,
    ]);
  });

  it('clamps board card and table row depths independently', () => {
    const tasks = nestedTasks(6);

    const boardModel = buildTaskBoardPresentationModel({
      taskListStatuses: [status()],
      tasks,
    });
    const tableModel = buildTaskTablePresentationModel({ tasks });
    const deepestBoardTask = boardModel.columns[0]?.tasks.find(
      (item) => item.task.id === 'task-6',
    );
    const deepestTableRow = tableModel.rows.find(
      (item) => item.task.id === 'task-6',
    );

    expect(deepestBoardTask?.depth).toBe(3);
    expect(deepestTableRow?.cardDepth).toBe(3);
    expect(deepestTableRow?.tableDepth).toBe(5);
  });

  it('hides board parent metadata when the parent is already in the same column', () => {
    const todoParent = task({
      id: 'todo-parent',
      title: 'Todo parent',
      status: 'todo',
    });
    const todoChild = task({
      id: 'todo-child',
      parent_id: todoParent.id,
      status: 'todo',
    });
    const doingParent = task({
      id: 'doing-parent',
      title: 'Doing parent',
      board_position: 3000,
      status: 'doing',
    });
    const todoChildWithDoingParent = task({
      id: 'todo-child-with-doing-parent',
      board_position: 4000,
      parent_id: doingParent.id,
      status: 'todo',
    });

    const model = buildTaskBoardPresentationModel({
      taskListStatuses: [
        status({ slug: 'todo', category: 'not_started' }),
        status({ slug: 'doing', name: 'Doing', category: 'active' }),
      ],
      tasks: [todoChildWithDoingParent, doingParent, todoChild, todoParent],
    });
    const todoColumn = model.columns.find((column) => column.status === 'todo');

    expect(
      todoColumn?.tasks.find((item) => item.task.id === todoChild.id),
    ).toMatchObject({
      parentInColumn: true,
      showParent: false,
    });
    expect(
      todoColumn?.tasks.find(
        (item) => item.task.id === todoChildWithDoingParent.id,
      ),
    ).toMatchObject({
      parent: doingParent,
      parentInColumn: false,
      showParent: true,
    });
  });

  it('centralizes checklist progress display flags', () => {
    const model = buildTaskTablePresentationModel({
      tasks: [
        task({
          checklist_done: 2,
          checklist_total: 3,
        }),
      ],
    });

    expect(model.rows[0]?.progress).toEqual({
      checklistProgressLabel: '2/3',
      hasChecklistProgress: true,
    });
  });

  it('falls back for unknown and empty status labels', () => {
    expect(
      resolveTaskStatusLabel(
        task({
          status: 'ready_for_qa',
          status_label: '',
        }),
      ),
    ).toBe('Ready For Qa');
    expect(
      resolveTaskStatusLabel(
        task({
          status: 'blocked',
          status_label: 'Blocked from task',
        }),
        [status({ slug: 'blocked', name: '' })],
      ),
    ).toBe('Blocked from task');
    expect(
      resolveTaskStatusLabel(
        task({
          status: '',
          status_label: '',
        }),
      ),
    ).toBe('Unknown');

    const boardModel = buildTaskBoardPresentationModel({
      taskListStatuses: [status({ slug: 'blocked', name: '' })],
      tasks: [task({ status: 'blocked', status_label: '' })],
    });

    expect(boardModel.columns[0]?.label).toBe('blocked');
  });
});

function nestedTasks(depth: number): PmsTask[] {
  const tasks: PmsTask[] = [];
  for (let index = 0; index <= depth; index += 1) {
    tasks.push(
      task({
        id: `task-${index}`,
        board_position: (index + 1) * 1000,
        parent_id: index === 0 ? null : `task-${index - 1}`,
        title: `Task ${index}`,
      }),
    );
  }
  return tasks;
}

function task(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    archived: false,
    assignee_id: null,
    assignee_ids: [],
    assignee_name: null,
    assignee_names: [],
    board_position: 1000,
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
    title: 'Task title',
    updated_at: '2026-05-21T00:00:00Z',
    ...overrides,
  };
}

function status(overrides: Partial<PmsTaskListStatus> = {}): PmsTaskListStatus {
  return {
    category: 'not_started',
    color: '#9ca3af',
    id: 'status-1',
    name: 'Todo',
    slug: 'todo',
    sort_order: 1,
    ...overrides,
  } as PmsTaskListStatus;
}
