import type {
  getTaskDetail,
  listTaskActivityLogs,
  PmsActivityLog,
  PmsAttachment,
  PmsChecklistItem,
  PmsComment,
  PmsTask,
  PmsTaskDocLink,
} from '../api/pms-api';

export interface TaskDetailResourcesState {
  activityLogs: PmsActivityLog[];
  attachments: PmsAttachment[];
  checklistItems: PmsChecklistItem[];
  comments: PmsComment[];
  linkedDocs: PmsTaskDocLink[];
  loading: boolean;
  subtasks: PmsTask[];
}

type TaskDetail = Awaited<ReturnType<typeof getTaskDetail>>;
type TaskActivityLogs = Awaited<ReturnType<typeof listTaskActivityLogs>>;

type TaskDetailLoadedResources = Omit<TaskDetailResourcesState, 'loading'>;

type TaskDetailResourceUpdate<T> = T | ((current: T) => T);

export type TaskDetailResourcesAction =
  | {
      type: 'loaded';
      detail: TaskDetail;
      logs: TaskActivityLogs;
    }
  | { type: 'loading'; value: boolean }
  | { type: 'comments'; value: TaskDetailResourceUpdate<PmsComment[]> }
  | { type: 'subtasks'; value: TaskDetailResourceUpdate<PmsTask[]> }
  | { type: 'attachments'; value: TaskDetailResourceUpdate<PmsAttachment[]> }
  | { type: 'linkedDocs'; value: TaskDetailResourceUpdate<PmsTaskDocLink[]> }
  | {
      type: 'checklistItems';
      value: TaskDetailResourceUpdate<PmsChecklistItem[]>;
    };

export const INITIAL_TASK_DETAIL_RESOURCES_STATE: TaskDetailResourcesState = {
  activityLogs: [],
  attachments: [],
  checklistItems: [],
  comments: [],
  linkedDocs: [],
  loading: true,
  subtasks: [],
};

function resolveResourceValue<T>(
  value: TaskDetailResourceUpdate<T>,
  current: T,
): T {
  return typeof value === 'function'
    ? (value as (currentValue: T) => T)(current)
    : value;
}

export function taskDetailResourcesFromLoaded({
  detail,
  logs,
}: {
  detail: TaskDetail;
  logs: TaskActivityLogs;
}): TaskDetailLoadedResources {
  return {
    activityLogs: logs.items,
    attachments: detail.attachments ?? [],
    checklistItems: detail.checklist_items ?? [],
    comments: detail.comments,
    linkedDocs: detail.linked_docs ?? [],
    subtasks: (detail.subtasks ?? []).filter((subtask) => !subtask.archived),
  };
}

export function taskDetailResourcesReducer(
  state: TaskDetailResourcesState,
  action: TaskDetailResourcesAction,
): TaskDetailResourcesState {
  switch (action.type) {
    case 'loaded':
      return {
        ...state,
        ...taskDetailResourcesFromLoaded({
          detail: action.detail,
          logs: action.logs,
        }),
      };
    case 'loading':
      return { ...state, loading: action.value };
    case 'comments':
      return {
        ...state,
        comments: resolveResourceValue(action.value, state.comments),
      };
    case 'subtasks':
      return {
        ...state,
        subtasks: resolveResourceValue(action.value, state.subtasks),
      };
    case 'attachments':
      return {
        ...state,
        attachments: resolveResourceValue(action.value, state.attachments),
      };
    case 'linkedDocs':
      return {
        ...state,
        linkedDocs: resolveResourceValue(action.value, state.linkedDocs),
      };
    case 'checklistItems':
      return {
        ...state,
        checklistItems: resolveResourceValue(
          action.value,
          state.checklistItems,
        ),
      };
  }
}
