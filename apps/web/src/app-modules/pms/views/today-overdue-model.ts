import type { PmsTask } from '../api/pms-api';

const CLOSED_PMS_TASK_STATUSES = new Set([
  'done',
  'canceled',
  'closed',
  'complete',
]);

export type TodayOverdueTaskGroups = {
  overdue: PmsTask[];
  today: PmsTask[];
};

export function isPmsTaskScheduleOpen(status: string): boolean {
  return !CLOSED_PMS_TASK_STATUSES.has(status);
}

export function buildTodayOverdueTaskGroups(
  tasks: PmsTask[],
  todayKey: string,
): TodayOverdueTaskGroups {
  const groups: TodayOverdueTaskGroups = {
    overdue: [],
    today: [],
  };
  for (const task of tasks) {
    if (!task.due_date || !isPmsTaskScheduleOpen(task.status)) {
      continue;
    }
    if (task.due_date < todayKey) {
      groups.overdue.push(task);
    } else if (task.due_date === todayKey) {
      groups.today.push(task);
    }
  }
  return groups;
}
