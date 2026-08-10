import { describe, expect, it } from 'vitest';

import type { DocsHubItem } from '@/src/app-modules/docs/public-api';
import type {
  PmsFolder,
  PmsSpace,
  PmsSpaceMember,
  PmsTaskList,
} from '../api/pms-api';

import {
  buildSpaceOverviewCollections,
  buildSpaceOverviewLoadSuccess,
  SPACE_OVERVIEW_INITIAL_STATE,
  sortSpaceDocs,
  sortSpaceFolders,
  sortTaskLists,
  spaceOverviewReducer,
} from './space-overview-model';

describe('space overview model', () => {
  it('sorts docs, folders, and task lists for stable display', () => {
    expect(
      sortSpaceDocs(
        [
          docsHubItem({ id: 'doc-b', title: 'Beta', sortOrder: 2 }),
          docsHubItem({ id: 'doc-a', title: 'Alpha', sortOrder: 2 }),
          docsHubItem({ id: 'doc-root', title: 'Root', sortOrder: 0 }),
        ],
        'en-US',
      ).map((item) => item.id),
    ).toEqual(['doc-root', 'doc-a', 'doc-b']);
    expect(
      sortSpaceFolders(
        [
          pmsFolder({ id: 'folder-b', name: 'Beta', sort_order: 2 }),
          pmsFolder({ id: 'folder-a', name: 'Alpha', sort_order: 2 }),
          pmsFolder({ id: 'folder-root', name: 'Root', sort_order: 1 }),
        ],
        'en-US',
      ).map((folder) => folder.id),
    ).toEqual(['folder-root', 'folder-a', 'folder-b']);
    expect(
      sortTaskLists(
        [
          pmsTaskList({
            id: 'list-b',
            name: 'Beta',
            folder_name: 'Folder',
            sort_order: 2,
          }),
          pmsTaskList({
            id: 'list-a',
            name: 'Alpha',
            folder_name: 'Folder',
            sort_order: 2,
          }),
          pmsTaskList({
            id: 'list-root',
            name: 'Root',
            folder_name: null,
            sort_order: 1,
          }),
        ],
        'en-US',
      ).map((list) => list.id),
    ).toEqual(['list-root', 'list-a', 'list-b']);
  });

  it('normalizes load success payloads', () => {
    const load = buildSpaceOverviewLoadSuccess({
      lists: [
        pmsTaskList({ id: 'later', sort_order: 2 }),
        pmsTaskList({ id: 'first', sort_order: 1 }),
      ],
      folders: [
        pmsFolder({ id: 'folder-b', sort_order: 2 }),
        pmsFolder({ id: 'folder-a', sort_order: 1 }),
      ],
      spaceDocs: [
        docsHubItem({ id: 'doc-b', title: 'Beta', sortOrder: 2 }),
        docsHubItem({ id: 'doc-a', title: 'Alpha', sortOrder: 1 }),
      ],
      members: [spaceMember({ user_id: 'member-1' })],
      spaces: [
        pmsSpace({ id: 'other', current_user_role: 'member' }),
        pmsSpace({ id: 'space-1', current_user_role: 'admin' }),
      ],
      spaceId: 'space-1',
      locale: 'en-US',
    });

    expect(load.type).toBe('loadSuccess');
    expect(load.lists.map((list) => list.id)).toEqual(['first', 'later']);
    expect(load.folders.map((folder) => folder.id)).toEqual([
      'folder-a',
      'folder-b',
    ]);
    expect(load.spaceDocs.map((doc) => doc.id)).toEqual(['doc-a', 'doc-b']);
    expect(load.members).toHaveLength(1);
    expect(load.spaceMeta?.id).toBe('space-1');
  });

  it('handles reducer transitions without mutating collapsed folder state', () => {
    const opened = spaceOverviewReducer(SPACE_OVERVIEW_INITIAL_STATE, {
      type: 'setCreateListOpen',
      open: true,
    });
    expect(opened.createListOpen).toBe(true);

    const collapsed = spaceOverviewReducer(opened, {
      type: 'toggleFolder',
      folderId: 'folder-1',
    });
    expect(collapsed.collapsedFolderIds.has('folder-1')).toBe(true);
    expect(opened.collapsedFolderIds.has('folder-1')).toBe(false);

    const expanded = spaceOverviewReducer(collapsed, {
      type: 'toggleFolder',
      folderId: 'folder-1',
    });
    expect(expanded.collapsedFolderIds.has('folder-1')).toBe(false);

    const allCollapsed = spaceOverviewReducer(expanded, {
      type: 'setAllFoldersCollapsed',
      folderIds: ['folder-1', 'folder-2'],
      collapsed: true,
    });
    expect(Array.from(allCollapsed.collapsedFolderIds)).toEqual([
      'folder-1',
      'folder-2',
    ]);

    const membersChanged = spaceOverviewReducer(allCollapsed, {
      type: 'membersChanged',
    });
    expect(membersChanged.refreshSeq).toBe(1);

    const renamed = spaceOverviewReducer(membersChanged, {
      type: 'setSpaceMeta',
      spaceMeta: pmsSpace({ id: 'space-1', name: 'Renamed Space' }),
    });
    expect(renamed.spaceMeta?.name).toBe('Renamed Space');
  });

  it('adds lists in sorted order', () => {
    const state = spaceOverviewReducer(
      {
        ...SPACE_OVERVIEW_INITIAL_STATE,
        lists: [
          pmsTaskList({
            id: 'existing',
            name: 'Existing',
            folder_name: 'Folder',
            sort_order: 2,
          }),
        ],
      },
      {
        type: 'addList',
        list: pmsTaskList({
          id: 'created',
          name: 'Created',
          folder_name: null,
          sort_order: 1,
        }),
        locale: 'en-US',
      },
    );

    expect(state.lists.map((list) => list.id)).toEqual(['created', 'existing']);
  });

  it('removes archived lists and upserts restored lists in the active overview', () => {
    const activeState = {
      ...SPACE_OVERVIEW_INITIAL_STATE,
      lists: [pmsTaskList({ id: 'list-1' })],
    };
    const archived = spaceOverviewReducer(activeState, {
      type: 'taskListChanged',
      change: {
        type: 'updated',
        taskList: pmsTaskList({ id: 'list-1', archived: true }),
      },
      locale: 'en-US',
      spaceId: 'space-1',
    });
    expect(archived.lists).toEqual([]);

    const restored = spaceOverviewReducer(archived, {
      type: 'taskListChanged',
      change: {
        type: 'updated',
        taskList: pmsTaskList({ id: 'list-1', archived: false }),
      },
      locale: 'en-US',
      spaceId: 'space-1',
    });
    expect(restored.lists.map((list) => list.id)).toEqual(['list-1']);
  });

  it('applies persisted list moves and document ordering', () => {
    const state = spaceOverviewReducer(
      {
        ...SPACE_OVERVIEW_INITIAL_STATE,
        folders: [pmsFolder({ id: 'folder-1', name: 'Folder' })],
        lists: [
          pmsTaskList({ id: 'list-1', sort_order: 1 }),
          pmsTaskList({ id: 'list-2', sort_order: 2 }),
        ],
        spaceDocs: [
          docsHubItem({ id: 'doc-1', sortOrder: 1 }),
          docsHubItem({ id: 'doc-2', sortOrder: 2 }),
        ],
      },
      {
        type: 'applyOrderChanges',
        listChanges: [{ id: 'list-1', folder_id: 'folder-1', sort_order: 3 }],
        docChanges: [
          { id: 'doc-1', sort_order: 4 },
          { id: 'doc-2', sort_order: 1 },
        ],
        locale: 'en-US',
      },
    );

    expect(state.lists.find((list) => list.id === 'list-1')).toMatchObject({
      folder_id: 'folder-1',
      folder_name: 'Folder',
      sort_order: 3,
    });
    expect(state.spaceDocs.map((doc) => doc.id)).toEqual(['doc-2', 'doc-1']);
  });

  it('builds folder groupings, collapse state, and recent items', () => {
    const collections = buildSpaceOverviewCollections({
      lists: [
        pmsTaskList({
          id: 'root',
          name: 'Root list',
          folder_id: null,
          folder_name: null,
          updated_at: '2026-01-01T00:00:00Z',
        }),
        pmsTaskList({
          id: 'child',
          name: 'Child list',
          folder_id: 'folder-1',
          folder_name: 'Folder',
          updated_at: '2026-01-04T00:00:00Z',
        }),
        pmsTaskList({
          id: 'orphan',
          name: 'Orphan list',
          folder_id: 'missing-folder',
          folder_name: 'Missing',
          updated_at: '2026-01-05T00:00:00Z',
        }),
        pmsTaskList({
          id: 'archived',
          archived: true,
          updated_at: '2026-01-06T00:00:00Z',
        }),
      ],
      folders: [pmsFolder({ id: 'folder-1', name: 'Folder' })],
      spaceDocs: [
        docsHubItem({
          id: 'doc-1',
          title: 'Doc',
          updated_at: '2026-01-03T00:00:00Z',
        }),
      ],
      collapsedFolderIds: new Set(['folder-1']),
      spaceName: 'Launch',
      fallbackSpaceName: 'Space',
    });

    expect(collections.rootLists.map((list) => list.id)).toEqual(['root']);
    expect(
      collections.listsByFolder.get('folder-1')?.map((list) => list.id),
    ).toEqual(['child']);
    expect(collections.allFoldersCollapsed).toBe(true);
    expect(collections.recentItems.map((item) => item.id)).toEqual([
      'orphan',
      'child',
      'doc-1',
      'root',
      'folder-1',
    ]);
    expect(
      collections.recentItems.find((item) => item.id === 'doc-1'),
    ).toMatchObject({
      context: 'Launch',
      kind: 'doc',
    });
  });
});

function pmsTaskList(overrides: Partial<PmsTaskList> = {}): PmsTaskList {
  return {
    id: 'list-1',
    name: 'List',
    team_id: 'space-1',
    team_name: 'Space',
    folder_id: null,
    folder_name: null,
    sort_order: 1,
    task_count: 0,
    progress: 0,
    updated_at: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    status_mode: 'inherit',
    ...overrides,
  } as PmsTaskList;
}

function pmsFolder(overrides: Partial<PmsFolder> = {}): PmsFolder {
  return {
    id: 'folder-1',
    name: 'Folder',
    team_id: 'space-1',
    sort_order: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as PmsFolder;
}

function pmsSpace(overrides: Partial<PmsSpace> = {}): PmsSpace {
  return {
    id: 'space-1',
    name: 'Space',
    current_user_role: 'member',
    ...overrides,
  } as PmsSpace;
}

function spaceMember(overrides: Partial<PmsSpaceMember> = {}): PmsSpaceMember {
  return {
    user_id: 'member-1',
    full_name: 'Ada Lovelace',
    email: 'ada@example.test',
    role: 'member',
    ...overrides,
  } as PmsSpaceMember;
}

function docsHubItem({
  sortOrder = 1,
  ...overrides
}: Partial<DocsHubItem> & { sortOrder?: number } = {}): DocsHubItem {
  return {
    id: 'doc-1',
    title: 'Doc',
    updated_at: '2026-01-01T00:00:00Z',
    primary_target: {
      app: 'pms',
      type: 'space',
      id: 'space-1',
      sort_order: sortOrder,
      name: 'Space',
    },
    ...overrides,
  } as DocsHubItem;
}
