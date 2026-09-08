import {
  getDocsItemPrimaryTargetId,
  getDocsItemPrimaryTargetSortOrder,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import type { PmsFolder, PmsSpace, PmsTaskList } from '../api/pms-api';

export const SPACE_COLORS = [
  'bg-emerald-500',
  'bg-blue-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
];

export type FolderWithLists = {
  folder: PmsFolder;
  lists: PmsTaskList[];
};

export type PmsSidebarSpaceTreeItem = PmsSpace & {
  archivedLists: PmsTaskList[];
  rootLists: PmsTaskList[];
  folders: FolderWithLists[];
};

type SpaceGroup = {
  archivedLists: PmsTaskList[];
  team: PmsSpace;
  rootLists: PmsTaskList[];
  folders: Map<string, FolderWithLists>;
};

export function getSpaceDocSpaceId(doc: DocsHubItem): string {
  return getDocsItemPrimaryTargetId(doc, 'pms', 'space') ?? '';
}

export function getSpaceDocSortOrder(doc: DocsHubItem): number {
  return getDocsItemPrimaryTargetSortOrder(doc);
}

export function sortSpaceDocs(
  items: DocsHubItem[],
  locale = 'ko-KR',
): DocsHubItem[] {
  return Array.from(items).sort(
    (left, right) =>
      getSpaceDocSortOrder(left) - getSpaceDocSortOrder(right) ||
      left.title.localeCompare(right.title, locale),
  );
}

export function buildPmsSidebarSpaceTree({
  folders,
  lists,
  locale = 'ko-KR',
  spaces,
  untitledSpaceName,
}: {
  folders: PmsFolder[];
  lists: PmsTaskList[];
  locale?: string;
  spaces: PmsSpace[];
  untitledSpaceName: string;
}): PmsSidebarSpaceTreeItem[] {
  const folderMap = new Map(folders.map((folder) => [folder.id, folder]));
  const groups = new Map<string, SpaceGroup>();

  for (const team of spaces) {
    groups.set(team.id, {
      archivedLists: [],
      team,
      rootLists: [],
      folders: new Map(),
    });
  }

  const ensureGroup = (teamId: string, fallbackName: string): SpaceGroup => {
    const existing = groups.get(teamId);
    if (existing) return existing;
    const placeholder = createPlaceholderSpace(teamId, fallbackName);
    const created: SpaceGroup = {
      archivedLists: [],
      team: placeholder,
      rootLists: [],
      folders: new Map(),
    };
    groups.set(teamId, created);
    return created;
  };

  for (const list of lists) {
    if (!list.team_id) continue;

    const current = ensureGroup(
      list.team_id,
      list.team_name ?? untitledSpaceName,
    );
    if (list.archived) {
      current.archivedLists.push(list);
      continue;
    }
    const folder =
      list.folder_id && folderMap.has(list.folder_id)
        ? folderMap.get(list.folder_id)
        : null;
    if (!folder) {
      current.rootLists.push(list);
      continue;
    }
    const folderEntry = current.folders.get(folder.id) ?? {
      folder,
      lists: [],
    };
    folderEntry.lists.push(list);
    current.folders.set(folder.id, folderEntry);
  }

  for (const folder of folders) {
    if (!folder.team_id) continue;
    const current = ensureGroup(folder.team_id, untitledSpaceName);
    if (!current.folders.has(folder.id)) {
      current.folders.set(folder.id, { folder, lists: [] });
    }
  }

  const sortedSpaces = Array.from(groups.values()).map((space) => {
    const archivedLists = Array.from(space.archivedLists).sort((left, right) =>
      compareTaskLists(left, right, locale),
    );
    const rootLists = Array.from(space.rootLists).sort((left, right) =>
      compareTaskLists(left, right, locale),
    );
    const sortedFolders = Array.from(space.folders.values())
      .map((entry) => ({
        folder: entry.folder,
        lists: Array.from(entry.lists).sort((left, right) =>
          compareTaskLists(left, right, locale),
        ),
      }))
      .sort((left, right) => compareFolders(left.folder, right.folder, locale));
    return {
      ...space.team,
      archivedLists,
      rootLists,
      folders: sortedFolders,
    };
  });

  return sortedSpaces.sort((left, right) =>
    left.name.localeCompare(right.name, locale),
  );
}

function createPlaceholderSpace(teamId: string, name: string): PmsSpace {
  return {
    id: teamId,
    key: '',
    name,
    description: '',
    member_count: 0,
    current_user_role: null,
    created_at: '',
    updated_at: '',
  };
}

function compareTaskLists(
  left: PmsTaskList,
  right: PmsTaskList,
  locale: string,
): number {
  return (
    left.sort_order - right.sort_order ||
    left.name.localeCompare(right.name, locale)
  );
}

function compareFolders(
  left: PmsFolder,
  right: PmsFolder,
  locale: string,
): number {
  return (
    left.sort_order - right.sort_order ||
    left.name.localeCompare(right.name, locale)
  );
}
