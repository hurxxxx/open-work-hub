import type { DatesSetArg, EventInput } from '@fullcalendar/core';

import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';
import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

export interface CalendarDateSelectPayload {
  allDay: boolean;
  anchor: { x: number; y: number } | null;
  end: Date;
  start: Date;
}

export interface CalendarDatesSetPayload {
  currentDate: Date;
  rangeEnd: Date;
  rangeStart: Date;
  view: string;
}

export interface FullCalendarDateSelectLike {
  allDay: boolean;
  end: Date;
  jsEvent?: {
    clientX?: unknown;
    clientY?: unknown;
  } | null;
  start: Date;
}

export interface FullCalendarEventLike {
  allDay: boolean;
  endStr: string;
  extendedProps: Record<string, unknown>;
  startStr: string;
}

export interface FullCalendarEventDropLike {
  event: FullCalendarEventLike;
  revert: () => void;
}

export interface CalendarEventDropPayload {
  event: CalendarEvent;
  newAllDay: boolean;
  newEnd: string;
  newStart: string;
  revert: () => void;
}

export interface FullCalendarEventResizeLike {
  event: Pick<FullCalendarEventLike, 'endStr' | 'extendedProps'>;
  revert: () => void;
}

export interface CalendarEventResizePayload {
  event: CalendarEvent;
  newEnd: string;
  revert: () => void;
}

export function toFullCalendarEvent(event: CalendarEvent): EventInput {
  return {
    id: event.id,
    title: event.title,
    start: event.start,
    end: event.end,
    allDay: event.allDay,
    backgroundColor: event.color,
    borderColor: event.color,
    extendedProps: {
      sourceType: event.sourceType,
      sourceId: event.sourceId,
      metadata: event.metadata,
      original: event,
    },
  };
}

export function getCalendarEventOriginal(input: {
  extendedProps: Record<string, unknown>;
}): CalendarEvent | null {
  return (input.extendedProps.original as CalendarEvent | undefined) ?? null;
}

export function buildDateSelectPayload(
  input: FullCalendarDateSelectLike,
): CalendarDateSelectPayload {
  const native = input.jsEvent;
  const anchor =
    typeof native?.clientX === 'number' && typeof native.clientY === 'number'
      ? { x: native.clientX, y: native.clientY }
      : null;
  return {
    allDay: input.allDay,
    anchor,
    end: input.end,
    start: input.start,
  };
}

export function buildDatesSetPayload(
  input: DatesSetArg,
): CalendarDatesSetPayload {
  return {
    currentDate: input.view.calendar.getDate(),
    rangeEnd: input.end,
    rangeStart: input.start,
    view: input.view.type,
  };
}

export function buildEventDropPayload(
  input: FullCalendarEventDropLike,
): CalendarEventDropPayload | null {
  const original = getCalendarEventOriginal(input.event);
  if (!original || !input.event.startStr) {
    return null;
  }
  return {
    event: original,
    newAllDay: input.event.allDay,
    newEnd: input.event.endStr || input.event.startStr,
    newStart: input.event.startStr,
    revert: input.revert,
  };
}

export function buildEventResizePayload(
  input: FullCalendarEventResizeLike,
): CalendarEventResizePayload | null {
  const original = getCalendarEventOriginal(input.event);
  if (!original || !input.event.endStr) {
    return null;
  }
  return {
    event: original,
    newEnd: input.event.endStr,
    revert: input.revert,
  };
}

export function getKoreanHolidayDayClass(date: Date): string[] {
  return getKoreanHolidayLabel(date) ? ['fc-korean-holiday'] : [];
}

export function getKoreanHolidayLabel(date: Date): string | null {
  const names = getKoreanHolidayNames(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  );
  return names?.join(', ') ?? null;
}
