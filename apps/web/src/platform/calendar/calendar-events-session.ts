import {
  ALL_CALENDAR_SOURCES,
  type CalendarEvent,
  type CalendarSourceFilter,
} from './calendar-types';

export type CalendarEventsState = {
  events: CalendarEvent[];
  loading: boolean;
  error: string | null;
  refreshToken: number;
};

export type CalendarEventsAction =
  | {
      type: 'idle';
    }
  | {
      type: 'loading';
    }
  | {
      type: 'loaded';
      events: CalendarEvent[];
    }
  | {
      type: 'failed';
      message: string;
    }
  | {
      type: 'refresh';
    };

export const INITIAL_CALENDAR_EVENTS_STATE: CalendarEventsState = {
  events: [],
  loading: false,
  error: null,
  refreshToken: 0,
};

export function calendarEventsReducer(
  state: CalendarEventsState,
  action: CalendarEventsAction,
): CalendarEventsState {
  switch (action.type) {
    case 'idle':
      return {
        ...state,
        events: [],
        loading: false,
        error: null,
      };
    case 'loading':
      return {
        ...state,
        loading: true,
        error: null,
      };
    case 'loaded':
      return {
        ...state,
        events: action.events,
        loading: false,
        error: null,
      };
    case 'failed':
      return {
        ...state,
        events: [],
        loading: false,
        error: action.message,
      };
    case 'refresh':
      return {
        ...state,
        refreshToken: state.refreshToken + 1,
      };
  }
}

export function getCalendarEventSourcesKey(
  sources?: CalendarSourceFilter,
): string {
  const list = sources ?? ALL_CALENDAR_SOURCES;
  return Array.from(list).sort().join(',');
}
