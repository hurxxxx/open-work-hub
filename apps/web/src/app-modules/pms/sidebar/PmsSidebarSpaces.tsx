import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, ChevronRight, Loader2, Plus } from 'lucide-react';
import { useConfirm } from '@aidoo/ui/feedback/confirm-dialog';
import { InlineNotice } from '@aidoo/ui/feedback/inline-notice';
import { usePrompt } from '@aidoo/ui/feedback/prompt-dialog';

import {
  createNativeDoc,
  deleteDocsItem,
  listDocsHub,
  updateDocContainer,
  updateDocsItem,
  withDocsItemPrimaryContainerSortOrder,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import { createWhiteboard } from '@/src/app-modules/whiteboard/public-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  hasWorkspaceMembership,
  teamRoleAllows,
} from '@/src/platform/auth/auth-api';
import {
  listPmsTaskLists,
  listFolders,
  updateFolder,
  deleteFolder,
  listSpaces,
  updateSpace,
  deleteSpace,
  reorderPmsTaskLists,
  updatePmsTaskList,
  type PmsFolder,
  type PmsTaskList,
  type PmsSpace,
} from '../api/pms-api';
import {
  applyFlatReorder,
  computeFlatDropTarget,
  type FlatDropZone,
} from '../api/pms-sidebar-reorder';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import { CreateTaskListModal } from '../views/CreateTaskListModal';
import { CreateSpaceModal } from '../views/CreateSpaceModal';
import { SpaceMembersModal } from '../views/SpaceMembersModal';
import { CreateFolderModal } from '../views/CreateFolderModal';
import {
  SPACE_COLORS,
  SpaceItem,
  getSpaceDocSpaceId,
  getSpaceDocSortOrder,
  sortSpaceDocs,
  type FolderWithLists,
} from './SpaceTree';
import { SpaceOrderEditorModal } from './SpaceOrderEditorModal';

interface PmsSidebarSpacesProps {
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  isExpanded: boolean;
  onToggle: () => void;
}

function upsertList(lists: PmsTaskList[], item: PmsTaskList): PmsTaskList[] {
  return [item, ...lists.filter((current) => current.id !== item.id)].sort(
    (left, right) => right.updated_at.localeCompare(left.updated_at),
  );
}

function upsertSpace(spaces: PmsSpace[], space: PmsSpace): PmsSpace[] {
  return [space, ...spaces.filter((item) => item.id !== space.id)].sort(
    (left, right) => left.name.localeCompare(right.name, 'ko'),
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function PmsSidebarSpaces({
  activeNavItemId,
  currentWorkspaceSlug,
  isExpanded,
  onToggle,
}: PmsSidebarSpacesProps) {
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const canReadTeams = hasWorkspaceMembership(user, currentWorkspaceSlug);
  const canWriteTeams = hasWorkspaceMembership(user, currentWorkspaceSlug);
  const pmsRootPath = resolveDefaultWorkspaceAppPath(user, 'pms');
  const knownSpaceIdsRef = useRef(new Set<string>());
  const canManageSpace = useCallback(
    (team: PmsSpace) => teamRoleAllows(team.current_user_role, 'admin'),
    [],
  );

  const [pmsLists, setPmsTaskLists] = useState<PmsTaskList[]>([]);
  const [pmsFolders, setPmsFolders] = useState<PmsFolder[]>([]);
  const [pmsTeams, setPmsTeams] = useState<PmsSpace[]>([]);
  const [pmsLoading, setPmsLoading] = useState(false);
  const [pmsError, setPmsError] = useState<string | null>(null);
  const [createTaskListOpen, setCreateTaskListOpen] = useState(false);
  const [createTaskListTeamId, setCreateTaskListTeamId] = useState<
    string | null
  >(null);
  const [createTaskListFolderId, setCreateTaskListFolderId] = useState<
    string | null
  >(null);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [manageMembersSpace, setManageMembersSpace] = useState<{
    id: string;
    name: string;
    canManage: boolean;
    currentUserRole: string | null;
  } | null>(null);
  const [orderEditorSpace, setOrderEditorSpace] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [expandedSpaces, setExpandedSpaces] = useState<Set<string>>(new Set());
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [createFolderTeamId, setCreateFolderTeamId] = useState<string | null>(
    null,
  );
  const [spaceDocsMap, setSpaceDocsMap] = useState<Map<string, DocsHubItem[]>>(
    new Map(),
  );

  useEffect(() => {
    let cancelled = false;
    if (!token) return undefined;

    setPmsLoading(true);
    setPmsError(null);

    const listRequest = listPmsTaskLists(token).then((response) => {
      if (cancelled) return;
      setPmsTaskLists(response.items);
    });

    const folderRequest = listFolders(token)
      .then((response) => {
        if (cancelled) return;
        setPmsFolders(response.items);
      })
      .catch(() => {
        if (cancelled) return;
        setPmsFolders([]);
      });

    const teamRequest = canReadTeams
      ? listSpaces(token)
          .then((teams) => {
            if (cancelled) return;
            setPmsTeams(Array.isArray(teams) ? teams : []);
          })
          .catch(() => {
            if (cancelled) return;
            setPmsTeams([]);
          })
      : Promise.resolve().then(() => {
          if (cancelled) return;
          setPmsTeams([]);
        });

    Promise.allSettled([listRequest, folderRequest, teamRequest]).finally(
      () => {
        if (!cancelled) {
          setPmsLoading(false);
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [canReadTeams, token]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handler = () => {
      setCreateSpaceOpen(true);
    };
    window.addEventListener('pms:create-space', handler);
    return () => {
      window.removeEventListener('pms:create-space', handler);
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    for (const team of pmsTeams) {
      if (!teamRoleAllows(team.current_user_role, 'viewer')) {
        continue;
      }
      listDocsHub(token, {
        view: 'all',
        container_app: 'pms',
        container_type: 'space',
        container_id: team.id,
        page_size: 200,
        sort_by: 'container_sort_order',
        sort_dir: 'asc',
      })
        .then((res) =>
          setSpaceDocsMap((prev) =>
            new Map(prev).set(team.id, sortSpaceDocs(res.items)),
          ),
        )
        .catch(() => undefined);
    }
  }, [token, pmsTeams]);

  const openCreateTaskList = (teamId: string | null) => {
    setCreateTaskListTeamId(teamId);
    setCreateTaskListFolderId(null);
    setCreateTaskListOpen(true);
  };

  const openCreateFolder = (teamId: string) => {
    setCreateFolderTeamId(teamId);
    setCreateFolderOpen(true);
  };

  const toggleSpace = (spaceId: string) => {
    setExpandedSpaces((prev) => {
      const next = new Set(prev);
      if (next.has(spaceId)) next.delete(spaceId);
      else next.add(spaceId);
      return next;
    });
  };

  const handleCreateDoc = useCallback(
    async (spaceId: string) => {
      if (!token) return;
      const title = await prompt({
        title: 'New Document',
        placeholder: 'Document name',
        defaultValue: '',
      });
      if (!title) return;
      try {
        const doc = await createNativeDoc(token, {
          title,
          source_app: 'pms',
          source_kind: 'manual',
          primary_container: {
            app: 'pms',
            type: 'space',
            id: spaceId,
          },
        });
        setSpaceDocsMap((prev) => {
          const next = new Map(prev);
          next.set(spaceId, sortSpaceDocs([...(next.get(spaceId) ?? []), doc]));
          return next;
        });
        navigate(`/tool/pms-space-${spaceId}-docs-${doc.id}`);
      } catch {
        /* ignore */
      }
    },
    [navigate, prompt, token],
  );

  const handleCreateWhiteboard = useCallback(
    async (spaceId: string) => {
      if (!token) return;
      const title = await prompt({
        title: 'New Whiteboard',
        placeholder: 'Whiteboard name',
        defaultValue: '',
      });
      if (!title) return;
      try {
        const board = await createWhiteboard(
          token,
          {
            title,
            source_app: 'pms',
            source_kind: 'manual',
            primary_container: {
              app: 'pms',
              type: 'space',
              id: spaceId,
            },
          },
          currentWorkspaceSlug,
        );
        navigate(`/tool/pms-space-${spaceId}-whiteboards-${board.id}`);
      } catch {
        /* ignore */
      }
    },
    [currentWorkspaceSlug, navigate, prompt, token],
  );

  const handleRenameDoc = useCallback(
    async (docId: string, newTitle: string) => {
      if (!token) return;
      try {
        const updated = await updateDocsItem(token, docId, { title: newTitle });
        const teamId = getSpaceDocSpaceId(updated);
        if (!teamId) return;
        setSpaceDocsMap((prev) => {
          const next = new Map(prev);
          const docs = next.get(teamId) ?? [];
          next.set(
            teamId,
            sortSpaceDocs(
              docs.map((doc) => (doc.id === updated.id ? updated : doc)),
            ),
          );
          return next;
        });
      } catch {
        /* ignore */
      }
    },
    [token],
  );

  const handleDeleteDoc = useCallback(
    async (docId: string) => {
      if (!token) return;
      if (
        !(await confirm({
          title: 'Delete Collection',
          description:
            'Move this document collection and all its pages to Trash?',
          confirmLabel: 'Move to Trash',
          variant: 'danger',
        }))
      )
        return;
      const deletedTeamId =
        [...spaceDocsMap.entries()].find(([, docs]) =>
          docs.some((doc) => doc.id === docId),
        )?.[0] ?? null;
      try {
        await deleteDocsItem(token, docId);
        setSpaceDocsMap((prev) => {
          const next = new Map(prev);
          for (const [teamId, docs] of next) {
            next.set(
              teamId,
              docs.filter((doc) => doc.id !== docId),
            );
          }
          return next;
        });
        if (
          deletedTeamId &&
          activeNavItemId === `pms-space-${deletedTeamId}-docs-${docId}`
        ) {
          navigate(`/tool/pms-space-${deletedTeamId}-docs`);
        }
      } catch {
        /* ignore */
      }
    },
    [activeNavItemId, confirm, navigate, spaceDocsMap, token],
  );

  const handleSaveSpaceOrder = useCallback(
    async (
      spaceId: string,
      payload: {
        lists: Array<{
          id: string;
          name: string;
          folder_id: string | null;
          sort_order: number;
          issue_count: number;
        }>;
        docs: Array<{
          id: string;
          title: string;
          sort_order: number;
        }>;
      },
    ) => {
      if (!token) return;
      const currentLists = pmsLists.filter((list) => list.team_id === spaceId);
      const currentDocs = spaceDocsMap.get(spaceId) ?? [];
      const listChanges = payload.lists
        .filter((item) => {
          const current = currentLists.find((list) => list.id === item.id);
          return (
            current &&
            ((current.folder_id ?? null) !== item.folder_id ||
              current.sort_order !== item.sort_order)
          );
        })
        .map((item) => ({
          id: item.id,
          folder_id: item.folder_id,
          sort_order: item.sort_order,
        }));
      const docChanges = payload.docs
        .filter((item) => {
          const current = currentDocs.find((doc) => doc.id === item.id);
          return current && getSpaceDocSortOrder(current) !== item.sort_order;
        })
        .map((item) => ({
          id: item.id,
          sort_order: item.sort_order,
        }));

      if (listChanges.length === 0 && docChanges.length === 0) return;

      const nextListMap = new Map(payload.lists.map((item) => [item.id, item]));
      const nextDocMap = new Map(payload.docs.map((item) => [item.id, item]));
      const listSnapshot = pmsLists;
      const docSnapshot = spaceDocsMap;

      setPmsTaskLists((current) =>
        current.map((list) => {
          const next = nextListMap.get(list.id);
          return next
            ? {
                ...list,
                folder_id: next.folder_id,
                sort_order: next.sort_order,
              }
            : list;
        }),
      );
      setSpaceDocsMap((current) => {
        const next = new Map(current);
        const docs = (next.get(spaceId) ?? []).map((doc) => {
          const updated = nextDocMap.get(doc.id);
          return updated
            ? withDocsItemPrimaryContainerSortOrder(doc, updated.sort_order)
            : doc;
        });
        next.set(spaceId, sortSpaceDocs(docs));
        return next;
      });

      try {
        await Promise.all([
          listChanges.length > 0
            ? reorderPmsTaskLists(token, spaceId, { items: listChanges })
            : Promise.resolve(),
          docChanges.length > 0
            ? Promise.all(
                docChanges.map((item) =>
                  updateDocContainer(token, item.id, {
                    app: 'pms',
                    type: 'space',
                    id: spaceId,
                    sort_order: item.sort_order,
                  }),
                ),
              ).then(() => undefined)
            : Promise.resolve(),
        ]);
      } catch (error) {
        setPmsTaskLists(listSnapshot);
        setSpaceDocsMap(docSnapshot);
        throw new Error(getErrorMessage(error, '순서를 저장하지 못했습니다.'));
      }
    },
    [pmsLists, spaceDocsMap, token],
  );

  const handleRenameFolder = useCallback(
    async (folderId: string, currentName: string) => {
      if (!token) return;
      const newName = await prompt({
        title: 'Rename Folder',
        defaultValue: currentName,
        placeholder: 'Folder name',
      });
      if (!newName || newName === currentName) return;
      try {
        const updated = await updateFolder(token, folderId, { name: newName });
        setPmsFolders((current) =>
          current.map((folder) =>
            folder.id === updated.id ? updated : folder,
          ),
        );
      } catch {
        /* ignore */
      }
    },
    [prompt, token],
  );

  const handleReorderDoc = useCallback(
    async (
      spaceId: string,
      activeDocId: string,
      overDocId: string,
      zone: FlatDropZone,
    ) => {
      if (!token) return;
      setPmsError(null);
      const docsInSpace = spaceDocsMap.get(spaceId) ?? [];
      const items = docsInSpace.map((doc) => ({
        id: doc.id,
        parent_id: getSpaceDocSpaceId(doc),
        sort_order: getSpaceDocSortOrder(doc),
        name: doc.title,
      }));
      const target = computeFlatDropTarget(items, overDocId, zone);
      if (!target) return;
      const result = applyFlatReorder(items, activeDocId, target, {
        allowCrossParent: false,
      });
      if (!result) return;
      const patchMap = new Map(result.nextItems.map((item) => [item.id, item]));
      const snapshot = spaceDocsMap;
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        const docs = (next.get(spaceId) ?? []).map((doc) => {
          const patch = patchMap.get(doc.id);
          return patch
            ? withDocsItemPrimaryContainerSortOrder(doc, patch.sort_order)
            : doc;
        });
        next.set(spaceId, sortSpaceDocs(docs));
        return next;
      });
      try {
        await Promise.all(
          result.patches.map((patch) =>
            updateDocContainer(token, patch.id, {
              app: 'pms',
              type: 'space',
              id: spaceId,
              sort_order: patch.sort_order,
            }),
          ),
        );
      } catch (error) {
        setSpaceDocsMap(snapshot);
        setPmsError(getErrorMessage(error, '문서 순서를 변경하지 못했습니다.'));
      }
    },
    [spaceDocsMap, token],
  );

  const handleReorderList = useCallback(
    async (
      spaceId: string,
      activeListId: string,
      overListId: string,
      zone: FlatDropZone,
    ) => {
      if (!token) return;
      setPmsError(null);
      const listsInSpace = pmsLists.filter((list) => list.team_id === spaceId);
      const items = listsInSpace.map((list) => ({
        id: list.id,
        parent_id: list.folder_id ?? null,
        sort_order: list.sort_order,
        name: list.name,
      }));
      const target = computeFlatDropTarget(items, overListId, zone);
      if (!target) return;
      const result = applyFlatReorder(items, activeListId, target);
      if (!result) return;
      const patchMap = new Map(result.nextItems.map((item) => [item.id, item]));
      const snapshot = pmsLists;
      setPmsTaskLists((current) =>
        current.map((list) => {
          const next = patchMap.get(list.id);
          if (!next) return list;
          return {
            ...list,
            sort_order: next.sort_order,
            folder_id: next.parent_id,
          };
        }),
      );
      try {
        await Promise.all(
          result.patches.map((patch) =>
            updatePmsTaskList(token, patch.id, {
              folder_id: patch.parent_id,
              sort_order: patch.sort_order,
            }),
          ),
        );
      } catch (error) {
        setPmsTaskLists(snapshot);
        setPmsError(
          getErrorMessage(error, '리스트 순서를 변경하지 못했습니다.'),
        );
      }
    },
    [pmsLists, token],
  );

  const handleMoveFolder = useCallback(
    async (spaceId: string, folderId: string, direction: 'up' | 'down') => {
      if (!token) return;
      setPmsError(null);

      const orderedFolders = pmsFolders
        .filter((folder) => folder.team_id === spaceId)
        .slice()
        .sort(
          (left, right) =>
            left.sort_order - right.sort_order ||
            left.name.localeCompare(right.name, 'ko'),
        );
      const currentIndex = orderedFolders.findIndex(
        (folder) => folder.id === folderId,
      );
      if (currentIndex < 0) return;

      const targetIndex =
        direction === 'up' ? currentIndex - 1 : currentIndex + 1;
      if (targetIndex < 0 || targetIndex >= orderedFolders.length) return;

      const nextOrder = [...orderedFolders];
      const [movedFolder] = nextOrder.splice(currentIndex, 1);
      nextOrder.splice(targetIndex, 0, movedFolder);

      const updates = nextOrder
        .map((folder, index) => ({ folder, sort_order: index }))
        .filter(({ folder, sort_order }) => folder.sort_order !== sort_order);

      if (updates.length === 0) return;

      try {
        const updatedFolders = new Map<string, PmsFolder>();
        for (const { folder, sort_order } of updates) {
          const updated = await updateFolder(token, folder.id, { sort_order });
          updatedFolders.set(updated.id, updated);
        }
        setPmsFolders((current) =>
          current.map((folder) => updatedFolders.get(folder.id) ?? folder),
        );
      } catch (error) {
        setPmsError(getErrorMessage(error, '폴더 순서를 변경하지 못했습니다.'));
      }
    },
    [pmsFolders, token],
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (!token) return;
      if (
        !(await confirm({
          title: 'Delete Folder',
          description:
            'Delete this folder? Lists inside will be moved to the space root.',
          confirmLabel: 'Delete',
          variant: 'danger',
        }))
      )
        return;
      try {
        await deleteFolder(token, folderId);
        setPmsFolders((current) =>
          current.filter((folder) => folder.id !== folderId),
        );
        listPmsTaskLists(token)
          .then((res) => setPmsTaskLists(res.items))
          .catch(() => undefined);
      } catch {
        /* ignore */
      }
    },
    [confirm, token],
  );

  const handleRenameSpace = useCallback(
    async (spaceId: string, newName: string) => {
      if (!token) return;
      try {
        const updated = await updateSpace(token, spaceId, { name: newName });
        setPmsTeams((current) =>
          current.map((team) => (team.id === updated.id ? updated : team)),
        );
      } catch {
        /* ignore */
      }
    },
    [token],
  );

  const handleDeleteSpace = useCallback(
    async (spaceId: string) => {
      if (!token) return;
      if (
        !(await confirm({
          title: 'Delete Space',
          description: 'Move this space and its contents to Trash?',
          confirmLabel: 'Move to Trash',
          variant: 'danger',
        }))
      )
        return;
      setPmsError(null);
      try {
        await deleteSpace(token, spaceId);
        const activeListInSpace = pmsLists.some(
          (list) =>
            list.team_id === spaceId &&
            activeNavItemId === `pms-list-${list.id}`,
        );
        const activeSpaceRoute =
          activeNavItemId === `pms-space-${spaceId}` ||
          activeNavItemId.startsWith(`pms-space-${spaceId}-docs`);

        setPmsTeams((current) => current.filter((team) => team.id !== spaceId));
        setPmsTaskLists((current) =>
          current.filter((list) => list.team_id !== spaceId),
        );
        setPmsFolders((current) =>
          current.filter((folder) => folder.team_id !== spaceId),
        );
        setSpaceDocsMap((current) => {
          const next = new Map(current);
          next.delete(spaceId);
          return next;
        });
        knownSpaceIdsRef.current.delete(spaceId);
        setExpandedSpaces((current) => {
          const next = new Set(current);
          next.delete(spaceId);
          return next;
        });

        if (activeSpaceRoute || activeListInSpace) {
          navigate(
            currentWorkspaceSlug
              ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms')
              : pmsRootPath,
          );
        }
      } catch (error) {
        setPmsError(
          getErrorMessage(error, '스페이스를 휴지통으로 옮기지 못했습니다.'),
        );
      }
    },
    [
      activeNavItemId,
      confirm,
      currentWorkspaceSlug,
      navigate,
      pmsLists,
      pmsRootPath,
      token,
    ],
  );

  const groupedSpaces = useMemo(() => {
    type SpaceGroup = {
      team: PmsSpace;
      rootLists: PmsTaskList[];
      folders: Map<string, FolderWithLists>;
    };

    const folderMap = new Map(pmsFolders.map((folder) => [folder.id, folder]));
    const spaces = new Map<string, SpaceGroup>();

    for (const team of pmsTeams) {
      spaces.set(team.id, {
        team,
        rootLists: [],
        folders: new Map(),
      });
    }

    function ensureGroup(teamId: string, fallbackName: string): SpaceGroup {
      const existing = spaces.get(teamId);
      if (existing) return existing;
      const placeholder: PmsSpace = {
        id: teamId,
        workspace_id: '',
        workspace_key: '',
        key: '',
        name: fallbackName,
        description: '',
        member_count: 0,
        current_user_role: null,
        created_at: '',
        updated_at: '',
      };
      const created: SpaceGroup = {
        team: placeholder,
        rootLists: [],
        folders: new Map<string, FolderWithLists>(),
      };
      spaces.set(teamId, created);
      return created;
    }

    for (const list of pmsLists) {
      if (!list.team_id) {
        continue;
      }

      const current = ensureGroup(
        list.team_id,
        list.team_name ?? 'Untitled Space',
      );
      if (list.folder_id && folderMap.has(list.folder_id)) {
        const folder = folderMap.get(list.folder_id);
        if (folder) {
          const folderEntry = current.folders.get(folder.id) ?? {
            folder,
            lists: [],
          };
          folderEntry.lists.push(list);
          current.folders.set(folder.id, folderEntry);
        } else {
          current.rootLists.push(list);
        }
      } else {
        current.rootLists.push(list);
      }
    }

    for (const folder of pmsFolders) {
      if (!folder.team_id) continue;
      const current = ensureGroup(folder.team_id, 'Untitled Space');
      if (!current.folders.has(folder.id)) {
        current.folders.set(folder.id, { folder, lists: [] });
      }
    }

    const sortByOrderThenName = (left: PmsTaskList, right: PmsTaskList) =>
      left.sort_order - right.sort_order ||
      left.name.localeCompare(right.name, 'ko');

    return Array.from(spaces.values())
      .map((space) => ({
        ...space.team,
        rootLists: [...space.rootLists].sort(sortByOrderThenName),
        folders: Array.from(space.folders.values())
          .map((entry) => ({
            folder: entry.folder,
            lists: [...entry.lists].sort(sortByOrderThenName),
          }))
          .sort(
            (left, right) =>
              left.folder.sort_order - right.folder.sort_order ||
              left.folder.name.localeCompare(right.folder.name, 'ko'),
          ),
      }))
      .sort((left, right) => left.name.localeCompare(right.name, 'ko'));
  }, [pmsFolders, pmsLists, pmsTeams]);

  useEffect(() => {
    setExpandedSpaces((current) => {
      const next = new Set(current);
      for (const space of groupedSpaces) {
        if (!knownSpaceIdsRef.current.has(space.id)) {
          knownSpaceIdsRef.current.add(space.id);
          next.add(space.id);
        }
      }
      return next;
    });
  }, [groupedSpaces]);

  return (
    <>
      {confirmDialog}
      {promptDialog}
      <SpaceOrderEditorModal
        isOpen={orderEditorSpace !== null}
        onClose={() => setOrderEditorSpace(null)}
        spaceName={orderEditorSpace?.name ?? ''}
        folders={pmsFolders.filter(
          (folder) => folder.team_id === orderEditorSpace?.id,
        )}
        lists={pmsLists.filter((list) => list.team_id === orderEditorSpace?.id)}
        docs={
          orderEditorSpace ? (spaceDocsMap.get(orderEditorSpace.id) ?? []) : []
        }
        onSave={async (payload) => {
          if (!orderEditorSpace) return;
          await handleSaveSpaceOrder(orderEditorSpace.id, payload);
        }}
      />
      <div className="space-y-1">
        <div className="w-full flex items-center justify-between px-3 py-1">
          <button
            onClick={onToggle}
            className="sidebar-section-label sidebar-section-header group/section flex items-center gap-1"
          >
            {isExpanded ? (
              <ChevronDown
                size={11}
                className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
              />
            ) : (
              <ChevronRight
                size={11}
                className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
              />
            )}
            <span>Spaces</span>
          </button>
          {canWriteTeams && (
            <button
              onClick={() => setCreateSpaceOpen(true)}
              className="p-1 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
              title="Create Space"
            >
              <Plus size={12} />
            </button>
          )}
        </div>

        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden space-y-1"
            >
              {pmsLoading ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2
                    size={14}
                    className="animate-spin text-gray-500 dark:text-gray-400"
                  />
                </div>
              ) : (
                <>
                  {pmsError ? (
                    <div className="px-2">
                      <InlineNotice tone="danger">{pmsError}</InlineNotice>
                    </div>
                  ) : null}
                  {groupedSpaces.map((space, index) => {
                    const spaceCanCreate = teamRoleAllows(
                      space.current_user_role,
                      'member',
                    );
                    const spaceCanManage = canManageSpace(space);
                    return (
                      <SpaceItem
                        key={space.id}
                        spaceId={space.id}
                        name={space.name}
                        iconColor={SPACE_COLORS[index % SPACE_COLORS.length]}
                        rootLists={space.rootLists}
                        folders={space.folders}
                        expanded={expandedSpaces.has(space.id)}
                        onToggle={() => toggleSpace(space.id)}
                        onNavigate={() =>
                          navigate(`/tool/pms-space-${space.id}`)
                        }
                        onAddList={() => openCreateTaskList(space.id)}
                        onAddListToFolder={(folderId) => {
                          setCreateTaskListTeamId(space.id);
                          setCreateTaskListFolderId(folderId);
                          setCreateTaskListOpen(true);
                        }}
                        onAddFolder={() => openCreateFolder(space.id)}
                        onOpenDocs={() => {
                          void handleCreateDoc(space.id);
                        }}
                        onCreateWhiteboard={() => {
                          void handleCreateWhiteboard(space.id);
                        }}
                        onOpenWhiteboards={() => {
                          navigate(`/tool/pms-space-${space.id}-whiteboards`);
                        }}
                        onMoveFolder={(folderId, direction) => {
                          void handleMoveFolder(space.id, folderId, direction);
                        }}
                        onRenameFolder={(folderId, currentName) => {
                          void handleRenameFolder(folderId, currentName);
                        }}
                        onDeleteFolder={(folderId) => {
                          void handleDeleteFolder(folderId);
                        }}
                        onRenameSpace={(newName) => {
                          void handleRenameSpace(space.id, newName);
                        }}
                        onDeleteSpace={() => {
                          void handleDeleteSpace(space.id);
                        }}
                        onManageMembers={() => {
                          setManageMembersSpace({
                            id: space.id,
                            name: space.name,
                            canManage: spaceCanManage,
                            currentUserRole: space.current_user_role,
                          });
                        }}
                        onOpenOrderEditor={() => {
                          setOrderEditorSpace({
                            id: space.id,
                            name: space.name,
                          });
                        }}
                        spaceDocs={spaceDocsMap.get(space.id) ?? []}
                        onRenameDoc={(pageId, newTitle) => {
                          void handleRenameDoc(pageId, newTitle);
                        }}
                        onDeleteDoc={(pageId) => {
                          void handleDeleteDoc(pageId);
                        }}
                        onReorderList={(activeListId, overListId, zone) =>
                          handleReorderList(
                            space.id,
                            activeListId,
                            overListId,
                            zone,
                          )
                        }
                        onReorderDoc={(activeDocId, overDocId, zone) =>
                          handleReorderDoc(
                            space.id,
                            activeDocId,
                            overDocId,
                            zone,
                          )
                        }
                        activeNavItemId={activeNavItemId}
                        canCreateSpaceContent={spaceCanCreate}
                        canManageSpace={spaceCanManage}
                        canManageCollections={teamRoleAllows(
                          space.current_user_role,
                          'admin',
                        )}
                      />
                    );
                  })}

                  {canWriteTeams && (
                    <button
                      onClick={() => setCreateSpaceOpen(true)}
                      className="sidebar-submenu-item ml-1 w-full"
                    >
                      <Plus size={13} />
                      <span className="sidebar-submenu-label">New Space</span>
                    </button>
                  )}
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <CreateTaskListModal
        isOpen={createTaskListOpen}
        onClose={() => setCreateTaskListOpen(false)}
        teamId={createTaskListTeamId}
        folderId={createTaskListFolderId}
        onCreated={(list) => {
          setPmsTaskLists((current) => upsertList(current, list));
          const teamId = list.team_id;
          if (teamId) {
            knownSpaceIdsRef.current.add(teamId);
            setExpandedSpaces((current) => {
              const next = new Set(current);
              next.add(teamId);
              return next;
            });
          }
          navigate(`/tool/pms-list-${list.id}`);
        }}
      />

      <CreateSpaceModal
        isOpen={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={(space) => {
          knownSpaceIdsRef.current.add(space.id);
          setPmsTeams((current) => upsertSpace(current, space));
          setExpandedSpaces((current) => new Set(current).add(space.id));
        }}
      />

      <SpaceMembersModal
        isOpen={manageMembersSpace !== null}
        onClose={() => setManageMembersSpace(null)}
        spaceId={manageMembersSpace?.id ?? null}
        spaceName={manageMembersSpace?.name ?? ''}
        canManage={manageMembersSpace?.canManage ?? false}
        currentUserRole={manageMembersSpace?.currentUserRole ?? null}
        onChanged={() => {
          if (token) {
            listSpaces(token)
              .then((teams) => {
                if (Array.isArray(teams)) setPmsTeams(teams);
              })
              .catch(() => undefined);
          }
        }}
      />

      {createFolderTeamId && (
        <CreateFolderModal
          isOpen={createFolderOpen}
          onClose={() => setCreateFolderOpen(false)}
          teamId={createFolderTeamId}
          onCreated={(folder) => {
            setPmsFolders((current) => [...current, folder]);
            if (token) {
              listPmsTaskLists(token)
                .then((res) => setPmsTaskLists(res.items))
                .catch(() => undefined);
            }
          }}
        />
      )}
    </>
  );
}
