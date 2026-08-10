import type { PmsTask, PmsTaskList } from '../api/pms-api';

export function buildPmsTaskContextLabel({
  fallbackSpaceName,
  task,
  taskLists,
}: {
  fallbackSpaceName: string;
  task: Pick<PmsTask, 'list_id'>;
  taskLists: readonly PmsTaskList[];
}): string | null {
  const taskList = taskLists.find((item) => item.id === task.list_id);
  if (!taskList) return null;

  return [
    taskList.team_name ?? fallbackSpaceName,
    taskList.folder_name,
    taskList.name,
  ]
    .filter((value): value is string => Boolean(value))
    .join(' / ');
}
