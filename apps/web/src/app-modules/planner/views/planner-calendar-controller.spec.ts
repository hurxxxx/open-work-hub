import { describe, expect, it, vi } from 'vitest';

import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  buildPlannerSurfaceModeSearchParams,
  movePlannerVisiblePeriod,
  pickPlannerDate,
  resolvePlannerCalendarEventClick,
  runPlannerCalendarCommand,
} from './planner-calendar-controller';
import { initializePlannerCalendarSession } from './planner-calendar-session';

function baseSession() {
  return initializePlannerCalendarSession({
    today: new Date(2026, 4, 26),
    viewMode: 'Month',
    surfaceMode: 'calendar',
    timelineRangeDays: 28,
  });
}

function calendarEvent(overrides: Partial<CalendarEvent>): CalendarEvent {
  return {
    id: 'event-1',
    title: 'Event',
    start: '2026-05-26T09:00:00+09:00',
    end: '2026-05-26T10:00:00+09:00',
    allDay: false,
    sourceType: 'planner_event',
    sourceId: 'source-1',
    color: '#14b8a6',
    workspace: { id: 'workspace-1', slug: 'hq', name: 'HQ' },
    metadata: {},
    ...overrides,
  } as CalendarEvent;
}

describe('planner calendar controller', () => {
  it('builds surface mode query params without dropping unrelated params', () => {
    const params = new URLSearchParams('event=event-1&view=timeline');

    expect(
      buildPlannerSurfaceModeSearchParams(params, 'calendar').toString(),
    ).toBe('event=event-1');
    expect(
      buildPlannerSurfaceModeSearchParams(params, 'timeline').toString(),
    ).toBe('event=event-1&view=timeline');
  });

  it('moves timeline periods in session state without imperative calendar commands', () => {
    const session = {
      ...baseSession(),
      pickerOpen: true,
      calendarState: {
        currentDate: new Date(2026, 4, 26),
        rangeStart: '2026-05-24',
        rangeEnd: '2026-06-21',
      },
    };

    const previous = movePlannerVisiblePeriod(session, {
      direction: 'previous',
      viewMode: 'Month',
      surfaceMode: 'timeline',
      timelineRangeDays: 28,
    });
    const today = movePlannerVisiblePeriod(session, {
      direction: 'today',
      viewMode: 'Month',
      surfaceMode: 'timeline',
      timelineRangeDays: 28,
      now: new Date(2026, 6, 15),
    });

    expect(previous.command).toEqual({ type: 'none' });
    expect(previous.session.pickerOpen).toBe(false);
    expect(previous.session.calendarState).toEqual({
      currentDate: new Date(2026, 3, 28),
      rangeStart: '2026-04-26',
      rangeEnd: '2026-05-24',
    });
    expect(today.session.calendarState).toEqual({
      currentDate: new Date(2026, 6, 15),
      rangeStart: '2026-07-12',
      rangeEnd: '2026-08-09',
    });
  });

  it('returns imperative commands for calendar periods and date picks', () => {
    const session = {
      ...baseSession(),
      pickerOpen: true,
    };

    const previous = movePlannerVisiblePeriod(session, {
      direction: 'previous',
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });
    const today = movePlannerVisiblePeriod(session, {
      direction: 'today',
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });
    const picked = pickPlannerDate(session, {
      year: 2026,
      month: 6,
      day: 15,
      viewMode: 'Month',
      surfaceMode: 'calendar',
    });

    expect(previous.command).toEqual({ type: 'previousPeriod' });
    expect(previous.session).toBe(session);
    expect(today.command).toEqual({ type: 'today' });
    expect(today.session.pickerOpen).toBe(false);
    expect(picked.command).toEqual({
      type: 'gotoDate',
      date: new Date(2026, 6, 15),
    });
  });

  it('runs imperative calendar commands against the calendar handle', () => {
    const calendar = {
      prev: vi.fn(),
      next: vi.fn(),
      today: vi.fn(),
      gotoDate: vi.fn(),
      changeView: vi.fn(),
      getCurrentView: vi.fn(),
    };
    const date = new Date(2026, 6, 15);

    runPlannerCalendarCommand(calendar, { type: 'previousPeriod' });
    runPlannerCalendarCommand(calendar, { type: 'nextPeriod' });
    runPlannerCalendarCommand(calendar, { type: 'today' });
    runPlannerCalendarCommand(calendar, { type: 'gotoDate', date });
    runPlannerCalendarCommand(calendar, { type: 'none' });

    expect(calendar.prev).toHaveBeenCalledTimes(1);
    expect(calendar.next).toHaveBeenCalledTimes(1);
    expect(calendar.today).toHaveBeenCalledTimes(1);
    expect(calendar.gotoDate).toHaveBeenCalledWith(date);
  });

  it('resolves event clicks to modal, task panel, and error actions', () => {
    expect(
      resolvePlannerCalendarEventClick(
        calendarEvent({ sourceType: 'planner_event', sourceId: 'planner-1' }),
      ),
    ).toEqual({ type: 'openPlannerEvent', eventId: 'planner-1' });

    expect(
      resolvePlannerCalendarEventClick(
        calendarEvent({ sourceType: 'meeting', sourceId: 'meeting-1' }),
      ),
    ).toEqual({
      type: 'previewMeeting',
      meetingId: 'meeting-1',
    });

    expect(
      resolvePlannerCalendarEventClick(
        calendarEvent({
          sourceType: 'pms_due',
          sourceId: 'task 1',
          metadata: { taskListId: 'list-1' },
        }),
      ),
    ).toEqual({
      type: 'openTask',
      taskId: 'task 1',
      taskListId: 'list-1',
    });

    expect(
      resolvePlannerCalendarEventClick(
        calendarEvent({ sourceType: 'pms_due', metadata: {} }),
      ),
    ).toEqual({ type: 'missingTaskList' });
  });
});
