// Calendar events API client. Talks to the unified events endpoint
// (Phase 2: GET /api/v1/calendar/events) which JOINs Meeting + PMS issues
// scoped to the current authenticated user.
//
// During Phase 1.3 the backend endpoint does not yet exist. The hook in
// use-calendar-events.ts can fall back to MOCK_CALENDAR_EVENTS until Phase 2 lands.
import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

import {
  ALL_CALENDAR_SOURCES,
  CALENDAR_SOURCE_COLORS,
  type CalendarEvent,
  type CalendarSourceFilter,
} from './calendar-types';

export class CalendarApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'CalendarApiError';
  }
}

export interface ListCalendarEventsOptions {
  from: string;          // ISO date (YYYY-MM-DD) or full ISO datetime
  to: string;            // exclusive
  sources?: CalendarSourceFilter;
}

export type CalendarEventsResponse = ApiSchema<'CalendarEventsResponse'>;

export async function listCalendarEvents(
  token: string,
  workspaceSlug: string,
  options: ListCalendarEventsOptions,
): Promise<CalendarEventsResponse> {
  const params = new URLSearchParams();
  params.set('from', options.from);
  params.set('to', options.to);
  const sources = options.sources ?? ALL_CALENDAR_SOURCES;
  if (sources.length > 0) {
    params.set('sources', sources.join(','));
  }
  const path = rewriteWorkspaceApiPath(
    `/api/v1/calendar/events?${params.toString()}`,
    workspaceSlug,
  );
  try {
    return await apiFetchJson<CalendarEventsResponse>(path, token);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new CalendarApiError(
        error.status,
        error.message || `Calendar events request failed with ${error.status}.`,
      );
    }
    throw error;
  }
}

// Mock fixture used while the backend endpoint is not yet wired (Phase 1.3 → Phase 2).
// Matches the set of scenarios verified in Phase 1.1 spike: overlapping events,
// all-day, multi-day, midnight crossing.
//
// Anchored relative to today so the dev never sees an empty calendar regardless
// of when they open it.
function isoOffset(daysFromToday: number, hour: number, minute = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromToday);
  d.setHours(hour, minute, 0, 0);
  // FullCalendar accepts native Date toISOString() and resolves under the
  // calendar's timeZone option ('Asia/Seoul'). We stay UTC-naive here and let
  // the calendar component convert.
  return d.toISOString();
}

function isoDate(daysFromToday: number): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromToday);
  return d.toISOString().slice(0, 10);
}

export function buildMockCalendarEvents(): CalendarEvent[] {
  return [
    {
      id: 'mock-meeting-1',
      title: '분기 전략 회의 (mock)',
      start: isoOffset(0, 10, 0),
      end: isoOffset(0, 11, 0),
      allDay: false,
      sourceType: 'meeting',
      sourceId: 'mock-meeting-1',
      color: CALENDAR_SOURCE_COLORS.meeting,
      metadata: { meetingId: 'mock-meeting-1', attendeeCount: 5 },
    },
    {
      id: 'mock-meeting-2',
      title: '겹침 테스트 — 제품 리뷰',
      start: isoOffset(0, 10, 30),
      end: isoOffset(0, 11, 30),
      allDay: false,
      sourceType: 'meeting',
      sourceId: 'mock-meeting-2',
      color: CALENDAR_SOURCE_COLORS.meeting,
      metadata: { meetingId: 'mock-meeting-2', attendeeCount: 3 },
    },
    {
      id: 'mock-pms-due-1',
      title: 'INDUSTRIAL-12 디자인 리뷰 마감',
      start: isoDate(1),
      end: isoDate(2),
      allDay: true,
      sourceType: 'pms_due',
      sourceId: 'mock-issue-12',
      color: CALENDAR_SOURCE_COLORS.pms_due,
      metadata: { taskListKey: 'INDUSTRIAL', issueNumber: 12, status: 'in_progress' },
    },
    {
      id: 'mock-pms-block-1',
      title: 'INDUSTRIAL-15 워크숍 출장 (3일)',
      start: isoDate(2),
      end: isoDate(5),
      allDay: true,
      sourceType: 'pms_block',
      sourceId: 'mock-issue-15',
      color: CALENDAR_SOURCE_COLORS.pms_block,
      metadata: { taskListKey: 'INDUSTRIAL', issueNumber: 15, status: 'todo' },
    },
    {
      id: 'mock-meeting-3',
      title: '심야 배포 자정 가로지름',
      start: isoOffset(3, 23, 30),
      end: isoOffset(4, 0, 30),
      allDay: false,
      sourceType: 'meeting',
      sourceId: 'mock-meeting-3',
      color: CALENDAR_SOURCE_COLORS.meeting,
      metadata: { meetingId: 'mock-meeting-3', attendeeCount: 2 },
    },
  ];
}
