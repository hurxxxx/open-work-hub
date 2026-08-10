import type {
  PmsStatusCategory,
  PmsTaskListStatus,
} from '../api/pms-api';

export type TaskListWorkflowStatusMode = 'inherit' | 'custom';
export type TaskListWorkflowStatusSource = 'space' | 'list';

export const WORKFLOW_STATUS_CATEGORIES = [
  'not_started',
  'active',
  'done',
  'closed',
] as const satisfies readonly PmsStatusCategory[];

export type WorkflowStatusCreateCommand =
  | {
      kind: 'space';
      spaceId: string;
      payload: WorkflowStatusMutationPayload & { sort_order: number };
    }
  | {
      kind: 'list';
      taskListId: string;
      payload: WorkflowStatusMutationPayload & { sort_order: number };
    }
  | WorkflowStatusNoopCommand;

export type WorkflowStatusUpdateCommand =
  | {
      kind: 'space';
      statusId: string;
      payload: WorkflowStatusMutationPayload;
    }
  | {
      kind: 'list';
      statusId: string;
      payload: WorkflowStatusMutationPayload;
    }
  | WorkflowStatusNoopCommand;

export type WorkflowStatusNoopCommand = {
  kind: 'noop';
  reason:
    | 'missing_name'
    | 'missing_status_id'
    | 'missing_task_list_id'
    | 'missing_team_id';
};

export type WorkflowStatusMutationPayload = {
  name: string;
  color?: string;
  category?: PmsStatusCategory;
};

export interface TaskListWorkflowSettingsModel {
  canEditWorkflow: boolean;
  statusMode: TaskListWorkflowStatusMode;
  statusSource: TaskListWorkflowStatusSource;
  statusesByCategory: Map<PmsStatusCategory, PmsTaskListStatus[]>;
  workflowReadOnly: boolean;
}

export function createTaskListWorkflowSettingsModel({
  currentUserRole,
  statusMode,
  statusSource,
  statuses,
}: {
  currentUserRole: string | null;
  statusMode: TaskListWorkflowStatusMode;
  statusSource: TaskListWorkflowStatusSource;
  statuses: readonly PmsTaskListStatus[];
}): TaskListWorkflowSettingsModel {
  const canEditWorkflow = canRoleEditWorkflow(currentUserRole);

  return {
    canEditWorkflow,
    statusMode,
    statusSource,
    statusesByCategory: groupStatusesByCategory(statuses),
    workflowReadOnly: isWorkflowReadOnly({ canEditWorkflow }),
  };
}

export function normalizeWorkflowStatusMode(
  mode: TaskListWorkflowStatusMode | null | undefined,
): TaskListWorkflowStatusMode {
  return mode ?? 'custom';
}

export function normalizeWorkflowStatusSource(
  source: TaskListWorkflowStatusSource | null | undefined,
): TaskListWorkflowStatusSource {
  return source ?? 'list';
}

export function canRoleEditWorkflow(role: string | null): boolean {
  return role === 'owner' || role === 'admin';
}

export function isWorkflowReadOnly({
  canEditWorkflow,
}: {
  canEditWorkflow: boolean;
}): boolean {
  return !canEditWorkflow;
}

export function groupStatusesByCategory(
  statuses: readonly PmsTaskListStatus[],
): Map<PmsStatusCategory, PmsTaskListStatus[]> {
  const grouped = new Map<PmsStatusCategory, PmsTaskListStatus[]>(
    WORKFLOW_STATUS_CATEGORIES.map((category) => [category, []]),
  );

  for (const status of statuses) {
    grouped.get(status.category)?.push(status);
  }

  return grouped;
}

export function buildCreateWorkflowStatusCommand({
  category,
  color,
  name,
  sortOrder,
  statusSource,
  taskListId,
  teamId,
}: {
  category: PmsStatusCategory;
  color: string;
  name: string;
  sortOrder: number;
  statusSource: TaskListWorkflowStatusSource;
  taskListId: string | null | undefined;
  teamId: string | null | undefined;
}): WorkflowStatusCreateCommand {
  const normalizedName = name.trim();
  if (!normalizedName) return { kind: 'noop', reason: 'missing_name' };

  const payload = {
    name: normalizedName,
    color,
    category,
    sort_order: sortOrder,
  };

  if (statusSource === 'space') {
    if (!teamId) return { kind: 'noop', reason: 'missing_team_id' };
    return { kind: 'space', spaceId: teamId, payload };
  }

  if (!taskListId) return { kind: 'noop', reason: 'missing_task_list_id' };
  return { kind: 'list', taskListId, payload };
}

export function buildUpdateWorkflowStatusCommand({
  category,
  color,
  name,
  statusId,
  statusSource,
}: {
  category: PmsStatusCategory;
  color: string;
  name: string;
  statusId: string | null | undefined;
  statusSource: TaskListWorkflowStatusSource;
}): WorkflowStatusUpdateCommand {
  if (!statusId) return { kind: 'noop', reason: 'missing_status_id' };

  const normalizedName = name.trim();
  if (!normalizedName) return { kind: 'noop', reason: 'missing_name' };

  const payload = {
    name: normalizedName,
    color,
    category,
  };

  if (statusSource === 'space') {
    return { kind: 'space', statusId, payload };
  }

  return { kind: 'list', statusId, payload };
}
