import { describe, expect, it } from 'vitest';

import type { PmsFolder, PmsSpace, PmsTaskList } from '../api/pms-api';
import { buildPmsSidebarSpaceTree } from './space-tree-model';

function space(id: string, name: string): PmsSpace {
  return {
    id,
    key: id,
    name,
    description: '',
    member_count: 1,
    current_user_role: 'admin',
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
  } as PmsSpace;
}

function folder(
  id: string,
  teamId: string,
  name: string,
  sortOrder: number,
): PmsFolder {
  return {
    id,
    team_id: teamId,
    name,
    sort_order: sortOrder,
    list_count: 0,
  };
}

function list(
  id: string,
  teamId: string | null,
  name: string,
  sortOrder: number,
  folderId: string | null = null,
  archived = false,
): PmsTaskList {
  return {
    archived,
    id,
    team_id: teamId,
    team_name: teamId ? `Space ${teamId}` : null,
    folder_id: folderId,
    folder_name: null,
    key: id,
    name,
    role: 'admin',
    sort_order: sortOrder,
    status_mode: 'inherit',
    updated_at: '2026-05-30T00:00:00Z',
  } as PmsTaskList;
}

describe('PMS sidebar space tree model', () => {
  it('groups lists under folders and preserves empty folders', () => {
    const tree = buildPmsSidebarSpaceTree({
      spaces: [space('team-1', 'Team 1')],
      folders: [
        folder('folder-1', 'team-1', 'Folder 1', 10),
        folder('folder-empty', 'team-1', 'Empty', 20),
      ],
      lists: [list('list-1', 'team-1', 'List 1', 10, 'folder-1')],
      untitledSpaceName: 'Untitled',
    });

    expect(tree).toHaveLength(1);
    expect(tree[0].rootLists).toEqual([]);
    expect(tree[0].folders.map((entry) => entry.folder.id)).toEqual([
      'folder-1',
      'folder-empty',
    ]);
    expect(tree[0].folders[0].lists.map((item) => item.id)).toEqual(['list-1']);
    expect(tree[0].folders[1].lists).toEqual([]);
  });

  it('puts lists with missing or unknown folders at the space root', () => {
    const tree = buildPmsSidebarSpaceTree({
      spaces: [space('team-1', 'Team 1')],
      folders: [folder('folder-1', 'team-1', 'Folder 1', 10)],
      lists: [
        list('root', 'team-1', 'Root', 10),
        list('orphan-folder', 'team-1', 'Orphan', 20, 'missing-folder'),
        list('no-space', null, 'Ignored', 30),
      ],
      untitledSpaceName: 'Untitled',
    });

    expect(tree[0].rootLists.map((item) => item.id)).toEqual([
      'root',
      'orphan-folder',
    ]);
  });

  it('separates archived lists from active folders and roots', () => {
    const tree = buildPmsSidebarSpaceTree({
      spaces: [space('team-1', 'Team 1')],
      folders: [folder('folder-1', 'team-1', 'Folder 1', 10)],
      lists: [
        list('active', 'team-1', 'Active', 10, 'folder-1'),
        list('archived-root', 'team-1', 'Archived root', 20, null, true),
        list(
          'archived-folder',
          'team-1',
          'Archived folder',
          30,
          'folder-1',
          true,
        ),
      ],
      untitledSpaceName: 'Untitled',
    });

    expect(tree[0].folders[0].lists.map((item) => item.id)).toEqual(['active']);
    expect(tree[0].rootLists).toEqual([]);
    expect(tree[0].archivedLists.map((item) => item.id)).toEqual([
      'archived-root',
      'archived-folder',
    ]);
  });

  it('creates placeholder spaces for orphan lists and folders', () => {
    const tree = buildPmsSidebarSpaceTree({
      spaces: [],
      folders: [folder('folder-1', 'team-1', 'Folder 1', 10)],
      lists: [list('list-1', 'team-2', 'List 1', 10)],
      untitledSpaceName: 'Untitled',
    });

    expect(tree.map((item) => [item.id, item.name])).toEqual([
      ['team-2', 'Space team-2'],
      ['team-1', 'Untitled'],
    ]);
  });

  it('sorts spaces, folders, and lists by order then localized name', () => {
    const tree = buildPmsSidebarSpaceTree({
      spaces: [space('z', 'Zulu'), space('a', 'Alpha')],
      folders: [folder('f2', 'a', 'Bravo', 10), folder('f1', 'a', 'Alpha', 10)],
      lists: [
        list('l3', 'a', 'Charlie', 20),
        list('l2', 'a', 'Bravo', 10),
        list('l1', 'a', 'Alpha', 10),
        list('lf2', 'a', 'Folder Bravo', 10, 'f2'),
        list('lf1', 'a', 'Folder Alpha', 10, 'f2'),
      ],
      locale: 'en-US',
      untitledSpaceName: 'Untitled',
    });

    expect(tree.map((item) => item.name)).toEqual(['Alpha', 'Zulu']);
    expect(tree[0].rootLists.map((item) => item.id)).toEqual([
      'l1',
      'l2',
      'l3',
    ]);
    expect(tree[0].folders.map((entry) => entry.folder.id)).toEqual([
      'f1',
      'f2',
    ]);
    expect(tree[0].folders[1].lists.map((item) => item.id)).toEqual([
      'lf1',
      'lf2',
    ]);
  });
});
