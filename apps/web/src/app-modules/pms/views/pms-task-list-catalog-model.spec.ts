import { describe, expect, it } from 'vitest';

import type { PmsTaskList } from '../api/pms-api';
import {
  hasArchivedPmsTaskListInFolder,
  listActivePmsTaskListsForSpace,
  reconcilePmsTaskListCatalog,
} from './pms-task-list-catalog-model';

function taskList(
  id: string,
  archived = false,
  teamId = 'space-1',
): PmsTaskList {
  return { id, archived, team_id: teamId } as PmsTaskList;
}

describe('PMS task-list catalog model', () => {
  it('selects only active lists in the requested space', () => {
    const lists = [
      taskList('active'),
      taskList('archived', true),
      taskList('other-space', false, 'space-2'),
    ];

    expect(
      listActivePmsTaskListsForSpace(lists, 'space-1').map((item) => item.id),
    ).toEqual(['active']);
  });

  it('detects archived lists that preserve a folder location', () => {
    const lists = [
      { ...taskList('active'), folder_id: 'folder-1' },
      { ...taskList('archived', true), folder_id: 'folder-2' },
    ];

    expect(hasArchivedPmsTaskListInFolder(lists, 'folder-1')).toBe(false);
    expect(hasArchivedPmsTaskListInFolder(lists, 'folder-2')).toBe(true);
  });

  it('removes archived lists from an active-only catalog', () => {
    expect(
      reconcilePmsTaskListCatalog(
        [taskList('list-1'), taskList('list-2')],
        taskList('list-1', true),
        'active',
      ).map((item) => item.id),
    ).toEqual(['list-2']);
  });

  it('upserts restored lists into an active-only catalog', () => {
    expect(
      reconcilePmsTaskListCatalog(
        [taskList('list-1')],
        taskList('list-2'),
        'active',
      ).map((item) => item.id),
    ).toEqual(['list-2', 'list-1']);
  });

  it('keeps both active and archived lists in an all-state catalog', () => {
    const archived = taskList('list-1', true);
    expect(
      reconcilePmsTaskListCatalog([taskList('list-1')], archived, 'all'),
    ).toEqual([archived]);
  });
});
