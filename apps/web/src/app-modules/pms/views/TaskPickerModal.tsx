import { useAppAdmission } from '@/src/platform/apps/app-bootstrap-context';
import { useEffect, useMemo, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
import { ResourcePickerDialog } from '@/src/components/picker/ResourcePickerDialog';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  listPmsTaskLists,
  listTaskListTasks,
  type PmsTask,
} from '../api/pms-api';
import {
  EMPTY_EXCLUDED_TASK_IDS,
  INITIAL_TASK_PICKER_MODAL_STATE,
  buildTaskPickerTaskParams,
  getVisibleTaskPickerTasks,
  taskPickerModalReducer,
} from './task-picker-model';

export interface TaskPickerModalCopy {
  titleKey: string;
  descriptionKey: string;
  appLabelKey: string;
  noAccessActionKey: string;
  loadListsErrorKey: string;
  loadTasksErrorKey: string;
  attachErrorKey: string;
  taskListLabelKey: string;
  noTaskListsKey: string;
  searchPlaceholderKey: string;
  emptyKey: string;
}

export interface TaskPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (task: PmsTask) => Promise<void> | void;
  excludeTaskIds?: string[];

  copy?: TaskPickerModalCopy;
  contentClassName?: string;
  fixedTaskListId?: string | null;
  layer?: 'default' | 'elevated';
  overlayClassName?: string;
}

const DEFAULT_TASK_PICKER_MODAL_COPY: TaskPickerModalCopy = {
  titleKey: 'pms.taskPicker.title',
  descriptionKey: 'pms.taskPicker.description',
  appLabelKey: 'pms.taskPicker.pmsApp',
  noAccessActionKey: 'pms.taskPicker.attachAction',
  loadListsErrorKey: 'pms.taskPicker.errors.loadListsFailed',
  loadTasksErrorKey: 'pms.taskPicker.errors.loadTasksFailed',
  attachErrorKey: 'pms.taskPicker.errors.attachFailed',
  taskListLabelKey: 'pms.taskPicker.taskListLabel',
  noTaskListsKey: 'pms.taskPicker.noTaskLists',
  searchPlaceholderKey: 'pms.taskPicker.searchPlaceholder',
  emptyKey: 'pms.taskPicker.empty',
};

export function TaskPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeTaskIds = EMPTY_EXCLUDED_TASK_IDS,
  copy = DEFAULT_TASK_PICKER_MODAL_COPY,
  contentClassName,
  fixedTaskListId = null,
  layer,
  overlayClassName,
}: TaskPickerModalProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const canAccess = useAppAdmission('pms');
  const {
    attachErrorKey,
    descriptionKey,
    emptyKey,
    loadListsErrorKey,
    loadTasksErrorKey,
    noAccessActionKey,
    noTaskListsKey,
    searchPlaceholderKey,
    taskListLabelKey,
    titleKey,
    appLabelKey,
  } = copy;
  const [
    {
      taskLists,
      selectedTaskListId,
      tasks,
      query,
      loading,
      submittingId,
      error,
    },
    dispatch,
  ] = useReducer(taskPickerModalReducer, INITIAL_TASK_PICKER_MODAL_STATE);

  useEffect(() => {
    if (!isOpen || !token || !canAccess) return;
    let cancelled = false;
    dispatch({ type: 'resetForOpen', selectedTaskListId: fixedTaskListId });
    if (fixedTaskListId) {
      return () => {
        cancelled = true;
      };
    }
    listPmsTaskLists(token, undefined)
      .then((response) => {
        if (cancelled) return;
        dispatch({ type: 'taskListsLoaded', taskLists: response.items });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'taskListsFailed',
          message: err.message || t(loadListsErrorKey),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [canAccess, fixedTaskListId, isOpen, loadListsErrorKey, t, token]);

  useEffect(() => {
    if (!isOpen || !token || !canAccess || !selectedTaskListId) {
      dispatch({ type: 'tasksIdle' });
      return;
    }
    let cancelled = false;
    dispatch({ type: 'tasksLoading' });
    listTaskListTasks(
      token,
      selectedTaskListId,
      buildTaskPickerTaskParams(query),
    )
      .then((response) => {
        if (cancelled) return;
        dispatch({ type: 'tasksLoaded', tasks: response.items });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'tasksFailed',
          message: err.message || t(loadTasksErrorKey),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [
    canAccess,
    isOpen,
    loadTasksErrorKey,
    query,
    selectedTaskListId,
    t,
    token,
  ]);

  const filteredTasks = useMemo(
    () => getVisibleTaskPickerTasks(tasks, excludeTaskIds),
    [excludeTaskIds, tasks],
  );

  async function handlePick(task: PmsTask) {
    dispatch({ type: 'pickStarted', taskId: task.id });
    try {
      await onPick(task);
      onClose();
    } catch (err) {
      dispatch({
        type: 'pickFailed',
        message: err instanceof Error ? err.message : t(attachErrorKey),
      });
    } finally {
      dispatch({ type: 'pickFinished' });
    }
  }

  return (
    <ResourcePickerDialog
      accessNotice={
        <NoAccessNotice
          appLabel={t(appLabelKey)}
          action={t(noAccessActionKey)}
        />
      }
      canAccess={canAccess}
      closeLabel={t('common:actions.close')}
      contentClassName={contentClassName}
      controlsSlot={
        fixedTaskListId ? null : (
          <label className="block space-y-1">
            <span className="app-text-control-sm text-app-ink/70">
              {t(taskListLabelKey)}
            </span>
            <select
              value={selectedTaskListId ?? ''}
              onChange={(event) =>
                dispatch({
                  type: 'setSelectedTaskListId',
                  taskListId: event.target.value || null,
                })
              }
              className="app-field-input"
            >
              {taskLists.length === 0 ? (
                <option value="">{t(noTaskListsKey)}</option>
              ) : null}
              {taskLists.map((taskList) => (
                <option key={taskList.id} value={taskList.id}>
                  {taskList.key} · {taskList.name}
                </option>
              ))}
            </select>
          </label>
        )
      }
      description={t(descriptionKey)}
      emptyLabel={t(emptyKey)}
      error={error}
      getItemId={(task) => task.id}
      isOpen={isOpen}
      items={filteredTasks}
      layer={layer}
      loading={loading}
      overlayClassName={overlayClassName}
      onClose={onClose}
      onPick={(task) => void handlePick(task)}
      renderItem={(task) => (
        <div className="min-w-0">
          <p className="app-text-body line-clamp-1 text-app-ink">
            {task.title}
          </p>
          <p className="app-text-caption text-app-ink/40">
            {task.reference} · {task.status_label}
          </p>
        </div>
      )}
      search={{
        label: t('common:actions.search'),
        onChange: (value) => dispatch({ type: 'setQuery', query: value }),
        placeholder: t(searchPlaceholderKey),
        value: query,
      }}
      submittingId={submittingId}
      title={t(titleKey)}
    />
  );
}
