import type { PmsTask, PmsTaskListStatus } from '../api/pms-api';
import { getStatusSlugs } from './pms-constants';
import { buildTaskHierarchy, sortTasksByHierarchy } from './pms-task-hierarchy';

const BOARD_CARD_DEPTH_CAP = 3;
const TABLE_CARD_DEPTH_CAP = 3;
const TABLE_ROW_DEPTH_CAP = 5;
const FALLBACK_BOARD_EXCLUDED_STATUSES = new Set(['canceled', 'complete']);
const UNKNOWN_STATUS_LABEL = 'Unknown';

export type TaskProgressPresentation = {
  checklistProgressLabel: string;
  hasChecklistProgress: boolean;
};

export type BoardTaskPresentation = {
  childCount: number;
  depth: number;
  parent: PmsTask | null;
  parentInColumn: boolean;
  progress: TaskProgressPresentation;
  showParent: boolean;
  task: PmsTask;
};

export type BoardStatusColumnPresentation = {
  label: string;
  status: string;
  taskCount: number;
  tasks: BoardTaskPresentation[];
};

export type TaskBoardPresentationModel = {
  columns: BoardStatusColumnPresentation[];
};

export type TableTaskPresentation = {
  cardDepth: number;
  childCount: number;
  progress: TaskProgressPresentation;
  statusLabel: string;
  tableDepth: number;
  task: PmsTask;
};

export type TaskTablePresentationModel = {
  rows: TableTaskPresentation[];
};

export function buildTaskBoardPresentationModel({
  taskListStatuses,
  tasks,
}: {
  taskListStatuses?: PmsTaskListStatus[];
  tasks: PmsTask[];
}): TaskBoardPresentationModel {
  const hierarchy = buildTaskHierarchy(tasks);

  return {
    columns: getVisibleBoardStatusSlugs(taskListStatuses).map((status) => {
      const statusTasks = tasks.filter((task) => task.status === status);
      const orderedTasks = sortTasksByHierarchy(statusTasks, tasks);

      return {
        label: resolveBoardStatusLabel(status, statusTasks, taskListStatuses),
        status,
        taskCount: statusTasks.length,
        tasks: orderedTasks.map((task) => {
          const taskHierarchy = hierarchy.get(task.id);
          const parent = taskHierarchy?.parent ?? null;
          const parentInColumn = parent ? parent.status === status : false;

          return {
            childCount: taskHierarchy?.childCount ?? 0,
            depth: clampDepth(taskHierarchy?.depth ?? 0, BOARD_CARD_DEPTH_CAP),
            parent,
            parentInColumn,
            progress: buildTaskProgressPresentation(task),
            showParent: Boolean(parent && !parentInColumn),
            task,
          };
        }),
      };
    }),
  };
}

export function buildTaskTablePresentationModel({
  taskListStatuses,
  tasks,
}: {
  taskListStatuses?: PmsTaskListStatus[];
  tasks: PmsTask[];
}): TaskTablePresentationModel {
  const hierarchy = buildTaskHierarchy(tasks);
  const orderedTasks = sortTasksByHierarchy(tasks);

  return {
    rows: orderedTasks.map((task) => {
      const taskHierarchy = hierarchy.get(task.id);
      const depth = taskHierarchy?.depth ?? 0;

      return {
        cardDepth: clampDepth(depth, TABLE_CARD_DEPTH_CAP),
        childCount: taskHierarchy?.childCount ?? 0,
        progress: buildTaskProgressPresentation(task),
        statusLabel: resolveTaskStatusLabel(task, taskListStatuses),
        tableDepth: clampDepth(depth, TABLE_ROW_DEPTH_CAP),
        task,
      };
    }),
  };
}

export function getVisibleBoardStatusSlugs(
  taskListStatuses?: PmsTaskListStatus[],
): string[] {
  return getStatusSlugs(taskListStatuses).filter((status) => {
    const taskListStatus = taskListStatuses?.find(
      (item) => item.slug === status,
    );
    return taskListStatus
      ? taskListStatus.category !== 'closed'
      : !FALLBACK_BOARD_EXCLUDED_STATUSES.has(status);
  });
}

export function resolveTaskStatusLabel(
  task: PmsTask,
  taskListStatuses?: PmsTaskListStatus[],
): string {
  const taskListStatus = taskListStatuses?.find(
    (status) => status.slug === task.status,
  );

  return (
    firstNonBlank(
      taskListStatus?.name,
      task.status_label,
      titleCaseStatusSlug(task.status),
    ) ?? UNKNOWN_STATUS_LABEL
  );
}

function buildTaskProgressPresentation(
  task: PmsTask,
): TaskProgressPresentation {
  return {
    checklistProgressLabel: `${task.checklist_done}/${task.checklist_total}`,
    hasChecklistProgress: task.checklist_total > 0,
  };
}

function resolveBoardStatusLabel(
  status: string,
  tasks: PmsTask[],
  taskListStatuses?: PmsTaskListStatus[],
): string {
  const taskListStatus = taskListStatuses?.find((item) => item.slug === status);

  return (
    firstNonBlank(
      taskListStatus?.name,
      tasks[0]?.status_label,
      boardStatusSlugLabel(status),
    ) ?? UNKNOWN_STATUS_LABEL
  );
}

function boardStatusSlugLabel(status: string): string | null {
  return status ? status.replace('_', ' ') : null;
}

function titleCaseStatusSlug(status: string): string | null {
  if (!status) return null;
  return status
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function firstNonBlank(
  ...values: Array<string | null | undefined>
): string | null {
  return (
    values.find(
      (value) =>
        value !== undefined && value !== null && value.trim().length > 0,
    ) ?? null
  );
}

function clampDepth(depth: number, maxDepth: number): number {
  return Math.min(depth, maxDepth);
}
