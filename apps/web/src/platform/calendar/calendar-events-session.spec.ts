import { describe, expect, it } from 'vitest';

import { ALL_CALENDAR_SOURCES, type CalendarEvent } from './calendar-types';
import {
  calendarEventsReducer,
  getCalendarEventSourcesKey,
  INITIAL_CALENDAR_EVENTS_STATE,
} from './calendar-events-session';

function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 'event-1',
    title: 'Planning',
    start: '2026-05-31T09:00:00Z',
    end: '2026-05-31T10:00:00Z',
    allDay: false,
    sourceType: 'meeting',
    sourceId: 'meeting-1',
    color: '#3b82f6',
    metadata: { meetingId: 'meeting-1', attendeeCount: 3 },
    ...overrides,
  };
}

describe('calendar events session', () => {
  it('moves through loading, loaded, failed, and idle states', () => {
    const loading = calendarEventsReducer(
      {
        ...INITIAL_CALENDAR_EVENTS_STATE,
        error: 'Previous',
      },
      { type: 'loading' },
    );
    const loaded = calendarEventsReducer(loading, {
      type: 'loaded',
      events: [event()],
    });
    const failed = calendarEventsReducer(loaded, {
      type: 'failed',
      message: 'Network failed',
    });
    const idle = calendarEventsReducer(failed, { type: 'idle' });

    expect(loading).toMatchObject({
      loading: true,
      error: null,
    });
    expect(loaded).toMatchObject({
      events: [event()],
      loading: false,
      error: null,
      hasUsableSnapshot: true,
    });
    expect(failed).toMatchObject({
      events: [event()],
      loading: false,
      error: 'Network failed',
      hasUsableSnapshot: true,
    });
    expect(idle).toMatchObject({
      events: [],
      loading: false,
      error: null,
      hasUsableSnapshot: false,
    });
  });

  it('upserts and removes events without waiting for a reload', () => {
    const initial = {
      ...INITIAL_CALENDAR_EVENTS_STATE,
      events: [event()],
    };
    const updated = event({ title: 'Updated planning' });
    const replaced = calendarEventsReducer(initial, {
      type: 'upsert',
      event: updated,
    });
    const appended = calendarEventsReducer(replaced, {
      type: 'upsert',
      event: event({ id: 'event-2', sourceId: 'meeting-2' }),
    });
    const removed = calendarEventsReducer(appended, {
      type: 'remove',
      eventId: 'event-1',
    });

    expect(replaced.events).toEqual([updated]);
    expect(appended.events.map((item) => item.id)).toEqual([
      'event-1',
      'event-2',
    ]);
    expect(removed.events.map((item) => item.id)).toEqual(['event-2']);
    expect(removed.hasUsableSnapshot).toBe(true);
  });

  it('increments refresh token without changing loaded data', () => {
    const state = {
      ...INITIAL_CALENDAR_EVENTS_STATE,
      events: [event()],
      refreshToken: 3,
    };

    expect(calendarEventsReducer(state, { type: 'refresh' })).toEqual({
      ...state,
      refreshToken: 4,
    });
  });

  it('builds a stable source key regardless of input order', () => {
    expect(
      getCalendarEventSourcesKey(['pms_due', 'meeting', 'planner_event']),
    ).toBe('meeting,planner_event,pms_due');
    expect(
      getCalendarEventSourcesKey(['planner_event', 'pms_due', 'meeting']),
    ).toBe('meeting,planner_event,pms_due');
    expect(getCalendarEventSourcesKey()).toBe(
      Array.from(ALL_CALENDAR_SOURCES).sort().join(','),
    );
  });
});
