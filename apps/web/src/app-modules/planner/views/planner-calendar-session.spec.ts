import { describe, expect, it, vi } from 'vitest';

import {
  applySurfaceMode,
  chooseCalendarSelectionTarget,
  closePlannerEventModal,
  handleMeetingCreated,
  initializePlannerCalendarSession,
  openPlannerEventCreate,
  openPicker,
  pickDate,
  selectTimelineRangeDays,
} from './planner-calendar-session';

describe('planner calendar session', () => {
  it('rebuilds the visible range and closes the picker when switching to timeline', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 4, 26, 15, 30),
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });

    const nextSession = applySurfaceMode(
      {
        ...session,
        pickerOpen: true,
      },
      {
        viewMode: 'Month',
        surfaceMode: 'timeline',
      },
    );

    expect(nextSession.pickerOpen).toBe(false);
    expect(nextSession.calendarState).toEqual({
      currentDate: new Date(2026, 4, 26),
      rangeStart: '2026-05-24',
      rangeEnd: '2026-06-21',
    });
  });

  it('persists timeline range intent and recalculates the visible query range', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 4, 26),
      viewMode: 'Month',
      surfaceMode: 'timeline',
      timelineRangeDays: 28,
    });

    const result = selectTimelineRangeDays(session, {
      days: 56,
      viewMode: 'Month',
      surfaceMode: 'timeline',
    });

    expect(result.command.persistTimelineRangeDays).toBe(56);
    expect(result.session.timelineRangeDays).toBe(56);
    expect(result.session.calendarState).toMatchObject({
      rangeStart: '2026-05-24',
      rangeEnd: '2026-07-19',
    });
  });

  it('syncs the picker cursor to the current calendar date when opened', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 0, 3),
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });

    const nextSession = openPicker({
      ...session,
      calendarState: {
        currentDate: new Date(2026, 9, 14),
        rangeStart: '2026-09-27',
        rangeEnd: '2026-11-08',
      },
    });

    expect(nextSession.pickerOpen).toBe(true);
    expect(nextSession.pickerYear).toBe(2026);
    expect(nextSession.pickerMonth).toBe(9);
  });

  it('returns a calendar goto command for calendar date picker selections', () => {
    const session = openPicker(
      initializePlannerCalendarSession({
        today: new Date(2026, 4, 26),
        viewMode: 'Day',
        surfaceMode: 'calendar',
        timelineRangeDays: 28,
      }),
    );

    const result = pickDate(session, {
      year: 2026,
      month: 5,
      day: 18,
      viewMode: 'Day',
      surfaceMode: 'calendar',
    });

    expect(result.session.pickerOpen).toBe(false);
    expect(result.command.gotoDate).toEqual(new Date(2026, 5, 18));
    expect(result.session.calendarState).toBe(session.calendarState);
  });

  it('applies direct timeline range state for timeline date picker selections', () => {
    const session = openPicker(
      initializePlannerCalendarSession({
        today: new Date(2026, 4, 26),
        viewMode: 'Month',
        surfaceMode: 'timeline',
        timelineRangeDays: 14,
      }),
    );

    const result = pickDate(session, {
      year: 2026,
      month: 6,
      day: 15,
      viewMode: 'Month',
      surfaceMode: 'timeline',
    });

    expect(result.command.gotoDate).toBeUndefined();
    expect(result.session.pickerOpen).toBe(false);
    expect(result.session.calendarState).toEqual({
      currentDate: new Date(2026, 6, 15),
      rangeStart: '2026-07-12',
      rangeEnd: '2026-07-26',
    });
  });

  it('opens multi-day calendar selections as all-day planner events', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 4, 26),
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });
    const range = {
      start: new Date(2026, 6, 6),
      end: new Date(2026, 6, 10),
      allDay: true,
    };

    const choosing = chooseCalendarSelectionTarget(session, {
      selection: {
        range,
        anchor: { x: 12, y: 34 },
      },
    });
    const eventSession = chooseCalendarSelectionTarget(choosing, {
      target: 'event',
    });

    expect(choosing.creationChoice).toEqual({
      range,
      anchor: { x: 12, y: 34 },
    });
    expect(eventSession.creationChoice).toBeNull();
    expect(eventSession.plannerEventModalOpen).toBe(true);
    expect(eventSession.plannerEventId).toBeNull();
    expect(eventSession.plannerEventRange).toBe(range);
  });

  it('opens single-day all-day selections with the all-day mode off by default', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 4, 26),
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });

    const eventSession = openPlannerEventCreate(
      session,
      {
        start: new Date(2026, 6, 6),
        end: new Date(2026, 6, 7),
        allDay: true,
      },
      new Date(2026, 6, 1, 10, 12),
    );

    expect(eventSession.plannerEventRange).toEqual({
      start: new Date(2026, 6, 6, 11),
      end: new Date(2026, 6, 6, 12),
      allDay: false,
    });
  });

  it('opens new planner events with the all-day mode off by default', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 4, 26),
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });

    const eventSession = openPlannerEventCreate(
      session,
      undefined,
      new Date(2026, 6, 1, 10, 12),
    );

    expect(eventSession.plannerEventRange).toEqual({
      start: new Date(2026, 4, 26, 11),
      end: new Date(2026, 4, 26, 12),
      allDay: false,
    });
  });

  it('branches empty calendar selection to meeting creation state', () => {
    const session = initializePlannerCalendarSession({
      today: new Date(2026, 4, 26),
      viewMode: 'Month',
      surfaceMode: 'calendar',
      timelineRangeDays: 28,
    });
    const range = {
      start: new Date(2026, 5, 1),
      end: new Date(2026, 5, 2),
      allDay: true,
    };

    const choosing = chooseCalendarSelectionTarget(session, {
      selection: { range, anchor: null },
    });
    const meetingSession = chooseCalendarSelectionTarget(choosing, {
      target: 'meeting',
    });

    expect(meetingSession.creationChoice).toBeNull();
    expect(meetingSession.meetingCreateOpen).toBe(true);
    expect(meetingSession.meetingCreateRange).toBe(range);
  });

  it('clears event query intent when closing the planner event modal', () => {
    const session = {
      ...initializePlannerCalendarSession({
        today: new Date(2026, 4, 26),
        viewMode: 'Month',
        surfaceMode: 'calendar',
        timelineRangeDays: 28,
      }),
      plannerEventModalOpen: true,
      plannerEventId: 'event-1',
    };

    const result = closePlannerEventModal(session, {
      hasEventQueryIntent: true,
    });

    expect(result.session.plannerEventModalOpen).toBe(false);
    expect(result.session.plannerEventId).toBeNull();
    expect(result.command.clearEventQueryIntent).toBe(true);
  });

  it('closes meeting creation, opens preview, and marks refresh needed after meeting creation', () => {
    const session = {
      ...initializePlannerCalendarSession({
        today: new Date(2026, 4, 26),
        viewMode: 'Month',
        surfaceMode: 'calendar',
        timelineRangeDays: 28,
      }),
      meetingCreateOpen: true,
      meetingCreateRange: {
        start: new Date(2026, 5, 1),
        end: new Date(2026, 5, 2),
        allDay: true,
      },
    };

    const result = handleMeetingCreated(session, 'meeting-1');

    expect(result.session.meetingCreateOpen).toBe(false);
    expect(result.session.meetingCreateRange).toBeNull();
    expect(result.session.previewMeetingId).toBe('meeting-1');
    expect(result.command.refreshNeeded).toBe(true);
  });
});
