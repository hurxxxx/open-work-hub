import type {
  createTaskListTask,
  PmsTaskListStatus,
  TaskFilterParams,
} from '../api/pms-api';
import { createDefaultTaskFilterParams } from '../api/pms-filters';
import { getDefaultTaskStatus } from './pms-constants';

export type ScopedTaskFilterState = {
  taskListId: string;
  params: TaskFilterParams;
};

export type ScopedTaskSelectionState = {
  taskListId: string;
  ids: Set<string>;
};

export type ScopedStateUpdate<T> = T | ((current: T) => T);

export type InlineTaskCreatePayload = Parameters<typeof createTaskListTask>[2];

export const EMPTY_SELECTED_TASK_IDS = new Set<string>();

export function createDefaultTaskFilterParamsForList(): TaskFilterParams {
  return createDefaultTaskFilterParams();
}

export function selectScopedTaskFilterParams(
  state: ScopedTaskFilterState,
  taskListId: string,
  defaultParams: TaskFilterParams,
): TaskFilterParams {
  return state.taskListId === taskListId ? state.params : defaultParams;
}

export function resolveScopedTaskFilterState(
  current: ScopedTaskFilterState,
  taskListId: string,
  next: ScopedStateUpdate<TaskFilterParams>,
): ScopedTaskFilterState {
  const currentParams =
    current.taskListId === taskListId
      ? current.params
      : createDefaultTaskFilterParams();
  return {
    taskListId,
    params: typeof next === 'function' ? next(currentParams) : next,
  };
}

export function selectScopedTaskSelectionIds(
  state: ScopedTaskSelectionState,
  taskListId: string,
): Set<string> {
  return state.taskListId === taskListId ? state.ids : EMPTY_SELECTED_TASK_IDS;
}

export function resolveScopedTaskSelectionState(
  current: ScopedTaskSelectionState,
  taskListId: string,
  next: ScopedStateUpdate<Set<string>>,
): ScopedTaskSelectionState {
  const currentIds =
    current.taskListId === taskListId ? current.ids : EMPTY_SELECTED_TASK_IDS;
  return {
    taskListId,
    ids: typeof next === 'function' ? next(currentIds) : next,
  };
}

export function buildInlineTaskCreatePayload(
  title: string,
  taskListStatuses: PmsTaskListStatus[],
  parentId: string | null,
): InlineTaskCreatePayload {
  return {
    title,
    description: '',
    status: getDefaultTaskStatus(taskListStatuses),
    priority: 'medium',
    assignee_id: null,
    milestone_id: null,
    start_date: null,
    due_date: null,
    parent_id: parentId,
  };
}
