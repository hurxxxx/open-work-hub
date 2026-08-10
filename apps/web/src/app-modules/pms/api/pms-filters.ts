import type { TaskFilterParams, PmsTask, PmsTaskListStatus } from './pms-api';
import { formatNativeDateInputValue } from '@/src/platform/time/native-date-input';

export const DEFAULT_ISSUE_ARCHIVED_STATE = 'active' as const;

const FALLBACK_COMPLETION_STATUS_SLUGS = new Set([
  'canceled',
  'closed',
  'complete',
  'done',
]);

type TaskStatusDefinition = Pick<PmsTaskListStatus, 'category' | 'slug'>;

function isCompletionStatus(status: TaskStatusDefinition): boolean {
  return status.category === 'done' || status.category === 'closed';
}

export function getCompletionStatusSlugs(
  taskListStatuses: readonly TaskStatusDefinition[],
): string[] {
  if (taskListStatuses.length === 0) {
    return Array.from(FALLBACK_COMPLETION_STATUS_SLUGS);
  }
  return taskListStatuses
    .filter(isCompletionStatus)
    .map((status) => status.slug);
}

export function mergeTaskListStatusesForFilter(
  taskListStatuses: readonly PmsTaskListStatus[],
): PmsTaskListStatus[] {
  const merged = new Map<string, PmsTaskListStatus>();
  for (const status of taskListStatuses) {
    const current = merged.get(status.slug);
    if (!current) {
      merged.set(status.slug, status);
      continue;
    }
    if (!isCompletionStatus(current) && isCompletionStatus(status)) {
      merged.set(status.slug, { ...current, category: status.category });
    }
  }
  return Array.from(merged.values());
}

export function getEffectiveTaskStatusFilter(
  selectedStatuses: readonly string[] | undefined,
  taskListStatuses: readonly TaskStatusDefinition[],
): string[] | undefined {
  if (selectedStatuses !== undefined) {
    return Array.from(selectedStatuses);
  }
  if (taskListStatuses.length === 0) {
    return undefined;
  }
  const completionStatuses = new Set(
    getCompletionStatusSlugs(taskListStatuses),
  );
  return taskListStatuses
    .filter((status) => !completionStatuses.has(status.slug))
    .map((status) => status.slug);
}

export function withEffectiveTaskStatusFilter(
  params: TaskFilterParams,
  taskListStatuses: readonly TaskStatusDefinition[],
): TaskFilterParams {
  const status = getEffectiveTaskStatusFilter(params.status, taskListStatuses);
  return status === undefined ? params : { ...params, status };
}

export function hasSelectedCompletionStatus(
  selectedStatuses: readonly string[] | undefined,
  taskListStatuses: readonly TaskStatusDefinition[],
): boolean {
  const effectiveStatuses = getEffectiveTaskStatusFilter(
    selectedStatuses,
    taskListStatuses,
  );
  if (!effectiveStatuses) return false;
  const completionStatuses = new Set(
    getCompletionStatusSlugs(taskListStatuses),
  );
  return effectiveStatuses.some((status) => completionStatuses.has(status));
}

export function setCompletionStatusesVisible(
  selectedStatuses: readonly string[] | undefined,
  taskListStatuses: readonly TaskStatusDefinition[],
  visible: boolean,
): string[] {
  const effectiveStatuses =
    getEffectiveTaskStatusFilter(selectedStatuses, taskListStatuses) ?? [];
  const completionStatuses = getCompletionStatusSlugs(taskListStatuses);
  const completionStatusSet = new Set(completionStatuses);
  if (!visible) {
    return effectiveStatuses.filter(
      (status) => !completionStatusSet.has(status),
    );
  }

  const next = Array.from(effectiveStatuses);
  const selectedStatusSet = new Set(next);
  for (const status of completionStatuses) {
    if (selectedStatusSet.has(status)) continue;
    next.push(status);
    selectedStatusSet.add(status);
  }
  return next;
}

export function createDefaultTaskFilterParams(
  overrides: Partial<TaskFilterParams> = {},
): TaskFilterParams {
  return {
    archived_state: DEFAULT_ISSUE_ARCHIVED_STATE,
    ...overrides,
  };
}

export function reconcileSelectedTaskIds(
  selectedIds: Set<string>,
  tasks: Array<Pick<PmsTask, 'id'>>,
): Set<string> {
  if (selectedIds.size === 0) {
    return selectedIds;
  }

  let hasStaleSelection = false;
  for (const selectedId of selectedIds) {
    if (!tasks.some((task) => task.id === selectedId)) {
      hasStaleSelection = true;
      break;
    }
  }

  if (!hasStaleSelection) {
    return selectedIds;
  }

  const visibleIds = new Set(tasks.map((task) => task.id));
  return new Set(Array.from(selectedIds).filter((id) => visibleIds.has(id)));
}

/** Apply the effective status selection to the local task collection. */
export function filterDefaultVisibleTasks(
  tasks: readonly PmsTask[],
  taskListStatuses: readonly PmsTaskListStatus[],
  params: Pick<TaskFilterParams, 'status'> = {},
): PmsTask[] {
  const effectiveStatuses = getEffectiveTaskStatusFilter(
    params.status,
    taskListStatuses,
  );
  if (effectiveStatuses !== undefined) {
    const selectedStatuses = new Set(effectiveStatuses);
    return tasks.filter((task) => selectedStatuses.has(task.status));
  }

  const completionStatusSlugs = new Set(
    getCompletionStatusSlugs(taskListStatuses),
  );

  return tasks.filter(
    (task) =>
      !completionStatusSlugs.has(task.status) &&
      task.progress !== 1 &&
      task.progress !== null,
  );
}

export function toLocalDateInputValue(value: Date = new Date()): string {
  return formatNativeDateInputValue(value);
}
