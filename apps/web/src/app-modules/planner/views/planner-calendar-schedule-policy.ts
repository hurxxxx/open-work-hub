import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

export type PlannerCalendarScheduleRejectReason =
  | 'meetingAllDayDisallowed'
  | 'taskAllDayOnly'
  | 'unsupportedResize';

export type PlannerCalendarScheduleCommand =
  | {
      type: 'updatePlannerEvent';
      sourceId: string;
      payload: { allDay: boolean; start: string; end: string };
    }
  | {
      type: 'updateMeeting';
      sourceId: string;

      payload: { start_at?: string; end_at: string };
    }
  | {
      type: 'updateTask';
      sourceId: string;

      payload: { due_date?: string | null; start_date?: string | null };
    };

export type PlannerCalendarSchedulePolicyResult =
  | { status: 'command'; command: PlannerCalendarScheduleCommand }
  | {
      status: 'reject';
      revert: true;
      reason: PlannerCalendarScheduleRejectReason;
    };

interface PlannerEventScheduleMetadata {
  plannerAllDay?: boolean | null;
  plannerStartHasTime?: boolean | null;
  plannerEndHasTime?: boolean | null;
}

/** Convert FullCalendar's exclusive all-day end into an inclusive date. */
export function inclusiveDateFromExclusiveAllDayEnd(endIso: string): string {
  const [year, month, day] = endIso.slice(0, 10).split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function getPlannerEventScheduleMetadata(
  event: CalendarEvent,
): PlannerEventScheduleMetadata {
  return event.metadata as CalendarEvent['metadata'] &
    PlannerEventScheduleMetadata;
}

function plannerEventAllDayForPayload(
  event: CalendarEvent,
  newAllDay: boolean,
): boolean {
  const metadata = getPlannerEventScheduleMetadata(event);
  if (newAllDay && event.allDay && metadata.plannerAllDay === false) {
    return false;
  }
  return newAllDay;
}

function plannerEventDateTimeForPayload(
  valueIso: string,
  hasTime: boolean | null | undefined,
): string {
  return hasTime === false ? valueIso.slice(0, 10) : valueIso;
}

function plannerEventEndForPayload(
  event: CalendarEvent,
  newEndIso: string,
  newAllDay: boolean,
  payloadAllDay: boolean,
): string {
  const metadata = getPlannerEventScheduleMetadata(event);
  const endIso =
    newAllDay && !payloadAllDay
      ? inclusiveDateFromExclusiveAllDayEnd(newEndIso)
      : newEndIso;
  return plannerEventDateTimeForPayload(endIso, metadata.plannerEndHasTime);
}

export function getPlannerCalendarDropPolicy(
  event: CalendarEvent,
  newStartIso: string,
  newEndIso: string,
  newAllDay: boolean,
): PlannerCalendarSchedulePolicyResult {
  if (event.sourceType === 'planner_event') {
    const metadata = getPlannerEventScheduleMetadata(event);
    const payloadAllDay = plannerEventAllDayForPayload(event, newAllDay);
    return {
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: event.sourceId,
        payload: {
          allDay: payloadAllDay,
          start: payloadAllDay
            ? newStartIso
            : plannerEventDateTimeForPayload(
                newStartIso,
                metadata.plannerStartHasTime,
              ),
          end: payloadAllDay
            ? newEndIso
            : plannerEventEndForPayload(
                event,
                newEndIso,
                newAllDay,
                payloadAllDay,
              ),
        },
      },
    };
  }

  if (event.sourceType === 'meeting') {
    if (newAllDay) {
      return {
        status: 'reject',
        revert: true,
        reason: 'meetingAllDayDisallowed',
      };
    }

    return {
      status: 'command',
      command: {
        type: 'updateMeeting',
        sourceId: event.sourceId,
        payload: {
          start_at: newStartIso,
          end_at: newEndIso,
        },
      },
    };
  }

  if (!newAllDay) {
    return { status: 'reject', revert: true, reason: 'taskAllDayOnly' };
  }

  const payload: { due_date?: string | null; start_date?: string | null } = {
    due_date: inclusiveDateFromExclusiveAllDayEnd(newEndIso),
  };
  if (event.sourceType === 'pms_block') {
    payload.start_date = newStartIso.slice(0, 10);
  }

  return {
    status: 'command',
    command: {
      type: 'updateTask',
      sourceId: event.sourceId,
      payload,
    },
  };
}

export function getPlannerCalendarResizePolicy(
  event: CalendarEvent,
  newEndIso: string,
): PlannerCalendarSchedulePolicyResult {
  if (event.sourceType === 'meeting') {
    return {
      status: 'command',
      command: {
        type: 'updateMeeting',
        sourceId: event.sourceId,
        payload: { end_at: newEndIso },
      },
    };
  }

  if (event.sourceType === 'planner_event') {
    const metadata = getPlannerEventScheduleMetadata(event);
    const payloadAllDay = plannerEventAllDayForPayload(event, event.allDay);
    return {
      status: 'command',
      command: {
        type: 'updatePlannerEvent',
        sourceId: event.sourceId,
        payload: {
          allDay: payloadAllDay,
          start: payloadAllDay
            ? event.start
            : plannerEventDateTimeForPayload(
                event.start,
                metadata.plannerStartHasTime,
              ),
          end: payloadAllDay
            ? newEndIso
            : plannerEventEndForPayload(
                event,
                newEndIso,
                event.allDay,
                payloadAllDay,
              ),
        },
      },
    };
  }

  if (event.sourceType === 'pms_block') {
    return {
      status: 'command',
      command: {
        type: 'updateTask',
        sourceId: event.sourceId,
        payload: {
          due_date: inclusiveDateFromExclusiveAllDayEnd(newEndIso),
        },
      },
    };
  }

  return { status: 'reject', revert: true, reason: 'unsupportedResize' };
}
