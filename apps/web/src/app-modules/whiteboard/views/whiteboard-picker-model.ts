import {
  createInitialPickerState,
  pickerReducer,
  projectPickerItems,
  type PickerState,
} from '@/src/platform/pickers/picker-model';
import type { WhiteboardHubItem } from '../api/whiteboard-api';

export const WHITEBOARD_PICKER_RESULT_LIMIT = 50;

export type WhiteboardPickerState = PickerState<WhiteboardHubItem>;

export type WhiteboardPickerAction =
  | { type: 'load' }
  | { type: 'loaded'; items: WhiteboardHubItem[] }
  | { type: 'failed'; message: string }
  | { type: 'query'; value: string }
  | { type: 'submit'; itemId: string }
  | { type: 'submit-failed'; message: string }
  | { type: 'submit-finished' };

export const INITIAL_WHITEBOARD_PICKER_STATE =
  createInitialPickerState<WhiteboardHubItem>();

export function whiteboardPickerReducer(
  state: WhiteboardPickerState,
  action: WhiteboardPickerAction,
): WhiteboardPickerState {
  switch (action.type) {
    case 'submit':
      return pickerReducer(state, action, INITIAL_WHITEBOARD_PICKER_STATE);
    case 'submit-failed':
      return pickerReducer(
        state,
        { ...action, clearSubmitting: false },
        INITIAL_WHITEBOARD_PICKER_STATE,
      );
    default:
      return pickerReducer(state, action, INITIAL_WHITEBOARD_PICKER_STATE);
  }
}

export function filterWhiteboardsForPicker(
  items: WhiteboardHubItem[],
  options: {
    query: string;
    excludeWhiteboardIds: readonly string[];
    limit?: number;
  },
): WhiteboardHubItem[] {
  const {
    query,
    excludeWhiteboardIds,
    limit = WHITEBOARD_PICKER_RESULT_LIMIT,
  } = options;
  return projectPickerItems({
    items,
    excludeIds: excludeWhiteboardIds,
    getItemId: (item) => item.id,
    limit,
    matchesQuery: (item, normalizedQuery) =>
      item.title.toLowerCase().includes(normalizedQuery),
    query,
  });
}
