import type {
  DocsHubItem,
  DocsPageItem,
} from '@/src/app-modules/docs/public-api';
import { formatDateTime } from '@/src/platform/time/time-utils';

import {
  parseServerDateTime,
  type MeetingDetail as MeetingDetailType,
} from '../../api/meeting-api';

export function formatMeetingDetailRange(
  start: string,
  end: string,
  timeZone: string,
  locale: string,
): string {
  const startDate = parseServerDateTime(start);
  const endDate = parseServerDateTime(end);
  return `${formatDateTime(startDate, {
    locale,
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  })} - ${formatDateTime(endDate, {
    hour: '2-digit',
    locale,
    minute: '2-digit',
    timeZone,
  })}`;
}

export interface MeetingDetailState {
  meeting: MeetingDetailType | null;
  notesDoc: DocsHubItem | null;
  notesPage: DocsPageItem | null;
  loading: boolean;
  error: string | null;
  detailOpen: boolean;
}

export type MeetingDetailAction =
  | { type: 'loadStarted' }
  | {
      type: 'loadSucceeded';
      meeting: MeetingDetailType;
      notesDoc: DocsHubItem | null;
      notesPage: DocsPageItem | null;
    }
  | { type: 'loadFailed'; error: string }
  | { type: 'setDetailOpen'; open: boolean }
  | { type: 'setNotesPage'; notesPage: DocsPageItem }
  | { type: 'updateNotesContent'; content: Record<string, unknown>[] };

export const MEETING_DETAIL_INITIAL_STATE: MeetingDetailState = {
  meeting: null,
  notesDoc: null,
  notesPage: null,
  loading: true,
  error: null,
  detailOpen: false,
};

export function meetingDetailReducer(
  state: MeetingDetailState,
  action: MeetingDetailAction,
): MeetingDetailState {
  switch (action.type) {
    case 'loadStarted':
      return {
        ...state,
        loading: true,
        error: null,
      };
    case 'loadSucceeded':
      return {
        ...state,
        meeting: action.meeting,
        notesDoc: action.notesDoc,
        notesPage: action.notesPage,
        loading: false,
        error: null,
      };
    case 'loadFailed':
      return {
        ...state,
        meeting: null,
        notesDoc: null,
        notesPage: null,
        loading: false,
        error: action.error,
      };
    case 'setDetailOpen':
      return {
        ...state,
        detailOpen: action.open,
      };
    case 'setNotesPage':
      return {
        ...state,
        notesPage: action.notesPage,
      };
    case 'updateNotesContent':
      return state.notesPage
        ? {
            ...state,
            notesPage: {
              ...state.notesPage,
              content_blocks: action.content,
            },
          }
        : state;
    default:
      return state;
  }
}
