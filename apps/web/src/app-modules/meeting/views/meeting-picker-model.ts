import {
  createInitialPickerState,
  pickerReducer,
  projectPickerItems,
  type PickerState,
} from '@/src/platform/pickers/picker-model';
import type { MeetingListItem } from '../api/meeting-api';

export const MEETING_PICKER_RESULT_LIMIT = 50;

export type MeetingPickerState = PickerState<MeetingListItem>;

export type MeetingPickerAction =
  | { type: 'reset' }
  | { type: 'load' }
  | { type: 'loaded'; items: MeetingListItem[] }
  | { type: 'failed'; message: string }
  | { type: 'query'; value: string }
  | { type: 'submit'; meetingId: string }
  | { type: 'submit-failed'; message: string }
  | { type: 'submit-finished' };

export const INITIAL_MEETING_PICKER_STATE =
  createInitialPickerState<MeetingListItem>();

export function meetingPickerReducer(
  state: MeetingPickerState,
  action: MeetingPickerAction,
): MeetingPickerState {
  switch (action.type) {
    case 'load':
      return pickerReducer(
        state,
        { ...action, resetQuery: true },
        INITIAL_MEETING_PICKER_STATE,
      );
    case 'submit':
      return pickerReducer(
        state,
        { type: 'submit', itemId: action.meetingId },
        INITIAL_MEETING_PICKER_STATE,
      );
    case 'submit-failed':
      return pickerReducer(
        state,
        { ...action, clearSubmitting: false },
        INITIAL_MEETING_PICKER_STATE,
      );
    default:
      return pickerReducer(state, action, INITIAL_MEETING_PICKER_STATE);
  }
}

export function sortMeetingsForPicker(items: MeetingListItem[]): MeetingListItem[] {
  return items
    .slice()
    .sort((left, right) => (left.start_at < right.start_at ? 1 : -1));
}

export function filterMeetingsForPicker(
  items: MeetingListItem[],
  options: {
    excludeMeetingIds: readonly string[];
    query: string;
    limit?: number;
  },
): MeetingListItem[] {
  const { excludeMeetingIds, query, limit = MEETING_PICKER_RESULT_LIMIT } = options;
  return projectPickerItems({
    items,
    excludeIds: excludeMeetingIds,
    getItemId: (item) => item.id,
    limit,
    matchesQuery: (item, normalizedQuery) =>
      item.title.toLowerCase().includes(normalizedQuery),
    query,
  });
}
