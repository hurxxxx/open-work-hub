// useCalendarEvents — fetch unified calendar events for a date range.
//
// Pattern follows the existing useState/useEffect + cancelled flag convention used
// across the app (see MeetingView.tsx:34-79). Codebase has no React Query, so this
// hook intentionally avoids it to stay consistent.
//
// Mock-mode: when the backend /api/v1/calendar/events endpoint does not yet exist
// (Phase 1.3), the hook can fall back to MOCK fixture instead of issuing a real
// request. This mode is opt-in via the `useMockData` option so production code can
// flip to real-mode just by removing the flag.
import { useEffect, useMemo, useState } from 'react';

import { useAuth } from '@/src/domains/auth/auth-provider';

import {
  buildMockCalendarEvents,
  listCalendarEvents,
} from './calendar-api';
import {
  ALL_CALENDAR_SOURCES,
  type CalendarEvent,
  type CalendarSourceFilter,
} from './calendar-types';

export interface UseCalendarEventsOptions {
  workspaceSlug: string | undefined;
  from: string; // ISO date or datetime
  to: string;   // exclusive
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
  const { workspaceSlug, from, to, sources, useMockData = true } = options;

  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  // Stable join string so changing source order doesn't refetch.
  const sourcesKey = useMemo(() => {
    const list = sources ?? ALL_CALENDAR_SOURCES;
    return [...list].sort().join(',');
  }, [sources]);

  useEffect(() => {
    let cancelled = false;

    if (useMockData) {
      // Synchronous mock — no loading flicker.
      setEvents(buildMockCalendarEvents());
      setLoading(false);
      setError(null);
      return () => {
        cancelled = true;
      };
    }

    if (!token || !workspaceSlug) {
      setEvents([]);
      setLoading(false);
      setError(null);
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    setError(null);
    listCalendarEvents(token, workspaceSlug, {
      from,
      to,
      sources: sources ?? ALL_CALENDAR_SOURCES,
    })
      .then((response) => {
        if (cancelled) return;
        setEvents(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? '캘린더 일정을 불러올 수 없습니다.');
        setEvents([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [refreshToken, token, workspaceSlug, from, to, sourcesKey, useMockData, sources]);

  return {
    events,
    loading,
    error,
    refresh: () => setRefreshToken((n) => n + 1),
  };
}
