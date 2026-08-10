import type {
  CalendarEvent,
  CalendarSourceType,
} from '@/src/platform/calendar/calendar-types';
import {
  getZonedDateParts,
  parseDateOnlyParts,
} from '@/src/platform/time/time-utils';

const MS_PER_DAY = 86_400_000;
const SOURCE_ORDER: CalendarSourceType[] = [
  'meeting',
  'pms_block',
  'pms_due',
  'planner_event',
];

export interface TimelineItem {
  event: CalendarEvent;
  start: Date;
  endExclusive: Date;
  left: number;
  width: number;
  clippedStart: boolean;
  clippedEnd: boolean;
}

export interface TimelineItemGroup {
  source: CalendarSourceType;
  items: TimelineItem[];
}

export interface TimelineSourceCount {
  source: CalendarSourceType;
  count: number;
  color: string | undefined;
}

export function dateOnlyToLocalDate(value: string | null | undefined): Date | null {
  const parts = parseDateOnlyParts(value);
  return parts ? new Date(parts.year, parts.month - 1, parts.day) : null;
}

export function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, days: number): Date {
  const next = startOfLocalDay(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function diffDays(left: Date, right: Date): number {
  return Math.round(
    (startOfLocalDay(left).getTime() - startOfLocalDay(right).getTime()) /
      MS_PER_DAY,
  );
}

export function diffTimestampDays(leftTimestamp: number, right: Date): number {
  return Math.round(
    (leftTimestamp - startOfLocalDay(right).getTime()) / MS_PER_DAY,
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function getBaseDayWidth(totalDays: number): number {
  if (totalDays <= 14) return 64;
  if (totalDays <= 28) return 42;
  if (totalDays <= 56) return 30;
  return 24;
}

function getMaxDayWidth(totalDays: number): number {
  if (totalDays <= 14) return 96;
  if (totalDays <= 28) return 56;
  if (totalDays <= 56) return 36;
  return 28;
}

export function getTimelineDayWidth(
  totalDays: number,
  viewportWidth: number,
  leftColumnWidth: number,
): number {
  const baseDayWidth = getBaseDayWidth(totalDays);
  const maxDayWidth = getMaxDayWidth(totalDays);
  const availableGridWidth = Math.max(0, viewportWidth - leftColumnWidth);
  const fittedDayWidth =
    availableGridWidth > 0 ? Math.floor(availableGridWidth / totalDays) : 0;

  return clamp(
    Math.max(baseDayWidth, fittedDayWidth),
    baseDayWidth,
    maxDayWidth,
  );
}

export function toTimelineDate(value: string, timeZone: string): Date | null {
  const dateOnly = dateOnlyToLocalDate(value);
  if (dateOnly) {
    return dateOnly;
  }

  const parts = getZonedDateParts(value, timeZone);
  return parts
    ? new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute)
    : null;
}

export function buildDays(rangeStart: Date, totalDays: number): Date[] {
  return Array.from({ length: totalDays }, (_, index) =>
    addDays(rangeStart, index),
  );
}

export function buildMonthSpans(days: Date[], formatter: Intl.DateTimeFormat) {
  const spans: Array<{ key: string; label: string; days: number }> = [];

  for (const day of days) {
    const key = `${day.getFullYear()}-${day.getMonth()}`;
    const current = spans.at(-1);
    if (current?.key === key) {
      current.days += 1;
    } else {
      spans.push({ key, label: formatter.format(day), days: 1 });
    }
  }

  return spans;
}

export function buildTimelineItems(
  events: CalendarEvent[],
  rangeStart: Date,
  rangeEnd: Date,
  timeZone: string,
  dayWidth: number,
): TimelineItem[] {
  const totalDays = Math.max(1, diffDays(rangeEnd, rangeStart));
  const items: TimelineItem[] = [];

  for (const event of events) {
    const start = toTimelineDate(event.start, timeZone);
    const rawEnd = toTimelineDate(event.end, timeZone);
    if (!start || !rawEnd) {
      continue;
    }

    const endExclusive = event.allDay ? rawEnd : addDays(rawEnd, 1);
    const startOffset = diffDays(start, rangeStart);
    const endOffset = Math.max(
      startOffset + 1,
      diffDays(endExclusive, rangeStart),
    );
    const visibleStart = clamp(startOffset, 0, totalDays);
    const visibleEnd = clamp(endOffset, 0, totalDays);
    const width = Math.max(
      dayWidth * 0.6,
      (visibleEnd - visibleStart) * dayWidth,
    );

    items.push({
      event,
      start,
      endExclusive,
      left: visibleStart * dayWidth,
      width,
      clippedStart: startOffset < 0,
      clippedEnd: endOffset > totalDays,
    });
  }

  items.sort((left, right) => {
    const byStart = left.start.getTime() - right.start.getTime();
    return byStart || left.event.title.localeCompare(right.event.title);
  });

  return items;
}

export function buildItemGroups(items: TimelineItem[]): {
  groupedItems: TimelineItemGroup[];
  sourceCounts: TimelineSourceCount[];
} {
  const itemsBySource = new Map<CalendarSourceType, TimelineItem[]>();
  for (const source of SOURCE_ORDER) {
    itemsBySource.set(source, []);
  }

  for (const item of items) {
    itemsBySource.get(item.event.sourceType)?.push(item);
  }

  const groupedItems: TimelineItemGroup[] = [];
  const sourceCounts: TimelineSourceCount[] = [];
  for (const source of SOURCE_ORDER) {
    const sourceItems = itemsBySource.get(source) ?? [];
    if (sourceItems.length === 0) {
      continue;
    }
    groupedItems.push({ source, items: sourceItems });
    sourceCounts.push({
      source,
      count: sourceItems.length,
      color: sourceItems[0]?.event.color ?? undefined,
    });
  }

  return { groupedItems, sourceCounts };
}
