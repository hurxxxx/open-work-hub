import { useAppAdmission } from '@/src/platform/apps/app-bootstrap-context';
import { Button, InlineNotice } from '@open-work-hub/ui';
import {
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  ExternalLink,
  Loader2,
  Plus,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import { buildAppPath } from '@/src/platform/apps/app-links';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';
import {
  PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
  type FloatingPmsOpenEventDetail,
  type PersonalTodoPmsTaskCreatedEventDetail,
} from '@/src/platform/personal-widgets/floating-panel-events';

import {
  getTaskDetail,
  listAllPmsTaskLists,
  listPersonalPmsAssignedTasks,
  listTaskListStatuses,
  type PersonalPmsTask,
  type PmsTask,
  type PmsTaskList,
  type PmsTaskListStatus,
} from '../api/pms-api';
import { taskListRoleAllows } from '../api/pms-permissions';
import { NewTaskModal } from './NewTaskModal';
import { TaskDetail } from './TaskDetail';
import { TaskDetailModal } from './TaskDetailModal';
import { formatDate, getStatusLabel, getStatusTone } from './pms-constants';
import { reconcilePmsTaskListCatalog } from './pms-task-list-catalog-model';
import { usePmsTaskListChangeSubscription } from './usePmsTaskListChangeSubscription';

const FLOATING_PMS_STATUS_LOAD_CONCURRENCY = 4;

function taskListLabel(taskList: PmsTaskList): string {
  return [taskList.team_name, taskList.folder_name, taskList.name]
    .filter(Boolean)
    .join(' / ');
}

function statusToneClass(
  status: string,
  statuses?: PmsTaskListStatus[],
): string {
  switch (getStatusTone(status, statuses)) {
    case 'accent':
      return 'bg-app-accent/10 text-app-accent';
    case 'danger':
      return 'bg-[var(--ui-color-danger)]/10 text-[var(--ui-color-danger)]';
    case 'success':
      return 'bg-[var(--ui-color-success)]/10 text-[var(--ui-color-success)]';
    case 'warning':
      return 'bg-[var(--ui-color-warning)]/15 text-[var(--ui-color-warning)]';
    default:
      return 'bg-app-surface text-app-ink/55';
  }
}

function dueDateToneClass(dueDate: string | null | undefined): string {
  if (!dueDate) {
    return 'text-app-ink/45';
  }
  const today = new Date().toISOString().slice(0, 10);
  if (dueDate < today) {
    return 'text-[var(--ui-color-danger)]';
  }
  if (dueDate === today) {
    return 'text-[var(--ui-color-warning)]';
  }
  return 'text-app-ink/45';
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export type FloatingPmsWidgetOpenRequest = {
  detail: FloatingPmsOpenEventDetail;
  id: number;
};

export function FloatingPmsWidget({
  onChanged,
  onCreateTaskOpenRequestHandled,
  openRequest,
  reloadSeq = 0,
}: {
  onChanged?: () => void;
  onCreateTaskOpenRequestHandled?: (requestId: number) => void;
  openRequest?: FloatingPmsWidgetOpenRequest | null;
  reloadSeq?: number;
}) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const canAccessPms = useAppAdmission('pms');
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<PersonalPmsTask[]>([]);
  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [statusesByListId, setStatusesByListId] = useState<
    Record<string, PmsTaskListStatus[]>
  >({});
  const [newTaskListId, setNewTaskListId] = useState('');
  const [newTaskListsLoading, setNewTaskListsLoading] = useState(false);
  const [newTaskInitialTitle, setNewTaskInitialTitle] = useState('');
  const [newTaskModalKey, setNewTaskModalKey] = useState(0);
  const [newTaskSourceTodoId, setNewTaskSourceTodoId] = useState<string | null>(
    null,
  );
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedExternalTask, setSelectedExternalTask] =
    useState<PersonalPmsTask | null>(null);
  const [loadingTaskDetailId, setLoadingTaskDetailId] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reloadGenerationRef = useRef(0);

  const taskListById = useMemo(
    () => new Map(taskLists.map((taskList) => [taskList.id, taskList])),
    [taskLists],
  );
  const editableTaskLists = useMemo(
    () =>
      taskLists.filter((taskList) =>
        taskListRoleAllows(taskList.role, 'member'),
      ),
    [taskLists],
  );
  const selectedNewTaskList =
    editableTaskLists.find((taskList) => taskList.id === newTaskListId) ??
    editableTaskLists[0] ??
    null;
  const newTaskListOptions = useMemo(
    () =>
      editableTaskLists.map((taskList) => ({
        id: taskList.id,
        label: taskListLabel(taskList),
      })),
    [editableTaskLists],
  );
  const openTasks = tasks;
  const selectedTask =
    selectedExternalTask?.id === selectedTaskId
      ? selectedExternalTask
      : (openTasks.find((task) => task.id === selectedTaskId) ?? null);
  const selectedTaskList = selectedTask
    ? (taskListById.get(selectedTask.list_id) ?? null)
    : null;
  const selectedTaskStatuses = selectedTask
    ? (statusesByListId[selectedTask.list_id] ?? [])
    : [];

  const loadTaskLists = useCallback(async (): Promise<PmsTaskList[]> => {
    if (!token) return [];
    const response = await listAllPmsTaskLists(token, undefined);
    const lists = response.items;
    const statusEntries = await runRequestsWithConcurrency(
      lists.map((taskList) => taskList.id),
      FLOATING_PMS_STATUS_LOAD_CONCURRENCY,
      async (taskListId) => {
        try {
          const statusResponse = await listTaskListStatuses(token, taskListId);
          return [taskListId, statusResponse.items] as const;
        } catch {
          return [taskListId, [] as PmsTaskListStatus[]] as const;
        }
      },
    );
    setTaskLists(lists);
    setStatusesByListId((current) => ({
      ...current,
      ...Object.fromEntries(statusEntries),
    }));
    return lists;
  }, [token]);

  const reload = useCallback(async () => {
    const reloadGeneration = reloadGenerationRef.current + 1;
    reloadGenerationRef.current = reloadGeneration;
    if (!token) {
      setTasks([]);
      setTaskLists([]);
      setStatusesByListId({});
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const assignedResponse = await listPersonalPmsAssignedTasks(token);
      if (reloadGeneration !== reloadGenerationRef.current) return;
      setTasks(assignedResponse.items);
    } catch (caughtError) {
      if (reloadGeneration !== reloadGenerationRef.current) return;
      setError(
        getErrorMessage(caughtError, t('pms.errors.assignedIssuesLoadFailed')),
      );
    } finally {
      if (reloadGeneration === reloadGenerationRef.current) setLoading(false);
    }
  }, [t, token]);

  useEffect(() => {
    let cancelled = false;
    setNewTaskListsLoading(true);
    loadTaskLists()
      .then((lists) => {
        if (cancelled) return;
        setNewTaskListId((current) =>
          current && lists.some((taskList) => taskList.id === current)
            ? current
            : (lists.find((taskList) =>
                taskListRoleAllows(taskList.role, 'member'),
              )?.id ?? ''),
        );
      })
      .catch(() => {
        if (!cancelled) setNewTaskListId('');
      })
      .finally(() => {
        if (!cancelled) setNewTaskListsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadTaskLists, reloadSeq]);

  useEffect(() => {
    void reload();
  }, [reload, reloadSeq]);

  usePmsTaskListChangeSubscription(
    useCallback(
      (detail) => {
        const changedListId =
          detail.type === 'updated' ? detail.taskList.id : detail.taskListId;
        const leftActiveCatalog =
          detail.type === 'deleted' || detail.taskList.archived;

        setTaskLists((current) =>
          detail.type === 'updated'
            ? reconcilePmsTaskListCatalog(current, detail.taskList, 'active')
            : current.filter((taskList) => taskList.id !== detail.taskListId),
        );
        if (leftActiveCatalog) {
          setTasks((current) =>
            current.filter((task) => task.list_id !== changedListId),
          );
          setNewTaskListId((current) =>
            current === changedListId ? '' : current,
          );
          setStatusesByListId((current) => {
            const next = { ...current };
            delete next[changedListId];
            return next;
          });
          if (selectedTask?.list_id === changedListId) {
            setSelectedTaskId(null);
            setSelectedExternalTask(null);
            setLoadingTaskDetailId(null);
          }
        }

        void reload();
        void loadTaskLists();
      },
      [loadTaskLists, reload, selectedTask?.list_id],
    ),
  );

  useEffect(() => {
    if (
      selectedTaskId &&
      loadingTaskDetailId !== selectedTaskId &&
      selectedExternalTask?.id !== selectedTaskId &&
      !openTasks.some((task) => task.id === selectedTaskId)
    ) {
      setSelectedTaskId(null);
    }
  }, [loadingTaskDetailId, openTasks, selectedExternalTask, selectedTaskId]);

  useEffect(() => {
    const detail = openRequest?.detail;
    if (!detail || detail.mode === 'panel') {
      return undefined;
    }
    if (detail.mode === 'createTask') {
      setNewTaskInitialTitle(detail.title?.trim() ?? '');
      setNewTaskModalKey((current) => current + 1);
      setNewTaskSourceTodoId(detail.sourceTodoId ?? null);
      setNewTaskOpen(true);
      if (openRequest) {
        onCreateTaskOpenRequestHandled?.(openRequest.id);
      }
      return undefined;
    }
    if (detail.mode !== 'openTask') {
      return undefined;
    }
    if (!token) {
      return undefined;
    }

    let cancelled = false;
    const existingTask = openTasks.find((task) => task.id === detail.taskId);
    setError(null);
    setSelectedTaskId(detail.taskId);
    setSelectedExternalTask(existingTask ?? null);
    setLoadingTaskDetailId(detail.taskId);

    void loadTaskLists();
    getTaskDetail(token, detail.taskId)
      .then(async (response) => {
        const task = response.task;
        let taskStatuses: PmsTaskListStatus[] | null = null;
        try {
          const statusResponse = await listTaskListStatuses(
            token,
            task.list_id,
          );
          taskStatuses = statusResponse.items;
        } catch {
          taskStatuses = null;
        }
        if (cancelled) {
          return;
        }
        setSelectedExternalTask(task);
        if (taskStatuses) {
          setStatusesByListId((current) => ({
            ...current,
            [task.list_id]: taskStatuses,
          }));
        }
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(
            getErrorMessage(caughtError, t('pms.errors.requestedIssueFailed')),
          );
          setSelectedTaskId(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingTaskDetailId(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    loadTaskLists,
    onCreateTaskOpenRequestHandled,
    openRequest,
    openTasks,
    t,
    token,
  ]);

  const handleTaskCreated = useCallback(
    (createdTask: PmsTask) => {
      void reload();
      onChanged?.();
      if (!newTaskSourceTodoId) {
        return;
      }
      window.dispatchEvent(
        new CustomEvent<PersonalTodoPmsTaskCreatedEventDetail>(
          PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
          {
            detail: {
              taskId: createdTask.id,
              title: createdTask.title,
              todoId: newTaskSourceTodoId,
            },
          },
        ),
      );
    },
    [newTaskSourceTodoId, onChanged, reload],
  );

  const closeSelectedTask = useCallback(() => {
    setSelectedTaskId(null);
    setSelectedExternalTask(null);
    setLoadingTaskDetailId(null);
  }, []);

  const closeNewTaskModal = useCallback(() => {
    setNewTaskOpen(false);
    setNewTaskInitialTitle('');
    setNewTaskSourceTodoId(null);
  }, []);

  const handleTaskUpdated = useCallback(async () => {
    await reload();
    onChanged?.();
  }, [onChanged, reload]);

  const detailModal =
    selectedTask && typeof document !== 'undefined'
      ? createPortal(
          <TaskDetailModal
            className="z-[120]"
            closeLabel={t('common:actions.close')}
            onClose={closeSelectedTask}
          >
            <TaskDetail
              canEdit={taskListRoleAllows(selectedTaskList?.role, 'member')}
              onClose={closeSelectedTask}
              onUpdate={handleTaskUpdated}
              spaceId={selectedTaskList?.team_id ?? null}
              spaceName={selectedTaskList?.team_name}
              task={selectedTask}
              taskListStatuses={selectedTaskStatuses}
            />
          </TaskDetailModal>,
          document.body,
        )
      : null;

  return (
    <div className="flex h-full min-w-0 flex-col bg-app-bg text-app-ink">
      <section className="flex shrink-0 items-center justify-between gap-3 border-b border-app-border px-4 py-3">
        <div className="min-w-0">
          <h4 className="app-text-title-sm text-app-ink">
            {t('pms.floating.assignedTitle')}
          </h4>
          <p className="app-text-caption text-app-ink/45">
            {t('pms.floating.assignedCount', { count: openTasks.length })}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            className="shrink-0 gap-1.5"
            disabled={!canAccessPms}
            onClick={() => {
              setNewTaskInitialTitle('');
              setNewTaskModalKey((current) => current + 1);
              setNewTaskSourceTodoId(null);
              setNewTaskOpen(true);
            }}
            variant="primary"
          >
            <Plus aria-hidden="true" size={15} />
            <span>{t('pms.newTask')}</span>
          </Button>
        </div>
      </section>

      {error ? (
        <div className="shrink-0 px-4 py-3">
          <InlineNotice tone="danger">{error}</InlineNotice>
        </div>
      ) : null}

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {loading && openTasks.length === 0 ? (
          <div className="flex h-full items-center justify-center text-app-ink/40">
            <Loader2 aria-hidden="true" className="animate-spin" size={20} />
          </div>
        ) : openTasks.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center">
            <div className="grid justify-items-center gap-2">
              <ClipboardList
                aria-hidden="true"
                className="text-app-ink/25"
                size={24}
              />
              <p className="app-text-body-sm text-app-ink/45">
                {t('pms.floating.emptyAssigned')}
              </p>
            </div>
          </div>
        ) : (
          <ul className="divide-y divide-app-border">
            {openTasks.map((task) => {
              const taskStatuses = statusesByListId[task.list_id] ?? [];
              const taskList = taskListById.get(task.list_id) ?? null;
              return (
                <li key={task.id}>
                  <button
                    type="button"
                    aria-label={t('pms.floating.openTask', {
                      title: task.title,
                    })}
                    className="w-full px-4 py-3 text-left transition-colors hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-inset focus:ring-app-accent/30"
                    onClick={() => {
                      setSelectedExternalTask(task);
                      setSelectedTaskId(task.id);
                      void loadTaskLists();
                    }}
                  >
                    <div className="flex min-w-0 items-start gap-2.5">
                      <CheckCircle2
                        aria-hidden="true"
                        className="mt-0.5 shrink-0 text-app-ink/30"
                        size={16}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="app-text-body-sm line-clamp-2 text-app-ink">
                          {task.title}
                        </p>
                        <p className="app-text-caption mt-1 truncate text-app-ink/45">
                          {taskListById.get(task.list_id)?.team_name}
                          {taskList ? ` · ${taskListLabel(taskList)}` : null}
                        </p>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span
                            className={cn(
                              'app-text-micro rounded-full px-2 py-0.5',
                              statusToneClass(task.status, taskStatuses),
                            )}
                          >
                            {getStatusLabel(task.status, taskStatuses)}
                          </span>
                          {task.due_date ? (
                            <span
                              className={cn(
                                'app-text-micro inline-flex items-center gap-1',
                                dueDateToneClass(task.due_date),
                              )}
                            >
                              <CalendarDays aria-hidden="true" size={12} />
                              {formatDate(task.due_date)}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="flex shrink-0 justify-end border-t border-app-border px-4 py-3">
        <Button
          className="gap-1.5"
          disabled={!canAccessPms}
          onClick={() => navigate(buildAppPath('pms'))}
          variant="secondary"
        >
          <ExternalLink aria-hidden="true" size={14} />
          <span>{t('pms.title')}</span>
        </Button>
      </div>

      {newTaskOpen ? (
        <NewTaskModal
          key={newTaskModalKey}
          canCreate={
            selectedNewTaskList
              ? !newTaskListsLoading &&
                taskListRoleAllows(selectedNewTaskList.role, 'member')
              : false
          }
          contentClassName="z-[120]"
          initialTitle={newTaskInitialTitle}
          isOpen={newTaskOpen}
          onClose={closeNewTaskModal}
          onCreated={handleTaskCreated}
          onTaskListIdChange={setNewTaskListId}
          overlayClassName="z-[119]"
          parentPickerContentClassName="z-[122]"
          parentPickerOverlayClassName="z-[121]"
          taskListId={selectedNewTaskList?.id ?? ''}
          taskListLoading={newTaskListsLoading}
          taskListSpaceId={selectedNewTaskList?.team_id ?? null}
          taskListOptions={newTaskListOptions}
          taskListStatuses={
            selectedNewTaskList
              ? (statusesByListId[selectedNewTaskList.id] ?? [])
              : []
          }
        />
      ) : null}

      {detailModal}
    </div>
  );
}

export function useFloatingPmsAssignedSummary(
  token: string | null,
  reloadSeq = 0,
): { available: boolean; count: number } {
  const [count, setCount] = useState(0);
  const [available, setAvailable] = useState(false);
  const [taskListRevision, setTaskListRevision] = useState(0);

  usePmsTaskListChangeSubscription(
    useCallback(() => {
      setTaskListRevision((current) => current + 1);
    }, []),
  );

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setCount(0);
      setAvailable(false);
      return undefined;
    }
    listPersonalPmsAssignedTasks(token)
      .then((response) => {
        if (!cancelled) {
          setCount(response.items.length);
          setAvailable(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCount(0);
          setAvailable(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadSeq, taskListRevision, token]);

  return { available, count };
}

export function useFloatingPmsAssignedCount(
  token: string | null,
  reloadSeq = 0,
): number {
  return useFloatingPmsAssignedSummary(token, reloadSeq).count;
}
