import { useCallback, useEffect, useReducer, type SetStateAction } from 'react';

import {
  getTaskDetail,
  listTaskActivityLogs,
  type PmsAttachment,
  type PmsChecklistItem,
  type PmsComment,
  type PmsTask,
  type PmsTaskDocLink,
} from '../api/pms-api';
import {
  INITIAL_TASK_DETAIL_RESOURCES_STATE,
  taskDetailResourcesReducer,
} from './task-detail-resources-model';
export {
  INITIAL_TASK_DETAIL_RESOURCES_STATE,
  taskDetailResourcesFromLoaded,
  taskDetailResourcesReducer,
} from './task-detail-resources-model';
export type {
  TaskDetailResourcesAction,
  TaskDetailResourcesState,
} from './task-detail-resources-model';

export function useTaskDetailResources({
  taskId,
  token,
}: {
  taskId: string;
  token: string | null;
}) {
  const [state, dispatch] = useReducer(
    taskDetailResourcesReducer,
    INITIAL_TASK_DETAIL_RESOURCES_STATE,
  );

  useEffect(() => {
    if (!token) {
      dispatch({ type: 'loading', value: false });
      return;
    }
    dispatch({ type: 'loading', value: true });
    Promise.all([
      getTaskDetail(token, taskId),
      listTaskActivityLogs(token, taskId),
    ])
      .then(([detail, logs]) => dispatch({ type: 'loaded', detail, logs }))
      .finally(() => dispatch({ type: 'loading', value: false }));
  }, [token, taskId]);

  return {
    state,
    setAttachments: useCallback(
      (value: SetStateAction<PmsAttachment[]>) =>
        dispatch({ type: 'attachments', value }),
      [],
    ),
    setChecklistItems: useCallback(
      (value: SetStateAction<PmsChecklistItem[]>) =>
        dispatch({ type: 'checklistItems', value }),
      [],
    ),
    setComments: useCallback(
      (value: SetStateAction<PmsComment[]>) =>
        dispatch({ type: 'comments', value }),
      [],
    ),
    setLinkedDocs: useCallback(
      (value: SetStateAction<PmsTaskDocLink[]>) =>
        dispatch({ type: 'linkedDocs', value }),
      [],
    ),
    setSubtasks: useCallback(
      (value: SetStateAction<PmsTask[]>) =>
        dispatch({ type: 'subtasks', value }),
      [],
    ),
  };
}
