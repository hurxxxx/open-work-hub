import {
  getDocsItemPrimaryTargetSortOrder,
  withDocsItemPrimaryTargetSortOrder,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';

import type {
  PmsFolder,
  PmsSpace,
  PmsSpaceMember,
  PmsTaskList,
} from '../api/pms-api';

export type SpaceOverviewRecentItem = {
  id: string;
  kind: 'doc' | 'folder' | 'list';
  name: string;
  context: string;
  updatedAt: string;
};

export interface SpaceOverviewState {
  lists: PmsTaskList[];
  folders: PmsFolder[];
  spaceDocs: DocsHubItem[];
  members: PmsSpaceMember[];
  spaceMeta: PmsSpace | null;
  loading: boolean;
  createListOpen: boolean;
  membersModalOpen: boolean;
  collapsedFolderIds: Set<string>;
  refreshSeq: number;
}

export type SpaceOverviewAction =
  | { type: 'loadStart' }
  | {
      type: 'loadSuccess';
      lists: PmsTaskList[];
      folders: PmsFolder[];
      spaceDocs: DocsHubItem[];
      members: PmsSpaceMember[];
      spaceMeta: PmsSpace | null;
    }
  | { type: 'loadDone' }
  | { type: 'setCreateListOpen'; open: boolean }
  | { type: 'setMembersModalOpen'; open: boolean }
  | { type: 'toggleFolder'; folderId: string }
  | { type: 'setAllFoldersCollapsed'; folderIds: string[]; collapsed: boolean }
  | { type: 'addList'; list: PmsTaskList; locale: string }
  | {
      type: 'applyOrderChanges';
      listChanges: Array<{
        id: string;
        folder_id: string | null;
        sort_order: number;
      }>;
      docChanges: Array<{ id: string; sort_order: number }>;
      locale: string;
    }
  | { type: 'setSpaceMeta'; spaceMeta: PmsSpace | null }
  | {
      type: 'taskListChanged';
      change:
        | { type: 'updated'; taskList: PmsTaskList }
        | { type: 'deleted'; taskListId: string };
      locale: string;
      spaceId: string;
    }
  | { type: 'membersChanged' };

export const SPACE_OVERVIEW_INITIAL_STATE: SpaceOverviewState = {
  lists: [],
  folders: [],
  spaceDocs: [],
  members: [],
  spaceMeta: null,
  loading: true,
  createListOpen: false,
  membersModalOpen: false,
  collapsedFolderIds: new Set(),
  refreshSeq: 0,
};

export function sortSpaceDocs(
  items: DocsHubItem[],
  locale: string,
): DocsHubItem[] {
  const sorted = Array.from(items);
  sorted.sort(
    (left, right) =>
      getDocsItemPrimaryTargetSortOrder(left) -
        getDocsItemPrimaryTargetSortOrder(right) ||
      left.title.localeCompare(right.title, locale),
  );
  return sorted;
}

export function sortTaskLists(
  items: PmsTaskList[],
  locale: string,
): PmsTaskList[] {
  const sorted = Array.from(items);
  sorted.sort(
    (left, right) =>
      (left.folder_name ?? '').localeCompare(right.folder_name ?? '', locale) ||
      left.sort_order - right.sort_order ||
      left.name.localeCompare(right.name, locale),
  );
  return sorted;
}

export function sortSpaceFolders(
  items: PmsFolder[],
  locale: string,
): PmsFolder[] {
  const sorted = Array.from(items);
  sorted.sort(
    (left, right) =>
      left.sort_order - right.sort_order ||
      left.name.localeCompare(right.name, locale),
  );
  return sorted;
}

export function buildSpaceOverviewLoadSuccess(input: {
  lists: PmsTaskList[];
  folders: PmsFolder[];
  spaceDocs: DocsHubItem[];
  members: PmsSpaceMember[];
  spaces: PmsSpace[] | null;
  spaceId: string;
  locale: string;
}): Extract<SpaceOverviewAction, { type: 'loadSuccess' }> {
  return {
    type: 'loadSuccess',
    lists: sortTaskLists(input.lists, input.locale),
    folders: sortSpaceFolders(input.folders, input.locale),
    spaceDocs: sortSpaceDocs(input.spaceDocs, input.locale),
    members: input.members,
    spaceMeta:
      input.spaces?.find((space) => space.id === input.spaceId) ?? null,
  };
}

export function spaceOverviewReducer(
  state: SpaceOverviewState,
  action: SpaceOverviewAction,
): SpaceOverviewState {
  switch (action.type) {
    case 'loadStart':
      return { ...state, loading: true };
    case 'loadSuccess':
      return {
        ...state,
        lists: action.lists,
        folders: action.folders,
        spaceDocs: action.spaceDocs,
        members: action.members,
        spaceMeta: action.spaceMeta,
      };
    case 'loadDone':
      return { ...state, loading: false };
    case 'setCreateListOpen':
      return { ...state, createListOpen: action.open };
    case 'setMembersModalOpen':
      return { ...state, membersModalOpen: action.open };
    case 'toggleFolder': {
      const collapsedFolderIds = new Set(state.collapsedFolderIds);
      if (collapsedFolderIds.has(action.folderId)) {
        collapsedFolderIds.delete(action.folderId);
      } else {
        collapsedFolderIds.add(action.folderId);
      }
      return { ...state, collapsedFolderIds };
    }
    case 'setAllFoldersCollapsed':
      return {
        ...state,
        collapsedFolderIds: action.collapsed
          ? new Set(action.folderIds)
          : new Set(),
      };
    case 'addList':
      return {
        ...state,
        lists: sortTaskLists([...state.lists, action.list], action.locale),
      };
    case 'applyOrderChanges': {
      const listChangeMap = new Map(
        action.listChanges.map((item) => [item.id, item]),
      );
      const docChangeMap = new Map(
        action.docChanges.map((item) => [item.id, item]),
      );
      const folderNameMap = new Map(
        state.folders.map((folder) => [folder.id, folder.name]),
      );
      return {
        ...state,
        lists: sortTaskLists(
          state.lists.map((list) => {
            const change = listChangeMap.get(list.id);
            return change
              ? {
                  ...list,
                  folder_id: change.folder_id,
                  folder_name: change.folder_id
                    ? (folderNameMap.get(change.folder_id) ?? null)
                    : null,
                  sort_order: change.sort_order,
                }
              : list;
          }),
          action.locale,
        ),
        spaceDocs: sortSpaceDocs(
          state.spaceDocs.map((doc) => {
            const change = docChangeMap.get(doc.id);
            return change
              ? withDocsItemPrimaryTargetSortOrder(doc, change.sort_order)
              : doc;
          }),
          action.locale,
        ),
      };
    }
    case 'setSpaceMeta':
      return { ...state, spaceMeta: action.spaceMeta };
    case 'taskListChanged': {
      const change = action.change;
      if (change.type === 'deleted') {
        return {
          ...state,
          lists: state.lists.filter((list) => list.id !== change.taskListId),
        };
      }
      if (change.taskList.team_id !== action.spaceId) return state;
      const withoutChanged = state.lists.filter(
        (list) => list.id !== change.taskList.id,
      );
      return {
        ...state,
        lists: change.taskList.archived
          ? withoutChanged
          : sortTaskLists([change.taskList, ...withoutChanged], action.locale),
      };
    }
    case 'membersChanged':
      return { ...state, refreshSeq: state.refreshSeq + 1 };
    default:
      return state;
  }
}

export function buildSpaceOverviewCollections({
  collapsedFolderIds,
  fallbackSpaceName,
  folders,
  lists,
  spaceDocs,
  spaceName,
}: {
  lists: PmsTaskList[];
  folders: PmsFolder[];
  spaceDocs: DocsHubItem[];
  collapsedFolderIds: Set<string>;
  spaceName?: string | null;
  fallbackSpaceName: string;
}): {
  rootLists: PmsTaskList[];
  listsByFolder: Map<string, PmsTaskList[]>;
  recentItems: SpaceOverviewRecentItem[];
  allFoldersCollapsed: boolean;
} {
  const activeLists = lists.filter((list) => !list.archived);
  const folderMap = new Map(folders.map((folder) => [folder.id, folder]));
  const listsByFolder = new Map<string, PmsTaskList[]>();
  const rootLists: PmsTaskList[] = [];
  for (const list of activeLists) {
    if (list.folder_id && folderMap.has(list.folder_id)) {
      const arr = listsByFolder.get(list.folder_id) ?? [];
      arr.push(list);
      listsByFolder.set(list.folder_id, arr);
    } else if (!list.folder_id) {
      rootLists.push(list);
    }
  }

  return {
    rootLists,
    listsByFolder,
    recentItems: buildRecentItems({
      fallbackSpaceName,
      folders,
      lists: activeLists,
      spaceDocs,
      spaceName,
    }),
    allFoldersCollapsed:
      folders.length > 0 &&
      folders.every((folder) => collapsedFolderIds.has(folder.id)),
  };
}

function buildRecentItems({
  fallbackSpaceName,
  folders,
  lists,
  spaceDocs,
  spaceName,
}: {
  lists: PmsTaskList[];
  folders: PmsFolder[];
  spaceDocs: DocsHubItem[];
  spaceName?: string | null;
  fallbackSpaceName: string;
}): SpaceOverviewRecentItem[] {
  const context = spaceName ?? fallbackSpaceName;
  const listItems: SpaceOverviewRecentItem[] = lists.map((list) => ({
    id: list.id,
    kind: 'list',
    name: list.name,
    context: list.folder_name ?? list.team_name ?? '',
    updatedAt: list.updated_at,
  }));
  const folderItems: SpaceOverviewRecentItem[] = folders.map((folder) => ({
    id: folder.id,
    kind: 'folder',
    name: folder.name,
    context,
    updatedAt: '',
  }));
  const docItems: SpaceOverviewRecentItem[] = spaceDocs.map((doc) => ({
    id: doc.id,
    kind: 'doc',
    name: doc.title,
    context,
    updatedAt: doc.updated_at,
  }));
  const items = [...listItems, ...folderItems, ...docItems];
  items.sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  return items.slice(0, 6);
}
