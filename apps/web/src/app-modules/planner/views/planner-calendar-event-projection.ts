import type { PlannerEvent } from '../api/planner-api';
import {
  CALENDAR_SOURCE_COLORS,
  type CalendarEvent,
} from '@/src/platform/calendar/calendar-types';

const PLANNER_CALENDAR_EVENT_PREFIX = 'planner-event-';

export function plannerCalendarEventId(eventId: string): string {
  return `${PLANNER_CALENDAR_EVENT_PREFIX}${eventId}`;
}

export function plannerEventToCalendarEvent(
  event: PlannerEvent,
): CalendarEvent {
  return {
    id: plannerCalendarEventId(event.id),
    title: event.title,
    start: event.calendarStart,
    end: event.calendarEnd,
    allDay: event.calendarAllDay,
    sourceType: 'planner_event',
    sourceId: event.id,
    color: CALENDAR_SOURCE_COLORS.planner_event,
    workspace: null,
    metadata: {
      plannerEventId: event.id,
      ownerId: event.ownerId,
      ownerName: event.ownerName || null,
      location: event.location || null,
      plannerAllDay: event.allDay,
      plannerStartHasTime: event.startHasTime,
      plannerEndHasTime: event.endHasTime,
      plannerTimeZone: event.timeZone,
    },
  };
}
