import { projectPickerItems } from '@/src/platform/pickers/picker-model';
import type {
  PmsTask,
  PmsTaskList,
  TaskFilterParams,
} from '../api/pms-api';

export const TASK_PICKER_RESULT_LIMIT = 50;
export const EMPTY_EXCLUDED_TASK_IDS: string[] = [];

export interface TaskPickerModalState {
  taskLists: PmsTaskList[];
  selectedTaskListId: string | null;
  tasks: PmsTask[];
  query: string;
  loading: boolean;
  submittingId: string | null;
  error: string | null;
}

export type TaskPickerModalAction =
  | { type: 'resetForOpen'; selectedTaskListId?: string | null }
  | { type: 'taskListsLoaded'; taskLists: PmsTaskList[] }
  | { type: 'taskListsFailed'; message: string }
  | { type: 'tasksIdle' }
  | { type: 'tasksLoading' }
  | { type: 'tasksLoaded'; tasks: PmsTask[] }
  | { type: 'tasksFailed'; message: string }
  | { type: 'setSelectedTaskListId'; taskListId: string | null }
  | { type: 'setQuery'; query: string }
  | { type: 'pickStarted'; taskId: string }
  | { type: 'pickFailed'; message: string }
  | { type: 'pickFinished' };

export const INITIAL_TASK_PICKER_MODAL_STATE: TaskPickerModalState = {
  taskLists: [],
  selectedTaskListId: null,
  tasks: [],
  query: '',
  loading: false,
  submittingId: null,
  error: null,
};

export function taskPickerModalReducer(
  state: TaskPickerModalState,
  action: TaskPickerModalAction,
): TaskPickerModalState {
  switch (action.type) {
    case 'resetForOpen':
      return {
        ...INITIAL_TASK_PICKER_MODAL_STATE,
        selectedTaskListId: action.selectedTaskListId ?? null,
      };
    case 'taskListsLoaded':
      return {
        ...state,
        taskLists: action.taskLists,
        selectedTaskListId: action.taskLists[0]?.id ?? null,
      };
    case 'taskListsFailed':
      return {
        ...state,
        error: action.message,
        taskLists: [],
        selectedTaskListId: null,
      };
    case 'tasksIdle':
      return { ...state, tasks: [], loading: false };
    case 'tasksLoading':
      return { ...state, loading: true };
    case 'tasksLoaded':
      return { ...state, tasks: action.tasks, loading: false };
    case 'tasksFailed':
      return { ...state, error: action.message, tasks: [], loading: false };
    case 'setSelectedTaskListId':
      return { ...state, selectedTaskListId: action.taskListId };
    case 'setQuery':
      return { ...state, query: action.query };
    case 'pickStarted':
      return { ...state, submittingId: action.taskId, error: null };
    case 'pickFailed':
      return { ...state, error: action.message, submittingId: null };
    case 'pickFinished':
      return { ...state, submittingId: null };
    default:
      return state;
  }
}

export function buildTaskPickerTaskParams(query: string): TaskFilterParams {
  const trimmedQuery = query.trim();
  return {
    archived_state: 'active',
    q: trimmedQuery || undefined,
  };
}

export function getVisibleTaskPickerTasks(
  tasks: PmsTask[],
  excludeTaskIds: string[],
): PmsTask[] {
  return projectPickerItems({
    items: tasks,
    excludeIds: excludeTaskIds,
    getItemId: (task) => task.id,
    limit: TASK_PICKER_RESULT_LIMIT,
  });
}
