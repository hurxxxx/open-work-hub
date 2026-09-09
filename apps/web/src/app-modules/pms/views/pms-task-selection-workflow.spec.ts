import { describe, expect, it } from 'vitest';

import type { PmsTask } from '../api/pms-api';
import {
  createPmsTaskSelectionSearchParams,
  createRequestedPmsTaskListSelectionState,
  findPmsTaskById,
  findPmsTaskInBundles,
  getRequestedPmsTaskId,
  resolveReloadedPmsTaskSelection,
  resolvePmsTaskClosedTransition,
  resolvePmsTaskSelectedTransition,
  resolveRequestedPmsTaskTransition,
  resolveSingleListPmsTaskSelection,
  resolveSingleListPmsTaskDetailTransition,
} from './pms-task-selection-workflow';

function task(
  id: string,
  overrides: Partial<Pick<PmsTask, 'archived' | 'list_id'>> = {},
): PmsTask {
  return {
    id,
    archived: false,
    list_id: 'list-1',
    title: `Task ${id}`,
    ...overrides,
  } as PmsTask;
}

describe('PMS task selection workflow', () => {
  it('reads, sets, and clears the task URL param without dropping siblings', () => {
    const params = new URLSearchParams('view=board&task= task-1 ');

    expect(getRequestedPmsTaskId(params)).toBe('task-1');

    const selected = createPmsTaskSelectionSearchParams(params, 'task-2');
    expect(selected.toString()).toBe('view=board&task=task-2');

    const cleared = createPmsTaskSelectionSearchParams(selected, null);
    expect(cleared.toString()).toBe('view=board');
  });

  it('finds requested tasks in visible collections before callers load detail', () => {
    const visibleTask = task('task-2');
    const bundles = new Map([
      ['list-1', { tasks: [task('task-1')] }],
      ['list-2', { tasks: [visibleTask] }],
    ]);

    expect(findPmsTaskById([task('task-1'), visibleTask], 'task-2')).toBe(
      visibleTask,
    );
    expect(findPmsTaskInBundles(bundles, 'task-2')).toBe(visibleTask);
    expect(findPmsTaskInBundles(bundles, 'missing')).toBeNull();
  });

  it('resolves user select and close transitions with URL patches', () => {
    const selectedTask = task('task-1');
    const selected = resolvePmsTaskSelectedTransition({
      searchParams: new URLSearchParams('view=board'),
      task: selectedTask,
    });

    expect(selected.selectedTask).toBe(selectedTask);
    expect(selected.detailRequest).toBeNull();
    expect(selected.searchParams?.toString()).toBe('view=board&task=task-1');

    const closed = resolvePmsTaskClosedTransition<PmsTask>({
      searchParams: selected.searchParams ?? new URLSearchParams(),
    });
    expect(closed.selectedTask).toBeNull();
    expect(closed.detailRequest).toBeNull();
    expect(closed.searchParams?.toString()).toBe('view=board');
  });

  it('uses visible requested tasks before asking adapters to load detail', () => {
    const visibleTask = task('task-1');

    expect(
      resolveRequestedPmsTaskTransition({
        requestedTaskId: 'task-1',
        visibleTask,
      }),
    ).toEqual({
      detailRequest: null,
      searchParams: null,
      selectedTask: visibleTask,
    });
    expect(
      resolveRequestedPmsTaskTransition({
        requestedTaskId: 'task-2',
        visibleTask: null,
      }),
    ).toEqual({
      detailRequest: { taskId: 'task-2' },
      searchParams: null,
      selectedTask: null,
    });
  });

  it('keeps or clears stale selections based on the view policy', () => {
    const currentTask = task('task-1');

    expect(
      resolveReloadedPmsTaskSelection({
        currentTask,
        missingPolicy: 'preserve',
        tasks: [task('task-2')],
      }),
    ).toBe(currentTask);
    expect(
      resolveReloadedPmsTaskSelection({
        currentTask,
        missingPolicy: 'clear',
        tasks: [task('task-2')],
      }),
    ).toBeNull();
  });

  it('hides single-list selections when the active list changes', () => {
    const selected = task('task-1', { list_id: 'list-1' });

    expect(
      resolveSingleListPmsTaskSelection({
        selectedTaskListId: 'list-1',
        task: selected,
      }),
    ).toBe(selected);
    expect(
      resolveSingleListPmsTaskSelection({
        selectedTaskListId: 'list-2',
        task: selected,
      }),
    ).toBeNull();
  });

  it('builds archived-aware list state for requested task detail', () => {
    expect(
      createRequestedPmsTaskListSelectionState(
        task('active-task', { archived: false, list_id: 'list-1' }),
      ),
    ).toEqual({
      filterParams: { archived_state: 'active' },
      selectedIds: new Set(),
      taskListId: 'list-1',
    });
    expect(
      createRequestedPmsTaskListSelectionState(
        task('archived-task', { archived: true, list_id: 'list-2' }),
      ).filterParams,
    ).toEqual({ archived_state: 'archived' });

    expect(
      resolveSingleListPmsTaskDetailTransition(
        task('archived-task', { archived: true, list_id: 'list-2' }),
      ),
    ).toEqual({
      listState: {
        filterParams: { archived_state: 'archived' },
        selectedIds: new Set(),
        taskListId: 'list-2',
      },
      selectedTask: task('archived-task', {
        archived: true,
        list_id: 'list-2',
      }),
    });
  });
});
