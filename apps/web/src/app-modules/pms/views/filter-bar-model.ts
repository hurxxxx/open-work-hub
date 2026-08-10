import type {
  PmsLabel,
  PmsMilestone,
  PmsTaskListMember,
  TaskFilterParams,
} from '../api/pms-api';
import {
  createDefaultTaskFilterParams,
  DEFAULT_ISSUE_ARCHIVED_STATE,
} from '../api/pms-filters';

export interface SavedFilter {
  name: string;
  params: TaskFilterParams;
}

export type FilterBarStatusOption = {
  value: string;
  label: string;
};

export type TaskFilterPill = {
  label: string;
  clearParams: TaskFilterParams;
};

type TranslateFilterLabel = (
  key: string,
  options?: Record<string, unknown>,
) => string;
type SavedFilterStorage = Pick<Storage, 'getItem' | 'setItem'>;

function savedFilterStorageKey(taskListId: string) {
  return `pms_saved_filters_${taskListId}`;
}

export function loadSavedFilters(
  taskListId: string,
  storage: SavedFilterStorage = localStorage,
): SavedFilter[] {
  try {
    const raw = storage.getItem(savedFilterStorageKey(taskListId));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveSavedFilters(
  taskListId: string,
  filters: SavedFilter[],
  storage: SavedFilterStorage = localStorage,
): void {
  storage.setItem(savedFilterStorageKey(taskListId), JSON.stringify(filters));
}

export function isFilterActive(params: TaskFilterParams): boolean {
  return !!(
    (params.status && params.status.length > 0) ||
    params.priority ||
    params.assignee_id ||
    params.label_id ||
    params.milestone_id ||
    params.start_date_from ||
    params.start_date_to ||
    params.due_date_from ||
    params.due_date_to ||
    (params.archived_state &&
      params.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE)
  );
}

export function createClearedTaskFilterParams(
  params: TaskFilterParams,
): TaskFilterParams {
  return createDefaultTaskFilterParams({ q: params.q });
}

export function createSavedTaskFilterParams(
  params: TaskFilterParams,
): TaskFilterParams {
  return createDefaultTaskFilterParams({
    ...params,
    q: undefined,
  });
}

export function createSavedFilter(
  name: string,
  params: TaskFilterParams,
): SavedFilter | null {
  const normalizedName = name.trim();
  if (!normalizedName) return null;
  return {
    name: normalizedName,
    params: createSavedTaskFilterParams(params),
  };
}

export function removeSavedFilterAt(
  filters: readonly SavedFilter[],
  index: number,
): SavedFilter[] {
  return filters.filter((_, currentIndex) => currentIndex !== index);
}

export function paramsFromSavedFilter(
  saved: SavedFilter,
  currentParams: TaskFilterParams,
): TaskFilterParams {
  return createLoadedSavedTaskFilterParams(saved.params, currentParams);
}

export function createLoadedSavedTaskFilterParams(
  savedParams: TaskFilterParams,
  currentParams: TaskFilterParams,
): TaskFilterParams {
  return createDefaultTaskFilterParams({
    ...savedParams,
    q: currentParams.q,
  });
}

export function buildTaskFilterPills({
  labels,
  members,
  milestones,
  params,
  statusOptions,
  translate,
}: {
  labels: readonly PmsLabel[];
  members: readonly PmsTaskListMember[];
  milestones: readonly PmsMilestone[];
  params: TaskFilterParams;
  statusOptions: readonly FilterBarStatusOption[];
  translate: TranslateFilterLabel;
}): TaskFilterPill[] {
  const pills: TaskFilterPill[] = [];
  if (params.status && params.status.length > 0) {
    const statusLabels = params.status
      .map((status) => statusOptions.find((option) => option.value === status)?.label ?? status)
      .join(', ');
    pills.push({
      label: translate('pms.filter.pillStatus', { value: statusLabels }),
      clearParams: { ...params, status: undefined },
    });
  }
  if (params.priority) {
    pills.push({
      label: translate('pms.filter.pillPriority', {
        value: priorityLabel(params.priority, translate),
      }),
      clearParams: { ...params, priority: undefined },
    });
  }
  if (params.assignee_id) {
    const name =
      members.find((member) => member.user_id === params.assignee_id)?.full_name ??
      translate('common:feedback.unknown');
    pills.push({
      label: translate('pms.filter.pillAssignee', { value: name }),
      clearParams: { ...params, assignee_id: undefined },
    });
  }
  if (params.label_id) {
    const name =
      labels.find((label) => label.id === params.label_id)?.name ??
      translate('common:feedback.unknown');
    pills.push({
      label: translate('pms.filter.pillLabel', { value: name }),
      clearParams: { ...params, label_id: undefined },
    });
  }
  if (params.milestone_id) {
    const name =
      milestones.find((milestone) => milestone.id === params.milestone_id)?.title ??
      translate('common:feedback.unknown');
    pills.push({
      label: translate('pms.filter.pillMilestone', { value: name }),
      clearParams: { ...params, milestone_id: undefined },
    });
  }
  if (params.start_date_from || params.start_date_to) {
    pills.push({
      label: translate('pms.filter.pillStart', {
        from: params.start_date_from ?? '...',
        to: params.start_date_to ?? '...',
      }),
      clearParams: {
        ...params,
        start_date_from: undefined,
        start_date_to: undefined,
      },
    });
  }
  if (params.due_date_from || params.due_date_to) {
    pills.push({
      label: translate('pms.filter.pillDue', {
        from: params.due_date_from ?? '...',
        to: params.due_date_to ?? '...',
      }),
      clearParams: {
        ...params,
        due_date_from: undefined,
        due_date_to: undefined,
      },
    });
  }
  if (
    params.archived_state &&
    params.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE
  ) {
    pills.push({
      label: translate('pms.filter.pillArchive', {
        value: archiveLabel(params.archived_state, translate),
      }),
      clearParams: {
        ...params,
        archived_state: DEFAULT_ISSUE_ARCHIVED_STATE,
      },
    });
  }
  return pills;
}

function priorityLabel(
  priority: NonNullable<TaskFilterParams['priority']>,
  translate: TranslateFilterLabel,
): string {
  const priorityLabelKeys: Record<string, string> = {
    critical: 'pms.priorityCritical',
    high: 'pms.priorityHigh',
    low: 'pms.priorityLow',
    medium: 'pms.priorityMedium',
  };
  return priorityLabelKeys[priority]
    ? translate(priorityLabelKeys[priority])
    : priority;
}

function archiveLabel(
  archivedState: NonNullable<TaskFilterParams['archived_state']>,
  translate: TranslateFilterLabel,
): string {
  const archiveLabelKeys: Record<string, string> = {
    active: 'pms.filter.archive.active',
    all: 'pms.filter.all',
    archived: 'pms.filter.archive.archived',
  };
  return archiveLabelKeys[archivedState]
    ? translate(archiveLabelKeys[archivedState])
    : archivedState;
}
