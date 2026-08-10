import type {
  BulkUpdatePayload,
  PmsLabel,
  PmsTaskListStatus,
} from '../api/pms-api';

export const BULK_DEFAULT_STATUS_OPTIONS = [
  { value: 'todo', labelKey: 'pms.filter.status.todo' },
  { value: 'in_progress', labelKey: 'pms.filter.status.inProgress' },
  { value: 'review', labelKey: 'pms.filter.status.review' },
  { value: 'done', labelKey: 'pms.filter.status.done' },
  { value: 'complete', labelKey: 'pms.filter.status.complete' },
] as const;

export type BulkStatusOption = {
  value: string;
  label: string;
};

type TranslateBulkActionLabel = (key: string) => string;

export type BulkUpdateActionPayload = Omit<BulkUpdatePayload, 'task_ids'>;

export type BulkUpdateAction =
  | { type: 'archive' }
  | { type: 'restore' }
  | { type: 'delete' }
  | { type: 'status'; status: string }
  | { type: 'priority'; priority: string }
  | { type: 'assignee'; assigneeId: string | null }
  | { type: 'add-label'; labelId: string }
  | { type: 'remove-label'; labelId: string };

export type BulkLabelAction = {
  key: string;
  label: PmsLabel;
  payload: BulkUpdateActionPayload;
};

export type BulkLabelActions = {
  add: BulkLabelAction[];
  remove: BulkLabelAction[];
};

export function buildBulkStatusOptions({
  taskListStatuses,
  translate,
}: {
  taskListStatuses?: readonly PmsTaskListStatus[];
  translate: TranslateBulkActionLabel;
}): BulkStatusOption[] {
  if (taskListStatuses && taskListStatuses.length > 0) {
    return taskListStatuses.map((status) => ({
      value: status.slug,
      label: status.name,
    }));
  }

  return BULK_DEFAULT_STATUS_OPTIONS.map((option) => ({
    value: option.value,
    label: translate(option.labelKey),
  }));
}

export function selectedTaskIdsToArray(
  selectedIds: ReadonlySet<string>,
): string[] {
  return Array.from(selectedIds);
}

export function buildBulkActionPayload(
  action: BulkUpdateAction,
): BulkUpdateActionPayload {
  switch (action.type) {
    case 'archive':
      return { archived: true };
    case 'restore':
      return { archived: false };
    case 'delete':
      return { delete: true };
    case 'status':
      return { status: action.status };
    case 'priority':
      return { priority: action.priority };
    case 'assignee':
      return { assignee_id: action.assigneeId };
    case 'add-label':
      return { add_label_ids: [action.labelId] };
    case 'remove-label':
      return { remove_label_ids: [action.labelId] };
  }
}

export function buildBulkUpdateRequest(
  taskIds: readonly string[],
  payload: BulkUpdateActionPayload,
): BulkUpdatePayload {
  return {
    task_ids: [...taskIds],
    ...payload,
  };
}

export function buildBulkLabelActions(
  labels: readonly PmsLabel[],
): BulkLabelActions {
  return {
    add: labels.map((label) => ({
      key: `add-${label.id}`,
      label,
      payload: buildBulkActionPayload({
        type: 'add-label',
        labelId: label.id,
      }),
    })),
    remove: labels.map((label) => ({
      key: `rm-${label.id}`,
      label,
      payload: buildBulkActionPayload({
        type: 'remove-label',
        labelId: label.id,
      }),
    })),
  };
}
