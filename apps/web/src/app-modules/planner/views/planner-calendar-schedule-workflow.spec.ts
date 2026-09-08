import { describe, expect, it, vi } from 'vitest';

import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  createPlannerCalendarScheduleWorkflow,
  type PlannerCalendarScheduleAdapters,
  type PlannerCalendarScheduleMessages,
} from './planner-calendar-schedule-workflow';

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

function messages(): PlannerCalendarScheduleMessages {
  return {
    meetingAllDayDisallowed: 'meeting all-day is not allowed',
    taskAllDayOnly: 'tasks must stay all-day',
    eventMoveFailed: 'event move failed',
    meetingMoveFailed: 'meeting move failed',
    taskScheduleMoveFailed: 'task schedule move failed',
  };
}

function adapters(
  overrides: Partial<PlannerCalendarScheduleAdapters> = {},
): PlannerCalendarScheduleAdapters {
  return {
    updatePlannerEvent: vi.fn().mockResolvedValue(null),
    updateMeeting: vi.fn().mockResolvedValue(null),
    updateTask: vi.fn().mockResolvedValue(null),
    ...overrides,
  };
}

describe('planner calendar schedule workflow', () => {
  it('reverts without policy errors when auth is missing', async () => {
    const scheduleAdapters = adapters();
    const revert = vi.fn();
    const setActionError = vi.fn();

    await createPlannerCalendarScheduleWorkflow({
      token: null,
      adapters: scheduleAdapters,
      messages: messages(),
      refresh: vi.fn(),
      setActionError,
    }).drop(
      event({ sourceType: 'meeting' }),
      '2026-03-12',
      '2026-03-13',
      true,
      revert,
    );

    expect(revert).toHaveBeenCalledOnce();
    expect(setActionError).not.toHaveBeenCalled();
    expect(scheduleAdapters.updateMeeting).not.toHaveBeenCalled();
  });

  it('rejects invalid drops after reverting first', async () => {
    const calls: string[] = [];
    const workflow = createPlannerCalendarScheduleWorkflow({
      token: 'token',
      adapters: adapters(),
      messages: messages(),
      refresh: vi.fn(),
      setActionError: (message) => calls.push(`error:${message}`),
    });

    await workflow.drop(
      event({ sourceType: 'meeting' }),
      '2026-03-12',
      '2026-03-13',
      true,
      () => calls.push('revert'),
    );

    expect(calls).toEqual(['revert', 'error:meeting all-day is not allowed']);
  });

  it('reverts unsupported resize without an error message', async () => {
    const scheduleAdapters = adapters();
    const revert = vi.fn();
    const setActionError = vi.fn();

    await createPlannerCalendarScheduleWorkflow({
      token: 'token',
      adapters: scheduleAdapters,
      messages: messages(),
      refresh: vi.fn(),
      setActionError,
    }).resize(event({ sourceType: 'pms_due' }), '2026-03-15', revert);

    expect(revert).toHaveBeenCalledOnce();
    expect(setActionError).not.toHaveBeenCalled();
    expect(scheduleAdapters.updateTask).not.toHaveBeenCalled();
  });

  it('runs planner event drop commands and refreshes on success', async () => {
    const scheduleAdapters = adapters();
    const refresh = vi.fn();

    await createPlannerCalendarScheduleWorkflow({
      token: 'token',
      adapters: scheduleAdapters,
      messages: messages(),
      refresh,
      setActionError: vi.fn(),
    }).drop(
      event({ sourceId: 'planner-1', sourceType: 'planner_event' }),
      '2026-03-12T09:00:00+09:00',
      '2026-03-12T10:00:00+09:00',
      false,
      vi.fn(),
    );

    expect(scheduleAdapters.updatePlannerEvent).toHaveBeenCalledWith(
      'token',
      'planner-1',
      {
        allDay: false,
        start: '2026-03-12T09:00:00+09:00',
        end: '2026-03-12T10:00:00+09:00',
      },
    );
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('runs meeting resize commands through the meeting adapter', async () => {
    const scheduleAdapters = adapters();

    await createPlannerCalendarScheduleWorkflow({
      token: 'token',
      adapters: scheduleAdapters,
      messages: messages(),
      refresh: vi.fn(),
      setActionError: vi.fn(),
    }).resize(
      event({ sourceId: 'meeting-1', sourceType: 'meeting' }),
      '2026-03-10T11:00:00+09:00',
      vi.fn(),
    );

    expect(scheduleAdapters.updateMeeting).toHaveBeenCalledWith(
      'token',
      'meeting-1',
      { end_at: '2026-03-10T11:00:00+09:00' },
    );
  });

  it('reverts and reports Error messages from failed commands', async () => {
    const revert = vi.fn();
    const setActionError = vi.fn();

    await createPlannerCalendarScheduleWorkflow({
      token: 'token',
      adapters: adapters({
        updateTask: vi.fn().mockRejectedValue(new Error('permission denied')),
      }),
      messages: messages(),
      refresh: vi.fn(),
      setActionError,
    }).drop(
      event({ sourceId: 'task-1', sourceType: 'pms_due' }),
      '2026-03-12',
      '2026-03-13',
      true,
      revert,
    );

    expect(revert).toHaveBeenCalledOnce();
    expect(setActionError).toHaveBeenCalledWith('permission denied');
  });

  it('uses command-specific fallback errors for non-Error failures', async () => {
    const setActionError = vi.fn();

    await createPlannerCalendarScheduleWorkflow({
      token: 'token',
      adapters: adapters({
        updateTask: vi.fn().mockRejectedValue('failed'),
      }),
      messages: messages(),
      refresh: vi.fn(),
      setActionError,
    }).drop(
      event({ sourceId: 'task-1', sourceType: 'pms_due' }),
      '2026-03-12',
      '2026-03-13',
      true,
      vi.fn(),
    );

    expect(setActionError).toHaveBeenCalledWith('task schedule move failed');
  });
});
