import { describe, expect, it, vi } from 'vitest';
import type { DatesSetArg } from '@fullcalendar/core';

import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';
import {
  buildDateSelectPayload,
  buildDatesSetPayload,
  buildEventDropPayload,
  buildEventResizePayload,
  getCalendarEventOriginal,
  getKoreanHolidayDayClass,
  getKoreanHolidayLabel,
  toFullCalendarEvent,
} from './unified-calendar-adapter';

describe('unified calendar adapter', () => {
  it('uses the FullCalendar active date for datesSet payloads', () => {
    const activeDate = new Date(2026, 5, 15);
    const rangeStart = new Date(2026, 4, 31);
    const rangeEnd = new Date(2026, 6, 12);

    expect(
      buildDatesSetPayload({
        end: rangeEnd,
        start: rangeStart,
        view: {
          calendar: {
            getDate: () => activeDate,
          },
          type: 'dayGridMonth',
        },
      } as unknown as DatesSetArg),
    ).toEqual({
      currentDate: activeDate,
      rangeEnd,
      rangeStart,
      view: 'dayGridMonth',
    });
  });

  it('roundtrips Open ALM calendar events through FullCalendar extended props', () => {
    const source = calendarEvent({ id: 'event-1' });
    const fullCalendarEvent = toFullCalendarEvent(source);

    expect(fullCalendarEvent).toMatchObject({
      id: 'event-1',
      title: 'Calendar event',
      start: '2026-05-20T09:00:00+09:00',
      end: '2026-05-20T10:00:00+09:00',
      backgroundColor: '#3b82f6',
      borderColor: '#3b82f6',
      extendedProps: {
        sourceType: 'meeting',
        sourceId: 'meeting-1',
        metadata: { meetingId: 'meeting-1' },
        original: source,
      },
    });
    expect(
      getCalendarEventOriginal({
        extendedProps: fullCalendarEvent.extendedProps ?? {},
      }),
    ).toBe(source);
  });

  it('builds date select payloads with optional pointer anchors', () => {
    const start = new Date('2026-05-20T00:00:00.000Z');
    const end = new Date('2026-05-21T00:00:00.000Z');

    expect(
      buildDateSelectPayload({
        allDay: true,
        end,
        jsEvent: { clientX: 12, clientY: 24 },
        start,
      }),
    ).toEqual({ allDay: true, anchor: { x: 12, y: 24 }, end, start });
    expect(
      buildDateSelectPayload({
        allDay: false,
        end,
        jsEvent: { clientX: 'bad', clientY: 24 },
        start,
      }).anchor,
    ).toBeNull();
  });

  it('builds drop payloads and falls back to startStr when endStr is missing', () => {
    const source = calendarEvent();
    const revert = vi.fn();

    expect(
      buildEventDropPayload({
        event: {
          allDay: false,
          endStr: '',
          extendedProps: { original: source },
          startStr: '2026-05-20T11:00:00+09:00',
        },
        revert,
      }),
    ).toEqual({
      event: source,
      newAllDay: false,
      newEnd: '2026-05-20T11:00:00+09:00',
      newStart: '2026-05-20T11:00:00+09:00',
      revert,
    });
  });

  it('ignores drop and resize callbacks without required FullCalendar data', () => {
    const source = calendarEvent();

    expect(
      buildEventDropPayload({
        event: {
          allDay: false,
          endStr: '2026-05-20T10:00:00+09:00',
          extendedProps: {},
          startStr: '2026-05-20T09:00:00+09:00',
        },
        revert: vi.fn(),
      }),
    ).toBeNull();
    expect(
      buildEventDropPayload({
        event: {
          allDay: false,
          endStr: '2026-05-20T10:00:00+09:00',
          extendedProps: { original: source },
          startStr: '',
        },
        revert: vi.fn(),
      }),
    ).toBeNull();
    expect(
      buildEventResizePayload({
        event: {
          endStr: '',
          extendedProps: { original: source },
        },
        revert: vi.fn(),
      }),
    ).toBeNull();
  });

  it('builds resize payloads with the timezone-preserving end string', () => {
    const source = calendarEvent();
    const revert = vi.fn();

    expect(
      buildEventResizePayload({
        event: {
          endStr: '2026-05-20T12:00:00+09:00',
          extendedProps: { original: source },
        },
        revert,
      }),
    ).toEqual({
      event: source,
      newEnd: '2026-05-20T12:00:00+09:00',
      revert,
    });
  });

  it('classifies Korean holiday day cells and labels', () => {
    expect(getKoreanHolidayDayClass(new Date(2026, 0, 1))).toEqual([
      'fc-korean-holiday',
    ]);
    expect(getKoreanHolidayLabel(new Date(2026, 0, 1))).toBeTruthy();
    expect(getKoreanHolidayDayClass(new Date(2026, 0, 2))).toEqual([]);
    expect(getKoreanHolidayLabel(new Date(2026, 0, 2))).toBeNull();
  });
});

function calendarEvent(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    allDay: false,
    color: '#3b82f6',
    end: '2026-05-20T10:00:00+09:00',
    id: 'event-1',
    metadata: { meetingId: 'meeting-1' },
    sourceId: 'meeting-1',
    sourceType: 'meeting',
    start: '2026-05-20T09:00:00+09:00',
    title: 'Calendar event',
    ...overrides,
  } as CalendarEvent;
}
