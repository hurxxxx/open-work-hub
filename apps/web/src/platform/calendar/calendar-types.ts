// Unified calendar event shape consumed by <UnifiedCalendar/>.
// Sourced from meeting + PMS tasks via /api/v1/calendar/events (Phase 2),
// or from a mock fixture during Phase 1.3 development.
//
// Notes:
//   - start/end are ISO 8601 strings WITH offset (e.g. '2026-04-15T10:00:00+09:00')
//     or YYYY-MM-DD for all-day events.
//   - sourceType drives the color + popover content per Design D4/D5.
//   - sourceId is the upstream entity primary key (meeting id or task id).
//   - metadata holds source-specific extras the UI wants to render in the popover
//     without an extra fetch.

import { APP_CALENDAR_SOURCE_COLORS } from '@/src/platform/theme/app-color-fallbacks';

export type CalendarSourceType =
  | 'meeting'
  | 'pms_due'
  | 'pms_block'
  | 'planner_event';

export interface CalendarEventMetadata {
  meetingId?: string | null;
  attendeeCount?: number | null;
  taskListId?: string | null;
  taskListKey?: string | null;
  taskNumber?: number | null;
  status?: string | null;
  assigneeIds?: string[] | null;
  plannerEventId?: string | null;
  ownerId?: string | null;
  ownerName?: string | null;
  location?: string | null;
  plannerAllDay?: boolean | null;
  plannerStartHasTime?: boolean | null;
  plannerEndHasTime?: boolean | null;
  plannerTimeZone?: string | null;
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  allDay: boolean;
  sourceType: CalendarSourceType;
  sourceId: string;
  color: string;
  metadata: CalendarEventMetadata;
}

export interface CalendarEventsRange {
  // Inclusive start, exclusive end. Both ISO date or datetime.
  from: string;
  to: string;
}

export type CalendarSourceFilter = ReadonlyArray<CalendarSourceType>;

export const ALL_CALENDAR_SOURCES: CalendarSourceFilter = [
  'meeting',
  'pms_due',
  'pms_block',
  'planner_event',
];

export const CALENDAR_SOURCE_COLORS: Record<CalendarSourceType, string> = {
  ...APP_CALENDAR_SOURCE_COLORS,
};
