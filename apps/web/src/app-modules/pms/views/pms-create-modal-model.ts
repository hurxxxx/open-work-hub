import type { createFolder, createPmsTaskList } from '../api/pms-api';

export type PmsCreateModalState = {
  name: string;
  description: string;
  submitting: boolean;
  error: string;
};

export type PmsCreateModalAction =
  | {
      type: 'name';
      value: string;
    }
  | {
      type: 'description';
      value: string;
    }
  | {
      type: 'submit';
    }
  | {
      type: 'failed';
      message: string;
    }
  | {
      type: 'finished';
    }
  | {
      type: 'reset';
    };

export const INITIAL_PMS_CREATE_MODAL_STATE: PmsCreateModalState = {
  name: '',
  description: '',
  submitting: false,
  error: '',
};

export type CreateFolderPayload = Parameters<typeof createFolder>[1];
export type CreateTaskListPayload = Parameters<typeof createPmsTaskList>[1];

export function canSubmitCreateName(name: string): boolean {
  return name.trim().length > 0;
}

export function createFolderPayload({
  name,
  teamId,
}: {
  name: string;
  teamId: string;
}): CreateFolderPayload {
  return {
    name: name.trim(),
    team_id: teamId,
  };
}

export function createTaskListPayload({
  description,
  folderId,
  name,
  teamId,
}: {
  description: string;
  folderId: string | null;
  name: string;
  teamId: string | null;
}): CreateTaskListPayload {
  return {
    name: name.trim(),
    description: description.trim(),
    team_id: teamId,
    folder_id: folderId,
  };
}

export function pmsCreateModalReducer(
  state: PmsCreateModalState,
  action: PmsCreateModalAction,
): PmsCreateModalState {
  switch (action.type) {
    case 'name':
      return {
        ...state,
        name: action.value,
      };
    case 'description':
      return {
        ...state,
        description: action.value,
      };
    case 'submit':
      return {
        ...state,
        submitting: true,
        error: '',
      };
    case 'failed':
      return {
        ...state,
        error: action.message,
      };
    case 'finished':
      return {
        ...state,
        submitting: false,
      };
    case 'reset':
      return INITIAL_PMS_CREATE_MODAL_STATE;
  }
}
