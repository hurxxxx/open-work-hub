import { describe, expect, it } from 'vitest';

import type { PmsTask } from '../api/pms-api';
import {
  buildClearAssigneesPatch,
  buildDatePatch,
  buildToggleAssigneePatch,
  canDropTaskInList,
  dropZoneFromPointer,
  selectedAssigneeIds,
} from './list-view-editing-model';

function task(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    id: 'task-1',
    title: 'Task',
    task_number: 1,
    board_position: 1000,
    parent_id: null,
    status: 'todo',
    assignee_id: null,
    assignee_ids: [],
    start_date: null,
    due_date: null,
    ...overrides,
  } as PmsTask;
}

describe('list view editing model', () => {
  it('builds date patches that preserve start/due invariants', () => {
    expect(
      buildDatePatch(
        task({ due_date: '2026-05-30' }),
        'start_date',
        '2026-06-01',
      ),
    ).toEqual({
      due_date: '2026-06-01',
      start_date: '2026-06-01',
    });
    expect(
      buildDatePatch(
        task({ start_date: '2026-06-01' }),
        'due_date',
        '2026-05-30',
      ),
    ).toEqual({
      due_date: '2026-05-30',
      start_date: '2026-05-30',
    });
    expect(buildDatePatch(task(), 'due_date', '')).toEqual({
      due_date: null,
    });
    expect(
      buildDatePatch(task(), 'completed_date', '2026-06-18'),
    ).toEqual({
      completed_date: '2026-06-18',
    });
    expect(buildDatePatch(task(), 'completed_date', '')).toEqual({
      completed_date: null,
    });
  });

  it('selects and toggles assignee patch payloads', () => {
    const singleAssignee = task({ assignee_id: 'user-1', assignee_ids: [] });
    expect(selectedAssigneeIds(singleAssignee)).toEqual(['user-1']);

    expect(buildToggleAssigneePatch(singleAssignee, 'user-2')).toEqual({
      assignee_id: 'user-1',
      assignee_ids: ['user-1', 'user-2'],
    });
    expect(
      buildToggleAssigneePatch(
        task({ assignee_id: 'user-1', assignee_ids: ['user-1', 'user-2'] }),
        'user-1',
      ),
    ).toEqual({
      assignee_id: 'user-2',
      assignee_ids: ['user-2'],
    });
    expect(buildClearAssigneesPatch()).toEqual({
      assignee_id: null,
      assignee_ids: [],
    });
  });

  it('accepts hierarchy drops while preserving visible status groups', () => {
    const todoRoot = task({ id: 'todo-root', status: 'todo' });
    const activeRoot = task({
      id: 'active-root',
      board_position: 2000,
      status: 'active',
    });
    const todoChild = task({
      id: 'todo-child',
      parent_id: todoRoot.id,
      status: 'todo',
    });
    const activeChild = task({
      id: 'active-child',
      parent_id: activeRoot.id,
      status: 'todo',
    });
    const todoSibling = task({
      id: 'todo-sibling',
      board_position: 2000,
      status: 'todo',
    });

    expect(
      canDropTaskInList({
        groupBy: 'none',
        sourceTaskId: todoChild.id,
        targetTask: activeChild,
        tasks: [todoRoot, activeRoot, todoChild, activeChild],
        zone: 'after',
      }),
    ).toBe(true);
    expect(
      canDropTaskInList({
        groupBy: 'none',
        sourceTaskId: todoSibling.id,
        targetTask: todoRoot,
        tasks: [todoRoot, todoSibling],
        zone: 'inside',
      }),
    ).toBe(true);
    expect(
      canDropTaskInList({
        groupBy: 'status',
        sourceTaskId: todoRoot.id,
        targetTask: activeRoot,
        tasks: [todoRoot, activeRoot, todoChild, activeChild],
        zone: 'after',
      }),
    ).toBe(false);
    expect(
      canDropTaskInList({
        groupBy: 'none',
        sourceTaskId: todoRoot.id,
        targetTask: activeRoot,
        tasks: [todoRoot, activeRoot, todoChild, activeChild],
        zone: 'after',
      }),
    ).toBe(true);
  });

  it('chooses the drop zone from pointer position', () => {
    const rect = { height: 40, top: 100 };

    expect(dropZoneFromPointer(rect, 110)).toBe('before');
    expect(dropZoneFromPointer(rect, 121)).toBe('inside');
    expect(dropZoneFromPointer(rect, 132)).toBe('after');
  });
});
