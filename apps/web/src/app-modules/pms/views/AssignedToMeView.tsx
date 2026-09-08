import { useAuth } from '@/src/platform/auth/auth-provider';
import { AnimatePresence, LazyMotion, domAnimation } from 'motion/react';
import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  getTaskDetail,
  listAllAssignedTasks,
  listAllPmsTaskLists,
  type PmsTask,
  type PmsTaskList,
} from '../api/pms-api';
import { taskListRoleAllows } from '../api/pms-permissions';
import { ListView } from './ListView';
import {
  PmsCenteredLoadingState,
  PmsCenteredStateBlock,
} from './PmsCenteredStateBlock';
import { TaskDetail } from './TaskDetail';
import { TaskDetailModal } from './TaskDetailModal';
import { buildPmsTaskContextLabel } from './pms-task-context';
import {
  findPmsTaskById,
  getRequestedPmsTaskId,
  resolvePmsTaskClosedTransition,
  resolvePmsTaskSelectedTransition,
  resolveReloadedPmsTaskSelection,
  resolveRequestedPmsTaskTransition,
} from './pms-task-selection-workflow';
import { usePmsTaskListChangeSubscription } from './usePmsTaskListChangeSubscription';
import { usePmsTaskListGroupPreference } from './usePmsTaskListGroupPreference';

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

interface AssignedToMeState {
  selectedTask: PmsTask | null;
  tasks: PmsTask[];
  taskLists: PmsTaskList[];
  loading: boolean;
  loadError: string | null;
}

type AssignedToMeAction =
  | { type: 'load-started' }
  | { type: 'load-succeeded'; tasks: PmsTask[]; taskLists: PmsTaskList[] }
  | { type: 'load-failed'; error: string }
  | { type: 'select-task'; task: PmsTask }
  | { type: 'clear-selection' };

const INITIAL_ASSIGNED_TO_ME_STATE: AssignedToMeState = {
  selectedTask: null,
  tasks: [],
  taskLists: [],
  loading: true,
  loadError: null,
};

function assignedToMeReducer(
  state: AssignedToMeState,
  action: AssignedToMeAction,
): AssignedToMeState {
  switch (action.type) {
    case 'load-started':
      return { ...state, loading: true, loadError: null };
    case 'load-succeeded':
      return {
        ...state,
        tasks: action.tasks,
        taskLists: action.taskLists,
        selectedTask: resolveReloadedPmsTaskSelection({
          currentTask: state.selectedTask,
          missingPolicy: 'preserve',
          tasks: action.tasks,
        }),
        loading: false,
      };
    case 'load-failed':
      return {
        ...state,
        tasks: [],
        taskLists: [],
        loadError: action.error,
        loading: false,
      };
    case 'select-task':
      return { ...state, selectedTask: action.task };
    case 'clear-selection':
      return { ...state, selectedTask: null };
  }
}

export const AssignedToMeView = (_context: Record<string, never>) => {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();

  const [searchParams, setSearchParams] = useSearchParams();

  const { groupBy, setGroupBy } = usePmsTaskListGroupPreference({
    enabled: true,
  });
  const [state, dispatch] = useReducer(
    assignedToMeReducer,
    INITIAL_ASSIGNED_TO_ME_STATE,
  );
  const loadGenerationRef = useRef(0);
  const requestedTaskId = getRequestedPmsTaskId(searchParams);

  const reloadAssignedIssues = useCallback(async () => {
    if (!token || !user) {
      return;
    }

    const loadGeneration = loadGenerationRef.current + 1;
    loadGenerationRef.current = loadGeneration;
    dispatch({ type: 'load-started' });
    try {
      const [taskListResponse, issueResponse] = await Promise.all([
        listAllPmsTaskLists(token, undefined),
        listAllAssignedTasks(token),
      ]);
      if (loadGeneration !== loadGenerationRef.current) return;
      dispatch({
        type: 'load-succeeded',
        taskLists: taskListResponse.items,
        tasks: issueResponse.items,
      });
    } catch (error) {
      if (loadGeneration !== loadGenerationRef.current) return;
      dispatch({
        type: 'load-failed',
        error: getErrorMessage(error, t('pms.errors.assignedIssuesLoadFailed')),
      });
    }
  }, [t, token, user]);

  useEffect(() => {
    void reloadAssignedIssues();
  }, [reloadAssignedIssues]);

  useEffect(() => {
    if (!token || !requestedTaskId) {
      return;
    }

    const transition = resolveRequestedPmsTaskTransition({
      requestedTaskId,
      visibleTask: findPmsTaskById(state.tasks, requestedTaskId),
    });
    if (transition.selectedTask) {
      dispatch({ type: 'select-task', task: transition.selectedTask });
      return;
    }
    if (!transition.detailRequest) {
      return;
    }

    let cancelled = false;
    getTaskDetail(token, transition.detailRequest.taskId)
      .then((detail) => {
        if (!cancelled) {
          dispatch({ type: 'select-task', task: detail.task });
        }
      })
      .catch(() => {
        if (!cancelled) {
          dispatch({ type: 'clear-selection' });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.tasks, requestedTaskId, token]);

  const selectedTaskList = useMemo(
    () =>
      state.selectedTask
        ? (state.taskLists.find(
            (taskList) => taskList.id === state.selectedTask?.list_id,
          ) ?? null)
        : null,
    [state.selectedTask, state.taskLists],
  );
  const taskContextLabel = useCallback(
    (task: PmsTask) =>
      buildPmsTaskContextLabel({
        fallbackSpaceName: t('pms.spaceOverview.fallbackSpaceName'),
        task,
        taskLists: state.taskLists,
      }),
    [state.taskLists, t],
  );

  const handleSelectIssue = useCallback(
    (task: PmsTask) => {
      const transition = resolvePmsTaskSelectedTransition({
        searchParams,
        task,
      });
      if (transition.selectedTask) {
        dispatch({ type: 'select-task', task: transition.selectedTask });
      }
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
    if (!transition.selectedTask) {
      dispatch({ type: 'clear-selection' });
    }
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
        if (
          leftActiveCatalog &&
          state.selectedTask?.list_id === changedListId
        ) {
          handleClose();
        }
        void reloadAssignedIssues();
      },
      [handleClose, reloadAssignedIssues, state.selectedTask?.list_id],
    ),
  );

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-app-bg border-b border-app-border px-8 pt-6 pb-4">
        <h1 className="app-text-title-lg text-app-ink">
          {t('pms.assignedToMe')}
        </h1>
        <p className="app-text-body mt-1 text-app-ink/55">
          {t('pms.assignedToMeDescription')}
        </p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {state.loading ? (
          <PmsCenteredLoadingState minHeightClassName="py-16" />
        ) : state.loadError ? (
          <PmsCenteredStateBlock minHeightClassName="py-16" tone="danger">
            {state.loadError}
          </PmsCenteredStateBlock>
        ) : (
          <ListView
            groupBy={groupBy}
            tasks={state.tasks}
            onGroupByChange={setGroupBy}
            onSelectIssue={handleSelectIssue}
            taskContextLabel={taskContextLabel}
          />
        )}
      </main>

      <LazyMotion features={domAnimation}>
        <AnimatePresence>
          {state.selectedTask && (
            <TaskDetailModal
              closeLabel={t('common:actions.close')}
              onClose={handleClose}
            >
              <TaskDetail
                task={state.selectedTask}
                spaceName={selectedTaskList?.team_name}
                canEdit={taskListRoleAllows(selectedTaskList?.role, 'member')}
                onClose={handleClose}
                onUpdate={reloadAssignedIssues}
              />
            </TaskDetailModal>
          )}
        </AnimatePresence>
      </LazyMotion>
    </div>
  );
};
