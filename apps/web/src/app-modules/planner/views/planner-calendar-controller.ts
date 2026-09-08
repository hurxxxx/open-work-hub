import type { UnifiedCalendarHandle } from '@/src/components/calendar/UnifiedCalendar';
import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  closePicker,
  pickDate,
  type PlannerCalendarSession,
  type PlannerCalendarSessionResult,
} from './planner-calendar-session';
import {
  addDays,
  buildInitialPlannerRange,
  type PlannerSurfaceMode,
  type PlannerViewMode,
  type TimelineRangeDays,
} from './planner-calendar-view-model';

export type PlannerCalendarPeriodDirection = 'previous' | 'next' | 'today';

export type PlannerCalendarCommand =
  | { type: 'none' }
  | { type: 'previousPeriod' }
  | { type: 'nextPeriod' }
  | { type: 'today' }
  | { type: 'gotoDate'; date: Date };

export interface PlannerCalendarControllerResult {
  session: PlannerCalendarSession;
  command: PlannerCalendarCommand;
}

export type PlannerCalendarEventClickAction =
  | { type: 'ignore' }
  | { type: 'openPlannerEvent'; eventId: string }
  | { type: 'previewMeeting'; meetingId: string }
  | {
      type: 'openTask';
      taskId: string;
      taskListId: string;
    }
  | { type: 'missingTaskList' };

export function buildPlannerSurfaceModeSearchParams(
  searchParams: URLSearchParams,
  mode: PlannerSurfaceMode,
): URLSearchParams {
  const nextParams = new URLSearchParams(searchParams);
  if (mode === 'timeline') {
    nextParams.set('view', 'timeline');
  } else {
    nextParams.delete('view');
  }
  return nextParams;
}

export function movePlannerVisiblePeriod(
  session: PlannerCalendarSession,
  args: {
    direction: PlannerCalendarPeriodDirection;
    viewMode: PlannerViewMode;
    surfaceMode: PlannerSurfaceMode;
    timelineRangeDays: TimelineRangeDays;
    now?: Date;
  },
): PlannerCalendarControllerResult {
  if (args.surfaceMode === 'timeline') {
    const currentDate =
      args.direction === 'today'
        ? (args.now ?? new Date())
        : addDays(
            session.calendarState.currentDate,
            args.direction === 'previous'
              ? -args.timelineRangeDays
              : args.timelineRangeDays,
          );
    return {
      session: {
        ...session,
        pickerOpen: false,
        calendarState: buildInitialPlannerRange(
          currentDate,
          args.viewMode,
          'timeline',
          args.timelineRangeDays,
        ),
      },
      command: { type: 'none' },
    };
  }

  if (args.direction === 'today') {
    return {
      session: closePicker(session),
      command: { type: 'today' },
    };
  }

  return {
    session,
    command:
      args.direction === 'previous'
        ? { type: 'previousPeriod' }
        : { type: 'nextPeriod' },
  };
}

export function pickPlannerDate(
  session: PlannerCalendarSession,
  args: {
    year: number;
    month: number;
    day: number;
    viewMode: PlannerViewMode;
    surfaceMode: PlannerSurfaceMode;
  },
): PlannerCalendarControllerResult {
  const result: PlannerCalendarSessionResult = pickDate(session, args);
  return {
    session: result.session,
    command: result.command.gotoDate
      ? { type: 'gotoDate', date: result.command.gotoDate }
      : { type: 'none' },
  };
}

export function runPlannerCalendarCommand(
  calendar: UnifiedCalendarHandle | null,
  command: PlannerCalendarCommand,
): void {
  if (command.type === 'previousPeriod') {
    calendar?.prev();
    return;
  }
  if (command.type === 'nextPeriod') {
    calendar?.next();
    return;
  }
  if (command.type === 'today') {
    calendar?.today();
    return;
  }
  if (command.type === 'gotoDate') {
    calendar?.gotoDate(command.date);
  }
}

export function resolvePlannerCalendarEventClick(
  event: CalendarEvent,
): PlannerCalendarEventClickAction {
  if (event.sourceType === 'planner_event') {
    return { type: 'openPlannerEvent', eventId: event.sourceId };
  }

  if (event.sourceType === 'meeting') {
    return {
      type: 'previewMeeting',
      meetingId: event.sourceId,
    };
  }

  const listId = event.metadata.taskListId;
  if (!listId) {
    return { type: 'missingTaskList' };
  }
  return {
    type: 'openTask',
    taskId: event.sourceId,
    taskListId: listId,
  };
}
