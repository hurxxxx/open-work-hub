import type { PmsTaskList } from '../api/pms-api';

export type PmsTaskListCatalogScope = 'active' | 'all';

export function listActivePmsTaskListsForSpace(
  taskLists: PmsTaskList[],
  spaceId: string | null | undefined,
): PmsTaskList[] {
  if (!spaceId) return [];
  return taskLists.filter(
    (taskList) => taskList.team_id === spaceId && !taskList.archived,
  );
}

export function hasArchivedPmsTaskListInFolder(
  taskLists: PmsTaskList[],
  folderId: string,
): boolean {
  return taskLists.some(
    (taskList) => taskList.folder_id === folderId && taskList.archived,
  );
}

export function reconcilePmsTaskListCatalog(
  current: PmsTaskList[],
  taskList: PmsTaskList,
  scope: PmsTaskListCatalogScope,
): PmsTaskList[] {
  const existingIndex = current.findIndex((item) => item.id === taskList.id);
  const withoutTaskList = current.filter((item) => item.id !== taskList.id);

  if (scope === 'active' && taskList.archived) {
    return withoutTaskList;
  }
  if (existingIndex < 0) {
    return [taskList, ...current];
  }

  const next = [...current];
  next[existingIndex] = taskList;
  return next;
}
