import type { PmsTask, PmsTaskListGroupBy } from '../api/pms-api';

export interface IssueHierarchyInfo {
  childCount: number;
  depth: number;
  parent: PmsTask | null;
  sortKey: number[];
}

export type TaskReorderZone = 'after' | 'before' | 'inside';

export interface TaskBoardPositionUpdate {
  boardPosition: number;
  parentId?: string | null;
  taskId: string;
}

export interface TaskReorderInput {
  groupBy?: PmsTaskListGroupBy;
  sourceTaskId: string;
  targetTaskId: string;
  tasks: PmsTask[];
  zone: TaskReorderZone;
}

function issueOrder(task: PmsTask): number {
  return task.board_position || 0;
}

function compareSortKey(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftValue = left[index] ?? -1;
    const rightValue = right[index] ?? -1;
    if (leftValue !== rightValue) return leftValue - rightValue;
  }
  return 0;
}

function isDescendantOf(
  task: PmsTask,
  ancestorId: string,
  tasksById: Map<string, PmsTask>,
): boolean {
  const visited = new Set<string>();
  let parentId = task.parent_id ?? null;

  while (parentId && !visited.has(parentId)) {
    if (parentId === ancestorId) return true;
    visited.add(parentId);
    parentId = tasksById.get(parentId)?.parent_id ?? null;
  }

  return false;
}

function taskParentId(task: PmsTask): string | null {
  return task.parent_id ?? null;
}

function getDestinationSiblings(
  tasks: PmsTask[],
  sourceTaskId: string,
  destinationParentId: string | null,
): PmsTask[] {
  return sortTasksByHierarchy(
    tasks.filter(
      (task) =>
        task.id !== sourceTaskId && taskParentId(task) === destinationParentId,
    ),
    tasks,
  );
}

function buildSiblingPositionUpdates({
  destinationParentId,
  insertIndex,
  sourceTask,
  tasks,
}: {
  destinationParentId: string | null;
  insertIndex: number;
  sourceTask: PmsTask;
  tasks: PmsTask[];
}): TaskBoardPositionUpdate[] {
  const parentChanged = taskParentId(sourceTask) !== destinationParentId;
  const destinationSiblings = getDestinationSiblings(
    tasks,
    sourceTask.id,
    destinationParentId,
  );
  const safeInsertIndex = Math.max(
    0,
    Math.min(insertIndex, destinationSiblings.length),
  );
  const nextSiblings = [
    ...destinationSiblings.slice(0, safeInsertIndex),
    sourceTask,
    ...destinationSiblings.slice(safeInsertIndex),
  ];
  const sourceIndex = nextSiblings.findIndex(
    (task) => task.id === sourceTask.id,
  );
  const previousTask = nextSiblings[sourceIndex - 1] ?? null;
  const nextTask = nextSiblings[sourceIndex + 1] ?? null;
  const previousPosition = previousTask?.board_position ?? null;
  const nextPosition = nextTask?.board_position ?? null;

  const sourceUpdate = (boardPosition: number): TaskBoardPositionUpdate[] => {
    if (!parentChanged && boardPosition === sourceTask.board_position)
      return [];
    return [
      {
        boardPosition,
        ...(parentChanged ? { parentId: destinationParentId } : {}),
        taskId: sourceTask.id,
      },
    ];
  };

  if (
    previousPosition !== null &&
    nextPosition !== null &&
    nextPosition - previousPosition > 1
  ) {
    return sourceUpdate(Math.floor((previousPosition + nextPosition) / 2));
  }

  if (previousPosition !== null && nextPosition === null) {
    return sourceUpdate(previousPosition + 1000);
  }

  if (
    previousPosition === null &&
    nextPosition !== null &&
    nextPosition > 1000
  ) {
    return sourceUpdate(nextPosition - 1000);
  }

  return nextSiblings
    .map((task, index) => {
      const update: TaskBoardPositionUpdate = {
        boardPosition: (index + 1) * 1000,
        taskId: task.id,
      };
      if (task.id === sourceTask.id && parentChanged) {
        update.parentId = destinationParentId;
      }
      return update;
    })
    .filter((update) => {
      const task = nextSiblings.find((item) => item.id === update.taskId);
      return (
        task &&
        (task.board_position !== update.boardPosition ||
          update.parentId !== undefined)
      );
    });
}

export function buildTaskHierarchy(
  tasks: PmsTask[],
): Map<string, IssueHierarchyInfo> {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  const childCounts = new Map<string, number>();

  for (const task of tasks) {
    if (!task.parent_id) continue;
    childCounts.set(task.parent_id, (childCounts.get(task.parent_id) ?? 0) + 1);
  }

  const info = new Map<string, IssueHierarchyInfo>();

  for (const task of tasks) {
    const path: PmsTask[] = [];
    const visited = new Set<string>();
    let parent = task.parent_id ? (byId.get(task.parent_id) ?? null) : null;

    while (parent && !visited.has(parent.id)) {
      visited.add(parent.id);
      path.unshift(parent);
      parent = parent.parent_id ? (byId.get(parent.parent_id) ?? null) : null;
    }

    info.set(task.id, {
      childCount: childCounts.get(task.id) ?? 0,
      depth: path.length,
      parent: task.parent_id ? (byId.get(task.parent_id) ?? null) : null,
      sortKey: [...path.map(issueOrder), issueOrder(task)],
    });
  }

  return info;
}

export function sortTasksByHierarchy(
  tasks: PmsTask[],
  allIssues: PmsTask[] = tasks,
): PmsTask[] {
  const hierarchy = buildTaskHierarchy(allIssues);
  return Array.from(tasks).sort((left, right) => {
    const leftInfo = hierarchy.get(left.id);
    const rightInfo = hierarchy.get(right.id);
    const keyCompare = compareSortKey(
      leftInfo?.sortKey ?? [issueOrder(left)],
      rightInfo?.sortKey ?? [issueOrder(right)],
    );
    if (keyCompare !== 0) return keyCompare;
    return left.title.localeCompare(right.title);
  });
}

/** Preserve the server-provided sort order while keeping subtasks under parents. */
export function sortTasksByHierarchyUsingInputOrder(
  tasks: PmsTask[],
): PmsTask[] {
  const hierarchy = buildTaskHierarchy(tasks);
  const inputOrder = new Map(tasks.map((task, index) => [task.id, index]));

  const inputSortKey = (task: PmsTask): number[] => {
    const ancestors: PmsTask[] = [];
    const visited = new Set<string>();
    let current: PmsTask | null = task;
    while (current && !visited.has(current.id)) {
      visited.add(current.id);
      ancestors.unshift(current);
      current = hierarchy.get(current.id)?.parent ?? null;
    }
    return ancestors.map((item) => inputOrder.get(item.id) ?? 0);
  };

  return Array.from(tasks).sort((left, right) => {
    const keyCompare = compareSortKey(inputSortKey(left), inputSortKey(right));
    if (keyCompare !== 0) return keyCompare;
    return left.title.localeCompare(right.title);
  });
}

export function getTaskRoot(
  task: PmsTask,
  hierarchy: Map<string, IssueHierarchyInfo>,
): PmsTask {
  let current = task;
  let parent = hierarchy.get(current.id)?.parent ?? null;
  const visited = new Set<string>();

  while (parent && !visited.has(parent.id)) {
    visited.add(parent.id);
    current = parent;
    parent = hierarchy.get(current.id)?.parent ?? null;
  }

  return current;
}

export function getTaskAssigneeIds(task: PmsTask): string[] {
  const assigneeIds = task.assignee_ids?.filter(Boolean) ?? [];
  const effectiveIds =
    assigneeIds.length > 0
      ? assigneeIds
      : task.assignee_id
        ? [task.assignee_id]
        : [];
  return Array.from(new Set(effectiveIds)).sort();
}

export function getTaskAssigneeGroupKey(task: PmsTask): string {
  return JSON.stringify(getTaskAssigneeIds(task));
}

export function getTaskListGroupKey(
  task: PmsTask,
  hierarchy: Map<string, IssueHierarchyInfo>,
  groupBy: PmsTaskListGroupBy,
): string | null {
  if (groupBy === 'none') return null;
  const root = getTaskRoot(task, hierarchy);
  return groupBy === 'status' ? root.status : getTaskAssigneeGroupKey(root);
}

export function getTaskBoardPositionUpdates({
  groupBy = 'none',
  sourceTaskId,
  targetTaskId,
  tasks,
  zone,
}: TaskReorderInput): TaskBoardPositionUpdate[] {
  if (sourceTaskId === targetTaskId) return [];

  const sourceTask = tasks.find((task) => task.id === sourceTaskId);
  const targetTask = tasks.find((task) => task.id === targetTaskId);
  if (!sourceTask || !targetTask) return [];
  const tasksById = new Map(tasks.map((task) => [task.id, task]));
  const destinationParentId =
    zone === 'inside' ? targetTask.id : taskParentId(targetTask);
  if (
    destinationParentId === sourceTask.id ||
    (destinationParentId &&
      isDescendantOf(
        tasksById.get(destinationParentId) ?? targetTask,
        sourceTask.id,
        tasksById,
      ))
  ) {
    return [];
  }

  const hierarchy = buildTaskHierarchy(tasks);
  if (
    groupBy !== 'none' &&
    zone !== 'inside' &&
    getTaskListGroupKey(sourceTask, hierarchy, groupBy) !==
      getTaskListGroupKey(targetTask, hierarchy, groupBy)
  ) {
    return [];
  }

  const withoutSource = getDestinationSiblings(
    tasks,
    sourceTask.id,
    destinationParentId,
  );
  const targetIndex = withoutSource.findIndex(
    (task) => task.id === targetTask.id,
  );
  if (zone !== 'inside' && targetIndex < 0) return [];

  const insertIndex =
    zone === 'inside'
      ? withoutSource.length
      : zone === 'before'
        ? targetIndex
        : targetIndex + 1;
  return buildSiblingPositionUpdates({
    destinationParentId,
    insertIndex,
    sourceTask,
    tasks,
  });
}
