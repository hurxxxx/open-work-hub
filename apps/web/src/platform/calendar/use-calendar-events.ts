// Mock-mode: when the backend /api/v1/calendar/events endpoint does not yet exist
// (Phase 1.3), the hook can fall back to MOCK fixture instead of issuing a real
// request. This mode is opt-in via the `useMockData` option so production code can
// flip to real-mode just by removing the flag.
import { useCallback, useEffect, useMemo, useReducer } from 'react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { i18n } from '@/src/platform/i18n';

import { buildMockCalendarEvents, listCalendarEvents } from './calendar-api';
import {
  ALL_CALENDAR_SOURCES,
  type CalendarEvent,
  type CalendarSourceFilter,
} from './calendar-types';
import {
  calendarEventsReducer,
  getCalendarEventSourcesKey,
  INITIAL_CALENDAR_EVENTS_STATE,
} from './calendar-events-session';

export interface UseCalendarEventsOptions {
  from: string; // ISO date or datetime
  to: string; // exclusive
  sources?: CalendarSourceFilter;
  // Phase 1.3 escape hatch — defaults to true until Phase 2 backend is ready.
  useMockData?: boolean;
}

export interface UseCalendarEventsResult {
  events: CalendarEvent[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useCalendarEvents(
  options: UseCalendarEventsOptions,
): UseCalendarEventsResult {
  const { token } = useAuth();
  const { from, to, sources, useMockData = true } = options;
  const [{ error, events, loading, refreshToken }, dispatch] = useReducer(
    calendarEventsReducer,
    INITIAL_CALENDAR_EVENTS_STATE,
  );

  // Stable join string so changing source order doesn't refetch.
  const sourcesKey = useMemo(
    () => getCalendarEventSourcesKey(sources),
    [sources],
  );

  useEffect(() => {
    let cancelled = false;

    if (useMockData) {
      // Synchronous mock — no loading flicker.
      dispatch({
        type: 'loaded',
        events: buildMockCalendarEvents(),
      });
      return () => {
        cancelled = true;
      };
    }

    if (!token) {
      dispatch({ type: 'idle' });
      return () => {
        cancelled = true;
      };
    }

    dispatch({ type: 'loading' });
    listCalendarEvents(token, {
      from,
      to,
      sources: sources ?? ALL_CALENDAR_SOURCES,
    })
      .then((response) => {
        if (cancelled) return;
        dispatch({
          type: 'loaded',
          events: response.items,
        });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'failed',
          message: err.message ?? i18n.t('apps:planner.loadFailed'),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [refreshToken, token, from, to, sourcesKey, useMockData, sources]);

  const refresh = useCallback(() => {
    dispatch({ type: 'refresh' });
  }, []);

  return {
    events,
    loading,
    error,
    refresh,
  };
}
