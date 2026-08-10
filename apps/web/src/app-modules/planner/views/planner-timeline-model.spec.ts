import { describe, expect, it } from 'vitest';

import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  buildDays,
  buildItemGroups,
  buildMonthSpans,
  buildTimelineItems,
  getTimelineDayWidth,
} from './planner-timeline-model';

function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 'event-1',
    sourceId: 'source-1',
    sourceType: 'meeting',
    title: 'Event',
    start: '2026-03-10',
    end: '2026-03-11',
    allDay: true,
    color: '#3b82f6',
    metadata: {
      attendeeCount: null,
      location: null,
      status: null,
      taskListKey: null,
      taskNumber: null,
    },
    ...overrides,
  } as CalendarEvent;
}

describe('planner timeline model', () => {
  it('clips timeline items to the visible date range', () => {
    const rangeStart = new Date(2026, 2, 10);
    const rangeEnd = new Date(2026, 2, 15);
    const [startsBefore, endsAfter] = buildTimelineItems(
      [
        event({
          id: 'starts-before',
          title: 'Starts before',
          start: '2026-03-09',
          end: '2026-03-12',
        }),
        event({
          id: 'ends-after',
          title: 'Ends after',
          start: '2026-03-14',
          end: '2026-03-18',
        }),
      ],
      rangeStart,
      rangeEnd,
      'Asia/Seoul',
      40,
    );

    expect(startsBefore).toMatchObject({
      left: 0,
      width: 80,
      clippedStart: true,
      clippedEnd: false,
    });
    expect(endsAfter).toMatchObject({
      left: 160,
      width: 40,
      clippedStart: false,
      clippedEnd: true,
    });
  });

  it('keeps all-day end dates exclusive when sizing item bars', () => {
    const [item] = buildTimelineItems(
      [
        event({
          start: '2026-03-10',
          end: '2026-03-12',
          allDay: true,
        }),
      ],
      new Date(2026, 2, 10),
      new Date(2026, 2, 15),
      'Asia/Seoul',
      40,
    );

    expect(item.endExclusive).toEqual(new Date(2026, 2, 12));
    expect(item.width).toBe(80);
  });

  it('groups items by source order and counts source colors', () => {
    const items = buildTimelineItems(
      [
        event({
          id: 'due',
          sourceType: 'pms_due',
          title: 'Due',
          color: '#f59e0b',
        }),
        event({
          id: 'meeting',
          sourceType: 'meeting',
          title: 'Meeting',
          color: '#3b82f6',
        }),
        event({
          id: 'block',
          sourceType: 'pms_block',
          title: 'Block',
          color: '#22c55e',
        }),
      ],
      new Date(2026, 2, 10),
      new Date(2026, 2, 15),
      'Asia/Seoul',
      40,
    );

    const { groupedItems, sourceCounts } = buildItemGroups(items);

    expect(groupedItems.map((group) => group.source)).toEqual([
      'meeting',
      'pms_block',
      'pms_due',
    ]);
    expect(sourceCounts).toEqual([
      { source: 'meeting', count: 1, color: '#3b82f6' },
      { source: 'pms_block', count: 1, color: '#22c55e' },
      { source: 'pms_due', count: 1, color: '#f59e0b' },
    ]);
  });

  it('splits month spans when the visible days cross months', () => {
    const month = new Intl.DateTimeFormat('en-US', {
      month: 'long',
      year: 'numeric',
    });

    expect(buildMonthSpans(buildDays(new Date(2026, 0, 30), 4), month)).toEqual(
      [
        { key: '2026-0', label: 'January 2026', days: 2 },
        { key: '2026-1', label: 'February 2026', days: 2 },
      ],
    );
  });

  it('clamps day width between range-specific layout limits', () => {
    expect(getTimelineDayWidth(7, 0, 320)).toBe(64);
    expect(getTimelineDayWidth(7, 2_000, 320)).toBe(96);
    expect(getTimelineDayWidth(31, 0, 320)).toBe(30);
  });
});
