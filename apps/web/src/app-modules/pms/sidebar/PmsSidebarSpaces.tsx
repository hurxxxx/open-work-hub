import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, LazyMotion, domAnimation, m } from 'motion/react';
import { ChevronDown, ChevronRight, Loader2, Plus } from 'lucide-react';
import { useConfirm } from '@open-work-hub/ui/feedback/confirm-dialog';
import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';
import { usePrompt } from '@open-work-hub/ui/feedback/prompt-dialog';
import { useFeedback } from '@open-work-hub/ui';
import { useTranslation } from 'react-i18next';

import {
  createNativeDoc,
  deleteDocsItem,
  listDocsHub,
  updateDocTarget,
  updateDocsItem,
  withDocsItemPrimaryTargetSortOrder,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  hasWorkspaceMembership,
  teamRoleAllows,
} from '@/src/platform/auth/auth-api';
import {
  listAllPmsTaskLists,
  listFolders,
  deletePmsTaskList,
  updateFolder,
  deleteFolder,
  listSpaces,
  updateSpace,
  deleteSpace,
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
  buildWorkspaceAppEntryPath,
  buildWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import { CreateTaskListModal } from '../views/CreateTaskListModal';
import { CreateSpaceModal } from '../views/CreateSpaceModal';
import { SpaceMembersModal } from '../views/SpaceMembersModal';
import { CreateFolderModal } from '../views/CreateFolderModal';
import {
  SPACE_COLORS,
  buildPmsSidebarSpaceTree,
  getSpaceDocSpaceId,
  getSpaceDocSortOrder,
  sortSpaceDocs,
} from './space-tree-model';
import { SpaceItem } from './SpaceTree';
import { SpaceOrderEditorModal } from './SpaceOrderEditorModal';
import {
  buildSpaceOrderChanges,
  persistSpaceOrderChanges,
} from './space-order-persistence';
import {
  buildPmsSpaceDocsToolPath,
  buildPmsSpaceToolPath,
  buildPmsTaskListToolPath,
} from '../views/pms-view-route';
import {
  PMS_SPACE_CHANGED_EVENT,
  PMS_SPACE_ORDER_CHANGED_EVENT,
  PMS_TASK_LIST_CHANGED_EVENT,
  dispatchPmsSpaceChanged,
  dispatchPmsSpaceOrderChanged,
  dispatchPmsTaskListChanged,
  type PmsSpaceChangedDetail,
  type PmsSpaceOrderChangedDetail,
  type PmsTaskListChangedDetail,
} from '../views/pms-events';
import {
  hasArchivedPmsTaskListInFolder,
  listActivePmsTaskListsForSpace,
  reconcilePmsTaskListCatalog,
} from '../views/pms-task-list-catalog-model';

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

function upsertSpace(
  spaces: PmsSpace[],
  space: PmsSpace,
  locale = 'ko-KR',
): PmsSpace[] {
  return [space, ...spaces.filter((item) => item.id !== space.id)].sort(
    (left, right) => left.name.localeCompare(right.name, locale),
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

async function listSidebarTaskLists(
  token: string,
  workspaceSlug: string,
): Promise<PmsTaskList[]> {
  const [active, archived] = await Promise.all([
    listAllPmsTaskLists(token, undefined, workspaceSlug),
    listAllPmsTaskLists(token, undefined, workspaceSlug, {
      archived: true,
    }).catch(() => null),
  ]);
  return [...active.items, ...(archived?.items ?? [])];
}

export function PmsSidebarSpaces({
  activeNavItemId,
  currentWorkspaceSlug,
  isExpanded,
  onToggle,
}: PmsSidebarSpacesProps) {
  return usePmsSidebarSpacesElement({
    activeNavItemId,
    currentWorkspaceSlug,
    isExpanded,
    onToggle,
  });
}

interface PmsSidebarRuntimeState {
  pmsLists: PmsTaskList[];
  pmsFolders: PmsFolder[];
  pmsTeams: PmsSpace[];
  pmsLoading: boolean;
  pmsError: string | null;
  collapsedSpaces: Set<string>;
  spaceDocsMap: SpaceDocsMap;
}

type SpaceDocsMap = Map<string, DocsHubItem[]>;

type PmsSidebarRuntimeAction =
  | { type: 'loadStart' }
  | {
      type: 'loadComplete';
      lists: PmsTaskList[] | null;
      folders: PmsFolder[];
      teams: PmsSpace[];
    }
  | { type: 'setError'; error: string | null }
  | { type: 'setLists'; updater: (current: PmsTaskList[]) => PmsTaskList[] }
  | { type: 'setFolders'; updater: (current: PmsFolder[]) => PmsFolder[] }
  | { type: 'setTeams'; updater: (current: PmsSpace[]) => PmsSpace[] }
  | {
      type: 'setSpaceDocsMap';
      updater: (current: SpaceDocsMap) => SpaceDocsMap;
    }
  | { type: 'toggleSpace'; spaceId: string }
  | { type: 'expandSpace'; spaceId: string }
  | { type: 'removeSpace'; spaceId: string };

const PMS_SIDEBAR_INITIAL_STATE: PmsSidebarRuntimeState = {
  pmsLists: [],
  pmsFolders: [],
  pmsTeams: [],
  pmsLoading: false,
  pmsError: null,
  collapsedSpaces: new Set(),
  spaceDocsMap: new Map(),
};

function pmsSidebarRuntimeReducer(
  state: PmsSidebarRuntimeState,
  action: PmsSidebarRuntimeAction,
): PmsSidebarRuntimeState {
  switch (action.type) {
    case 'loadStart':
      return { ...state, pmsLoading: true, pmsError: null };
    case 'loadComplete':
      return {
        ...state,
        pmsLists: action.lists ?? state.pmsLists,
        pmsFolders: action.folders,
        pmsTeams: action.teams,
        pmsLoading: false,
      };
    case 'setError':
      return { ...state, pmsError: action.error };
    case 'setLists':
      return { ...state, pmsLists: action.updater(state.pmsLists) };
    case 'setFolders':
      return { ...state, pmsFolders: action.updater(state.pmsFolders) };
    case 'setTeams':
      return { ...state, pmsTeams: action.updater(state.pmsTeams) };
    case 'setSpaceDocsMap':
      return { ...state, spaceDocsMap: action.updater(state.spaceDocsMap) };
    case 'toggleSpace': {
      const collapsedSpaces = new Set(state.collapsedSpaces);
      if (collapsedSpaces.has(action.spaceId)) {
        collapsedSpaces.delete(action.spaceId);
      } else {
        collapsedSpaces.add(action.spaceId);
      }
      return { ...state, collapsedSpaces };
    }
    case 'expandSpace': {
      if (!state.collapsedSpaces.has(action.spaceId)) {
        return state;
      }
      const collapsedSpaces = new Set(state.collapsedSpaces);
      collapsedSpaces.delete(action.spaceId);
      return { ...state, collapsedSpaces };
    }
    case 'removeSpace': {
      const collapsedSpaces = new Set(state.collapsedSpaces);
      collapsedSpaces.delete(action.spaceId);
      const spaceDocsMap = new Map(state.spaceDocsMap);
      spaceDocsMap.delete(action.spaceId);
      return {
        ...state,
        pmsTeams: state.pmsTeams.filter((team) => team.id !== action.spaceId),
        pmsLists: state.pmsLists.filter(
          (list) => list.team_id !== action.spaceId,
        ),
        pmsFolders: state.pmsFolders.filter(
          (folder) => folder.team_id !== action.spaceId,
        ),
        collapsedSpaces,
        spaceDocsMap,
      };
    }
    default:
      return state;
  }
}

function usePmsSidebarSpacesElement({
  activeNavItemId,
  currentWorkspaceSlug,
  isExpanded,
  onToggle,
}: PmsSidebarSpacesProps) {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const { token, user } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const toast = useFeedback();
  const hasWorkspaceContext = Boolean(currentWorkspaceSlug);
  const canReadTeams =
    hasWorkspaceContext && hasWorkspaceMembership(user, currentWorkspaceSlug);
  const canWriteTeams = canReadTeams;
  const pmsRootPath = currentWorkspaceSlug
    ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms')
    : buildWorkspaceAppEntryPath('pms');
  const canManageSpace = useCallback(
    (team: PmsSpace) => teamRoleAllows(team.current_user_role, 'admin'),
    [],
  );

  const [state, dispatch] = useReducer(
    pmsSidebarRuntimeReducer,
    PMS_SIDEBAR_INITIAL_STATE,
  );
  const {
    pmsLists,
    pmsFolders,
    pmsTeams,
    pmsLoading,
    pmsError,
    collapsedSpaces,
    spaceDocsMap,
  } = state;
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
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [createFolderTeamId, setCreateFolderTeamId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    if (!token || !currentWorkspaceSlug) {
      dispatch({
        type: 'loadComplete',
        lists: [],
        folders: [],
        teams: [],
      });
      return undefined;
    }

    dispatch({ type: 'loadStart' });

    Promise.all([
      listSidebarTaskLists(token, currentWorkspaceSlug).catch(() => null),
      listFolders(token, undefined, currentWorkspaceSlug)
        .then((response) => response.items)
        .catch(() => []),
      canReadTeams
        ? listSpaces(token, currentWorkspaceSlug)
            .then((teams) => (Array.isArray(teams) ? teams : []))
            .catch(() => [])
        : Promise.resolve([]),
    ]).then(([lists, folders, teams]) => {
      if (cancelled) return;
      dispatch({
        type: 'loadComplete',
        lists,
        folders,
        teams,
      });
    });

    return () => {
      cancelled = true;
    };
  }, [canReadTeams, currentWorkspaceSlug, token]);

  useEffect(() => {
    if (!token) return;
    for (const team of pmsTeams) {
      if (!teamRoleAllows(team.current_user_role, 'viewer')) {
        continue;
      }
      listDocsHub(token, {
        view: 'all',
        space_id: team.id,
        page_size: 200,
        sort_by: 'target_sort_order',
        sort_dir: 'asc',
      })
        .then((res) =>
          dispatch({
            type: 'setSpaceDocsMap',
            updater: (prev) =>
              new Map(prev).set(team.id, sortSpaceDocs(res.items, locale)),
          }),
        )
        .catch(() => undefined);
    }
  }, [token, pmsTeams, locale]);

  useEffect(() => {
    const handleSpaceChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsSpaceChangedDetail>).detail;
      if (!detail) return;
      if (detail.type === 'updated') {
        dispatch({
          type: 'setTeams',
          updater: (current) => upsertSpace(current, detail.space, locale),
        });
      } else {
        dispatch({ type: 'removeSpace', spaceId: detail.spaceId });
      }
    };

    window.addEventListener(PMS_SPACE_CHANGED_EVENT, handleSpaceChanged);
    return () => {
      window.removeEventListener(PMS_SPACE_CHANGED_EVENT, handleSpaceChanged);
    };
  }, [locale]);

  useEffect(() => {
    const handleTaskListChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsTaskListChangedDetail>).detail;
      if (!detail) return;
      if (detail.type === 'updated') {
        dispatch({
          type: 'setLists',
          updater: (current) =>
            reconcilePmsTaskListCatalog(current, detail.taskList, 'all'),
        });
      } else {
        dispatch({
          type: 'setLists',
          updater: (current) =>
            current.filter((list) => list.id !== detail.taskListId),
        });
      }
    };

    window.addEventListener(PMS_TASK_LIST_CHANGED_EVENT, handleTaskListChanged);
    return () => {
      window.removeEventListener(
        PMS_TASK_LIST_CHANGED_EVENT,
        handleTaskListChanged,
      );
    };
  }, []);

  useEffect(() => {
    const handleSpaceOrderChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsSpaceOrderChangedDetail>).detail;
      if (!detail) return;
      const listChangeMap = new Map(
        detail.listChanges.map((item) => [item.id, item]),
      );
      const docChangeMap = new Map(
        detail.docChanges.map((item) => [item.id, item]),
      );

      dispatch({
        type: 'setLists',
        updater: (current) =>
          current.map((list) => {
            const change = listChangeMap.get(list.id);
            return change
              ? {
                  ...list,
                  folder_id: change.folder_id,
                  sort_order: change.sort_order,
                }
              : list;
          }),
      });
      dispatch({
        type: 'setSpaceDocsMap',
        updater: (current) => {
          const next = new Map(current);
          const docs = (next.get(detail.spaceId) ?? []).map((doc) => {
            const change = docChangeMap.get(doc.id);
            return change
              ? withDocsItemPrimaryTargetSortOrder(doc, change.sort_order)
              : doc;
          });
          next.set(detail.spaceId, sortSpaceDocs(docs, locale));
          return next;
        },
      });
    };

    window.addEventListener(
      PMS_SPACE_ORDER_CHANGED_EVENT,
      handleSpaceOrderChanged,
    );
    return () => {
      window.removeEventListener(
        PMS_SPACE_ORDER_CHANGED_EVENT,
        handleSpaceOrderChanged,
      );
    };
  }, [locale]);

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
    dispatch({ type: 'toggleSpace', spaceId });
  };

  const handleCreateDoc = useCallback(
    async (spaceId: string) => {
      if (!token) return;
      const title = await prompt({
        title: t('pms.sidebar.newDocument'),
        placeholder: t('pms.sidebar.documentName'),
        defaultValue: '',
        submitLabel: t('common:actions.create'),
        cancelLabel: t('common:actions.cancel'),
      });
      if (!title) return;
      try {
        const doc = await createNativeDoc(token, {
          title,
          source_app: 'pms',
          source_kind: 'manual',
          primary_target: {
            app: 'pms',
            type: 'space',
            id: spaceId,
          },
        });
        dispatch({
          type: 'setSpaceDocsMap',
          updater: (prev) => {
            const next = new Map(prev);
            next.set(
              spaceId,
              sortSpaceDocs([...(next.get(spaceId) ?? []), doc], locale),
            );
            return next;
          },
        });
        navigate(
          buildPmsSpaceDocsToolPath({
            docId: doc.id,
            spaceId,
            workspaceSlug: currentWorkspaceSlug,
          }),
        );
      } catch {
        /* ignore */
      }
    },
    [currentWorkspaceSlug, locale, navigate, prompt, token, t],
  );

  const handleRenameDoc = useCallback(
    async (docId: string, newTitle: string) => {
      if (!token) return;
      try {
        const updated = await updateDocsItem(token, docId, { title: newTitle });
        const teamId = getSpaceDocSpaceId(updated);
        if (!teamId) return;
        dispatch({
          type: 'setSpaceDocsMap',
          updater: (prev) => {
            const next = new Map(prev);
            const docs = next.get(teamId) ?? [];
            next.set(
              teamId,
              sortSpaceDocs(
                docs.map((doc) => (doc.id === updated.id ? updated : doc)),
                locale,
              ),
            );
            return next;
          },
        });
      } catch {
        /* ignore */
      }
    },
    [locale, token],
  );

  const handleDeleteDoc = useCallback(
    async (docId: string) => {
      if (!token) return;
      if (
        !(await confirm({
          title: t('pms.sidebar.deleteCollection'),
          description: t('pms.sidebar.deleteCollectionDescription'),
          confirmLabel: t('pms.sidebar.moveToTrash'),
          cancelLabel: t('common:actions.cancel'),
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
        dispatch({
          type: 'setSpaceDocsMap',
          updater: (prev) => {
            const next = new Map(prev);
            for (const [teamId, docs] of next) {
              next.set(
                teamId,
                docs.filter((doc) => doc.id !== docId),
              );
            }
            return next;
          },
        });
        if (
          deletedTeamId &&
          activeNavItemId === `pms-space-${deletedTeamId}-docs-${docId}`
        ) {
          navigate(
            buildPmsSpaceDocsToolPath({
              spaceId: deletedTeamId,
              workspaceSlug: currentWorkspaceSlug,
            }),
          );
        }
      } catch {
        /* ignore */
      }
    },
    [
      activeNavItemId,
      confirm,
      currentWorkspaceSlug,
      navigate,
      spaceDocsMap,
      token,
      t,
    ],
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
          task_count: number;
        }>;
        docs: Array<{
          id: string;
          title: string;
          sort_order: number;
        }>;
      },
    ) => {
      if (!token) return;
      const currentLists = listActivePmsTaskListsForSpace(pmsLists, spaceId);
      const currentDocs = spaceDocsMap.get(spaceId) ?? [];
      const changes = buildSpaceOrderChanges({
        currentDocs,
        currentLists,
        payload,
      });
      const { docChanges, listChanges } = changes;

      if (listChanges.length === 0 && docChanges.length === 0) return;

      const nextListMap = new Map(payload.lists.map((item) => [item.id, item]));
      const nextDocMap = new Map(payload.docs.map((item) => [item.id, item]));
      const listSnapshot = pmsLists;
      const docSnapshot = spaceDocsMap;

      dispatch({
        type: 'setLists',
        updater: (current) =>
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
      });
      dispatch({
        type: 'setSpaceDocsMap',
        updater: (current) => {
          const next = new Map(current);
          const docs = (next.get(spaceId) ?? []).map((doc) => {
            const updated = nextDocMap.get(doc.id);
            return updated
              ? withDocsItemPrimaryTargetSortOrder(doc, updated.sort_order)
              : doc;
          });
          next.set(spaceId, sortSpaceDocs(docs, locale));
          return next;
        },
      });

      try {
        await persistSpaceOrderChanges({ changes, spaceId, token });
        dispatchPmsSpaceOrderChanged({ spaceId, ...changes });
      } catch (error) {
        dispatch({ type: 'setLists', updater: () => listSnapshot });
        dispatch({ type: 'setSpaceDocsMap', updater: () => docSnapshot });
        throw new Error(
          getErrorMessage(error, t('pms.orderEditor.saveFailed')),
        );
      }
    },
    [locale, pmsLists, spaceDocsMap, token, t],
  );

  const handleRenameFolder = useCallback(
    async (folderId: string, currentName: string) => {
      if (!token) return;
      const newName = await prompt({
        title: t('pms.sidebar.renameFolder'),
        defaultValue: currentName,
        placeholder: t('pms.folderName'),
        submitLabel: t('common:actions.save'),
        cancelLabel: t('common:actions.cancel'),
      });
      if (!newName || newName === currentName) return;
      try {
        const updated = await updateFolder(token, folderId, { name: newName });
        dispatch({
          type: 'setFolders',
          updater: (current) =>
            current.map((folder) =>
              folder.id === updated.id ? updated : folder,
            ),
        });
      } catch {
        /* ignore */
      }
    },
    [prompt, token, t],
  );

  const handleRenameTaskList = useCallback(
    async (listId: string, currentName: string) => {
      if (!token) return;
      const newName = await prompt({
        title: t('pms.sidebar.renameList'),
        defaultValue: currentName,
        placeholder: t('pms.listName'),
        submitLabel: t('common:actions.save'),
        cancelLabel: t('common:actions.cancel'),
      });
      const trimmedName = newName?.trim() ?? '';
      if (!trimmedName || trimmedName === currentName) return;
      dispatch({ type: 'setError', error: null });
      try {
        const updated = await updatePmsTaskList(token, listId, {
          name: trimmedName,
        });
        dispatch({
          type: 'setLists',
          updater: (current) =>
            current.map((list) => (list.id === updated.id ? updated : list)),
        });
        dispatchPmsTaskListChanged({ type: 'updated', taskList: updated });
      } catch (error) {
        dispatch({
          type: 'setError',
          error: getErrorMessage(error, t('pms.sidebar.renameListFailed')),
        });
      }
    },
    [prompt, token, t],
  );

  const handleDeleteTaskList = useCallback(
    async (listId: string, currentName: string) => {
      if (!token) return;
      if (
        !(await confirm({
          title: t('pms.sidebar.deleteList'),
          description: t('pms.sidebar.deleteListDescription', {
            name: currentName,
          }),
          confirmLabel: t('common:actions.delete'),
          cancelLabel: t('common:actions.cancel'),
          variant: 'danger',
        }))
      )
        return;
      dispatch({ type: 'setError', error: null });
      try {
        await deletePmsTaskList(token, listId);
        dispatch({
          type: 'setLists',
          updater: (current) => current.filter((list) => list.id !== listId),
        });
        dispatchPmsTaskListChanged({ type: 'deleted', taskListId: listId });
        if (activeNavItemId === `pms-list-${listId}`) {
          navigate(
            currentWorkspaceSlug
              ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms')
              : pmsRootPath,
          );
        }
      } catch (error) {
        dispatch({
          type: 'setError',
          error: getErrorMessage(error, t('pms.sidebar.deleteListFailed')),
        });
      }
    },
    [
      activeNavItemId,
      confirm,
      currentWorkspaceSlug,
      navigate,
      pmsRootPath,
      token,
      t,
    ],
  );

  const handleArchiveTaskList = useCallback(
    async (listId: string, currentName: string, spaceId: string | null) => {
      if (!token) return;
      const confirmed = await confirm({
        title: t('pms.archive.confirmTitle'),
        description: t('pms.archive.confirmDescription', {
          name: currentName,
        }),
        confirmLabel: t('pms.archive.action'),
        cancelLabel: t('common:actions.cancel'),
      });
      if (!confirmed) return;
      dispatch({ type: 'setError', error: null });
      try {
        const updated = await updatePmsTaskList(token, listId, {
          archived: true,
        });
        dispatch({
          type: 'setLists',
          updater: (current) =>
            reconcilePmsTaskListCatalog(current, updated, 'all'),
        });
        dispatchPmsTaskListChanged({ type: 'updated', taskList: updated });
        toast.success(t('pms.archive.archivedToast', { name: currentName }));
        if (activeNavItemId === `pms-list-${listId}`) {
          navigate(
            spaceId
              ? buildPmsSpaceToolPath(spaceId, {
                  workspaceSlug: currentWorkspaceSlug,
                })
              : currentWorkspaceSlug
                ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms')
                : pmsRootPath,
          );
        }
      } catch (error) {
        toast.error(getErrorMessage(error, t('pms.archive.archiveFailed')));
      }
    },
    [
      activeNavItemId,
      confirm,
      currentWorkspaceSlug,
      navigate,
      pmsRootPath,
      t,
      toast,
      token,
    ],
  );

  const handleRestoreTaskList = useCallback(
    async (listId: string, currentName: string) => {
      if (!token) return;
      dispatch({ type: 'setError', error: null });
      try {
        const updated = await updatePmsTaskList(token, listId, {
          archived: false,
        });
        dispatch({
          type: 'setLists',
          updater: (current) =>
            reconcilePmsTaskListCatalog(current, updated, 'all'),
        });
        dispatchPmsTaskListChanged({ type: 'updated', taskList: updated });
        toast.success(t('pms.archive.restoredToast', { name: currentName }));
      } catch (error) {
        toast.error(getErrorMessage(error, t('pms.archive.restoreFailed')));
      }
    },
    [t, toast, token],
  );

  const handleReorderDoc = useCallback(
    async (
      spaceId: string,
      activeDocId: string,
      overDocId: string,
      zone: FlatDropZone,
    ) => {
      if (!token) return;
      dispatch({ type: 'setError', error: null });
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
      dispatch({
        type: 'setSpaceDocsMap',
        updater: (prev) => {
          const next = new Map(prev);
          const docs = (next.get(spaceId) ?? []).map((doc) => {
            const patch = patchMap.get(doc.id);
            return patch
              ? withDocsItemPrimaryTargetSortOrder(doc, patch.sort_order)
              : doc;
          });
          next.set(spaceId, sortSpaceDocs(docs, locale));
          return next;
        },
      });
      try {
        await Promise.all(
          result.patches.map((patch) =>
            updateDocTarget(token, patch.id, {
              app: 'pms',
              type: 'space',
              id: spaceId,
              sort_order: patch.sort_order,
            }),
          ),
        );
      } catch (error) {
        dispatch({ type: 'setSpaceDocsMap', updater: () => snapshot });
        dispatch({
          type: 'setError',
          error: getErrorMessage(error, t('pms.sidebar.docOrderFailed')),
        });
      }
    },
    [locale, spaceDocsMap, token, t],
  );

  const handleReorderList = useCallback(
    async (
      spaceId: string,
      activeListId: string,
      overListId: string,
      zone: FlatDropZone,
    ) => {
      if (!token) return;
      dispatch({ type: 'setError', error: null });
      const listsInSpace = listActivePmsTaskListsForSpace(pmsLists, spaceId);
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
      dispatch({
        type: 'setLists',
        updater: (current) =>
          current.map((list) => {
            const next = patchMap.get(list.id);
            if (!next) return list;
            return {
              ...list,
              sort_order: next.sort_order,
              folder_id: next.parent_id,
            };
          }),
      });
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
        dispatch({ type: 'setLists', updater: () => snapshot });
        dispatch({
          type: 'setError',
          error: getErrorMessage(error, t('pms.sidebar.listOrderFailed')),
        });
      }
    },
    [pmsLists, token, t],
  );

  const handleMoveFolder = useCallback(
    async (spaceId: string, folderId: string, direction: 'up' | 'down') => {
      if (!token) return;
      dispatch({ type: 'setError', error: null });

      const orderedFolders = pmsFolders.filter(
        (folder) => folder.team_id === spaceId,
      );
      orderedFolders.sort(
        (left, right) =>
          left.sort_order - right.sort_order ||
          left.name.localeCompare(right.name, locale),
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

      const updates = nextOrder.flatMap((folder, index) =>
        folder.sort_order === index ? [] : [{ folder, sort_order: index }],
      );

      if (updates.length === 0) return;

      try {
        const updatedFolders = new Map(
          (
            await Promise.all(
              updates.map(({ folder, sort_order }) =>
                updateFolder(token, folder.id, { sort_order }),
              ),
            )
          ).map((updated) => [updated.id, updated] as const),
        );
        dispatch({
          type: 'setFolders',
          updater: (current) =>
            current.map((folder) => updatedFolders.get(folder.id) ?? folder),
        });
      } catch (error) {
        dispatch({
          type: 'setError',
          error: getErrorMessage(error, t('pms.sidebar.folderOrderFailed')),
        });
      }
    },
    [locale, pmsFolders, token, t],
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (!token || !currentWorkspaceSlug) return;
      if (hasArchivedPmsTaskListInFolder(pmsLists, folderId)) {
        toast.error(t('pms.archive.folderDeleteBlocked'));
        return;
      }
      if (
        !(await confirm({
          title: t('pms.sidebar.deleteFolder'),
          description: t('pms.sidebar.deleteFolderDescription'),
          confirmLabel: t('common:actions.delete'),
          cancelLabel: t('common:actions.cancel'),
          variant: 'danger',
        }))
      )
        return;
      try {
        await deleteFolder(token, folderId);
        dispatch({
          type: 'setFolders',
          updater: (current) =>
            current.filter((folder) => folder.id !== folderId),
        });
        listSidebarTaskLists(token, currentWorkspaceSlug)
          .then((lists) => dispatch({ type: 'setLists', updater: () => lists }))
          .catch(() => undefined);
      } catch (error) {
        toast.error(
          getErrorMessage(error, t('pms.sidebar.deleteFolderFailed')),
        );
      }
    },
    [confirm, currentWorkspaceSlug, pmsLists, t, toast, token],
  );

  const handleRenameSpace = useCallback(
    async (spaceId: string, newName: string) => {
      if (!token) return;
      try {
        const updated = await updateSpace(token, spaceId, { name: newName });
        dispatch({
          type: 'setTeams',
          updater: (current) =>
            current.map((team) => (team.id === updated.id ? updated : team)),
        });
        dispatchPmsSpaceChanged({ type: 'updated', space: updated });
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
          title: t('pms.sidebar.deleteSpace'),
          description: t('pms.sidebar.deleteSpaceDescription'),
          confirmLabel: t('pms.sidebar.moveToTrash'),
          cancelLabel: t('common:actions.cancel'),
          variant: 'danger',
        }))
      )
        return;
      dispatch({ type: 'setError', error: null });
      try {
        await deleteSpace(token, spaceId);
        const activeListInSpace = pmsLists.some(
          (list) =>
            list.team_id === spaceId &&
            activeNavItemId === `pms-list-${list.id}`,
        );
        const activeSpaceRoute =
          activeNavItemId === `pms-space-${spaceId}` ||
          activeNavItemId.startsWith(`pms-space-${spaceId}-docs`) ||
          activeNavItemId.startsWith(`pms-space-${spaceId}-whiteboards`);

        dispatch({ type: 'removeSpace', spaceId });
        dispatchPmsSpaceChanged({ type: 'deleted', spaceId });

        if (activeSpaceRoute || activeListInSpace) {
          navigate(
            currentWorkspaceSlug
              ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms')
              : pmsRootPath,
          );
        }
      } catch (error) {
        dispatch({
          type: 'setError',
          error: getErrorMessage(error, t('pms.sidebar.deleteSpaceFailed')),
        });
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
      t,
    ],
  );

  const groupedSpaces = useMemo(() => {
    return buildPmsSidebarSpaceTree({
      folders: pmsFolders,
      lists: pmsLists,
      locale,
      spaces: pmsTeams,
      untitledSpaceName: t('pms.sidebar.untitledSpace'),
    });
  }, [locale, pmsFolders, pmsLists, pmsTeams, t]);

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
        lists={listActivePmsTaskListsForSpace(pmsLists, orderEditorSpace?.id)}
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
            type="button"
            onClick={onToggle}
            className="sidebar-section-label sidebar-section-header group/section flex items-center gap-1"
          >
            {isExpanded ? (
              <ChevronDown
                size={11}
                className="text-app-ink/55 dark:text-app-ink/65 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
              />
            ) : (
              <ChevronRight
                size={11}
                className="text-app-ink/55 dark:text-app-ink/65 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
              />
            )}
            <span>{t('pms.spaces')}</span>
          </button>
        </div>

        <LazyMotion features={domAnimation}>
          <AnimatePresence initial={false}>
            {isExpanded && (
              <m.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden space-y-1"
              >
                {pmsLoading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2
                      size={14}
                      className="animate-spin text-app-ink/55 dark:text-app-ink/65"
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
                          archivedLists={space.archivedLists}
                          folders={space.folders}
                          expanded={!collapsedSpaces.has(space.id)}
                          onToggle={() => toggleSpace(space.id)}
                          onNavigate={() =>
                            navigate(
                              buildPmsSpaceToolPath(space.id, {
                                workspaceSlug: currentWorkspaceSlug,
                              }),
                            )
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
                          onMoveFolder={(folderId, direction) => {
                            void handleMoveFolder(
                              space.id,
                              folderId,
                              direction,
                            );
                          }}
                          onRenameFolder={(folderId, currentName) => {
                            void handleRenameFolder(folderId, currentName);
                          }}
                          onDeleteFolder={(folderId) => {
                            void handleDeleteFolder(folderId);
                          }}
                          onRenameList={(listId, currentName) => {
                            void handleRenameTaskList(listId, currentName);
                          }}
                          onDeleteList={(listId, currentName) => {
                            void handleDeleteTaskList(listId, currentName);
                          }}
                          onArchiveList={(listId, currentName) => {
                            void handleArchiveTaskList(
                              listId,
                              currentName,
                              space.id,
                            );
                          }}
                          onRestoreList={(listId, currentName) => {
                            void handleRestoreTaskList(listId, currentName);
                          }}
                          onOpenListSettings={(listId) => {
                            navigate(
                              buildPmsTaskListToolPath({
                                taskListId: listId,
                                settings: true,
                                workspaceSlug: currentWorkspaceSlug,
                              }),
                            );
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
                          currentWorkspaceSlug={currentWorkspaceSlug}
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
                        type="button"
                        onClick={() => setCreateSpaceOpen(true)}
                        className="sidebar-submenu-item ml-1 w-full"
                      >
                        <Plus size={13} />
                        <span className="sidebar-submenu-label">
                          {t('pms.sidebar.newSpace')}
                        </span>
                      </button>
                    )}
                  </>
                )}
              </m.div>
            )}
          </AnimatePresence>
        </LazyMotion>
      </div>

      <CreateTaskListModal
        isOpen={createTaskListOpen}
        onClose={() => setCreateTaskListOpen(false)}
        teamId={createTaskListTeamId}
        folderId={createTaskListFolderId}
        onCreated={(list) => {
          dispatch({
            type: 'setLists',
            updater: (current) => upsertList(current, list),
          });
          const teamId = list.team_id;
          if (teamId) {
            dispatch({ type: 'expandSpace', spaceId: teamId });
          }
          navigate(
            buildPmsTaskListToolPath({
              taskListId: list.id,
              workspaceSlug: currentWorkspaceSlug,
            }),
          );
        }}
      />

      <CreateSpaceModal
        isOpen={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        workspaceSlug={currentWorkspaceSlug}
        onCreated={(space) => {
          dispatch({
            type: 'setTeams',
            updater: (current) => upsertSpace(current, space, locale),
          });
          dispatch({ type: 'expandSpace', spaceId: space.id });
        }}
      />

      <SpaceMembersModal
        isOpen={manageMembersSpace !== null}
        onClose={() => setManageMembersSpace(null)}
        spaceId={manageMembersSpace?.id ?? null}
        spaceName={manageMembersSpace?.name ?? ''}
        workspaceSlug={currentWorkspaceSlug}
        canManage={manageMembersSpace?.canManage ?? false}
        currentUserRole={manageMembersSpace?.currentUserRole ?? null}
        onChanged={() => {
          if (token) {
            listSpaces(token, currentWorkspaceSlug)
              .then((teams) => {
                if (Array.isArray(teams)) {
                  dispatch({ type: 'setTeams', updater: () => teams });
                }
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
            dispatch({
              type: 'setFolders',
              updater: (current) => [...current, folder],
            });
            if (token && currentWorkspaceSlug) {
              listSidebarTaskLists(token, currentWorkspaceSlug)
                .then((lists) =>
                  dispatch({ type: 'setLists', updater: () => lists }),
                )
                .catch(() => undefined);
            }
          }}
        />
      )}
    </>
  );
}
