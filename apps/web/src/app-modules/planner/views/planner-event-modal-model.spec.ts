import { describe, expect, it, vi } from 'vitest';

import { formatNativeDateTimeInputValue } from '@/src/platform/time/native-date-input';
import type { PlannerEvent } from '../api/planner-api';

import {
  buildDraftFromRange,
  buildPlannerEventSavePayload,
  canSave,
  initialPlannerEventModalState,
  plannerEventModalReducer,
  plannerEventModalSessionKey,
  plannerEventToDraft,
} from './planner-event-modal-model';

function event(overrides: Partial<PlannerEvent> = {}): PlannerEvent {
  return {
    id: 'event-1',
    ownerId: 'owner-1',
    ownerName: 'Owner',
    title: 'Planning',
    description: 'Discuss roadmap',
    location: 'Room 1',
    timeZone: 'Asia/Seoul',
    allDay: false,
    startHasTime: true,
    endHasTime: true,
    start: '2026-03-10T00:00:00.000Z',
    end: '2026-03-10T01:00:00.000Z',
    calendarStart: '2026-03-10T00:00:00.000Z',
    calendarEnd: '2026-03-10T01:00:00.000Z',
    calendarAllDay: false,
    createdAt: '2026-03-01T00:00:00.000Z',
    updatedAt: '2026-03-01T00:00:00.000Z',
    ...overrides,
  };
}

describe('planner event modal model', () => {
  it('builds create drafts from initial ranges', () => {
    expect(
      buildDraftFromRange({
        allDay: true,
        start: new Date(2026, 2, 10),
        end: new Date(2026, 2, 13),
      }),
    ).toEqual({
      allDay: true,
      startDateValue: '2026-03-10',
      startTimeValue: '',
      endDateValue: '2026-03-12',
      endTimeValue: '',
    });

    expect(
      buildDraftFromRange({
        allDay: false,
        start: new Date(2026, 2, 10, 9, 30),
        end: new Date(2026, 2, 10, 11, 0),
      }),
    ).toEqual({
      allDay: false,
      startDateValue: '2026-03-10',
      startTimeValue: '09:30',
      endDateValue: '2026-03-10',
      endTimeValue: '11:00',
    });
  });

  it('uses a rounded next-hour default timed draft', () => {
    expect(buildDraftFromRange(null, new Date(2026, 2, 10, 8, 45, 30))).toEqual(
      {
        allDay: false,
        startDateValue: '2026-03-10',
        startTimeValue: '09:00',
        endDateValue: '2026-03-10',
        endTimeValue: '10:00',
      },
    );
  });

  it('converts loaded events into editable drafts', () => {
    expect(
      plannerEventToDraft(
        event({
          allDay: true,
          start: '2026-03-10',
          end: '2026-03-13',
        }),
      ),
    ).toEqual({
      allDay: true,
      startDateValue: '2026-03-10',
      startTimeValue: '',
      endDateValue: '2026-03-12',
      endTimeValue: '',
    });

    const timed = event({
      allDay: false,
      start: '2026-03-10T09:30:00+09:00',
      end: '2026-03-10T11:00:00+09:00',
    });
    const timedStart = formatNativeDateTimeInputValue(new Date(timed.start));
    const timedEnd = formatNativeDateTimeInputValue(new Date(timed.end));

    expect(plannerEventToDraft(timed)).toEqual({
      allDay: false,
      startDateValue: timedStart.slice(0, 10),
      startTimeValue: timedStart.slice(11, 16),
      endDateValue: timedEnd.slice(0, 10),
      endTimeValue: timedEnd.slice(11, 16),
    });

    expect(
      plannerEventToDraft(
        event({
          allDay: false,
          start: '2026-03-10T09:30:00+09:00',
          end: '2026-03-10',
          startHasTime: true,
          endHasTime: false,
        }),
      ),
    ).toMatchObject({
      allDay: false,
      startTimeValue: timedStart.slice(11, 16),
      endDateValue: '2026-03-10',
      endTimeValue: '',
    });

    expect(
      plannerEventToDraft(
        event({
          allDay: false,
          start: '2026-03-10',
          end: '2026-03-10',
          startHasTime: false,
          endHasTime: false,
        }),
      ),
    ).toEqual({
      allDay: false,
      startDateValue: '2026-03-10',
      startTimeValue: '',
      endDateValue: '2026-03-10',
      endTimeValue: '',
    });
  });

  it('builds stable modal session keys', () => {
    expect(plannerEventModalSessionKey('event-1', null)).toBe('edit:event-1');
    expect(plannerEventModalSessionKey(null, null)).toBe('create:default');
    expect(
      plannerEventModalSessionKey(null, {
        allDay: false,
        start: new Date('2026-03-10T00:00:00.000Z'),
        end: new Date('2026-03-10T01:00:00.000Z'),
      }),
    ).toBe('create:timed:2026-03-10T00:00:00.000Z:2026-03-10T01:00:00.000Z');
  });

  it('loads event data through the reducer', () => {
    const state = plannerEventModalReducer(
      initialPlannerEventModalState(null, new Date(2026, 2, 10, 8)),
      {
        type: 'loadSuccess',
        event: event({
          title: 'Loaded title',
          description: 'Loaded description',
          location: 'Loaded location',
          allDay: true,
          start: '2026-03-10',
          end: '2026-03-11',
        }),
      },
    );

    expect(state).toMatchObject({
      loading: false,
      title: 'Loaded title',
      description: 'Loaded description',
      location: 'Loaded location',
      allDay: true,
      startDateValue: '2026-03-10',
      startTimeValue: '',
      endDateValue: '2026-03-10',
      endTimeValue: '',
    });
  });

  it('keeps all-day toggle date policy in the reducer', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 2, 10, 10, 12));
    try {
      const timed = {
        ...initialPlannerEventModalState(null, new Date(2026, 2, 10, 8)),
        startDateValue: '2026-03-10',
        startTimeValue: '23:00',
        endDateValue: '2026-03-11',
        endTimeValue: '01:00',
      };

      const allDay = plannerEventModalReducer(timed, {
        type: 'setAllDay',
        allDay: true,
      });
      expect(allDay).toMatchObject({
        allDay: true,
        startDateValue: '2026-03-10',
        startTimeValue: '',
        endDateValue: '2026-03-11',
        endTimeValue: '',
      });

      expect(
        plannerEventModalReducer(allDay, {
          type: 'setAllDay',
          allDay: false,
        }),
      ).toMatchObject({
        allDay: false,
        startDateValue: '2026-03-10',
        startTimeValue: '11:00',
        endDateValue: '2026-03-11',
        endTimeValue: '12:00',
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('validates required title and range ordering', () => {
    const base = {
      ...initialPlannerEventModalState(null, new Date(2026, 2, 10, 8)),
      title: '  Planning  ',
    };

    expect(canSave({ ...base, title: '   ' })).toBe(false);
    expect(
      canSave({
        ...base,
        allDay: false,
        startDateValue: '2026-03-10',
        startTimeValue: '10:00',
        endDateValue: '2026-03-10',
        endTimeValue: '10:00',
      }),
    ).toBe(false);
    expect(
      canSave({
        ...base,
        allDay: true,
        startDateValue: '2026-03-10',
        endDateValue: '2026-03-10',
      }),
    ).toBe(true);
    expect(
      canSave({
        ...base,
        allDay: false,
        startDateValue: '2026-03-10',
        startTimeValue: '10:00',
        endDateValue: '2026-03-10',
        endTimeValue: '',
      }),
    ).toBe(true);
    expect(
      canSave({
        ...base,
        allDay: false,
        startDateValue: '2026-03-10',
        startTimeValue: '',
        endDateValue: '2026-03-10',
        endTimeValue: '10:00',
      }),
    ).toBe(true);
    expect(
      canSave({
        ...base,
        allDay: false,
        startDateValue: '2026-03-10',
        startTimeValue: '',
        endDateValue: '2026-03-10',
        endTimeValue: '',
      }),
    ).toBe(true);
  });

  it('builds trimmed save payloads with API all-day end exclusivity', () => {
    expect(
      buildPlannerEventSavePayload({
        ...initialPlannerEventModalState(null, new Date(2026, 2, 10, 8)),
        title: '  Planning  ',
        description: '  Details  ',
        location: '  Room 1  ',
        allDay: true,
        startDateValue: '2026-03-10',
        endDateValue: '2026-03-12',
      }),
    ).toEqual({
      title: 'Planning',
      description: 'Details',
      location: 'Room 1',
      allDay: true,
      start: '2026-03-10',
      end: '2026-03-13',
    });

    const timedState = {
      ...initialPlannerEventModalState(null, new Date(2026, 2, 10, 8)),
      title: 'Planning',
      allDay: false,
      startDateValue: '2026-03-10',
      startTimeValue: '09:30',
      endDateValue: '2026-03-10',
      endTimeValue: '11:00',
    };

    expect(buildPlannerEventSavePayload(timedState)).toMatchObject({
      allDay: false,
      start: new Date('2026-03-10T09:30').toISOString(),
      end: new Date('2026-03-10T11:00').toISOString(),
    });

    expect(
      buildPlannerEventSavePayload({
        ...timedState,
        endTimeValue: '',
      }),
    ).toMatchObject({
      allDay: false,
      start: new Date('2026-03-10T09:30').toISOString(),
      end: '2026-03-10',
    });

    expect(
      buildPlannerEventSavePayload({
        ...timedState,
        startTimeValue: '',
      }),
    ).toMatchObject({
      allDay: false,
      start: '2026-03-10',
      end: new Date('2026-03-10T11:00').toISOString(),
    });

    expect(
      buildPlannerEventSavePayload({
        ...timedState,
        startTimeValue: '',
        endTimeValue: '',
      }),
    ).toMatchObject({
      allDay: false,
      start: '2026-03-10',
      end: '2026-03-10',
    });
  });
});
