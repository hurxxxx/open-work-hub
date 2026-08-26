import {
  type ReactNode,
  type SetStateAction,
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import {
  useParams,
  Link,
  Navigate,
  useSearchParams,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LazyMotion, domAnimation, m, AnimatePresence } from 'motion/react';
import { useConfirm } from '@open-work-hub/ui/feedback/confirm-dialog';
import { usePrompt } from '@open-work-hub/ui/feedback/prompt-dialog';
import { useFeedback } from '@open-work-hub/ui';
import {
  Archive,
  ArchiveRestore,
  Layout,
  Star,
  Plus,
  PencilRuler,
  List as ListIcon,
  Grid,
  Calendar,
  Activity,
  Table,
  Download,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  buildWorkspaceAppPath,
  getWorkspaceBySlug,
  getCurrentOrLastWorkspaceSlug,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  getPmsTaskList,
  listAllPmsTaskLists,
  listSpaces,
  listSpaceMembers,
  listAllTaskListTasks,
  listTaskListMilestones,
  listTaskListLabels,
  listTaskListStatuses,
  getTaskDetail,
  createTaskListTask,
  deletePmsTaskList,
  deleteTask,
  reorderTaskListTasks,
  updateTask,
  updatePmsTaskList,
  exportTaskListCsv,
  DEFAULT_PMS_TASK_SORT,
  type TaskFilterParams,
  type PmsTaskList,
  type PmsTask,
  type PmsTaskListMember,
  type PmsSpace,
  type PmsMilestone,
  type PmsLabel,
  type PmsTaskListStatus,
  type PmsTaskSort,
} from '../api/pms-api';
import {
  createDefaultTaskFilterParams,
  filterDefaultVisibleTasks,
  hasSelectedCompletionStatus,
  reconcileSelectedTaskIds,
  setCompletionStatusesVisible,
  withEffectiveTaskStatusFilter,
} from '../api/pms-filters';

import { SpaceTasksView } from './SpaceTasksView';
import { ListView } from './ListView';
import { BoardView } from './BoardView';
import { CalendarView } from './CalendarView';
import { GanttView } from './GanttView';
import { TableView } from './TableView';
import { TaskDetail } from './TaskDetail';
import { TaskDetailModal } from './TaskDetailModal';
import { NewTaskModal } from './NewTaskModal';
import { AssignedToMeView } from './AssignedToMeView';
import { TodayOverdueView } from './TodayOverdueView';
import { TaskListSettingsPanel } from './TaskListSettingsPanel';
import { CreateSpaceModal } from './CreateSpaceModal';
import { FilterBar } from './FilterBar';
import { BulkActionBar } from './BulkActionBar';
import { SpaceDocsView } from './SpaceDocsView';
import { SpaceWhiteboardsView } from './SpaceWhiteboardsView';
import { SpaceOverviewView } from './SpaceOverviewView';
import { ListContextMenu } from '../sidebar/ListContextMenu';
import {
  PmsCenteredLoadingState,
  PmsCenteredStateBlock,
} from './PmsCenteredStateBlock';
import {
  EMPTY_SELECTED_TASK_IDS,
  buildInlineTaskCreatePayload,
  createDefaultTaskFilterParamsForList,
  resolveScopedTaskFilterState,
  resolveScopedTaskSelectionState,
  selectScopedTaskFilterParams,
  selectScopedTaskSelectionIds,
  type ScopedTaskFilterState,
  type ScopedTaskSelectionState,
} from './pms-view-scoped-state-model';
import {
  buildPmsSpaceToolPath,
  clearPmsCreateTaskSearchParams,
  readPmsCreateTaskRequest,
  resolvePmsViewRoute,
} from './pms-view-route';
import {
  findPmsTaskById,
  getRequestedPmsTaskId,
  resolvePmsTaskClosedTransition,
  resolvePmsTaskSelectedTransition,
  resolveReloadedPmsTaskSelection,
  resolveRequestedPmsTaskTransition,
  resolveSingleListPmsTaskSelection,
  resolveSingleListPmsTaskDetailTransition,
} from './pms-task-selection-workflow';
import type { TaskBoardPositionUpdate } from './pms-task-hierarchy';
import { taskListRoleAllows } from '../api/pms-permissions';
import { WhiteboardContextSlotPanel } from '@/src/app-modules/whiteboard/public-api';
import {
  PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
  type PersonalTodoPmsTaskCreatedEventDetail,
} from '@/src/platform/personal-widgets/floating-panel-events';
import {
  PMS_SPACE_MEMBERS_CHANGED_EVENT,
  PMS_TASK_LIST_CHANGED_EVENT,
  dispatchPmsTaskListChanged,
  type PmsSpaceMembersChangedDetail,
  type PmsTaskListChangedDetail,
} from './pms-events';
import { usePmsTaskListGroupPreference } from './usePmsTaskListGroupPreference';
import { reconcilePmsTaskListCatalog } from './pms-task-list-catalog-model';

type PmsViewTab =
  | 'List'
  | 'Board'
  | 'Calendar'
  | 'Gantt'
  | 'Table'
  | 'Whiteboard';

const PMS_VIEW_TAB_LABEL_KEYS: Record<PmsViewTab, string> = {
  List: 'pms.viewTabs.list',
  Board: 'pms.viewTabs.board',
  Calendar: 'pms.viewTabs.calendar',
  Gantt: 'pms.viewTabs.gantt',
  Table: 'pms.viewTabs.table',
  Whiteboard: 'pms.viewTabs.whiteboard',
};

const PMS_VIEW_TABS = [
  'List',
  'Board',
  'Calendar',
  'Gantt',
  'Table',
  'Whiteboard',
] as const satisfies readonly PmsViewTab[];

const PMS_MOBILE_PRIMARY_TABS = [
  'List',
  'Board',
  'Calendar',
] as const satisfies readonly PmsViewTab[];

const PMS_MOBILE_MORE_TABS = [
  'Gantt',
  'Table',
  'Whiteboard',
] as const satisfies readonly PmsViewTab[];

const PMS_VIEW_TAB_QUERY: Record<string, PmsViewTab> = {
  board: 'Board',
  calendar: 'Calendar',
  gantt: 'Gantt',
  list: 'List',
  table: 'Table',
  whiteboard: 'Whiteboard',
};

function isSameListCollection(
  left: PmsTaskList[],
  right: PmsTaskList[],
): boolean {
  return (
    left.length === right.length &&
    left.every((item, index) => {
      const other = right[index];
      return (
        item?.id === other?.id &&
        item?.updated_at === other?.updated_at &&
        item?.archived === other?.archived &&
        item?.name === other?.name &&
        item?.team_id === other?.team_id &&
        item?.folder_id === other?.folder_id
      );
    })
  );
}

function resolveLoadedSpaceName(
  spaces: PmsSpace[],
  taskLists: PmsTaskList[],
  spaceId: string,
): string | null {
  return (
    spaces.find((space) => space.id === spaceId)?.name ??
    taskLists.find((taskList) => taskList.team_id === spaceId)?.team_name ??
    null
  );
}

export const PMSView = () => <>{usePMSViewElement()}</>;

function usePMSViewElement(): ReactNode {
  const { t } = useTranslation('apps');
  const { toolId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token, user } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const toast = useFeedback();
  const pmsRoot = resolveDefaultWorkspaceAppPath(user, 'pms');
  const currentWorkspaceSlug =
    getWorkspaceBySlug(user, searchParams.get('workspace'))?.slug ??
    getCurrentOrLastWorkspaceSlug();
  const pmsListRootPath = currentWorkspaceSlug
    ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms')
    : pmsRoot;
  const [selectedIssueDraft, setSelectedIssueDraft] = useState<PmsTask | null>(
    null,
  );
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);
  const [newTaskModalKey, setNewTaskModalKey] = useState(0);
  const [newTaskContext, setNewTaskContext] = useState<{
    initialTitle: string;
    sourceTodoId: string | null;
  }>({ initialTitle: '', sourceTodoId: null });

  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [spaces, setSpaces] = useState<PmsSpace[]>([]);
  const [selectedTaskListId, setSelectedTaskListId] = useState<string>('');
  const [tasks, setIssues] = useState<PmsTask[]>([]);
  const [members, setMembers] = useState<PmsTaskListMember[]>([]);
  const [milestones, setMilestones] = useState<PmsMilestone[]>([]);
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [taskListStatusState, setTaskListStatusState] = useState<{
    taskListId: string;
    items: PmsTaskListStatus[];
  }>({ taskListId: '', items: [] });
  const [taskSort, setTaskSort] = useState<PmsTaskSort>(DEFAULT_PMS_TASK_SORT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterParamsState, setFilterParamsState] =
    useState<ScopedTaskFilterState>(() => ({
      taskListId: '',
      params: createDefaultTaskFilterParams(),
    }));
  const [selectedTaskIdsState, setSelectedTaskIdsState] =
    useState<ScopedTaskSelectionState>({
      taskListId: '',
      ids: EMPTY_SELECTED_TASK_IDS,
    });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [taskListMenuOpen, setTaskListMenuOpen] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);

  const taskListMenuButtonRef = useRef<HTMLButtonElement>(null);
  const mobileMoreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mobileMoreOpen) return;
    function onClick(e: MouseEvent) {
      if (
        mobileMoreRef.current &&
        !mobileMoreRef.current.contains(e.target as Node)
      ) {
        setMobileMoreOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [mobileMoreOpen]);

  const createTaskRequested = searchParams.get('create') === '1';
  const createTaskRequest = useMemo(
    () => readPmsCreateTaskRequest(searchParams),
    [searchParams],
  );
  const pmsRoute = resolvePmsViewRoute({
    createTaskRequested,
    isNewTaskModalOpen,
    requestedTab: searchParams.get('tab'),
    routePathname: location.pathname,
    toolId,
  });
  const isAssignedTasksView = pmsRoute.kind === 'assigned';
  const isTodayView = pmsRoute.kind === 'today';
  const routeTaskListId = pmsRoute.kind === 'list' ? pmsRoute.taskListId : null;
  const spaceDocsSpaceId =
    pmsRoute.kind === 'spaceDocs' ? pmsRoute.spaceId : null;
  const spaceDocsDocId = pmsRoute.kind === 'spaceDocs' ? pmsRoute.docId : null;
  const spaceWhiteboardsSpaceId =
    pmsRoute.kind === 'spaceWhiteboards' ? pmsRoute.spaceId : null;
  const spaceWhiteboardsWhiteboardId =
    pmsRoute.kind === 'spaceWhiteboards' ? pmsRoute.whiteboardId : null;
  const spaceOverviewId =
    pmsRoute.kind === 'spaceOverview' ? pmsRoute.spaceId : null;
  const spaceTasksSpaceId =
    pmsRoute.kind === 'spaceTasks' ? pmsRoute.spaceId : null;
  const spaceTasksTab = pmsRoute.kind === 'spaceTasks' ? pmsRoute.tab : null;
  const isOverviewRoute = pmsRoute.kind === 'overview';
  const shouldLoadSingleTaskList =
    pmsRoute.kind === 'list' || pmsRoute.kind === 'taskCreateFallback';
  const selectedTaskList = taskLists.find(
    (taskList) => taskList.id === selectedTaskListId,
  );
  const selectedIssue = resolveSingleListPmsTaskSelection({
    selectedTaskListId,
    task: selectedIssueDraft,
  });
  const taskListName = selectedTaskList?.name || 'List';
  const isArchivedTaskList = selectedTaskList?.archived === true;
  const canEditTaskList =
    !isArchivedTaskList && taskListRoleAllows(selectedTaskList?.role, 'member');
  const canManageTaskList = taskListRoleAllows(selectedTaskList?.role, 'admin');
  const createTaskContextRef = useRef({
    canEditTaskList: false,
    selectedTaskListId: '',
  });
  createTaskContextRef.current = { canEditTaskList, selectedTaskListId };
  const requestedTaskId = getRequestedPmsTaskId(searchParams);
  const requestedTab = searchParams.get('tab');
  const taskListSettingsRequested = searchParams.get('settings') === '1';
  const activeTab = PMS_VIEW_TAB_QUERY[requestedTab ?? ''] ?? 'List';
  const { groupBy: taskListGroupBy, setGroupBy: setTaskListGroupBy } =
    usePmsTaskListGroupPreference({
      enabled: pmsRoute.kind === 'list' && activeTab === 'List',
      workspaceSlug: currentWorkspaceSlug,
    });
  const defaultFilterParams = useMemo(
    () => createDefaultTaskFilterParamsForList(),
    [],
  );
  const filterParams = selectScopedTaskFilterParams(
    filterParamsState,
    selectedTaskListId,
    defaultFilterParams,
  );
  const taskListStatuses = useMemo(
    () =>
      taskListStatusState.taskListId === selectedTaskListId
        ? taskListStatusState.items
        : [],
    [selectedTaskListId, taskListStatusState],
  );
  const taskListStatusesReady =
    taskListStatusState.taskListId === selectedTaskListId;
  const setFilterParams = useCallback(
    (next: SetStateAction<TaskFilterParams>) => {
      setFilterParamsState((current) =>
        resolveScopedTaskFilterState(current, selectedTaskListId, next),
      );
    },
    [selectedTaskListId],
  );
  const selectedTaskIds = selectScopedTaskSelectionIds(
    selectedTaskIdsState,
    selectedTaskListId,
  );
  const setSelectedTaskIds = useCallback(
    (next: SetStateAction<Set<string>>) => {
      setSelectedTaskIdsState((current) =>
        resolveScopedTaskSelectionState(current, selectedTaskListId, next),
      );
    },
    [selectedTaskListId],
  );
  const visibleTasks = useMemo(
    () =>
      filterDefaultVisibleTasks(tasks, taskListStatuses, {
        status: filterParams.status,
      }),
    [filterParams.status, taskListStatuses, tasks],
  );
  const showCompletedItems = hasSelectedCompletionStatus(
    filterParams.status,
    taskListStatuses,
  );
  const handleShowCompletedItemsChange = useCallback(
    (showCompleted: boolean) => {
      setFilterParams((current) => ({
        ...current,
        status: setCompletionStatusesVisible(
          current.status,
          taskListStatuses,
          showCompleted,
        ),
      }));
    },
    [setFilterParams, taskListStatuses],
  );
  useEffect(() => {
    setSelectedTaskIds((current) =>
      reconcileSelectedTaskIds(current, visibleTasks),
    );
  }, [setSelectedTaskIds, visibleTasks]);
  const selectedTaskListWhiteboardContext = useMemo(
    () =>
      selectedTaskListId
        ? { app: 'pms', type: 'task_list', id: selectedTaskListId }
        : null,
    [selectedTaskListId],
  );
  const mobileMoreActive = PMS_MOBILE_MORE_TABS.includes(
    activeTab as (typeof PMS_MOBILE_MORE_TABS)[number],
  );

  const openNewTaskModal = useCallback(
    ({
      initialTitle = '',
      sourceTodoId = null,
    }: {
      initialTitle?: string | null;
      sourceTodoId?: string | null;
    } = {}) => {
      setNewTaskContext({
        initialTitle: initialTitle?.trim() ?? '',
        sourceTodoId,
      });
      setNewTaskModalKey((current) => current + 1);
      setIsNewTaskModalOpen(true);
    },
    [],
  );

  const closeNewTaskModal = useCallback(() => {
    setIsNewTaskModalOpen(false);
    setNewTaskContext({ initialTitle: '', sourceTodoId: null });
  }, []);

  const selectViewTab = (tab: typeof activeTab) => {
    setMobileMoreOpen(false);
    const nextParams = new URLSearchParams(searchParams);
    if (tab === 'List') {
      nextParams.delete('tab');
    } else {
      nextParams.set('tab', tab.toLowerCase());
    }
    setSearchParams(nextParams, { replace: true });
  };

  useEffect(() => {
    if (!token || !selectedTaskList?.team_id) return;
    let cancelled = false;
    const selectedSpaceId = selectedTaskList.team_id;

    const reloadSpaceMembers = async () => {
      try {
        const response = await listSpaceMembers(
          token,
          selectedSpaceId,
          currentWorkspaceSlug,
        );
        if (!cancelled) {
          setMembers(response.items);
        }
      } catch {
        // Keep the current assignee candidates if a cross-panel refresh fails.
      }
    };

    const handleSpaceMembersChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsSpaceMembersChangedDetail>)
        .detail;
      if (detail?.spaceId !== selectedSpaceId) return;
      void reloadSpaceMembers();
    };

    window.addEventListener(
      PMS_SPACE_MEMBERS_CHANGED_EVENT,
      handleSpaceMembersChanged,
    );
    return () => {
      cancelled = true;
      window.removeEventListener(
        PMS_SPACE_MEMBERS_CHANGED_EVENT,
        handleSpaceMembersChanged,
      );
    };
  }, [currentWorkspaceSlug, selectedTaskList?.team_id, token]);

  useEffect(() => {
    if (
      !taskListSettingsRequested ||
      !selectedTaskListId ||
      loading ||
      isArchivedTaskList
    )
      return;
    setSettingsOpen(true);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('settings');
    setSearchParams(nextParams, { replace: true });
  }, [
    loading,
    searchParams,
    isArchivedTaskList,
    selectedTaskListId,
    setSearchParams,
    taskListSettingsRequested,
  ]);

  const getErrorMessage = useCallback(
    (error: unknown, fallback: string) =>
      error instanceof Error ? error.message : fallback,
    [],
  );

  const applyIssueCollection = useCallback(
    (nextIssues: PmsTask[]) => {
      setIssues(nextIssues);
      setSelectedTaskIds((current) =>
        reconcileSelectedTaskIds(current, nextIssues),
      );
      setSelectedIssueDraft((current) => {
        return resolveReloadedPmsTaskSelection({
          currentTask: current,
          missingPolicy: 'clear',
          tasks: nextIssues,
        });
      });
    },
    [setSelectedTaskIds],
  );

  const handleSelectIssue = useCallback(
    (task: PmsTask) => {
      const transition = resolvePmsTaskSelectedTransition({
        searchParams,
        task,
      });
      setSelectedIssueDraft(transition.selectedTask);
      if (transition.searchParams) {
        setSearchParams(transition.searchParams, { replace: true });
      }
    },
    [searchParams, setSearchParams],
  );

  const clearSelectedIssue = useCallback(() => {
    setSelectedIssueDraft(null);
    if (!requestedTaskId) {
      return;
    }

    const transition = resolvePmsTaskClosedTransition<PmsTask>({
      searchParams,
    });
    setSelectedIssueDraft(transition.selectedTask);
    if (transition.searchParams) {
      setSearchParams(transition.searchParams, { replace: true });
    }
  }, [requestedTaskId, searchParams, setSearchParams]);

  useEffect(() => {
    const handleTaskListChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsTaskListChangedDetail>).detail;
      if (!detail) return;
      if (detail.type === 'updated') {
        setTaskLists((current) =>
          reconcilePmsTaskListCatalog(current, detail.taskList, 'active'),
        );
        return;
      }

      setTaskLists((current) =>
        current.filter((taskList) => taskList.id !== detail.taskListId),
      );
      if (selectedTaskListId === detail.taskListId) {
        clearSelectedIssue();
        setSelectedTaskListId('');
        navigate(pmsListRootPath);
      }
    };

    window.addEventListener(PMS_TASK_LIST_CHANGED_EVENT, handleTaskListChanged);
    return () => {
      window.removeEventListener(
        PMS_TASK_LIST_CHANGED_EVENT,
        handleTaskListChanged,
      );
    };
  }, [clearSelectedIssue, navigate, pmsListRootPath, selectedTaskListId]);

  const handleRenameSelectedTaskList = useCallback(async () => {
    if (
      !token ||
      !selectedTaskList ||
      !canManageTaskList ||
      selectedTaskList.archived
    )
      return;
    const newName = await prompt({
      title: t('pms.sidebar.renameList'),
      defaultValue: selectedTaskList.name,
      placeholder: t('pms.listName'),
      submitLabel: t('common:actions.save'),
      cancelLabel: t('common:actions.cancel'),
    });
    const trimmedName = newName?.trim() ?? '';
    if (!trimmedName || trimmedName === selectedTaskList.name) return;
    setError(null);
    try {
      const updated = await updatePmsTaskList(token, selectedTaskList.id, {
        name: trimmedName,
      });
      setTaskLists((current) =>
        reconcilePmsTaskListCatalog(current, updated, 'active'),
      );
      dispatchPmsTaskListChanged({ type: 'updated', taskList: updated });
    } catch (error) {
      setError(getErrorMessage(error, t('pms.sidebar.renameListFailed')));
    }
  }, [canManageTaskList, getErrorMessage, prompt, selectedTaskList, t, token]);

  const handleArchiveSelectedTaskList = useCallback(async () => {
    if (
      !token ||
      !selectedTaskList ||
      !canManageTaskList ||
      selectedTaskList.archived
    )
      return;
    const confirmed = await confirm({
      title: t('pms.archive.confirmTitle'),
      description: t('pms.archive.confirmDescription', {
        name: selectedTaskList.name,
      }),
      confirmLabel: t('pms.archive.action'),
      cancelLabel: t('common:actions.cancel'),
    });
    if (!confirmed) return;

    setError(null);
    try {
      const updated = await updatePmsTaskList(token, selectedTaskList.id, {
        archived: true,
      });
      setTaskLists((current) =>
        reconcilePmsTaskListCatalog(current, updated, 'active'),
      );
      dispatchPmsTaskListChanged({ type: 'updated', taskList: updated });
      toast.success(
        t('pms.archive.archivedToast', { name: selectedTaskList.name }),
      );
      clearSelectedIssue();
      setSelectedTaskListId('');
      navigate(
        updated.team_id
          ? buildPmsSpaceToolPath(updated.team_id, {
              workspaceSlug: currentWorkspaceSlug,
            })
          : pmsListRootPath,
      );
    } catch (caughtError) {
      toast.error(getErrorMessage(caughtError, t('pms.archive.archiveFailed')));
    }
  }, [
    canManageTaskList,
    clearSelectedIssue,
    confirm,
    currentWorkspaceSlug,
    getErrorMessage,
    navigate,
    pmsListRootPath,
    selectedTaskList,
    t,
    toast,
    token,
  ]);

  const handleRestoreSelectedTaskList = useCallback(async () => {
    if (
      !token ||
      !selectedTaskList ||
      !canManageTaskList ||
      !selectedTaskList.archived
    )
      return;

    setError(null);
    try {
      const updated = await updatePmsTaskList(token, selectedTaskList.id, {
        archived: false,
      });
      setTaskLists((current) =>
        reconcilePmsTaskListCatalog(current, updated, 'active'),
      );
      dispatchPmsTaskListChanged({ type: 'updated', taskList: updated });
      toast.success(
        t('pms.archive.restoredToast', { name: selectedTaskList.name }),
      );
    } catch (caughtError) {
      toast.error(getErrorMessage(caughtError, t('pms.archive.restoreFailed')));
    }
  }, [canManageTaskList, getErrorMessage, selectedTaskList, t, toast, token]);

  const handleDeleteSelectedTaskList = useCallback(async () => {
    if (
      !token ||
      !selectedTaskList ||
      !canManageTaskList ||
      !selectedTaskList.archived
    )
      return;
    const confirmed = await confirm({
      title: t('pms.sidebar.deleteList'),
      description: t('pms.sidebar.deleteListDescription', {
        name: selectedTaskList.name,
      }),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!confirmed) return;
    setError(null);
    try {
      await deletePmsTaskList(token, selectedTaskList.id);
      setTaskLists((current) =>
        current.filter((taskList) => taskList.id !== selectedTaskList.id),
      );
      dispatchPmsTaskListChanged({
        type: 'deleted',
        taskListId: selectedTaskList.id,
      });
      clearSelectedIssue();
      setSelectedTaskListId('');
      navigate(
        selectedTaskList.team_id
          ? buildPmsSpaceToolPath(selectedTaskList.team_id, {
              workspaceSlug: currentWorkspaceSlug,
            })
          : pmsListRootPath,
      );
    } catch (error) {
      setError(getErrorMessage(error, t('pms.sidebar.deleteListFailed')));
    }
  }, [
    canManageTaskList,
    clearSelectedIssue,
    confirm,
    currentWorkspaceSlug,
    getErrorMessage,
    navigate,
    pmsListRootPath,
    selectedTaskList,
    t,
    token,
  ]);

  // Keep the task list catalog in sync with the route so newly created lists open immediately.
  useEffect(() => {
    if (!token) return;
    const activeToken = token;
    let cancelled = false;

    async function loadTaskLists() {
      setLoading(true);
      setError(null);

      try {
        const [response, spaceItems] = await Promise.all([
          listAllPmsTaskLists(activeToken, undefined, currentWorkspaceSlug),
          listSpaces(activeToken, currentWorkspaceSlug),
        ]);
        if (cancelled) {
          return;
        }

        setSpaces(spaceItems);
        let nextTaskLists = response.items;
        let requestedTaskListResolved = false;

        if (routeTaskListId) {
          requestedTaskListResolved = response.items.some(
            (taskList) => taskList.id === routeTaskListId,
          );
          if (!requestedTaskListResolved) {
            const requestedTaskList = await getPmsTaskList(
              activeToken,
              routeTaskListId,
            );
            if (cancelled) {
              return;
            }
            nextTaskLists = [...response.items, requestedTaskList];
            requestedTaskListResolved = true;
          }
        }

        setTaskLists((current) =>
          isSameListCollection(current, nextTaskLists)
            ? current
            : nextTaskLists,
        );
        setSelectedTaskListId((current) => {
          if (!shouldLoadSingleTaskList) {
            return '';
          }
          if (routeTaskListId) {
            return requestedTaskListResolved ? routeTaskListId : '';
          }
          if (createTaskRequested) {
            if (
              current &&
              nextTaskLists.some(
                (taskList) =>
                  taskList.id === current &&
                  taskListRoleAllows(taskList.role, 'member'),
              )
            ) {
              return current;
            }
            return (
              nextTaskLists.find((taskList) =>
                taskListRoleAllows(taskList.role, 'member'),
              )?.id ?? ''
            );
          }
          if (
            current &&
            nextTaskLists.some((taskList) => taskList.id === current)
          ) {
            return current;
          }
          return nextTaskLists[0]?.id || '';
        });
      } catch (err) {
        if (cancelled) {
          return;
        }
        setSelectedTaskListId('');
        setError(getErrorMessage(err, t('pms.errors.listLoadFailed')));
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTaskLists();

    return () => {
      cancelled = true;
    };
  }, [
    createTaskRequested,
    currentWorkspaceSlug,
    getErrorMessage,
    routeTaskListId,
    shouldLoadSingleTaskList,
    token,
    t,
  ]);

  const reloadIssues = useCallback(
    async (statuses: PmsTaskListStatus[] = taskListStatuses) => {
      if (!token || !selectedTaskListId) return;

      try {
        setError(null);
        const res = await listAllTaskListTasks(
          token,
          selectedTaskListId,
          withEffectiveTaskStatusFilter(filterParams, statuses),
          undefined,
          { sort: taskSort },
        );
        applyIssueCollection(res.items);
      } catch (err) {
        setError(getErrorMessage(err, t('pms.errors.issueLoadFailed')));
      }
    },
    [
      applyIssueCollection,
      getErrorMessage,
      filterParams,
      selectedTaskListId,
      taskListStatuses,
      taskSort,
      token,
      t,
    ],
  );

  const startTaskListDataLoad = useCallback(() => {
    setLoading(true);
    setError(null);
  }, []);

  const applyTaskListDataLoad = useCallback(
    ({
      issues,
      nextMembers,
      nextMilestones,
      nextLabels,
      nextStatuses,
    }: {
      issues: PmsTask[];
      nextMembers: PmsTaskListMember[];
      nextMilestones: PmsMilestone[];
      nextLabels: PmsLabel[];
      nextStatuses: PmsTaskListStatus[];
    }) => {
      applyIssueCollection(issues);
      setMembers(nextMembers);
      setMilestones(nextMilestones);
      setLabels(nextLabels);
      setTaskListStatusState({
        taskListId: selectedTaskListId,
        items: nextStatuses,
      });
    },
    [applyIssueCollection, selectedTaskListId],
  );

  const failTaskListDataLoad = useCallback(
    (err: unknown) => {
      setError(getErrorMessage(err, t('pms.errors.listDataFailed')));
    },
    [getErrorMessage, t],
  );

  // Load tasks, members, milestones, labels, and statuses when the selected list changes.
  useEffect(() => {
    if (!token || !selectedTaskListId || !shouldLoadSingleTaskList) return;
    let cancelled = false;
    const selectedList = taskLists.find(
      (taskList) => taskList.id === selectedTaskListId,
    );
    const selectedSpaceId = selectedList?.team_id;
    const statusRequest = listTaskListStatuses(token, selectedTaskListId);
    startTaskListDataLoad();
    Promise.all([
      statusRequest.then((statusResponse) =>
        listAllTaskListTasks(
          token,
          selectedTaskListId,
          withEffectiveTaskStatusFilter(filterParams, statusResponse.items),
          undefined,
          { sort: taskSort },
        ),
      ),
      selectedSpaceId
        ? listSpaceMembers(token, selectedSpaceId, currentWorkspaceSlug)
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }),
      listTaskListMilestones(token, selectedTaskListId),
      listTaskListLabels(token, selectedTaskListId),
      statusRequest,
    ])
      .then(([issueRes, memberRes, milestoneRes, labelRes, statusRes]) => {
        if (cancelled) return;
        applyTaskListDataLoad({
          issues: issueRes.items,
          nextMembers: memberRes.items,
          nextMilestones: milestoneRes.items,
          nextLabels: labelRes.items,
          nextStatuses: statusRes.items,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        failTaskListDataLoad(err);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    applyTaskListDataLoad,
    currentWorkspaceSlug,
    failTaskListDataLoad,
    taskLists,
    token,
    selectedTaskListId,
    shouldLoadSingleTaskList,
    filterParams,
    startTaskListDataLoad,
    taskSort,
  ]);

  const toggleIssueSelection = useCallback(
    (taskId: string) => {
      setSelectedTaskIds((prev) => {
        const next = new Set(prev);
        if (next.has(taskId)) next.delete(taskId);
        else next.add(taskId);
        return next;
      });
    },
    [setSelectedTaskIds],
  );

  const handleBulkDone = useCallback(async () => {
    setSelectedTaskIds(new Set());
    await reloadIssues();
  }, [reloadIssues, setSelectedTaskIds]);

  const handleLabelsChanged = useCallback((updated: PmsLabel[]) => {
    setLabels(updated);
  }, []);

  const handleMembersChanged = useCallback((updated: PmsTaskListMember[]) => {
    setMembers(updated);
  }, []);

  const handleStatusesChanged = useCallback(
    (updated: PmsTaskListStatus[]) => {
      setTaskListStatusState({
        taskListId: selectedTaskListId,
        items: updated,
      });
      void reloadIssues(updated);
    },
    [reloadIssues, selectedTaskListId],
  );

  const handleReorderIssues = useCallback(
    async (updates: TaskBoardPositionUpdate[]) => {
      if (
        !token ||
        !selectedTaskListId ||
        !canEditTaskList ||
        updates.length === 0
      ) {
        return;
      }
      const result = await reorderTaskListTasks(
        token,
        selectedTaskListId,
        {
          items: updates.map((update) => {
            const item: {
              board_position: number;
              parent_id?: string | null;
              task_id: string;
            } = {
              board_position: update.boardPosition,
              task_id: update.taskId,
            };
            if (update.parentId !== undefined) item.parent_id = update.parentId;
            return item;
          }),
        },
        currentWorkspaceSlug,
      );
      if (result.items.length === 0) return;
      const updatedById = new Map(
        result.items.map((item) => [item.id, item] as const),
      );
      applyIssueCollection(
        tasks.map((item) => updatedById.get(item.id) ?? item),
      );
    },
    [
      applyIssueCollection,
      canEditTaskList,
      currentWorkspaceSlug,
      selectedTaskListId,
      tasks,
      token,
    ],
  );

  const handleUpdateIssue = useCallback(
    async (taskId: string, payload: Record<string, unknown>) => {
      if (!token || !canEditTaskList) return;
      const updatedIssue = await updateTask(token, taskId, payload);
      applyIssueCollection(
        tasks.map((item) =>
          item.id === updatedIssue.id ? updatedIssue : item,
        ),
      );
      await reloadIssues();
    },
    [applyIssueCollection, canEditTaskList, tasks, reloadIssues, token],
  );

  const handleCreateIssueInline = useCallback(
    async (title: string, parentId: string | null) => {
      if (!token || !selectedTaskListId || !canEditTaskList) return;
      const createdIssue = await createTaskListTask(
        token,
        selectedTaskListId,
        buildInlineTaskCreatePayload(title, taskListStatuses, parentId),
      );
      applyIssueCollection([...tasks, createdIssue]);
      await reloadIssues();
    },
    [
      applyIssueCollection,
      canEditTaskList,
      tasks,
      reloadIssues,
      selectedTaskListId,
      taskListStatuses,
      token,
    ],
  );

  const handleDeleteIssueInline = useCallback(
    async (taskId: string) => {
      if (!token || !canEditTaskList) return;
      await deleteTask(token, taskId);
      applyIssueCollection(tasks.filter((task) => task.id !== taskId));
      await reloadIssues();
    },
    [applyIssueCollection, canEditTaskList, tasks, reloadIssues, token],
  );

  const prepareRequestedTaskLoad = useCallback(() => {
    setError(null);
    setSelectedTaskIds(new Set());
  }, [setSelectedTaskIds]);

  const applyRequestedTaskDetail = useCallback((task: PmsTask) => {
    const transition = resolveSingleListPmsTaskDetailTransition(task);
    const { listState } = transition;
    setFilterParamsState({
      taskListId: listState.taskListId,
      params: listState.filterParams,
    });
    setSelectedTaskIdsState({
      taskListId: listState.taskListId,
      ids: listState.selectedIds,
    });
    setSelectedTaskListId(listState.taskListId);
    setSelectedIssueDraft(transition.selectedTask);
  }, []);

  useEffect(() => {
    const transition = resolveRequestedPmsTaskTransition({
      requestedTaskId,
      visibleTask: findPmsTaskById(tasks, requestedTaskId),
    });
    if (transition.selectedTask) {
      setSelectedIssueDraft(transition.selectedTask);
      return;
    }
    if (!token || !transition.detailRequest) {
      return;
    }

    let cancelled = false;
    prepareRequestedTaskLoad();

    getTaskDetail(token, transition.detailRequest.taskId, currentWorkspaceSlug)
      .then((detail) => {
        if (cancelled) {
          return;
        }

        applyRequestedTaskDetail(detail.task);
      })
      .catch((caughtError) => {
        if (cancelled) {
          return;
        }

        setError(
          getErrorMessage(caughtError, t('pms.errors.requestedIssueFailed')),
        );
      });

    return () => {
      cancelled = true;
    };
  }, [
    applyRequestedTaskDetail,
    currentWorkspaceSlug,
    getErrorMessage,
    prepareRequestedTaskLoad,
    requestedTaskId,
    tasks,
    token,
    t,
  ]);

  const consumeCreateTaskRequest = useCallback(
    (
      nextParams: URLSearchParams,
      request: { sourceTodoId: string | null; title: string },
    ) => {
      const createTaskContext = createTaskContextRef.current;
      if (
        !createTaskContext.selectedTaskListId ||
        !createTaskContext.canEditTaskList
      ) {
        setSearchParams(nextParams, { replace: true });
        queueMicrotask(() => setError(t('pms.errors.createTaskNoList')));
        return;
      }

      setSearchParams(nextParams, { replace: true });
      queueMicrotask(() =>
        openNewTaskModal({
          initialTitle: request.title,
          sourceTodoId: request.sourceTodoId,
        }),
      );
    },
    [openNewTaskModal, setSearchParams, t],
  );

  useEffect(() => {
    if (!createTaskRequested || loading) {
      return;
    }

    const nextParams = clearPmsCreateTaskSearchParams(searchParams);

    queueMicrotask(() =>
      consumeCreateTaskRequest(nextParams, createTaskRequest),
    );
  }, [
    consumeCreateTaskRequest,
    createTaskRequest,
    createTaskRequested,
    loading,
    searchParams,
  ]);

  const handleNewTaskCreated = useCallback(
    (createdTask: PmsTask) => {
      void reloadIssues();
      if (!newTaskContext.sourceTodoId) {
        return;
      }
      window.dispatchEvent(
        new CustomEvent<PersonalTodoPmsTaskCreatedEventDetail>(
          PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
          {
            detail: {
              taskId: createdTask.id,
              title: createdTask.title,
              todoId: newTaskContext.sourceTodoId,
            },
          },
        ),
      );
    },
    [newTaskContext.sourceTodoId, reloadIssues],
  );

  if (isAssignedTasksView) {
    return <AssignedToMeView workspaceSlug={currentWorkspaceSlug} />;
  }
  if (isTodayView) {
    return <TodayOverdueView workspaceSlug={currentWorkspaceSlug} />;
  }
  if (spaceDocsSpaceId) {
    const spaceName = resolveLoadedSpaceName(
      spaces,
      taskLists,
      spaceDocsSpaceId,
    );
    return (
      <SpaceDocsView
        spaceId={spaceDocsSpaceId}
        spaceName={spaceName}
        docId={spaceDocsDocId}
        workspaceSlug={currentWorkspaceSlug}
      />
    );
  }
  if (spaceWhiteboardsSpaceId) {
    const spaceName = resolveLoadedSpaceName(
      spaces,
      taskLists,
      spaceWhiteboardsSpaceId,
    );
    return (
      <SpaceWhiteboardsView
        spaceId={spaceWhiteboardsSpaceId}
        spaceName={spaceName}
        whiteboardId={spaceWhiteboardsWhiteboardId}
        workspaceSlug={currentWorkspaceSlug}
      />
    );
  }
  if (spaceTasksSpaceId && spaceTasksTab) {
    const spaceName = resolveLoadedSpaceName(
      spaces,
      taskLists,
      spaceTasksSpaceId,
    );
    return (
      <SpaceTasksView
        activeTab={spaceTasksTab}
        spaceId={spaceTasksSpaceId}
        spaceName={spaceName}
        workspaceSlug={currentWorkspaceSlug}
      />
    );
  }
  if (spaceOverviewId) {
    const spaceName = resolveLoadedSpaceName(
      spaces,
      taskLists,
      spaceOverviewId,
    );
    return (
      <SpaceOverviewView
        spaceId={spaceOverviewId}
        spaceName={spaceName}
        workspaceSlug={currentWorkspaceSlug}
      />
    );
  }
  if (isOverviewRoute) {
    if (loading) {
      return <PmsCenteredLoadingState minHeightClassName="h-full" />;
    }
    if (error) {
      return (
        <PmsCenteredStateBlock minHeightClassName="h-full" tone="danger">
          {error}
        </PmsCenteredStateBlock>
      );
    }
    if (spaces.length > 0) {
      return (
        <Navigate
          replace
          to={buildPmsSpaceToolPath(spaces[0].id, {
            workspaceSlug: currentWorkspaceSlug,
          })}
        />
      );
    }
    return (
      <>
        <div className="flex h-full items-center justify-center px-8">
          <div className="w-full max-w-xl rounded-2xl border border-app-border bg-app-surface p-8 text-center">
            <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-app-accent text-app-accent-fg">
              <Layout size={22} />
            </div>
            <h1 className="app-text-title-lg text-app-ink">
              {t('pms.noSpacesTitle')}
            </h1>
            <p className="app-text-body mt-3 text-app-ink/60">
              {t('pms.noSpacesDescription')}
            </p>
            <div className="mt-6 flex justify-center">
              <button
                className="app-text-control-sm rounded-lg bg-app-accent px-4 py-2 text-app-accent-fg transition-colors hover:bg-app-accent/90"
                onClick={() => setCreateSpaceOpen(true)}
                type="button"
              >
                {t('pms.createSpace')}
              </button>
            </div>
          </div>
        </div>
        <CreateSpaceModal
          isOpen={createSpaceOpen}
          onClose={() => setCreateSpaceOpen(false)}
          workspaceSlug={currentWorkspaceSlug}
          onCreated={(space) => {
            setSpaces((current) => [
              space,
              ...current.filter((item) => item.id !== space.id),
            ]);
            navigate(
              buildPmsSpaceToolPath(space.id, {
                workspaceSlug: currentWorkspaceSlug,
              }),
            );
          }}
        />
      </>
    );
  }
  if (error && !loading && !selectedTaskListId) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-app-danger-text">
        {error}
      </div>
    );
  }
  if (!selectedTaskListId && !loading) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-app-ink/55">
        {t('pms.overviewPage.noLists')}
      </div>
    );
  }

  return (
    <LazyMotion features={domAnimation}>
      <div className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
        <header className="border-b border-app-border bg-app-bg px-4 pt-4 transition-colors lg:px-6 lg:pt-3">
          {/* Row 1: breadcrumb */}
          <nav className="app-text-caption mb-1.5 hidden min-w-0 items-center gap-1.5 text-app-ink/55 lg:flex">
            <Link
              to={
                currentWorkspaceSlug
                  ? `/w/${encodeURIComponent(currentWorkspaceSlug)}/pms`
                  : pmsRoot
              }
              className="hover:text-app-ink transition-colors shrink-0"
            >
              {t('pms.title')}
            </Link>
            {selectedTaskList?.team_name ? (
              <>
                <span className="text-app-ink/70 shrink-0">/</span>
                <span className="truncate max-w-[160px]">
                  {selectedTaskList.team_name}
                </span>
              </>
            ) : null}
            {selectedTaskList?.folder_name ? (
              <>
                <span className="text-app-ink/70 shrink-0">/</span>
                <span className="truncate max-w-[160px]">
                  {selectedTaskList.folder_name}
                </span>
              </>
            ) : null}
          </nav>

          {/* Row 2: title + actions */}
          <div className="mb-3 flex min-w-0 items-start justify-between gap-3 lg:items-center lg:gap-4">
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              <div className="flex size-8 shrink-0 items-center justify-center rounded bg-app-accent text-app-accent-fg lg:size-7">
                <Layout size={16} />
              </div>
              <div className="min-w-0">
                <h1 className="app-text-title-md min-w-0 truncate text-app-ink">
                  {selectedTaskList?.name || taskListName}
                </h1>
                {selectedTaskList?.team_name ? (
                  <p className="app-text-caption mt-0.5 truncate text-app-ink/45 lg:hidden">
                    {selectedTaskList.team_name}
                  </p>
                ) : null}
              </div>
              {isArchivedTaskList ? (
                <span className="app-text-caption inline-flex shrink-0 items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink/60">
                  <Archive size={12} />
                  {t('pms.archive.archivedBadge')}
                </span>
              ) : null}
              {canManageTaskList ? (
                <div className="relative shrink-0">
                  <button
                    ref={taskListMenuButtonRef}
                    type="button"
                    onClick={() => setTaskListMenuOpen((open) => !open)}
                    className="flex size-7 items-center justify-center rounded text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                    title={t('pms.spaceTree.listManagement')}
                    aria-label={t('pms.spaceTree.listManagement')}
                    aria-expanded={taskListMenuOpen}
                    aria-haspopup="menu"
                  >
                    <MoreHorizontal size={14} />
                  </button>
                  <ListContextMenu
                    open={taskListMenuOpen}
                    anchorRef={taskListMenuButtonRef}
                    onClose={() => setTaskListMenuOpen(false)}
                    onSettings={
                      isArchivedTaskList
                        ? undefined
                        : () => setSettingsOpen(true)
                    }
                    onRename={
                      isArchivedTaskList
                        ? undefined
                        : handleRenameSelectedTaskList
                    }
                    onArchive={
                      isArchivedTaskList
                        ? undefined
                        : handleArchiveSelectedTaskList
                    }
                    onRestore={
                      isArchivedTaskList
                        ? handleRestoreSelectedTaskList
                        : undefined
                    }
                    onDelete={
                      isArchivedTaskList
                        ? handleDeleteSelectedTaskList
                        : undefined
                    }
                  />
                </div>
              ) : null}
              <button
                type="button"
                className="shrink-0 text-app-ink/70 hover:text-yellow-500 transition-colors"
                title={t('pms.actions.favorite')}
              >
                <Star size={14} />
              </button>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {canManageTaskList && !isArchivedTaskList ? (
                <button
                  type="button"
                  onClick={() => void handleArchiveSelectedTaskList()}
                  className="app-text-control-sm hidden h-8 items-center gap-1.5 rounded px-2.5 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink lg:inline-flex"
                >
                  <Archive size={14} />
                  {t('pms.archive.action')}
                </button>
              ) : null}
              {canManageTaskList && isArchivedTaskList ? (
                <button
                  type="button"
                  onClick={() => void handleRestoreSelectedTaskList()}
                  className="app-text-control-sm hidden h-8 items-center gap-1.5 rounded border border-app-border px-2.5 text-app-ink/70 transition-colors hover:bg-app-surface-hover hover:text-app-ink lg:inline-flex"
                >
                  <ArchiveRestore size={14} />
                  {t('pms.archive.restore')}
                </button>
              ) : null}
              {selectedTaskListId && (
                <button
                  type="button"
                  onClick={() => {
                    if (token)
                      void exportTaskListCsv(token, selectedTaskListId);
                  }}
                  className="flex size-8 items-center justify-center rounded text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                  title={t('pms.actions.exportCsv')}
                >
                  <Download size={15} />
                </button>
              )}
              {canEditTaskList ? (
                <>
                  <div className="w-px h-5 bg-app-border mx-1" />
                  <button
                    type="button"
                    onClick={() => openNewTaskModal()}
                    className="app-control-primary h-9 w-9 shadow-sm sm:w-auto sm:px-3 lg:h-8"
                    aria-label={t('pms.newTask')}
                  >
                    <Plus size={14} />
                    <span className="hidden sm:inline">{t('pms.newTask')}</span>
                  </button>
                </>
              ) : null}
            </div>
          </div>

          <div className="hidden items-center gap-6 lg:flex">
            {PMS_VIEW_TABS.map((tab) => (
              <button
                type="button"
                key={tab}
                onClick={() => selectViewTab(tab)}
                className={cn(
                  'app-text-control-sm relative pb-3 transition-all',
                  activeTab === tab
                    ? 'text-app-ink'
                    : 'text-app-ink/55 hover:text-app-ink',
                )}
              >
                <div className="flex items-center gap-2">
                  {tab === 'List' && <ListIcon size={14} />}
                  {tab === 'Board' && <Grid size={14} />}
                  {tab === 'Calendar' && <Calendar size={14} />}
                  {tab === 'Gantt' && <Activity size={14} />}
                  {tab === 'Table' && <Table size={14} />}
                  {tab === 'Whiteboard' && <PencilRuler size={14} />}
                  {t(PMS_VIEW_TAB_LABEL_KEYS[tab])}
                </div>
                {activeTab === tab && (
                  <m.div
                    layoutId="activeTab"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-app-accent"
                  />
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1 pb-3 lg:hidden">
            <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
              {PMS_MOBILE_PRIMARY_TABS.map((tab) => (
                <button
                  type="button"
                  key={tab}
                  onClick={() => selectViewTab(tab)}
                  className={cn(
                    'app-control shrink-0 px-3',
                    activeTab === tab
                      ? 'app-control-active'
                      : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
                  )}
                >
                  {tab === 'List' && <ListIcon size={14} />}
                  {tab === 'Board' && <Grid size={14} />}
                  {tab === 'Calendar' && <Calendar size={14} />}
                  {t(PMS_VIEW_TAB_LABEL_KEYS[tab])}
                </button>
              ))}
            </div>

            <div ref={mobileMoreRef} className="relative shrink-0">
              <button
                type="button"
                onClick={() => setMobileMoreOpen((open) => !open)}
                className={cn(
                  'app-control px-3',
                  mobileMoreActive
                    ? 'app-control-active'
                    : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
                )}
              >
                <MoreHorizontal size={14} />
                {t('pms.actions.more')}
              </button>
              {mobileMoreOpen ? (
                <div className="absolute right-0 top-full z-30 mt-1 w-44 rounded-lg border border-app-border bg-app-bg py-1 shadow-xl">
                  {PMS_MOBILE_MORE_TABS.map((tab) => (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => selectViewTab(tab)}
                      className={cn(
                        'app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-app-surface-hover',
                        activeTab === tab ? 'text-app-accent' : 'text-app-ink',
                      )}
                    >
                      {tab === 'Gantt' && <Activity size={14} />}
                      {tab === 'Table' && <Table size={14} />}
                      {tab === 'Whiteboard' && <PencilRuler size={14} />}
                      {t(PMS_VIEW_TAB_LABEL_KEYS[tab])}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {isArchivedTaskList ? (
          <div className="app-text-caption flex items-center gap-2 border-b border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink/60 lg:px-6">
            <Archive size={13} className="shrink-0" />
            <span>{t('pms.archive.readOnlyNotice')}</span>
          </div>
        ) : null}

        {selectedTaskListId && activeTab !== 'Whiteboard' && (
          <FilterBar
            taskListId={selectedTaskListId}
            filterParams={filterParams}
            setFilterParams={setFilterParams}
            members={members}
            currentUserId={user?.id}
            milestones={milestones}
            labels={labels}
            taskListStatuses={taskListStatuses}
          />
        )}

        <main
          className={cn(
            'min-h-0 min-w-0 flex-1 custom-scrollbar',
            activeTab === 'Whiteboard'
              ? 'overflow-hidden p-2 lg:p-4'
              : activeTab === 'List'
                ? 'overflow-hidden p-4 lg:p-8'
                : 'overflow-y-auto p-4 lg:p-8',
          )}
        >
          {loading && tasks.length === 0 ? (
            <PmsCenteredLoadingState />
          ) : error ? (
            <PmsCenteredStateBlock tone="danger">{error}</PmsCenteredStateBlock>
          ) : (
            <AnimatePresence mode="wait">
              {activeTab === 'List' && (
                <m.div
                  key="list"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="h-full min-h-0 min-w-0"
                >
                  <ListView
                    completedItemsControlDisabled={!taskListStatusesReady}
                    groupBy={taskListGroupBy}
                    tasks={visibleTasks}
                    onGroupByChange={setTaskListGroupBy}
                    onSortChange={setTaskSort}
                    onShowCompletedItemsChange={handleShowCompletedItemsChange}
                    showCompletedItems={showCompletedItems}
                    sort={taskSort}
                    onSelectIssue={handleSelectIssue}
                    selectedIds={selectedTaskIds}
                    onToggleSelect={toggleIssueSelection}
                    taskListStatuses={taskListStatuses}
                    members={members}
                    currentUserId={user?.id}
                    canEdit={canEditTaskList}
                    onUpdateIssue={handleUpdateIssue}
                    onReorderIssues={handleReorderIssues}
                    onCreateIssue={handleCreateIssueInline}
                    onDeleteIssue={handleDeleteIssueInline}
                  />
                </m.div>
              )}
              {activeTab === 'Board' && (
                <m.div
                  key="board"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="h-full"
                >
                  <BoardView
                    tasks={visibleTasks}
                    onSelectIssue={handleSelectIssue}
                    onUpdateIssue={
                      canEditTaskList ? handleUpdateIssue : undefined
                    }
                    selectedIds={selectedTaskIds}
                    onToggleSelect={
                      canEditTaskList ? toggleIssueSelection : undefined
                    }
                    members={members}
                    taskListStatuses={taskListStatuses}
                  />
                </m.div>
              )}
              {activeTab === 'Calendar' && (
                <m.div
                  key="calendar"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="h-full"
                >
                  <CalendarView
                    tasks={visibleTasks}
                    taskListStatuses={taskListStatuses}
                  />
                </m.div>
              )}
              {activeTab === 'Gantt' && (
                <m.div
                  key="gantt"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="h-full"
                >
                  <GanttView
                    tasks={visibleTasks}
                    taskListStatuses={taskListStatuses}
                    onSelectIssue={handleSelectIssue}
                    onUpdateIssue={handleUpdateIssue}
                    canEdit={canEditTaskList}
                    onOpenStatusSettings={
                      canManageTaskList && !isArchivedTaskList
                        ? () => setSettingsOpen(true)
                        : undefined
                    }
                  />
                </m.div>
              )}
              {activeTab === 'Table' && (
                <m.div
                  key="table"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="h-full"
                >
                  <TableView
                    canEdit={canEditTaskList}
                    tasks={visibleTasks}
                    onSelectIssue={handleSelectIssue}
                    onUpdateIssue={handleUpdateIssue}
                    selectedIds={selectedTaskIds}
                    onToggleSelect={toggleIssueSelection}
                    members={members}
                    taskListStatuses={taskListStatuses}
                  />
                </m.div>
              )}
              {activeTab === 'Whiteboard' &&
                selectedTaskListWhiteboardContext && (
                  <m.div
                    key="whiteboard"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="flex h-full min-h-0"
                  >
                    <WhiteboardContextSlotPanel
                      context={selectedTaskListWhiteboardContext}
                      workspaceSlug={currentWorkspaceSlug}
                      defaultTitle={`${taskListName} Whiteboard`}
                      canEditContext={canEditTaskList}
                      className="min-h-[calc(100vh-220px)] w-full overflow-hidden"
                      editorClassName="min-h-[calc(100vh-220px)]"
                    />
                  </m.div>
                )}
            </AnimatePresence>
          )}
        </main>

        {/* Task detail — full-size modal overlay (ClickUp style) */}
        <AnimatePresence>
          {selectedIssue && (
            <TaskDetailModal
              closeLabel={t('common:actions.close')}
              onClose={clearSelectedIssue}
            >
              <TaskDetail
                task={selectedIssue}
                members={members}
                milestones={milestones}
                taskListLabels={labels}
                taskListStatuses={taskListStatuses}
                spaceName={selectedTaskList?.team_name}
                spaceId={selectedTaskList?.team_id ?? null}
                workspaceSlug={currentWorkspaceSlug}
                canEdit={canEditTaskList}
                onClose={clearSelectedIssue}
                onUpdate={reloadIssues}
              />
            </TaskDetailModal>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {isNewTaskModalOpen && (
            <NewTaskModal
              key={newTaskModalKey}
              isOpen={isNewTaskModalOpen}
              initialTitle={newTaskContext.initialTitle}
              onClose={closeNewTaskModal}
              taskListId={selectedTaskListId}
              taskListSpaceId={selectedTaskList?.team_id ?? null}
              onCreated={handleNewTaskCreated}
              taskListStatuses={taskListStatuses}
              canCreate={canEditTaskList}
              workspaceSlug={currentWorkspaceSlug}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {settingsOpen && selectedTaskListId && !isArchivedTaskList && (
            <TaskListSettingsPanel
              taskListId={selectedTaskListId}
              taskListName={selectedTaskList?.name ?? null}
              teamId={selectedTaskList?.team_id ?? null}
              workspaceSlug={currentWorkspaceSlug}
              currentUserRole={selectedTaskList?.role ?? null}
              onClose={() => setSettingsOpen(false)}
              onLabelsChanged={handleLabelsChanged}
              onMembersChanged={handleMembersChanged}
              onStatusesChanged={handleStatusesChanged}
            />
          )}
        </AnimatePresence>

        {canEditTaskList && selectedTaskIds.size > 0 && selectedTaskListId && (
          <BulkActionBar
            taskListId={selectedTaskListId}
            selectedIds={selectedTaskIds}
            totalCount={visibleTasks.length}
            onSelectAll={() =>
              setSelectedTaskIds(new Set(visibleTasks.map((task) => task.id)))
            }
            onDeselectAll={() => setSelectedTaskIds(new Set())}
            onDone={handleBulkDone}
            members={members}
            labels={labels}
            taskListStatuses={taskListStatuses}
          />
        )}

        <CreateSpaceModal
          isOpen={createSpaceOpen}
          onClose={() => setCreateSpaceOpen(false)}
          workspaceSlug={currentWorkspaceSlug}
          onCreated={(space) => {
            setSpaces((current) => [
              space,
              ...current.filter((item) => item.id !== space.id),
            ]);
            navigate(
              buildPmsSpaceToolPath(space.id, {
                workspaceSlug: currentWorkspaceSlug,
              }),
            );
          }}
        />
        {promptDialog}
        {confirmDialog}
      </div>
    </LazyMotion>
  );
}
