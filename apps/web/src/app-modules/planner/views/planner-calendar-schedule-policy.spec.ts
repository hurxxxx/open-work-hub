import { describe, expect, it } from 'vitest';

import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  getPlannerCalendarDropPolicy,
  getPlannerCalendarResizePolicy,
} from './planner-calendar-schedule-policy';

function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 'event-1',
    sourceId: 'source-1',
    sourceType: 'meeting',
    title: 'Event',
    start: '2026-03-10T09:00:00+09:00',
    end: '2026-03-10T10:00:00+09:00',
    allDay: false,
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

describe('planner calendar schedule policy', () => {
  it('rejects meeting drops onto all-day slots', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({ sourceType: 'meeting' }),
        '2026-03-12',
        '2026-03-13',
        true,
      ),
    ).toEqual({
      status: 'reject',
      revert: true,
      reason: 'meetingAllDayDisallowed',
    });
  });

  it('rejects timed task drops', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({ sourceType: 'pms_due' }),
        '2026-03-12T09:00:00+09:00',
        '2026-03-12T10:00:00+09:00',
        false,
      ),
    ).toEqual({
      status: 'reject',
      revert: true,
      reason: 'taskAllDayOnly',
    });
  });

  it('converts PMS due all-day drops from exclusive end to inclusive due date', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({ sourceId: 'task-1', sourceType: 'pms_due' }),
        '2026-03-12',
        '2026-03-13',
        true,
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updateTask',
        sourceId: 'task-1',
        payload: { due_date: '2026-03-12' },
      },
    });
  });

  it('sets PMS block start date and inclusive due date', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({ sourceId: 'task-1', sourceType: 'pms_block' }),
        '2026-03-12',
        '2026-03-15',
        true,
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updateTask',
        sourceId: 'task-1',
        payload: { due_date: '2026-03-14', start_date: '2026-03-12' },
      },
    });
  });

  it('preserves planner event all-day, start, and end drop payload behavior', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({ sourceId: 'planner-1', sourceType: 'planner_event' }),
        '2026-03-12T09:00:00+09:00',
        '2026-03-12T10:00:00+09:00',
        false,
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: 'planner-1',
        payload: {
          allDay: false,
          start: '2026-03-12T09:00:00+09:00',
          end: '2026-03-12T10:00:00+09:00',
        },
      },
    });
  });

  it('keeps projected date-only planner events non-all-day on all-day drops', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({
          sourceId: 'planner-1',
          sourceType: 'planner_event',
          allDay: true,
          start: '2026-03-10',
          end: '2026-03-11',
          metadata: {
            attendeeCount: null,
            location: null,
            plannerAllDay: false,
            plannerStartHasTime: false,
            plannerEndHasTime: false,
            status: null,
            taskListKey: null,
            taskNumber: null,
          },
        }),
        '2026-03-12',
        '2026-03-14',
        true,
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: 'planner-1',
        payload: {
          allDay: false,
          start: '2026-03-12',
          end: '2026-03-13',
        },
      },
    });
  });

  it('preserves planner event optional time flags on timed drops', () => {
    expect(
      getPlannerCalendarDropPolicy(
        event({
          sourceId: 'planner-1',
          sourceType: 'planner_event',
          metadata: {
            attendeeCount: null,
            location: null,
            plannerAllDay: false,
            plannerStartHasTime: true,
            plannerEndHasTime: false,
            status: null,
            taskListKey: null,
            taskNumber: null,
          },
        }),
        '2026-03-12T09:00:00+09:00',
        '2026-03-12T09:30:00+09:00',
        false,
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: 'planner-1',
        payload: {
          allDay: false,
          start: '2026-03-12T09:00:00+09:00',
          end: '2026-03-12',
        },
      },
    });
  });

  it('preserves planner event all-day, start, and end resize payload behavior', () => {
    expect(
      getPlannerCalendarResizePolicy(
        event({
          sourceId: 'planner-1',
          sourceType: 'planner_event',
          allDay: true,
          start: '2026-03-12',
        }),
        '2026-03-15',
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: 'planner-1',
        payload: {
          allDay: true,
          start: '2026-03-12',
          end: '2026-03-15',
        },
      },
    });
  });

  it('keeps projected date-only planner events non-all-day on all-day resizes', () => {
    expect(
      getPlannerCalendarResizePolicy(
        event({
          sourceId: 'planner-1',
          sourceType: 'planner_event',
          allDay: true,
          start: '2026-03-12',
          metadata: {
            attendeeCount: null,
            location: null,
            plannerAllDay: false,
            plannerStartHasTime: false,
            plannerEndHasTime: false,
            status: null,
            taskListKey: null,
            taskNumber: null,
          },
        }),
        '2026-03-16',
      ),
    ).toEqual({
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: 'planner-1',
        payload: {
          allDay: false,
          start: '2026-03-12',
          end: '2026-03-15',
        },
      },
    });
  });

  it('rejects resize cases that should revert without API calls', () => {
    expect(
      getPlannerCalendarResizePolicy(
        event({ sourceType: 'pms_due' }),
        '2026-03-15',
      ),
    ).toEqual({
      status: 'reject',
      revert: true,
      reason: 'unsupportedResize',
    });
  });
});
