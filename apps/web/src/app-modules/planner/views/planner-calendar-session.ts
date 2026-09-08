import type { UnifiedCalendarView } from '@/src/components/calendar/UnifiedCalendar';
import {
  buildInitialPlannerRange,
  formatLocalYmd,
  startOfLocalDay,
  type PlannerSurfaceMode,
  type PlannerViewMode,
  type TimelineRangeDays,
} from './planner-calendar-view-model';
import {
  copyDateWithTime,
  defaultTimedRange,
  defaultTimedRangeForDate,
} from './planner-event-default-time';

export interface PlannerEventDraftRange {
  start: Date;
  end: Date;
  allDay: boolean;
}

export interface PlannerCalendarRangeState {
  currentDate: Date;
  rangeStart: string;
  rangeEnd: string;
}

export interface PlannerCreationChoice {
  range: PlannerEventDraftRange;
  anchor: { x: number; y: number } | null;
}

export interface PlannerCalendarSession {
  calendarState: PlannerCalendarRangeState;
  timelineRangeDays: TimelineRangeDays;
  pickerOpen: boolean;
  pickerYear: number;
  pickerMonth: number;
  createMenuOpen: boolean;
  plannerEventModalOpen: boolean;
  plannerEventId: string | null;
  plannerEventRange: PlannerEventDraftRange | null;
  meetingCreateOpen: boolean;
  meetingCreateRange: PlannerEventDraftRange | null;
  creationChoice: PlannerCreationChoice | null;
  previewMeetingId: string | null;
}

export interface PlannerCalendarSessionCommand {
  gotoDate?: Date;
  persistTimelineRangeDays?: TimelineRangeDays;
  clearEventQueryIntent?: boolean;
  refreshNeeded?: boolean;
}

export interface PlannerCalendarSessionResult {
  session: PlannerCalendarSession;
  command: PlannerCalendarSessionCommand;
}

const FC_VIEW_TO_MODE: Record<UnifiedCalendarView, PlannerViewMode> = {
  dayGridMonth: 'Month',
  timeGridWeek: 'Week',
  timeGridDay: 'Day',
  listWeek: 'Agenda',
};

function buildDefaultPlannerEventRange(
  currentDate: Date,
  now = new Date(),
): PlannerEventDraftRange {
  const { start, end } = defaultTimedRangeForDate(currentDate, now);
  return { start, end, allDay: false };
}

function buildPlannerEventRangeFromSelection(
  range: PlannerEventDraftRange,
  now = new Date(),
): PlannerEventDraftRange {
  if (!range.allDay) {
    return range;
  }
  const defaultRange = defaultTimedRange(now);
  const selectedEndDate = new Date(
    range.end.getFullYear(),
    range.end.getMonth(),
    range.end.getDate(),
  );
  selectedEndDate.setDate(selectedEndDate.getDate() - 1);
  const selectedStartDate = new Date(
    range.start.getFullYear(),
    range.start.getMonth(),
    range.start.getDate(),
  );
  if (selectedEndDate > selectedStartDate) {
    return range;
  }
  const start = copyDateWithTime(range.start, defaultRange.start);
  const selectedEnd = copyDateWithTime(selectedEndDate, defaultRange.end);
  const end =
    selectedEnd > start
      ? selectedEnd
      : new Date(start.getTime() + 60 * 60 * 1000);
  return { start, end, allDay: false };
}

export function initializePlannerCalendarSession(args: {
  today: Date;
  viewMode: PlannerViewMode;
  surfaceMode: PlannerSurfaceMode;
  timelineRangeDays: TimelineRangeDays;
}): PlannerCalendarSession {
  return {
    calendarState: buildInitialPlannerRange(
      args.today,
      args.viewMode,
      args.surfaceMode,
      args.timelineRangeDays,
    ),
    timelineRangeDays: args.timelineRangeDays,
    pickerOpen: false,
    pickerYear: args.today.getFullYear(),
    pickerMonth: args.today.getMonth(),
    createMenuOpen: false,
    plannerEventModalOpen: false,
    plannerEventId: null,
    plannerEventRange: null,
    meetingCreateOpen: false,
    meetingCreateRange: null,
    creationChoice: null,
    previewMeetingId: null,
  };
}

export function applySurfaceMode(
  session: PlannerCalendarSession,
  args: {
    viewMode: PlannerViewMode;
    surfaceMode: PlannerSurfaceMode;
  },
): PlannerCalendarSession {
  return {
    ...session,
    pickerOpen: false,
    calendarState: buildInitialPlannerRange(
      session.calendarState.currentDate,
      args.viewMode,
      args.surfaceMode,
      session.timelineRangeDays,
    ),
  };
}

export function selectTimelineRangeDays(
  session: PlannerCalendarSession,
  args: {
    days: TimelineRangeDays;
    viewMode: PlannerViewMode;
    surfaceMode: PlannerSurfaceMode;
  },
): PlannerCalendarSessionResult {
  const nextSession = {
    ...session,
    timelineRangeDays: args.days,
    calendarState:
      args.surfaceMode === 'timeline'
        ? buildInitialPlannerRange(
            session.calendarState.currentDate,
            args.viewMode,
            'timeline',
            args.days,
          )
        : session.calendarState,
  };

  return {
    session: nextSession,
    command: { persistTimelineRangeDays: args.days },
  };
}

export function openPicker(
  session: PlannerCalendarSession,
): PlannerCalendarSession {
  return {
    ...session,
    pickerYear: session.calendarState.currentDate.getFullYear(),
    pickerMonth: session.calendarState.currentDate.getMonth(),
    pickerOpen: true,
  };
}

export function pickDate(
  session: PlannerCalendarSession,
  args: {
    year: number;
    month: number;
    day: number;
    viewMode: PlannerViewMode;
    surfaceMode: PlannerSurfaceMode;
  },
): PlannerCalendarSessionResult {
  const pickedDate = new Date(args.year, args.month, args.day);
  if (args.surfaceMode === 'timeline') {
    return {
      session: {
        ...session,
        pickerOpen: false,
        calendarState: buildInitialPlannerRange(
          pickedDate,
          args.viewMode,
          'timeline',
          session.timelineRangeDays,
        ),
      },
      command: {},
    };
  }

  return {
    session: {
      ...session,
      pickerOpen: false,
    },
    command: { gotoDate: pickedDate },
  };
}

export function applyCalendarDatesSet(
  session: PlannerCalendarSession,
  nextState: {
    view: UnifiedCalendarView;
    currentDate: Date;
    rangeStart: Date;
    rangeEnd: Date;
  },
): { session: PlannerCalendarSession; viewMode: PlannerViewMode } {
  const nextMode = FC_VIEW_TO_MODE[nextState.view];
  const nextCurrentDate = startOfLocalDay(nextState.currentDate);
  const nextRangeStart = formatLocalYmd(nextState.rangeStart);
  const nextRangeEnd = formatLocalYmd(nextState.rangeEnd);

  if (
    session.calendarState.currentDate.getTime() === nextCurrentDate.getTime() &&
    session.calendarState.rangeStart === nextRangeStart &&
    session.calendarState.rangeEnd === nextRangeEnd
  ) {
    return { session, viewMode: nextMode };
  }

  return {
    session: {
      ...session,
      calendarState: {
        currentDate: nextCurrentDate,
        rangeStart: nextRangeStart,
        rangeEnd: nextRangeEnd,
      },
    },
    viewMode: nextMode,
  };
}

export function openPlannerEventCreate(
  session: PlannerCalendarSession,
  range?: PlannerEventDraftRange,
  now = new Date(),
): PlannerCalendarSession {
  return {
    ...session,
    plannerEventId: null,
    plannerEventRange: range
      ? buildPlannerEventRangeFromSelection(range, now)
      : buildDefaultPlannerEventRange(session.calendarState.currentDate, now),
    plannerEventModalOpen: true,
    createMenuOpen: false,
  };
}

export function openPlannerEventEdit(
  session: PlannerCalendarSession,
  eventId: string,
): PlannerCalendarSession {
  return {
    ...session,
    plannerEventId: eventId,
    plannerEventRange: null,
    plannerEventModalOpen: true,
  };
}

export function chooseCalendarSelectionTarget(
  session: PlannerCalendarSession,
  args:
    | {
        selection: PlannerCreationChoice;
        target?: undefined;
      }
    | {
        target: 'event' | 'meeting' | 'dismiss';
      },
): PlannerCalendarSession {
  if ('selection' in args) {
    return {
      ...session,
      creationChoice: args.selection,
    };
  }

  if (!session.creationChoice || args.target === 'dismiss') {
    return {
      ...session,
      creationChoice: null,
    };
  }

  if (args.target === 'event') {
    return openPlannerEventCreate(
      {
        ...session,
        creationChoice: null,
      },
      session.creationChoice.range,
    );
  }

  return {
    ...session,
    meetingCreateRange: session.creationChoice.range,
    meetingCreateOpen: true,
    creationChoice: null,
  };
}

export function handleMeetingCreated(
  session: PlannerCalendarSession,
  meetingId: string,
): PlannerCalendarSessionResult {
  return {
    session: {
      ...session,
      meetingCreateOpen: false,
      meetingCreateRange: null,
      previewMeetingId: meetingId,
    },
    command: { refreshNeeded: true },
  };
}

export function closePlannerEventModal(
  session: PlannerCalendarSession,
  args: { hasEventQueryIntent: boolean },
): PlannerCalendarSessionResult {
  return {
    session: {
      ...session,
      plannerEventModalOpen: false,
      plannerEventId: null,
      plannerEventRange: null,
    },
    command: {
      clearEventQueryIntent: args.hasEventQueryIntent,
    },
  };
}

export function openMeetingCreate(
  session: PlannerCalendarSession,
  range: PlannerEventDraftRange | null = null,
): PlannerCalendarSession {
  return {
    ...session,
    createMenuOpen: false,
    meetingCreateRange: range,
    meetingCreateOpen: true,
  };
}

export function closeMeetingCreate(
  session: PlannerCalendarSession,
): PlannerCalendarSession {
  return {
    ...session,
    meetingCreateOpen: false,
    meetingCreateRange: null,
  };
}

export function closePreviewMeeting(
  session: PlannerCalendarSession,
): PlannerCalendarSession {
  return {
    ...session,
    previewMeetingId: null,
  };
}

export function toggleCreateMenu(
  session: PlannerCalendarSession,
): PlannerCalendarSession {
  return {
    ...session,
    createMenuOpen: !session.createMenuOpen,
  };
}

export function closeCreateMenu(
  session: PlannerCalendarSession,
): PlannerCalendarSession {
  if (!session.createMenuOpen) return session;
  return {
    ...session,
    createMenuOpen: false,
  };
}

export function closePicker(
  session: PlannerCalendarSession,
): PlannerCalendarSession {
  if (!session.pickerOpen) return session;
  return {
    ...session,
    pickerOpen: false,
  };
}

export function movePickerMonth(
  session: PlannerCalendarSession,
  monthDelta: number,
): PlannerCalendarSession {
  const next = new Date(
    session.pickerYear,
    session.pickerMonth + monthDelta,
    1,
  );
  return {
    ...session,
    pickerYear: next.getFullYear(),
    pickerMonth: next.getMonth(),
  };
}
