import { ChevronDown, FolderKanban, Layout } from 'lucide-react';
import { AnimatePresence, LazyMotion, domAnimation } from 'motion/react';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';
import {
  DEFAULT_PMS_TASK_SORT,
  createTaskListTask,
  deleteTask,
  getTaskDetail,
  listAllPmsTaskLists,
  listAllTaskListTasks,
  listSpaceMembers,
  listTaskListLabels,
  listTaskListMilestones,
  listTaskListStatuses,
  reorderTaskListTasks,
  updateTask,
  type PmsLabel,
  type PmsMilestone,
  type PmsTask,
  type PmsTaskList,
  type PmsTaskListMember,
  type PmsTaskListStatus,
  type TaskFilterParams,
} from '../api/pms-api';
import {
  createDefaultTaskFilterParams,
  filterDefaultVisibleTasks,
  mergeTaskListStatusesForFilter,
  withEffectiveTaskStatusFilter,
} from '../api/pms-filters';
import { taskListRoleAllows } from '../api/pms-permissions';
import { BoardView } from './BoardView';
import { CalendarView } from './CalendarView';
import { FilterBar } from './FilterBar';
import { GanttView } from './GanttView';
import { ListView } from './ListView';
import {
  PmsCenteredLoadingState,
  PmsCenteredStateBlock,
} from './PmsCenteredStateBlock';
import { PmsSpaceToolTabs } from './PmsSpaceToolTabs';
import { TableView } from './TableView';
import { TaskDetail } from './TaskDetail';
import { TaskDetailModal } from './TaskDetailModal';
import { getDefaultTaskStatus, getStatusSlugs } from './pms-constants';
import type { TaskBoardPositionUpdate } from './pms-task-hierarchy';
import {
  findPmsTaskInBundles,
  getRequestedPmsTaskId,
  resolvePmsTaskClosedTransition,
  resolvePmsTaskSelectedTransition,
  resolveRequestedPmsTaskTransition,
} from './pms-task-selection-workflow';
import type { PmsTaskListToolTab } from './pms-view-route';
import { usePmsTaskListChangeSubscription } from './usePmsTaskListChangeSubscription';

type ListBundle = {
  labels: PmsLabel[];
  milestones: PmsMilestone[];
  tasks: PmsTask[];
  members: PmsTaskListMember[];
  statuses: PmsTaskListStatus[];
};

type SpaceTasksViewProps = {
  activeTab: PmsTaskListToolTab;
  spaceId: string;
  spaceName?: string | null;
};

const PMS_SPACE_TASKS_SPACE_MEMBER_CONCURRENCY = 4;
const PMS_SPACE_TASKS_LIST_BUNDLE_CONCURRENCY = 2;

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function sortTaskLists(lists: PmsTaskList[], locale: string): PmsTaskList[] {
  const sorted = Array.from(lists);
  sorted.sort(
    (left, right) =>
      (left.team_name ?? '').localeCompare(right.team_name ?? '', locale) ||
      (left.folder_name ?? '').localeCompare(right.folder_name ?? '', locale) ||
      left.sort_order - right.sort_order ||
      left.name.localeCompare(right.name, locale),
  );
  return sorted;
}

function uniqueBy<T>(items: T[], keyOf: (item: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const key = keyOf(item);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

interface SpaceTasksState {
  taskLists: PmsTaskList[];
  bundles: Map<string, ListBundle>;
  selectedIssue: PmsTask | null;
  loading: boolean;
  error: string | null;
}

type SpaceTasksAction =
  | { type: 'load:start' }
  | {
      type: 'load:success';
      taskLists: PmsTaskList[];
      bundles: Map<string, ListBundle>;
    }
  | { type: 'load:fail'; message: string }
  | { type: 'selected:set'; task: PmsTask | null }
  | { type: 'selected:requested-loaded'; task: PmsTask | null }
  | {
      type: 'bundle:update-tasks';
      listId: string;
      updater: (tasks: PmsTask[]) => PmsTask[];
    };

const INITIAL_SPACE_TASKS_STATE: SpaceTasksState = {
  taskLists: [],
  bundles: new Map(),
  selectedIssue: null,
  loading: true,
  error: null,
};

function spaceTasksReducer(
  state: SpaceTasksState,
  action: SpaceTasksAction,
): SpaceTasksState {
  switch (action.type) {
    case 'load:start':
      return { ...state, loading: true, error: null };
    case 'load:success':
      return {
        ...state,
        taskLists: action.taskLists,
        bundles: action.bundles,
        selectedIssue: state.selectedIssue
          ? (findPmsTaskInBundles(action.bundles, state.selectedIssue.id) ??
            state.selectedIssue)
          : null,
        loading: false,
      };
    case 'load:fail':
      return {
        ...state,
        taskLists: [],
        bundles: new Map(),
        loading: false,
        error: action.message,
      };
    case 'selected:set':
      return { ...state, selectedIssue: action.task };
    case 'selected:requested-loaded':
      return { ...state, selectedIssue: action.task };
    case 'bundle:update-tasks': {
      const bundle = state.bundles.get(action.listId);
      if (!bundle) return state;
      const bundles = new Map(state.bundles);
      bundles.set(action.listId, {
        ...bundle,
        tasks: action.updater(bundle.tasks),
      });
      return { ...state, bundles };
    }
    default:
      return state;
  }
}

function useSpaceTasksViewElement({
  activeTab,
  spaceId,
  spaceName,
}: {
  activeTab: PmsTaskListToolTab;
  spaceId: string;
  spaceName?: string | null;
}) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const { token, user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filterParams, setFilterParams] = useState<TaskFilterParams>(() =>
    createDefaultTaskFilterParams(),
  );
  const [state, dispatch] = useReducer(
    spaceTasksReducer,
    INITIAL_SPACE_TASKS_STATE,
  );
  const loadGenerationRef = useRef(0);
  const { taskLists, bundles, selectedIssue, loading, error } = state;
  const requestedTaskId = getRequestedPmsTaskId(searchParams);

  useEffect(() => {
    if (!requestedTaskId) {
      dispatch({ type: 'selected:set', task: null });
    }
  }, [requestedTaskId]);

  const selectedTaskList = useMemo(
    () =>
      selectedIssue
        ? (taskLists.find(
            (taskList) => taskList.id === selectedIssue.list_id,
          ) ?? null)
        : null,
    [selectedIssue, taskLists],
  );
  const selectedBundle = selectedIssue
    ? (bundles.get(selectedIssue.list_id) ?? null)
    : null;

  const reloadSpaceTasks = useCallback(async () => {
    if (!token) return;
    const loadGeneration = loadGenerationRef.current + 1;
    loadGenerationRef.current = loadGeneration;
    dispatch({ type: 'load:start' });
    try {
      const listResponse = await listAllPmsTaskLists(token, spaceId);
      const sortedLists = sortTaskLists(
        listResponse.items.filter(
          (taskList) => !taskList.archived && taskList.team_id === spaceId,
        ),
        locale,
      );
      const uniqueSpaceIds = Array.from(
        new Set(
          sortedLists
            .map((taskList) => taskList.team_id)
            .filter((spaceId): spaceId is string => Boolean(spaceId)),
        ),
      );
      const memberEntries = await runRequestsWithConcurrency(
        uniqueSpaceIds,
        PMS_SPACE_TASKS_SPACE_MEMBER_CONCURRENCY,
        async (spaceId) => {
          try {
            const response = await listSpaceMembers(token, spaceId);
            return [spaceId, response.items] as const;
          } catch {
            return [spaceId, [] as PmsTaskListMember[]] as const;
          }
        },
      );
      const membersBySpace = new Map(memberEntries);
      const bundleEntries = await runRequestsWithConcurrency(
        sortedLists,
        PMS_SPACE_TASKS_LIST_BUNDLE_CONCURRENCY,
        async (taskList) => {
          const statusRequest = listTaskListStatuses(token, taskList.id).catch(
            () => ({
              items: [] as PmsTaskListStatus[],
            }),
          );
          const [
            issueResponse,
            statusResponse,
            labelResponse,
            milestoneResponse,
          ] = await Promise.all([
            statusRequest.then((response) =>
              listAllTaskListTasks(
                token,
                taskList.id,
                withEffectiveTaskStatusFilter(filterParams, response.items),
              ),
            ),
            statusRequest,
            listTaskListLabels(token, taskList.id).catch(() => ({
              items: [] as PmsLabel[],
            })),
            listTaskListMilestones(token, taskList.id).catch(() => ({
              items: [] as PmsMilestone[],
            })),
          ]);
          return [
            taskList.id,
            {
              labels: labelResponse.items,
              milestones: milestoneResponse.items,
              tasks: issueResponse.items,
              members: taskList.team_id
                ? (membersBySpace.get(taskList.team_id) ?? [])
                : [],
              statuses: statusResponse.items,
            },
          ] as const;
        },
      );
      if (loadGeneration !== loadGenerationRef.current) return;
      dispatch({
        type: 'load:success',
        taskLists: sortedLists,
        bundles: new Map(bundleEntries),
      });
    } catch (caughtError) {
      if (loadGeneration !== loadGenerationRef.current) return;
      dispatch({
        type: 'load:fail',
        message: getErrorMessage(caughtError, t('pms.errors.listDataFailed')),
      });
    }
  }, [filterParams, locale, spaceId, t, token]);

  useEffect(() => {
    void reloadSpaceTasks();
  }, [reloadSpaceTasks]);

  useEffect(() => {
    if (!token || !requestedTaskId || loading) {
      return;
    }
    const transition = resolveRequestedPmsTaskTransition({
      requestedTaskId,
      visibleTask: findPmsTaskInBundles(bundles, requestedTaskId),
    });
    if (transition.selectedTask) {
      dispatch({
        type: 'selected:requested-loaded',
        task: transition.selectedTask,
      });
      return;
    }
    if (!transition.detailRequest) {
      return;
    }

    let cancelled = false;
    getTaskDetail(token, transition.detailRequest.taskId)
      .then((detail) => {
        if (!cancelled) {
          dispatch({
            type: 'selected:requested-loaded',
            task: taskLists.some(
              (taskList) => taskList.id === detail.task.list_id,
            )
              ? detail.task
              : null,
          });
        }
      })
      .catch(() => {
        if (!cancelled)
          dispatch({ type: 'selected:requested-loaded', task: null });
      });

    return () => {
      cancelled = true;
    };
  }, [bundles, loading, requestedTaskId, taskLists, token]);

  const handleSelectIssue = useCallback(
    (task: PmsTask) => {
      const transition = resolvePmsTaskSelectedTransition({
        searchParams,
        task,
      });
      dispatch({ type: 'selected:set', task: transition.selectedTask });
      if (transition.searchParams) {
        setSearchParams(transition.searchParams, { replace: true });
      }
    },
    [searchParams, setSearchParams],
  );

  const handleClose = useCallback(() => {
    const transition = resolvePmsTaskClosedTransition<PmsTask>({
      searchParams,
    });
    dispatch({ type: 'selected:set', task: transition.selectedTask });
    if (transition.searchParams) {
      setSearchParams(transition.searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  usePmsTaskListChangeSubscription(
    useCallback(
      (detail) => {
        const changedListId =
          detail.type === 'updated' ? detail.taskList.id : detail.taskListId;
        const leftActiveCatalog =
          detail.type === 'deleted' || detail.taskList.archived;
        if (leftActiveCatalog && selectedIssue?.list_id === changedListId) {
          handleClose();
        }
        void reloadSpaceTasks();
      },
      [handleClose, reloadSpaceTasks, selectedIssue?.list_id],
    ),
  );

  const updateBundleIssues = useCallback(
    (listId: string, updater: (tasks: PmsTask[]) => PmsTask[]) => {
      dispatch({ type: 'bundle:update-tasks', listId, updater });
    },
    [],
  );

  const handleCreateIssue = useCallback(
    async (taskList: PmsTaskList, title: string, parentId: string | null) => {
      if (!token || !taskListRoleAllows(taskList.role, 'member')) return;
      const bundle = bundles.get(taskList.id);
      const created = await createTaskListTask(token, taskList.id, {
        title,
        description: '',
        status: getDefaultTaskStatus(bundle?.statuses),
        priority: 'medium',
        assignee_id: null,
        milestone_id: null,
        start_date: null,
        due_date: null,
        parent_id: parentId,
      });
      updateBundleIssues(taskList.id, (tasks) => [...tasks, created]);
    },
    [bundles, token, updateBundleIssues],
  );

  const handleDeleteIssue = useCallback(
    async (taskList: PmsTaskList, taskId: string) => {
      if (!token || !taskListRoleAllows(taskList.role, 'member')) return;
      await deleteTask(token, taskId);
      updateBundleIssues(taskList.id, (tasks) =>
        tasks.filter((task) => task.id !== taskId),
      );
      if (selectedIssue?.id === taskId)
        dispatch({ type: 'selected:set', task: null });
    },
    [selectedIssue?.id, token, updateBundleIssues],
  );

  const handleUpdateIssue = useCallback(
    async (
      taskList: PmsTaskList,
      taskId: string,
      payload: Record<string, unknown>,
    ) => {
      if (!token || !taskListRoleAllows(taskList.role, 'member')) return;
      const bundle = bundles.get(taskList.id);
      if (!bundle?.tasks.some((task) => task.id === taskId)) return;
      if (
        typeof payload.status === 'string' &&
        !getStatusSlugs(bundle.statuses).includes(payload.status)
      ) {
        return;
      }
      const updated = await updateTask(token, taskId, payload);
      updateBundleIssues(taskList.id, (tasks) =>
        tasks.map((task) => (task.id === updated.id ? updated : task)),
      );
      if (selectedIssue?.id === updated.id)
        dispatch({ type: 'selected:set', task: updated });
    },
    [bundles, selectedIssue?.id, token, updateBundleIssues],
  );

  const handleReorderIssues = useCallback(
    async (taskList: PmsTaskList, updates: TaskBoardPositionUpdate[]) => {
      if (
        !token ||
        !taskListRoleAllows(taskList.role, 'member') ||
        updates.length === 0
      ) {
        return;
      }
      const bundle = bundles.get(taskList.id);
      if (
        !bundle ||
        updates.some(
          (update) => !bundle.tasks.some((task) => task.id === update.taskId),
        )
      ) {
        return;
      }
      const result = await reorderTaskListTasks(token, taskList.id, {
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
      });
      if (result.items.length === 0) return;
      const updatedById = new Map(
        result.items.map((item) => [item.id, item] as const),
      );
      updateBundleIssues(taskList.id, (tasks) =>
        tasks.map((task) => updatedById.get(task.id) ?? task),
      );
      const updatedSelectedIssue = selectedIssue
        ? updatedById.get(selectedIssue.id)
        : undefined;
      if (updatedSelectedIssue) {
        dispatch({ type: 'selected:set', task: updatedSelectedIssue });
      }
    },
    [bundles, selectedIssue, token, updateBundleIssues],
  );

  const visibleTasksByListId = useMemo(
    () =>
      new Map(
        Array.from(bundles.entries()).map(([listId, bundle]) => [
          listId,
          filterDefaultVisibleTasks(bundle.tasks, bundle.statuses, {
            status: filterParams.status,
          }),
        ]),
      ),
    [bundles, filterParams.status],
  );
  const taskCount = useMemo(
    () =>
      Array.from(visibleTasksByListId.values()).reduce(
        (total, tasks) => total + tasks.length,
        0,
      ),
    [visibleTasksByListId],
  );
  const filterOptions = useMemo(() => {
    const allBundles = Array.from(bundles.values());
    return {
      labels: uniqueBy(
        allBundles.flatMap((bundle) => bundle.labels),
        (label) => label.id,
      ),
      members: uniqueBy(
        allBundles.flatMap((bundle) => bundle.members),
        (member) => member.user_id,
      ),
      milestones: uniqueBy(
        allBundles.flatMap((bundle) => bundle.milestones),
        (milestone) => milestone.id,
      ),
      statuses: mergeTaskListStatusesForFilter(
        allBundles.flatMap((bundle) => bundle.statuses),
      ),
    };
  }, [bundles]);

  const renderTaskListView = (
    taskList: PmsTaskList,
    bundle: ListBundle,
    visibleTasks: PmsTask[],
  ) => {
    const canEdit = taskListRoleAllows(taskList.role, 'member');
    const updateIssue = (taskId: string, payload: Record<string, unknown>) =>
      handleUpdateIssue(taskList, taskId, payload);

    if (visibleTasks.length === 0 && (activeTab !== 'list' || !canEdit)) {
      return (
        <p className="app-text-body-sm text-app-ink/40">
          {t('pms.allTasks.emptyList')}
        </p>
      );
    }

    if (activeTab === 'board') {
      return (
        <BoardView
          tasks={visibleTasks}
          members={bundle.members}
          onSelectIssue={handleSelectIssue}
          onUpdateIssue={canEdit ? updateIssue : undefined}
          taskListStatuses={bundle.statuses}
        />
      );
    }
    if (activeTab === 'calendar') {
      return (
        <CalendarView tasks={visibleTasks} taskListStatuses={bundle.statuses} />
      );
    }
    if (activeTab === 'gantt') {
      return (
        <GanttView
          canEdit={canEdit}
          tasks={visibleTasks}
          onSelectIssue={handleSelectIssue}
          onUpdateIssue={canEdit ? updateIssue : undefined}
          taskListStatuses={bundle.statuses}
        />
      );
    }
    if (activeTab === 'table') {
      return (
        <TableView
          canEdit={canEdit}
          tasks={visibleTasks}
          members={bundle.members}
          onSelectIssue={handleSelectIssue}
          onUpdateIssue={canEdit ? updateIssue : undefined}
          taskListStatuses={bundle.statuses}
        />
      );
    }
    return (
      <ListView
        canEdit={canEdit}
        groupBy="none"
        tasks={visibleTasks}
        members={bundle.members}
        currentUserId={user?.id}
        onCreateIssue={(title, parentId) =>
          handleCreateIssue(taskList, title, parentId)
        }
        onDeleteIssue={(taskId) => handleDeleteIssue(taskList, taskId)}
        onReorderIssues={(updates) => handleReorderIssues(taskList, updates)}
        onSelectIssue={handleSelectIssue}
        onUpdateIssue={updateIssue}
        showToolbar={false}
        sort={DEFAULT_PMS_TASK_SORT}
        taskListStatuses={bundle.statuses}
      />
    );
  };

  return (
    <div className="relative flex h-full min-w-0 flex-col">
      <header className="border-b border-app-border bg-app-bg px-4 pt-3 lg:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-7 shrink-0 items-center justify-center rounded bg-app-accent text-app-accent-fg">
            <Layout size={16} />
          </div>
          <div className="min-w-0">
            <h1 className="app-text-title-md truncate text-app-ink">
              {spaceName ?? t('pms.spaceOverview.fallbackSpaceName')}
            </h1>
            <p className="app-text-caption truncate text-app-ink/45">
              {t('pms.allTasks.summary', {
                lists: taskLists.length,
                tasks: taskCount,
              })}
            </p>
          </div>
        </div>
        <PmsSpaceToolTabs
          activeTab={activeTab}
          className="mt-3"
          spaceId={spaceId}
        />
      </header>

      {taskLists.length > 0 ? (
        <FilterBar
          taskListId={`space-tasks:${spaceId}`}
          filterParams={filterParams}
          setFilterParams={setFilterParams}
          members={filterOptions.members}
          currentUserId={user?.id}
          milestones={filterOptions.milestones}
          labels={filterOptions.labels}
          taskListStatuses={filterOptions.statuses}
        />
      ) : null}

      <main className="flex-1 overflow-y-auto bg-app-bg p-4 custom-scrollbar lg:p-6">
        {loading ? (
          <PmsCenteredLoadingState minHeightClassName="py-16" />
        ) : error ? (
          <PmsCenteredStateBlock minHeightClassName="py-16" tone="danger">
            {error}
          </PmsCenteredStateBlock>
        ) : taskLists.length === 0 ? (
          <PmsCenteredStateBlock minHeightClassName="py-16">
            {t('pms.overviewPage.noLists')}
          </PmsCenteredStateBlock>
        ) : (
          <div className="space-y-4">
            {taskLists.map((taskList) => {
              const bundle = bundles.get(taskList.id) ?? {
                labels: [],
                milestones: [],
                tasks: [],
                members: [],
                statuses: [],
              };
              const visibleTasks = visibleTasksByListId.get(taskList.id) ?? [];
              return (
                <section
                  key={taskList.id}
                  className="overflow-hidden rounded-lg border border-app-border bg-app-surface"
                >
                  <div className="flex min-w-0 items-center gap-3 border-b border-app-border px-4 py-3">
                    <ChevronDown
                      size={14}
                      className="shrink-0 text-app-ink/45"
                    />
                    <FolderKanban
                      size={16}
                      className="shrink-0 text-app-accent"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="app-text-caption truncate text-app-ink/45">
                        {taskList.folder_name
                          ? t('pms.allTasks.listLocationWithFolder', {
                              folder: taskList.folder_name,
                              space:
                                taskList.team_name ??
                                t('pms.spaceOverview.fallbackSpaceName'),
                            })
                          : t('pms.allTasks.listLocation', {
                              space:
                                taskList.team_name ??
                                t('pms.spaceOverview.fallbackSpaceName'),
                            })}
                      </p>
                      <h2 className="app-text-title-sm truncate text-app-ink">
                        {taskList.name}
                      </h2>
                    </div>
                    <span className="app-text-caption shrink-0 text-app-ink/45">
                      {t('pms.spaceOverview.taskCount', {
                        count: visibleTasks.length,
                      })}
                    </span>
                  </div>
                  <div className="p-4">
                    {renderTaskListView(taskList, bundle, visibleTasks)}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </main>

      <LazyMotion features={domAnimation}>
        <AnimatePresence>
          {selectedIssue ? (
            <TaskDetailModal
              closeLabel={t('common:actions.close')}
              onClose={handleClose}
            >
              <TaskDetail
                canEdit={taskListRoleAllows(selectedTaskList?.role, 'member')}
                members={selectedBundle?.members ?? []}
                task={selectedIssue}
                taskListStatuses={selectedBundle?.statuses ?? []}
                onClose={handleClose}
                onUpdate={reloadSpaceTasks}
                spaceName={selectedTaskList?.team_name}
              />
            </TaskDetailModal>
          ) : null}
        </AnimatePresence>
      </LazyMotion>
    </div>
  );
}

function SpaceTasksViewSession(props: SpaceTasksViewProps) {
  return useSpaceTasksViewElement(props);
}

export function SpaceTasksView(props: SpaceTasksViewProps) {
  const sessionKey = props.spaceId;
  return <SpaceTasksViewSession key={sessionKey} {...props} />;
}
