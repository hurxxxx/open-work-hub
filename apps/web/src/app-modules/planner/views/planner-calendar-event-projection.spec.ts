import { describe, expect, it } from 'vitest';

import type { PlannerEvent } from '../api/planner-api';
import { CALENDAR_SOURCE_COLORS } from '@/src/platform/calendar/calendar-types';
import {
  plannerCalendarEventId,
  plannerEventToCalendarEvent,
} from './planner-calendar-event-projection';

function plannerEvent(overrides: Partial<PlannerEvent> = {}): PlannerEvent {
  return {
    id: 'event-1',
    ownerId: 'user-1',
    ownerName: 'Planner User',
    title: 'Planning',
    description: 'Plan the work',
    location: 'Room 1',
    timeZone: 'Asia/Seoul',
    allDay: false,
    startHasTime: true,
    endHasTime: true,
    start: '2026-08-29T01:00:00+00:00',
    end: '2026-08-29T02:00:00+00:00',
    calendarStart: '2026-08-29T01:00:00+00:00',
    calendarEnd: '2026-08-29T02:00:00+00:00',
    calendarAllDay: false,
    createdAt: '2026-08-28T00:00:00+00:00',
    updatedAt: '2026-08-28T00:00:00+00:00',
    ...overrides,
  };
}

describe('plannerEventToCalendarEvent', () => {
  it('matches the unified calendar projection for a timed event', () => {
    expect(plannerEventToCalendarEvent(plannerEvent())).toEqual({
      id: 'planner-event-event-1',
      title: 'Planning',
      start: '2026-08-29T01:00:00+00:00',
      end: '2026-08-29T02:00:00+00:00',
      allDay: false,
      sourceType: 'planner_event',
      sourceId: 'event-1',
      color: CALENDAR_SOURCE_COLORS.planner_event,
      metadata: {
        plannerEventId: 'event-1',
        ownerId: 'user-1',
        ownerName: 'Planner User',
        location: 'Room 1',
        plannerAllDay: false,
        plannerStartHasTime: true,
        plannerEndHasTime: true,
        plannerTimeZone: 'Asia/Seoul',
      },
    });
  });

  it('projects start-only and end-only events as 30-minute markers', () => {
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          end: '2026-08-29',
          endHasTime: false,
          calendarEnd: '2026-08-29T01:30:00+00:00',
        }),
      ),
    ).toMatchObject({
      start: '2026-08-29T01:00:00+00:00',
      end: '2026-08-29T01:30:00+00:00',
      allDay: false,
    });
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          start: '2026-08-29',
          startHasTime: false,
          calendarStart: '2026-08-29T01:30:00+00:00',
        }),
      ),
    ).toMatchObject({
      start: '2026-08-29T01:30:00+00:00',
      end: '2026-08-29T02:00:00+00:00',
      allDay: false,
    });
  });

  it('clamps partial-time markers to the configured local-day boundary', () => {
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          start: '2026-08-29T14:50:00Z',
          end: '2026-08-29',
          endHasTime: false,
          calendarStart: '2026-08-29T14:50:00+00:00',
          calendarEnd: '2026-08-29T14:59:59.999999+00:00',
        }),
      ),
    ).toMatchObject({
      start: '2026-08-29T14:50:00+00:00',
      end: '2026-08-29T14:59:59.999999+00:00',
      allDay: false,
    });
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          start: '2026-08-29',
          end: '2026-08-28T15:10:00Z',
          startHasTime: false,
          calendarStart: '2026-08-28T15:00:00+00:00',
          calendarEnd: '2026-08-28T15:10:00+00:00',
        }),
      ),
    ).toMatchObject({
      start: '2026-08-28T15:00:00+00:00',
      end: '2026-08-28T15:10:00+00:00',
      allDay: false,
    });
  });

  it('projects date-only markers and true all-day ranges separately', () => {
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          start: '2026-08-29',
          end: '2026-08-29',
          startHasTime: false,
          endHasTime: false,
          calendarStart: '2026-08-29',
          calendarEnd: '2026-08-30',
          calendarAllDay: true,
        }),
      ),
    ).toMatchObject({
      start: '2026-08-29',
      end: '2026-08-30',
      allDay: true,
    });
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          allDay: true,
          start: '2026-08-29',
          end: '2026-08-31',
          startHasTime: false,
          endHasTime: false,
          calendarStart: '2026-08-29',
          calendarEnd: '2026-08-31',
          calendarAllDay: true,
        }),
      ),
    ).toMatchObject({
      start: '2026-08-29',
      end: '2026-08-31',
      allDay: true,
    });
    expect(plannerCalendarEventId('event-1')).toBe('planner-event-event-1');
  });

  it('uses server canonical bounds for a nonexistent local midnight', () => {
    expect(
      plannerEventToCalendarEvent(
        plannerEvent({
          timeZone: 'Africa/Cairo',
          start: '2024-04-26',
          end: '2024-04-25T22:10:00+00:00',
          startHasTime: false,
          calendarStart: '2024-04-25T22:00:00+00:00',
          calendarEnd: '2024-04-25T22:10:00+00:00',
        }),
      ),
    ).toMatchObject({
      start: '2024-04-25T22:00:00+00:00',
      end: '2024-04-25T22:10:00+00:00',
      allDay: false,
    });
  });
});
