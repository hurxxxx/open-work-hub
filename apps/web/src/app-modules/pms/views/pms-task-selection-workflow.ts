import type { PmsTask, TaskFilterParams } from '../api/pms-api';
import { createDefaultTaskFilterParams } from '../api/pms-filters';

export const PMS_TASK_SEARCH_PARAM = 'task';

export type PmsTaskSelectionMissingPolicy = 'clear' | 'preserve';

export type PmsTaskBundleLike<TTask extends Pick<PmsTask, 'id'>> = {
  tasks: readonly TTask[];
};

export type PmsTaskBundleEntries<TTask extends Pick<PmsTask, 'id'>> =
  readonly (readonly [string, PmsTaskBundleLike<TTask>])[];

export type PmsTaskBundleSource<TTask extends Pick<PmsTask, 'id'>> =
  | ReadonlyMap<string, PmsTaskBundleLike<TTask>>
  | PmsTaskBundleEntries<TTask>;

export type PmsRequestedTaskListSelectionState = {
  filterParams: TaskFilterParams;
  selectedIds: Set<string>;
  taskListId: string;
};

export type PmsTaskDetailRequest = {
  taskId: string;
};

export type PmsTaskSelectionTransition<TTask extends Pick<PmsTask, 'id'>> = {
  detailRequest: PmsTaskDetailRequest | null;
  searchParams: URLSearchParams | null;
  selectedTask: TTask | null;
};

export type PmsSingleListTaskDetailTransition = {
  listState: PmsRequestedTaskListSelectionState;
  selectedTask: PmsTask;
};

export function getRequestedPmsTaskId(
  searchParams: URLSearchParams,
): string | null {
  const taskId = searchParams.get(PMS_TASK_SEARCH_PARAM)?.trim();
  return taskId || null;
}

export function createPmsTaskSelectionSearchParams(
  searchParams: URLSearchParams,
  taskId: string | null,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  if (taskId) {
    next.set(PMS_TASK_SEARCH_PARAM, taskId);
  } else {
    next.delete(PMS_TASK_SEARCH_PARAM);
  }
  return next;
}

export function resolvePmsTaskSelectedTransition<
  TTask extends Pick<PmsTask, 'id'>,
>({
  searchParams,
  task,
}: {
  searchParams: URLSearchParams;
  task: TTask;
}): PmsTaskSelectionTransition<TTask> {
  return {
    detailRequest: null,
    searchParams: createPmsTaskSelectionSearchParams(searchParams, task.id),
    selectedTask: task,
  };
}

export function resolvePmsTaskClosedTransition<
  TTask extends Pick<PmsTask, 'id'>,
>({
  searchParams,
}: {
  searchParams: URLSearchParams;
}): PmsTaskSelectionTransition<TTask> {
  return {
    detailRequest: null,
    searchParams: createPmsTaskSelectionSearchParams(searchParams, null),
    selectedTask: null,
  };
}

export function findPmsTaskById<TTask extends Pick<PmsTask, 'id'>>(
  tasks: readonly TTask[],
  taskId: string | null,
): TTask | null {
  if (!taskId) {
    return null;
  }
  return tasks.find((task) => task.id === taskId) ?? null;
}

function isPmsTaskBundleEntries<TTask extends Pick<PmsTask, 'id'>>(
  bundles: PmsTaskBundleSource<TTask>,
): bundles is PmsTaskBundleEntries<TTask> {
  return Array.isArray(bundles);
}

export function findPmsTaskInBundles<TTask extends Pick<PmsTask, 'id'>>(
  bundles: PmsTaskBundleSource<TTask>,
  taskId: string | null,
): TTask | null {
  if (!taskId) {
    return null;
  }

  if (isPmsTaskBundleEntries(bundles)) {
    for (const [, bundle] of bundles) {
      const task = findPmsTaskById(bundle.tasks, taskId);
      if (task) {
        return task;
      }
    }
    return null;
  }

  for (const bundle of bundles.values()) {
    const task = findPmsTaskById(bundle.tasks, taskId);
    if (task) {
      return task;
    }
  }
  return null;
}

export function resolveRequestedPmsTaskTransition<
  TTask extends Pick<PmsTask, 'id'>,
>({
  requestedTaskId,
  visibleTask,
}: {
  requestedTaskId: string | null;
  visibleTask: TTask | null;
}): PmsTaskSelectionTransition<TTask> {
  if (!requestedTaskId) {
    return {
      detailRequest: null,
      searchParams: null,
      selectedTask: null,
    };
  }
  if (visibleTask) {
    return {
      detailRequest: null,
      searchParams: null,
      selectedTask: visibleTask,
    };
  }
  return {
    detailRequest: { taskId: requestedTaskId },
    searchParams: null,
    selectedTask: null,
  };
}

export function resolveReloadedPmsTaskSelection<
  TTask extends Pick<PmsTask, 'id'>,
>({
  currentTask,
  missingPolicy,
  tasks,
}: {
  currentTask: TTask | null;
  missingPolicy: PmsTaskSelectionMissingPolicy;
  tasks: readonly TTask[];
}): TTask | null {
  if (!currentTask) {
    return null;
  }
  return (
    findPmsTaskById(tasks, currentTask.id) ??
    (missingPolicy === 'preserve' ? currentTask : null)
  );
}

export function resolveSingleListPmsTaskSelection<
  TTask extends Pick<PmsTask, 'list_id'>,
>({
  selectedTaskListId,
  task,
}: {
  selectedTaskListId: string;
  task: TTask | null;
}): TTask | null {
  if (!task || task.list_id !== selectedTaskListId) {
    return null;
  }
  return task;
}

export function createRequestedPmsTaskListSelectionState(
  task: Pick<PmsTask, 'archived' | 'list_id'>,
): PmsRequestedTaskListSelectionState {
  return {
    filterParams: createDefaultTaskFilterParams({
      archived_state: task.archived ? 'archived' : 'active',
    }),
    selectedIds: new Set(),
    taskListId: task.list_id,
  };
}

export function resolveSingleListPmsTaskDetailTransition(
  task: PmsTask,
): PmsSingleListTaskDetailTransition {
  return {
    listState: createRequestedPmsTaskListSelectionState(task),
    selectedTask: task,
  };
}
