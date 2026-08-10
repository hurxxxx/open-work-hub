import type { PmsTask, PmsTaskListGroupBy } from '../api/pms-api';
import { getTaskBoardPositionUpdates } from './pms-task-hierarchy';

export type TaskDateField = 'completed_date' | 'due_date' | 'start_date';
export type TaskDropZone = 'after' | 'before' | 'inside';

export function selectedAssigneeIds(task: PmsTask): string[] {
  if (task.assignee_ids?.length) {
    return task.assignee_ids;
  }
  return task.assignee_id ? [task.assignee_id] : [];
}

export function buildToggleAssigneePatch(
  task: PmsTask,
  userId: string,
): { assignee_id: string | null; assignee_ids: string[] } {
  const selected = new Set(selectedAssigneeIds(task));
  if (selected.has(userId)) {
    selected.delete(userId);
  } else {
    selected.add(userId);
  }
  const nextIds = Array.from(selected);
  return {
    assignee_id: nextIds[0] ?? null,
    assignee_ids: nextIds,
  };
}

export function buildClearAssigneesPatch(): {
  assignee_id: null;
  assignee_ids: [];
} {
  return { assignee_id: null, assignee_ids: [] };
}

export function buildDatePatch(
  task: PmsTask,
  field: TaskDateField,
  value: string,
): Record<string, string | null> {
  const payload: Record<string, string | null> = { [field]: value || null };
  if (
    value &&
    field === 'start_date' &&
    task.due_date &&
    value > task.due_date
  ) {
    payload.due_date = value;
  }
  if (
    value &&
    field === 'due_date' &&
    task.start_date &&
    value < task.start_date
  ) {
    payload.start_date = value;
  }
  return payload;
}

export function canDropTaskInList({
  groupBy,
  sourceTaskId,
  targetTask,
  tasks,
  zone,
}: {
  groupBy: PmsTaskListGroupBy;
  sourceTaskId: string;
  targetTask: PmsTask;
  tasks: PmsTask[];
  zone?: TaskDropZone;
}): boolean {
  if (sourceTaskId === targetTask.id) {
    return false;
  }
  const zones = zone ? [zone] : (['inside', 'before', 'after'] as const);
  return zones.some(
    (candidateZone) =>
      getTaskBoardPositionUpdates({
        groupBy,
        sourceTaskId,
        targetTaskId: targetTask.id,
        tasks,
        zone: candidateZone,
      }).length > 0,
  );
}

export function dropZoneFromPointer(
  rect: Pick<DOMRect, 'height' | 'top'>,
  clientY: number,
): TaskDropZone {
  const offset = clientY - rect.top;
  if (offset <= rect.height * 0.25) return 'before';
  if (offset >= rect.height * 0.75) return 'after';
  return 'inside';
}
