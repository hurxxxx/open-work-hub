import { describe, expect, it } from 'vitest';

import type { PmsTask, PmsTaskList } from '../api/pms-api';
import {
  INITIAL_TASK_PICKER_MODAL_STATE,
  TASK_PICKER_RESULT_LIMIT,
  buildTaskPickerTaskParams,
  getVisibleTaskPickerTasks,
  taskPickerModalReducer,
} from './task-picker-model';

function taskList(id: string): PmsTaskList {
  return {
    id,
    key: id.toUpperCase(),
    name: `Task list ${id}`,
  } as PmsTaskList;
}

function task(id: string): PmsTask {
  return {
    id,
    title: `Task ${id}`,
    reference: `PMS-${id}`,
    status_label: 'Open',
  } as PmsTask;
}

describe('task picker model', () => {
  it('resets and selects the first loaded task list', () => {
    const dirtyState = {
      ...INITIAL_TASK_PICKER_MODAL_STATE,
      selectedTaskListId: 'old-list',
      tasks: [task('old-task')],
      query: 'old',
      loading: true,
      submittingId: 'old-task',
      error: 'Failed',
    };

    expect(
      taskPickerModalReducer(dirtyState, { type: 'resetForOpen' }),
    ).toEqual(INITIAL_TASK_PICKER_MODAL_STATE);
    expect(
      taskPickerModalReducer(dirtyState, {
        type: 'resetForOpen',
        selectedTaskListId: 'fixed-list',
      }),
    ).toMatchObject({
      selectedTaskListId: 'fixed-list',
      tasks: [],
      query: '',
      loading: false,
      submittingId: null,
      error: null,
    });

    expect(
      taskPickerModalReducer(INITIAL_TASK_PICKER_MODAL_STATE, {
        type: 'taskListsLoaded',
        taskLists: [taskList('list-1'), taskList('list-2')],
      }),
    ).toMatchObject({
      selectedTaskListId: 'list-1',
      taskLists: [taskList('list-1'), taskList('list-2')],
    });
  });

  it('clears task loading state when task loading becomes idle or fails', () => {
    const loadingState = taskPickerModalReducer(INITIAL_TASK_PICKER_MODAL_STATE, {
      type: 'tasksLoading',
    });

    expect(loadingState.loading).toBe(true);

    expect(taskPickerModalReducer(loadingState, { type: 'tasksIdle' })).toMatchObject({
      loading: false,
      tasks: [],
    });
    expect(
      taskPickerModalReducer(loadingState, {
        type: 'tasksFailed',
        message: 'Task load failed',
      }),
    ).toMatchObject({
      error: 'Task load failed',
      loading: false,
      tasks: [],
    });
  });

  it('tracks pick progress and clears submitting state after success or failure', () => {
    const pickingState = taskPickerModalReducer(INITIAL_TASK_PICKER_MODAL_STATE, {
      type: 'pickStarted',
      taskId: 'task-1',
    });

    expect(pickingState).toMatchObject({ submittingId: 'task-1', error: null });
    expect(taskPickerModalReducer(pickingState, { type: 'pickFinished' }).submittingId).toBeNull();
    expect(
      taskPickerModalReducer(pickingState, {
        type: 'pickFailed',
        message: 'Attach failed',
      }),
    ).toMatchObject({ submittingId: null, error: 'Attach failed' });
  });

  it('builds active task query params with trimmed optional search', () => {
    expect(buildTaskPickerTaskParams('   ')).toEqual({
      archived_state: 'active',
      q: undefined,
    });
    expect(buildTaskPickerTaskParams('  motor spec  ')).toEqual({
      archived_state: 'active',
      q: 'motor spec',
    });
  });

  it('filters excluded tasks and limits visible rows after exclusion', () => {
    const tasks = Array.from({ length: TASK_PICKER_RESULT_LIMIT + 3 }, (_, index) => task(String(index)));

    const visible = getVisibleTaskPickerTasks(tasks, ['0', '2']);

    expect(visible).toHaveLength(TASK_PICKER_RESULT_LIMIT);
    expect(visible.map((item) => item.id)).not.toContain('0');
    expect(visible.map((item) => item.id)).not.toContain('2');
    expect(visible[0]?.id).toBe('1');
    expect(visible[visible.length - 1]?.id).toBe('51');
  });
});
