// Mock-mode: when the backend /api/v1/calendar/events endpoint does not yet exist
// (Phase 1.3), the hook can fall back to MOCK fixture instead of issuing a real
// request. This mode is opt-in via the `useMockData` option so production code can
// flip to real-mode just by removing the flag.
import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { i18n } from '@/src/platform/i18n';

import { buildMockCalendarEvents, listCalendarEvents } from './calendar-api';
import { dispatchCalendarEventsChanged } from './calendar-events-changed';
import {
  calendarEventsReducer,
  getCalendarEventSourcesKey,
  INITIAL_CALENDAR_EVENTS_STATE,
} from './calendar-events-session';
import {
  ALL_CALENDAR_SOURCES,
  type CalendarEvent,
  type CalendarSourceFilter,
} from './calendar-types';

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
  hasUsableSnapshot: boolean;
  refresh: () => void;
  removeEvent: (eventId: string) => void;
  upsertEvent: (event: CalendarEvent) => void;
}

export function useCalendarEvents(
  options: UseCalendarEventsOptions,
): UseCalendarEventsResult {
  const { token } = useAuth();
  const { from, to, sources, useMockData = true } = options;
  const [
    { error, events, hasUsableSnapshot, loading, refreshToken },
    dispatch,
  ] = useReducer(calendarEventsReducer, INITIAL_CALENDAR_EVENTS_STATE);
  const requestVersionRef = useRef(0);

  // Stable join string so changing source order doesn't refetch.
  const sourcesKey = useMemo(
    () => getCalendarEventSourcesKey(sources),
    [sources],
  );

  useEffect(() => {
    let cancelled = false;
    const requestVersion = ++requestVersionRef.current;

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
        if (cancelled || requestVersion !== requestVersionRef.current) return;
        dispatch({
          type: 'loaded',
          events: response.items,
        });
      })
      .catch((err: Error) => {
        if (cancelled || requestVersion !== requestVersionRef.current) return;
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
    requestVersionRef.current += 1;
    dispatch({ type: 'refresh' });
  }, []);

  const removeEvent = useCallback((eventId: string) => {
    requestVersionRef.current += 1;
    dispatch({ type: 'remove', eventId });
    dispatchCalendarEventsChanged();
  }, []);

  const upsertEvent = useCallback((event: CalendarEvent) => {
    requestVersionRef.current += 1;
    dispatch({ type: 'upsert', event });
    dispatchCalendarEventsChanged();
  }, []);

  return {
    events,
    loading,
    error,
    hasUsableSnapshot,
    refresh,
    removeEvent,
    upsertEvent,
  };
}
