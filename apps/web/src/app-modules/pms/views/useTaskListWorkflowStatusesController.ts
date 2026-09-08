import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  createSpaceStatus,
  createTaskListStatus,
  listTaskListStatuses,
  updateSpaceStatus,
  updateTaskListStatus,
  updateTaskListStatusMode,
  type PmsStatusCategory,
  type PmsTaskListStatus,
  type PmsTaskListStatusesResponse,
} from '../api/pms-api';
import { PMS_WORKFLOW_DEFAULT_STATUS_COLOR } from './pms-color-palettes';
import {
  buildCreateWorkflowStatusCommand,
  buildUpdateWorkflowStatusCommand,
  createTaskListWorkflowSettingsModel,
  normalizeWorkflowStatusMode,
  normalizeWorkflowStatusSource,
  type TaskListWorkflowStatusMode,
  type TaskListWorkflowStatusSource,
} from './task-list-workflow-settings-model';

export interface TaskListWorkflowStatusesClient {
  createSpaceStatus: typeof createSpaceStatus;
  createTaskListStatus: typeof createTaskListStatus;
  listTaskListStatuses: typeof listTaskListStatuses;
  updateSpaceStatus: typeof updateSpaceStatus;
  updateTaskListStatus: typeof updateTaskListStatus;
  updateTaskListStatusMode: typeof updateTaskListStatusMode;
}

export interface TaskListWorkflowStatusesMessages {
  createFailed: string;
  loadFailed: string;
  updateFailed: string;
  updateModeFailed: string;
}

export interface UseTaskListWorkflowStatusesControllerParams {
  client?: TaskListWorkflowStatusesClient;
  currentUserRole: string | null;
  messages: TaskListWorkflowStatusesMessages;
  onError: (message: string | null) => void;
  onStatusesChanged?: (statuses: PmsTaskListStatus[]) => void;
  taskListId: string;
  teamId: string | null;
  token: string | null | undefined;
}

export const taskListWorkflowStatusesClient: TaskListWorkflowStatusesClient = {
  createSpaceStatus,
  createTaskListStatus,
  listTaskListStatuses,
  updateSpaceStatus,
  updateTaskListStatus,
  updateTaskListStatusMode,
};

export function useTaskListWorkflowStatusesController({
  client = taskListWorkflowStatusesClient,
  currentUserRole,
  messages,
  onError,
  onStatusesChanged,
  taskListId,
  teamId,
  token,
}: UseTaskListWorkflowStatusesControllerParams) {
  const [statuses, setStatuses] = useState<PmsTaskListStatus[]>([]);
  const [statusMode, setStatusMode] =
    useState<TaskListWorkflowStatusMode>('custom');
  const [statusSource, setStatusSource] =
    useState<TaskListWorkflowStatusSource>('list');
  const [loadingStatuses, setLoadingStatuses] = useState(true);
  const [newStatusName, setNewStatusName] = useState('');
  const [newStatusColor, setNewStatusColor] = useState(
    PMS_WORKFLOW_DEFAULT_STATUS_COLOR,
  );
  const [newStatusCategory, setNewStatusCategory] =
    useState<PmsStatusCategory>('active');
  const [creatingStatus, setCreatingStatus] = useState(false);
  const [editingStatusId, setEditingStatusId] = useState<string | null>(null);
  const [editStatusName, setEditStatusName] = useState('');
  const [editStatusColor, setEditStatusColor] = useState('');
  const [editStatusCategory, setEditStatusCategory] =
    useState<PmsStatusCategory>('active');

  const replaceStatuses = useCallback(
    (response: PmsTaskListStatusesResponse) => {
      setStatuses(response.items);
      setStatusMode(normalizeWorkflowStatusMode(response.mode));
      setStatusSource(normalizeWorkflowStatusSource(response.source));
      onStatusesChanged?.(response.items);
    },
    [onStatusesChanged],
  );

  const reloadStatuses = useCallback(async () => {
    if (!token) {
      setLoadingStatuses(false);
      return;
    }
    setLoadingStatuses(true);
    onError(null);
    try {
      replaceStatuses(await client.listTaskListStatuses(token, taskListId));
    } catch (caughtError) {
      onError(errorMessage(caughtError, messages.loadFailed));
    } finally {
      setLoadingStatuses(false);
    }
  }, [
    client,
    messages.loadFailed,
    onError,
    replaceStatuses,
    taskListId,
    token,
  ]);

  useEffect(() => {
    void reloadStatuses();
  }, [reloadStatuses]);

  const handleStatusModeChange = useCallback(
    async (mode: TaskListWorkflowStatusMode) => {
      if (!token || mode === statusMode) return;
      onError(null);
      try {
        const result = await client.updateTaskListStatusMode(
          token,
          taskListId,
          mode,
        );
        replaceStatuses(result);
      } catch (caughtError) {
        onError(errorMessage(caughtError, messages.updateModeFailed));
      }
    },
    [
      client,
      messages.updateModeFailed,
      onError,
      replaceStatuses,
      statusMode,
      taskListId,
      token,
    ],
  );

  const handleCreateStatus = useCallback(async () => {
    if (!token) return;
    const command = buildCreateWorkflowStatusCommand({
      category: newStatusCategory,
      color: newStatusColor,
      name: newStatusName,
      sortOrder: statuses.length,
      statusSource,
      taskListId,
      teamId,
    });
    if (command.kind === 'noop') return;
    setCreatingStatus(true);
    onError(null);
    try {
      const created =
        command.kind === 'space'
          ? await client.createSpaceStatus(
              token,
              command.spaceId,
              command.payload,
            )
          : await client.createTaskListStatus(
              token,
              command.taskListId,
              command.payload,
            );
      const updated = [...statuses, created];
      setStatuses(updated);
      onStatusesChanged?.(updated);
      setNewStatusName('');
      setNewStatusColor(PMS_WORKFLOW_DEFAULT_STATUS_COLOR);
      setNewStatusCategory('active');
    } catch (caughtError) {
      onError(errorMessage(caughtError, messages.createFailed));
    } finally {
      setCreatingStatus(false);
    }
  }, [
    client,
    messages.createFailed,
    newStatusCategory,
    newStatusColor,
    newStatusName,
    onError,
    onStatusesChanged,
    statusSource,
    statuses,
    taskListId,
    teamId,
    token,
  ]);

  const startEditStatus = useCallback((status: PmsTaskListStatus) => {
    setEditingStatusId(status.id);
    setEditStatusName(status.name);
    setEditStatusColor(status.color);
    setEditStatusCategory(status.category);
  }, []);

  const handleSaveEditStatus = useCallback(async () => {
    if (!token) return;
    const command = buildUpdateWorkflowStatusCommand({
      category: editStatusCategory,
      color: editStatusColor,
      name: editStatusName,
      statusId: editingStatusId,
      statusSource,
    });
    if (command.kind === 'noop') return;
    onError(null);
    try {
      const updatedStatus =
        command.kind === 'space'
          ? await client.updateSpaceStatus(
              token,
              command.statusId,
              command.payload,
            )
          : await client.updateTaskListStatus(
              token,
              command.statusId,
              command.payload,
            );
      const updated = statuses.map((status) =>
        status.id === command.statusId ? updatedStatus : status,
      );
      setStatuses(updated);
      onStatusesChanged?.(updated);
      setEditingStatusId(null);
    } catch (caughtError) {
      onError(errorMessage(caughtError, messages.updateFailed));
    }
  }, [
    client,
    editStatusCategory,
    editStatusColor,
    editStatusName,
    editingStatusId,
    messages.updateFailed,
    onError,
    onStatusesChanged,
    statusSource,
    statuses,
    token,
  ]);

  const workflowSettings = useMemo(
    () =>
      createTaskListWorkflowSettingsModel({
        currentUserRole,
        statusMode,
        statusSource,
        statuses,
      }),
    [currentUserRole, statusMode, statusSource, statuses],
  );

  return {
    canEditWorkflow: workflowSettings.canEditWorkflow,
    creatingStatus,
    editStatusCategory,
    editStatusColor,
    editStatusName,
    editingStatusId,
    handleCreateStatus,
    handleSaveEditStatus,
    handleStatusModeChange,
    loadingStatuses,
    newStatusCategory,
    newStatusColor,
    newStatusName,
    reloadStatuses,
    setEditStatusCategory,
    setEditStatusColor,
    setEditStatusName,
    setEditingStatusId,
    setNewStatusCategory,
    setNewStatusColor,
    setNewStatusName,
    startEditStatus,
    statuses,
    statusesByCategory: workflowSettings.statusesByCategory,
    statusMode,
    statusSource,
    workflowReadOnly: workflowSettings.workflowReadOnly,
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
