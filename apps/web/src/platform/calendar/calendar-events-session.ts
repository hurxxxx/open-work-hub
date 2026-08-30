import {
  ALL_CALENDAR_SOURCES,
  type CalendarEvent,
  type CalendarSourceFilter,
} from './calendar-types';

export type CalendarEventsState = {
  events: CalendarEvent[];
  loading: boolean;
  error: string | null;
  hasUsableSnapshot: boolean;
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
    }
  | {
      type: 'upsert';
      event: CalendarEvent;
    }
  | {
      type: 'remove';
      eventId: string;
    };

export const INITIAL_CALENDAR_EVENTS_STATE: CalendarEventsState = {
  events: [],
  loading: false,
  error: null,
  hasUsableSnapshot: false,
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
        hasUsableSnapshot: false,
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
        hasUsableSnapshot: true,
      };
    case 'failed':
      return {
        ...state,
        loading: false,
        error: action.message,
      };
    case 'refresh':
      return {
        ...state,
        refreshToken: state.refreshToken + 1,
      };
    case 'upsert': {
      const existingIndex = state.events.findIndex(
        (event) => event.id === action.event.id,
      );
      if (existingIndex < 0) {
        return {
          ...state,
          events: [...state.events, action.event],
          hasUsableSnapshot: true,
        };
      }
      const events = [...state.events];
      events[existingIndex] = action.event;
      return { ...state, events, hasUsableSnapshot: true };
    }
    case 'remove':
      return {
        ...state,
        events: state.events.filter((event) => event.id !== action.eventId),
      };
  }
}

export function getCalendarEventSourcesKey(
  sources?: CalendarSourceFilter,
): string {
  const list = sources ?? ALL_CALENDAR_SOURCES;
  return Array.from(list).sort().join(',');
}
