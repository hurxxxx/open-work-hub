import { describe, expect, it } from 'vitest';

import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  addDateKeyDays,
  buildCreateRangeForDateKey,
  buildTodayPlannerDayGroups,
  buildTodayPlannerRange,
  countRemainingTodayPlannerEntries,
} from './floating-today-planner-model';

function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    allDay: false,
    color: '#3b82f6',
    end: '2026-07-01T10:00:00+09:00',
    id: 'event-1',
    metadata: {},
    sourceId: 'source-1',
    sourceType: 'meeting',
    start: '2026-07-01T09:00:00+09:00',
    title: 'Event',
    ...overrides,
  };
}

describe('floating today planner model', () => {
  it('builds the yesterday, today, and tomorrow range with exclusive to date', () => {
    expect(
      buildTodayPlannerRange(new Date('2026-07-01T03:00:00Z'), 'Asia/Seoul'),
    ).toEqual({
      days: [
        { dateKey: '2026-06-30', id: 'yesterday', offset: -1 },
        { dateKey: '2026-07-01', id: 'today', offset: 0 },
        { dateKey: '2026-07-02', id: 'tomorrow', offset: 1 },
      ],
      from: '2026-06-30',
      todayKey: '2026-07-01',
      to: '2026-07-03',
    });
  });

  it('adds days across month boundaries', () => {
    expect(addDateKeyDays('2026-06-30', 1)).toBe('2026-07-01');
    expect(addDateKeyDays('2026-07-01', -1)).toBe('2026-06-30');
  });

  it('groups all-day events by every covered date using an exclusive end date', () => {
    const range = buildTodayPlannerRange(
      new Date('2026-07-01T03:00:00Z'),
      'Asia/Seoul',
    );
    const groups = buildTodayPlannerDayGroups(
      [
        event({
          allDay: true,
          end: '2026-07-02',
          id: 'all-day',
          start: '2026-06-30',
        }),
      ],
      range.days,
      'Asia/Seoul',
      new Date('2026-07-01T03:00:00Z'),
    );

    expect(groups.map((group) => group.entries.map((entry) => entry.event.id))).toEqual(
      [['all-day'], ['all-day'], []],
    );
  });

  it('moves past events after remaining events and counts only today remaining items', () => {
    const range = buildTodayPlannerRange(
      new Date('2026-07-01T03:00:00Z'),
      'Asia/Seoul',
    );
    const events = [
      event({
        end: '2026-07-01T08:00:00+09:00',
        id: 'past',
        start: '2026-07-01T07:00:00+09:00',
      }),
      event({
        end: '2026-07-01T15:00:00+09:00',
        id: 'future',
        start: '2026-07-01T14:00:00+09:00',
      }),
    ];
    const groups = buildTodayPlannerDayGroups(
      events,
      range.days,
      'Asia/Seoul',
      new Date('2026-07-01T03:00:00Z'),
    );

    expect(groups[1]?.entries.map((entry) => entry.event.id)).toEqual([
      'future',
      'past',
    ]);
    expect(
      countRemainingTodayPlannerEntries(
        events,
        range.todayKey,
        'Asia/Seoul',
        new Date('2026-07-01T03:00:00Z'),
      ),
    ).toBe(1);
  });

  it('builds a default one-hour create range from the next whole hour', () => {
    const range = buildCreateRangeForDateKey(
      '2026-07-02',
      new Date(2026, 6, 1, 10, 12),
    );

    expect(range).toMatchObject({ allDay: false });
    expect(range.start.getFullYear()).toBe(2026);
    expect(range.start.getMonth()).toBe(6);
    expect(range.start.getDate()).toBe(2);
    expect(range.start.getHours()).toBe(11);
    expect(range.end.getHours()).toBe(12);
  });
});
