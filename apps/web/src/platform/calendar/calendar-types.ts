// Unified calendar event shape consumed by <UnifiedCalendar/>.
// Sourced from meeting + PMS issues via /api/v1/calendar/events (Phase 2),
// or from a mock fixture during Phase 1.3 development.
//
// Notes:
//   - start/end are ISO 8601 strings WITH offset (e.g. '2026-04-15T10:00:00+09:00')
//     or YYYY-MM-DD for all-day events.
//   - sourceType drives the color + popover content per Design D4/D5.
//   - sourceId is the upstream entity primary key (meeting id or issue id).
//   - metadata holds source-specific extras the UI wants to render in the popover
//     without an extra fetch.

import type { ApiSchema } from '@/src/platform/api/types';

export type CalendarEventMetadata = ApiSchema<'CalendarEventMetadata'>;
export type CalendarEvent = ApiSchema<'CalendarEventOut'>;
export type CalendarSourceType = CalendarEvent['sourceType'];

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

// Color tokens per Design D5. Kept here so UnifiedCalendar + tests + mock fixture
// resolve to identical values. Hex chosen to avoid Tailwind class-string indirection
// inside FullCalendar's `backgroundColor` API.
export const CALENDAR_SOURCE_COLORS: Record<CalendarSourceType, string> = {
  meeting: '#3b82f6',  // blue-500
  pms_due: '#f59e0b',  // amber-500
  pms_block: '#22c55e', // green-500 fallback; pms_block ideally inherits status color from metadata
  planner_event: '#14b8a6', // teal-500
};
