import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';
import {
  parseApiDateTime,
  parseDateOnlyParts,
  zonedDateKey,
} from '@/src/platform/time/time-utils';
import { defaultTimedRangeForDate } from './planner-event-default-time';

export type TodayPlannerDayId = 'yesterday' | 'today' | 'tomorrow';

export interface TodayPlannerDay {
  dateKey: string;
  id: TodayPlannerDayId;
  offset: -1 | 0 | 1;
}

export interface TodayPlannerRange {
  days: TodayPlannerDay[];
  from: string;
  todayKey: string;
  to: string;
}

export interface TodayPlannerEntry {
  dayId: TodayPlannerDayId;
  dayKey: string;
  event: CalendarEvent;
  id: string;
  isPast: boolean;
  sortTime: number;
}

export interface TodayPlannerDayGroup extends TodayPlannerDay {
  entries: TodayPlannerEntry[];
}

const DAY_IDS: Record<-1 | 0 | 1, TodayPlannerDayId> = {
  [-1]: 'yesterday',
  0: 'today',
  1: 'tomorrow',
};

const DAY_MS = 86_400_000;

export function addDateKeyDays(dateKey: string, days: number): string {
  const parts = parseDateOnlyParts(dateKey);
  if (!parts) {
    return dateKey;
  }
  const next = new Date(
    Date.UTC(parts.year, parts.month - 1, parts.day) + days * DAY_MS,
  );
  return next.toISOString().slice(0, 10);
}

export function buildTodayPlannerRange(
  now: Date,
  timeZone: string,
): TodayPlannerRange {
  const todayKey = zonedDateKey(now, timeZone);
  const days: TodayPlannerDay[] = ([-1, 0, 1] as const).map((offset) => ({
    dateKey: addDateKeyDays(todayKey, offset),
    id: DAY_IDS[offset],
    offset,
  }));

  return {
    days,
    from: days[0]?.dateKey ?? todayKey,
    todayKey,
    to: addDateKeyDays(days[2]?.dateKey ?? todayKey, 1),
  };
}

export function buildCreateRangeForDateKey(
  dateKey: string,
  now = new Date(),
): {
  allDay: false;
  end: Date;
  start: Date;
} {
  const parts = parseDateOnlyParts(dateKey);
  const fallback = new Date();
  const date = parts
    ? new Date(parts.year, parts.month - 1, parts.day)
    : new Date(fallback.getFullYear(), fallback.getMonth(), fallback.getDate());
  const { start, end } = defaultTimedRangeForDate(date, now);
  return { allDay: false, end, start };
}

export function buildTodayPlannerDayGroups(
  events: readonly CalendarEvent[],
  days: readonly TodayPlannerDay[],
  timeZone: string,
  now: Date,
): TodayPlannerDayGroup[] {
  return days.map((day) => ({
    ...day,
    entries: events
      .filter((event) => eventOccursOnDateKey(event, day.dateKey, timeZone))
      .map((event) => ({
        dayId: day.id,
        dayKey: day.dateKey,
        event,
        id: `${day.dateKey}:${event.id}`,
        isPast: isEventPastForDateKey(event, day.dateKey, timeZone, now),
        sortTime: eventSortTime(event, day.dateKey, timeZone),
      }))
      .sort(compareTodayPlannerEntries),
  }));
}

export function countRemainingTodayPlannerEntries(
  events: readonly CalendarEvent[],
  todayKey: string,
  timeZone: string,
  now: Date,
): number {
  return events.filter(
    (event) =>
      eventOccursOnDateKey(event, todayKey, timeZone) &&
      !isEventPastForDateKey(event, todayKey, timeZone, now),
  ).length;
}

function compareTodayPlannerEntries(
  left: TodayPlannerEntry,
  right: TodayPlannerEntry,
): number {
  if (left.isPast !== right.isPast) {
    return left.isPast ? 1 : -1;
  }
  if (left.sortTime !== right.sortTime) {
    return left.sortTime - right.sortTime;
  }
  return left.event.title.localeCompare(right.event.title);
}

function eventOccursOnDateKey(
  event: CalendarEvent,
  dateKey: string,
  timeZone: string,
): boolean {
  const startKey = eventDateKey(event.start, event.allDay, timeZone);
  const endKey = eventDateKey(event.end, event.allDay, timeZone);
  if (!startKey) {
    return false;
  }
  if (event.allDay) {
    const exclusiveEndKey = endKey || addDateKeyDays(startKey, 1);
    return startKey <= dateKey && dateKey < exclusiveEndKey;
  }

  const inclusiveEndKey = endKey || startKey;
  return startKey <= dateKey && dateKey <= inclusiveEndKey;
}

function isEventPastForDateKey(
  event: CalendarEvent,
  dateKey: string,
  timeZone: string,
  now: Date,
): boolean {
  const todayKey = zonedDateKey(now, timeZone);
  if (dateKey < todayKey) {
    return true;
  }
  if (dateKey > todayKey || event.allDay) {
    return false;
  }
  const end = parseApiDateTime(event.end);
  return end ? end.getTime() < now.getTime() : false;
}

function eventSortTime(
  event: CalendarEvent,
  dateKey: string,
  timeZone: string,
): number {
  if (event.allDay) {
    return 0;
  }
  const startKey = eventDateKey(event.start, false, timeZone);
  if (startKey && startKey < dateKey) {
    return 1;
  }
  return parseApiDateTime(event.start)?.getTime() ?? Number.MAX_SAFE_INTEGER;
}

function eventDateKey(
  value: string,
  allDay: boolean,
  timeZone: string,
): string | null {
  if (allDay) {
    return parseDateOnlyParts(value.slice(0, 10)) ? value.slice(0, 10) : null;
  }
  const date = parseApiDateTime(value);
  return date ? zonedDateKey(date, timeZone) : null;
}
