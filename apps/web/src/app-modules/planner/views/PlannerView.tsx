import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { LazyMotion, domAnimation, m } from 'motion/react';
import {
  Activity,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/src/lib/utils';
import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useCalendarEvents } from '@/src/platform/calendar/use-calendar-events';
import type {
  CalendarEvent,
  CalendarSourceFilter,
} from '@/src/platform/calendar/calendar-types';
import { dispatchFloatingPmsOpen } from '@/src/platform/personal-widgets/floating-panel-events';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  getAllEligibleWorkspaces,
  type EligibleWorkspace,
} from '@/src/platform/workspaces/workspaces-api';
import { updateMeeting } from '@/src/app-modules/meeting/public-api';
import { updateTask } from '@/src/app-modules/pms/public-api';
import { updatePlannerEvent } from '../api/planner-api';
import {
  UnifiedCalendar,
  type UnifiedCalendarHandle,
  type UnifiedCalendarView,
} from '@/src/components/calendar/UnifiedCalendar';
import { MeetingCreateModal } from '@/src/app-modules/meeting';
import { MeetingPreviewModal } from './calendar/MeetingPreviewModal';
import { PlannerEventModal } from './PlannerEventModal';
import { PlannerEventChoicePopover } from './PlannerEventChoicePopover';
import { PlannerTimelineView } from './PlannerTimelineView';
import { createPlannerCalendarScheduleWorkflow } from './planner-calendar-schedule-workflow';
import {
  buildPlannerSurfaceModeSearchParams,
  movePlannerVisiblePeriod,
  pickPlannerDate,
  resolvePlannerCalendarEventClick,
  runPlannerCalendarCommand,
} from './planner-calendar-controller';
import {
  TIMELINE_RANGE_OPTIONS,
  buildPlannerDatePickerGrid,
  formatPlannerHeading,
  getPlannerDateFormatter,
  persistTimelineRangeDays,
  readTimelineRangeDays,
  type PlannerSurfaceMode,
  type PlannerViewMode,
  type TimelineRangeDays,
} from './planner-calendar-view-model';
import {
  applyCalendarDatesSet,
  applySurfaceMode,
  chooseCalendarSelectionTarget,
  closeCreateMenu,
  closeMeetingCreate,
  closePicker,
  closePlannerEventModal as closePlannerEventModalSession,
  closePreviewMeeting,
  handleMeetingCreated as handleMeetingCreatedSession,
  initializePlannerCalendarSession,
  movePickerMonth,
  openMeetingCreate,
  openPicker as openPlannerPicker,
  openPlannerEventCreate as openPlannerEventCreateSession,
  openPlannerEventEdit as openPlannerEventEditSession,
  selectTimelineRangeDays as selectTimelineRangeDaysSession,
  toggleCreateMenu,
  type PlannerEventDraftRange,
} from './planner-calendar-session';

const SURFACE_MODE_LABEL_KEYS: Record<PlannerSurfaceMode, string> = {
  calendar: 'planner.surfaces.calendar',
  timeline: 'planner.surfaces.timeline',
};

const TIMELINE_RANGE_LABEL_KEYS: Record<TimelineRangeDays, string> = {
  14: 'planner.timeline.rangeOptions.twoWeeks',
  28: 'planner.timeline.rangeOptions.fourWeeks',
  56: 'planner.timeline.rangeOptions.eightWeeks',
};

const VIEW_MODE_LABEL_KEYS: Record<PlannerViewMode, string> = {
  Month: 'planner.viewModes.month',
  Week: 'planner.viewModes.week',
  Day: 'planner.viewModes.day',
  Agenda: 'planner.viewModes.agenda',
};

const VIEW_MODE_TO_FC: Record<PlannerViewMode, UnifiedCalendarView> = {
  Month: 'dayGridMonth',
  Week: 'timeGridWeek',
  Day: 'timeGridDay',
  Agenda: 'listWeek',
};

const PLANNER_SOURCES = [
  'meeting',
  'pms_due',
  'pms_block',
  'planner_event',
] as const satisfies CalendarSourceFilter;

interface DatePickerPopoverProps {
  pickerYear: number;
  pickerMonth: number;
  viewYear: number;
  viewMonth: number;
  selectedDate: number;
  today: Date;
  onPrev: () => void;
  onNext: () => void;
  onPickToday: () => void;
  onPickDate: (year: number, month: number, day: number) => void;
}

function DatePickerPopover({
  pickerYear,
  pickerMonth,
  viewYear,
  viewMonth,
  selectedDate,
  today,
  onPrev,
  onNext,
  onPickToday,
  onPickDate,
}: DatePickerPopoverProps) {
  const { i18n, t } = useTranslation('apps');
  const cells = useMemo(
    () =>
      buildPlannerDatePickerGrid({
        pickerYear,
        pickerMonth,
        viewYear,
        viewMonth,
        selectedDate,
        today,
        getHolidayNames: getKoreanHolidayNames,
      }),
    [pickerMonth, pickerYear, selectedDate, today, viewMonth, viewYear],
  );

  return (
    <dialog
      open
      aria-label={t('planner.datePicker.chooseDate')}
      className="absolute right-0 top-full z-40 m-0 mt-2 w-72 rounded-lg border border-app-border bg-app-surface p-3 shadow-xl"
    >
      <div className="flex items-center justify-between mb-2">
        <button
          type="button"
          onClick={onPrev}
          aria-label={t('planner.datePicker.previousMonth')}
          className="flex size-7 items-center justify-center rounded text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink"
        >
          <ChevronLeft size={14} />
        </button>
        <div className="app-text-control text-app-ink tabular-nums">
          {getPlannerDateFormatter(i18n.language, 'monthYear').format(
            new Date(pickerYear, pickerMonth, 1),
          )}
        </div>
        <button
          type="button"
          onClick={onNext}
          aria-label={t('planner.datePicker.nextMonth')}
          className="flex size-7 items-center justify-center rounded text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="grid grid-cols-7 mb-1">
        {Array.from({ length: 7 }, (_, i) => (
          <div
            key={`weekday-${i}`}
            className={cn(
              'app-text-overline py-1 text-center',
              // Sun-start: index 0 is Sunday (red).
              i === 0 ? 'text-app-danger' : 'text-app-ink/55',
            )}
          >
            {getPlannerDateFormatter(i18n.language, 'weekdayNarrow').format(
              new Date(2026, 1, i + 1),
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((cell) => {
          if (cell.kind === 'blank') {
            return <div key={cell.key} className="h-8" />;
          }
          return (
            <button
              type="button"
              key={cell.key}
              onClick={() => onPickDate(pickerYear, pickerMonth, cell.day)}
              title={
                cell.holidayNames ? cell.holidayNames.join(', ') : undefined
              }
              className={cn(
                'app-text-control-sm flex h-8 items-center justify-center rounded transition-colors tabular-nums',
                cell.isSelected
                  ? 'bg-app-accent text-app-accent-fg font-semibold'
                  : cell.isToday
                    ? 'border border-app-accent text-app-accent font-semibold hover:bg-app-surface-hover'
                    : cell.holidayNames || cell.isSunday
                      ? 'text-app-danger hover:bg-app-surface-hover'
                      : 'text-app-ink hover:bg-app-surface-hover',
              )}
            >
              {cell.day}
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex justify-between border-t border-app-border pt-2">
        <button
          type="button"
          onClick={onPickToday}
          className="app-text-control-sm rounded px-2 py-1 text-app-accent hover:bg-app-surface-hover"
        >
          {t('planner.today')}
        </button>
      </div>
    </dialog>
  );
}

export const PlannerView = () => <>{usePlannerViewElement()}</>;

function usePlannerViewElement(): ReactNode {
  const { t, i18n } = useTranslation('apps');
  const today = new Date();
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [meetingWorkspaceSlug, setMeetingWorkspaceSlug] = useState<
    string | null
  >(null);
  const [meetingWorkspaces, setMeetingWorkspaces] = useState<
    EligibleWorkspace[]
  >([]);
  const [meetingWorkspacesLoading, setMeetingWorkspacesLoading] =
    useState(false);
  const [meetingWorkspaceError, setMeetingWorkspaceError] = useState<
    string | null
  >(null);
  const meetingEnabled = Boolean(meetingWorkspaceSlug);
  const [previewMeetingWorkspaceSlug, setPreviewMeetingWorkspaceSlug] =
    useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const surfaceMode: PlannerSurfaceMode =
    searchParams.get('view') === 'timeline' ? 'timeline' : 'calendar';
  const [timelineRangeDays, setTimelineRangeDaysState] =
    useState<TimelineRangeDays>(() => readTimelineRangeDays());
  const [viewMode, setViewMode] = useState<PlannerViewMode>('Month');
  const [session, setSession] = useState(() =>
    initializePlannerCalendarSession({
      today,
      viewMode: 'Month',
      surfaceMode,
      timelineRangeDays,
    }),
  );
  const calendarState = session.calendarState;
  const requestedPlannerEventId = searchParams.get('event');
  const plannerEventModalOpen =
    session.plannerEventModalOpen || Boolean(requestedPlannerEventId);
  const plannerEventId = requestedPlannerEventId ?? session.plannerEventId;
  const plannerEventRange = requestedPlannerEventId
    ? null
    : session.plannerEventRange;

  useEffect(() => {
    if (!token) {
      setMeetingWorkspaces([]);
      setMeetingWorkspaceSlug(null);
      return;
    }
    let cancelled = false;
    setMeetingWorkspacesLoading(true);
    setMeetingWorkspaceError(null);
    getAllEligibleWorkspaces(token, 'meeting')
      .then((workspaces) => {
        if (cancelled) return;
        setMeetingWorkspaces(workspaces);
        setMeetingWorkspaceSlug((current) => {
          if (workspaces.some((workspace) => workspace.slug === current)) {
            return current;
          }
          return workspaces.length === 1 ? workspaces[0].slug : null;
        });
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setMeetingWorkspaces([]);
        setMeetingWorkspaceSlug(null);
        setMeetingWorkspaceError(
          caught instanceof Error ? caught.message : String(caught),
        );
      })
      .finally(() => {
        if (!cancelled) setMeetingWorkspacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const calendarRef = useRef<UnifiedCalendarHandle | null>(null);
  const previousSurfaceMode = useRef(surfaceMode);
  const previousTimelineRangeDays = useRef(timelineRangeDays);

  const { events, loading, error, refresh } = useCalendarEvents({
    from: calendarState.rangeStart,
    to: calendarState.rangeEnd,
    sources: PLANNER_SOURCES,
    useMockData: false,
  });
  const calendarEvents = useMemo(
    () =>
      events.map((event) =>
        event.workspace
          ? { ...event, title: `[${event.workspace.name}] ${event.title}` }
          : event,
      ),
    [events],
  );

  // Mini date-picker popover. The picker has its own (year, month) cursor so
  // the user can browse without committing — the main view only updates when
  // they actually click a day.
  const pickerRef = useRef<HTMLDivElement>(null);
  const createMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!session.pickerOpen) return;
    function onMouseDown(event: MouseEvent) {
      if (
        pickerRef.current &&
        !pickerRef.current.contains(event.target as Node)
      ) {
        setSession(closePicker);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setSession(closePicker);
    }
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [session.pickerOpen]);

  useEffect(() => {
    if (!session.createMenuOpen) return;
    function onMouseDown(event: MouseEvent) {
      if (
        createMenuRef.current &&
        !createMenuRef.current.contains(event.target as Node)
      ) {
        setSession(closeCreateMenu);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setSession(closeCreateMenu);
    }
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [session.createMenuOpen]);

  const applySurfaceModeRangeChange = useCallback(() => {
    previousSurfaceMode.current = surfaceMode;
    previousTimelineRangeDays.current = timelineRangeDays;
    setSession((current) =>
      applySurfaceMode(current, {
        viewMode,
        surfaceMode,
      }),
    );
  }, [surfaceMode, timelineRangeDays, viewMode]);

  useEffect(() => {
    if (
      previousSurfaceMode.current === surfaceMode &&
      previousTimelineRangeDays.current === timelineRangeDays
    ) {
      return;
    }
    queueMicrotask(applySurfaceModeRangeChange);
  }, [applySurfaceModeRangeChange, surfaceMode, timelineRangeDays]);

  // When the popover opens, sync its cursor to whatever the main view is showing.
  const openPicker = () => {
    setSession(openPlannerPicker);
  };

  const setMode = (mode: PlannerViewMode) => {
    setViewMode(mode);
    calendarRef.current?.changeView(VIEW_MODE_TO_FC[mode]);
  };

  const setSurfaceMode = (mode: PlannerSurfaceMode) => {
    if (mode === surfaceMode) {
      return;
    }
    setSearchParams(buildPlannerSurfaceModeSearchParams(searchParams, mode), {
      replace: true,
    });
  };

  const selectTimelineRangeDays = (days: TimelineRangeDays) => {
    setTimelineRangeDaysState(days);
    const result = selectTimelineRangeDaysSession(session, {
      days,
      viewMode,
      surfaceMode,
    });
    if (result.command.persistTimelineRangeDays) {
      persistTimelineRangeDays(result.command.persistTimelineRangeDays);
    }
    setSession(result.session);
  };

  const goToPreviousPeriod = () => {
    const result = movePlannerVisiblePeriod(session, {
      direction: 'previous',
      viewMode,
      surfaceMode,
      timelineRangeDays,
    });
    setSession(result.session);
    runPlannerCalendarCommand(calendarRef.current, result.command);
  };

  const goToNextPeriod = () => {
    const result = movePlannerVisiblePeriod(session, {
      direction: 'next',
      viewMode,
      surfaceMode,
      timelineRangeDays,
    });
    setSession(result.session);
    runPlannerCalendarCommand(calendarRef.current, result.command);
  };

  const goToToday = () => {
    const result = movePlannerVisiblePeriod(session, {
      direction: 'today',
      viewMode,
      surfaceMode,
      timelineRangeDays,
    });
    setSession(result.session);
    runPlannerCalendarCommand(calendarRef.current, result.command);
  };
  const openPlannerEventCreate = useCallback(
    (range?: PlannerEventDraftRange) => {
      setSession((current) => openPlannerEventCreateSession(current, range));
    },
    [],
  );
  const openPlannerEventEdit = useCallback((eventId: string) => {
    setSession((current) => openPlannerEventEditSession(current, eventId));
  }, []);
  const openMeetingCreateFromPlannerEvent = useCallback(() => {
    if (!meetingEnabled) {
      return;
    }
    setSession((current) => openMeetingCreate(current));
  }, [meetingEnabled]);
  const closePlannerEventModal = useCallback(() => {
    const hasEventQueryIntent = Boolean(searchParams.get('event'));
    setSession((current) => {
      const result = closePlannerEventModalSession(current, {
        hasEventQueryIntent,
      });
      return result.session;
    });
    if (hasEventQueryIntent) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('event');
      setSearchParams(nextParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const [actionError, setActionError] = useState<string | null>(null);
  useEffect(() => {
    if (!actionError) return;
    const id = window.setTimeout(() => setActionError(null), 4000);
    return () => window.clearTimeout(id);
  }, [actionError]);

  useEffect(() => {
    if (meetingEnabled) {
      return;
    }
    setSession((current) => {
      if (!current.meetingCreateOpen && !current.creationChoice) {
        return current;
      }
      return {
        ...current,
        creationChoice: null,
        meetingCreateOpen: false,
        meetingCreateRange: null,
      };
    });
  }, [meetingEnabled]);

  useEffect(() => {
    function handlePlannerCreateEvent() {
      openPlannerEventCreate();
    }
    function handlePlannerCreateMeeting() {
      if (meetingEnabled) {
        openMeetingCreateFromPlannerEvent();
      }
    }
    window.addEventListener('planner:create-event', handlePlannerCreateEvent);
    window.addEventListener(
      'planner:create-meeting',
      handlePlannerCreateMeeting,
    );
    return () => {
      window.removeEventListener(
        'planner:create-event',
        handlePlannerCreateEvent,
      );
      window.removeEventListener(
        'planner:create-meeting',
        handlePlannerCreateMeeting,
      );
    };
  }, [
    meetingEnabled,
    openMeetingCreateFromPlannerEvent,
    openPlannerEventCreate,
  ]);

  const handleDatesSet = useCallback(
    (nextState: {
      view: UnifiedCalendarView;
      currentDate: Date;
      rangeStart: Date;
      rangeEnd: Date;
    }) => {
      const result = applyCalendarDatesSet(session, nextState);
      setViewMode((currentMode) =>
        currentMode === result.viewMode ? currentMode : result.viewMode,
      );
      setSession(result.session);
    },
    [session],
  );

  const handleEventClick = (event: CalendarEvent) => {
    const action = resolvePlannerCalendarEventClick(event);
    if (action.type === 'openPlannerEvent') {
      openPlannerEventEdit(action.eventId);
    } else if (action.type === 'previewMeeting') {
      setPreviewMeetingWorkspaceSlug(action.workspaceSlug);
      setSession((current) => ({
        ...current,
        previewMeetingId: action.meetingId,
      }));
    } else if (action.type === 'openTask') {
      dispatchFloatingPmsOpen({
        mode: 'openTask',
        taskId: action.taskId,
        taskListId: action.taskListId,
        workspaceSlug: action.workspaceSlug,
      });
    } else if (action.type === 'missingTaskList') {
      setActionError(t('planner.taskLocationMissing'));
    }
  };

  const scheduleWorkflow = createPlannerCalendarScheduleWorkflow({
    token,
    adapters: {
      updatePlannerEvent,
      updateMeeting,
      updateTask,
    },
    messages: {
      meetingAllDayDisallowed: t('planner.meetingAllDayDisallowed'),
      taskAllDayOnly: t('planner.taskAllDayOnly'),
      eventMoveFailed: t('planner.eventMoveFailed'),
      meetingMoveFailed: t('planner.meetingMoveFailed'),
      taskScheduleMoveFailed: t('planner.taskScheduleMoveFailed'),
    },
    refresh,
    setActionError,
  });

  const handleEventDrop = async (
    event: CalendarEvent,
    newStartIso: string,
    newEndIso: string,
    newAllDay: boolean,
    revert: () => void,
  ) => {
    await scheduleWorkflow.drop(
      event,
      newStartIso,
      newEndIso,
      newAllDay,
      revert,
    );
  };

  const handleEventResize = async (
    event: CalendarEvent,
    newEndIso: string,
    revert: () => void,
  ) => {
    await scheduleWorkflow.resize(event, newEndIso, revert);
  };
  const handleDateSelect = useCallback(
    (range: {
      start: Date;
      end: Date;
      allDay: boolean;
      anchor: { x: number; y: number } | null;
    }) => {
      if (!meetingEnabled) {
        openPlannerEventCreate({
          start: range.start,
          end: range.end,
          allDay: range.allDay,
        });
        return;
      }
      setSession((current) =>
        chooseCalendarSelectionTarget(current, {
          selection: {
            range: { start: range.start, end: range.end, allDay: range.allDay },
            anchor: range.anchor,
          },
        }),
      );
    },
    [meetingEnabled, openPlannerEventCreate],
  );
  const handleChoicePickEvent = useCallback(() => {
    setSession((current) =>
      chooseCalendarSelectionTarget(current, { target: 'event' }),
    );
  }, []);
  const handleChoicePickMeeting = useCallback(() => {
    if (!meetingEnabled) {
      setSession((current) =>
        chooseCalendarSelectionTarget(current, { target: 'dismiss' }),
      );
      return;
    }
    setSession((current) =>
      chooseCalendarSelectionTarget(current, { target: 'meeting' }),
    );
  }, [meetingEnabled]);
  const handleChoiceDismiss = useCallback(() => {
    setSession((current) =>
      chooseCalendarSelectionTarget(current, { target: 'dismiss' }),
    );
  }, []);
  const handlePlannerEventSaved = useCallback(() => {
    closePlannerEventModal();
    refresh();
  }, [closePlannerEventModal, refresh]);
  const handlePlannerEventDeleted = useCallback(() => {
    closePlannerEventModal();
    refresh();
  }, [closePlannerEventModal, refresh]);
  const handleMeetingCreated = useCallback(
    (meetingId: string) => {
      setPreviewMeetingWorkspaceSlug(meetingWorkspaceSlug);
      setSession((current) => {
        const result = handleMeetingCreatedSession(current, meetingId);
        return result.session;
      });
      refresh();
    },
    [meetingWorkspaceSlug, refresh],
  );

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="relative flex h-full flex-col gap-y-6 p-8"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="app-text-title-lg text-app-ink">
              {t('planner.planner')}
            </h1>
            <div className="flex items-center rounded-md border border-app-border bg-app-surface-sidebar p-1">
              {(['calendar', 'timeline'] as const).map((mode) => {
                const Icon = mode === 'calendar' ? CalendarDays : Activity;
                return (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSurfaceMode(mode)}
                    aria-pressed={surfaceMode === mode}
                    className={cn(
                      'app-text-control-sm flex items-center gap-1.5 rounded px-3 py-1 transition-all',
                      surfaceMode === mode
                        ? 'bg-app-surface-hover text-app-ink shadow-sm'
                        : 'text-app-ink/55 hover:text-app-ink',
                    )}
                  >
                    <Icon size={14} />
                    <span>{t(SURFACE_MODE_LABEL_KEYS[mode])}</span>
                  </button>
                );
              })}
            </div>
            {surfaceMode === 'calendar' ? (
              <div className="flex items-center bg-app-surface-sidebar border border-app-border rounded-md p-1">
                {(['Month', 'Week', 'Day', 'Agenda'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setMode(mode)}
                    className={cn(
                      'app-text-control-sm rounded px-3 py-1 transition-all',
                      viewMode === mode
                        ? 'bg-app-surface-hover text-app-ink shadow-sm'
                        : 'text-app-ink/55 hover:text-app-ink',
                    )}
                  >
                    {t(VIEW_MODE_LABEL_KEYS[mode])}
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex items-center bg-app-surface-sidebar border border-app-border rounded-md p-1">
                {TIMELINE_RANGE_OPTIONS.map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => selectTimelineRangeDays(days)}
                    aria-pressed={timelineRangeDays === days}
                    className={cn(
                      'app-text-control-sm rounded px-3 py-1 transition-all',
                      timelineRangeDays === days
                        ? 'bg-app-surface-hover text-app-ink shadow-sm'
                        : 'text-app-ink/55 hover:text-app-ink',
                    )}
                  >
                    {t(TIMELINE_RANGE_LABEL_KEYS[days])}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={goToToday}
              className="app-text-control-sm rounded-md border border-app-border px-3 py-1 text-app-ink/55 transition-colors hover:text-app-ink"
            >
              {t('planner.today')}
            </button>
          </div>
          <div className="flex items-center gap-3">
            <div ref={pickerRef} className="relative flex items-center gap-1">
              <button
                type="button"
                onClick={goToPreviousPeriod}
                aria-label={t('planner.previousPeriod')}
                className="flex size-8 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                type="button"
                onClick={() =>
                  session.pickerOpen ? setSession(closePicker) : openPicker()
                }
                aria-haspopup="dialog"
                aria-expanded={session.pickerOpen}
                className="app-text-control flex h-8 min-w-[180px] items-center justify-center rounded-md text-app-ink tabular-nums transition-colors hover:bg-app-surface-hover"
              >
                {formatPlannerHeading(
                  viewMode,
                  calendarState.currentDate,
                  i18n.language,
                  surfaceMode,
                  calendarState.rangeStart,
                  calendarState.rangeEnd,
                )}
              </button>
              <button
                type="button"
                onClick={goToNextPeriod}
                aria-label={t('planner.nextPeriod')}
                className="flex size-8 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              >
                <ChevronRight size={16} />
              </button>
              {session.pickerOpen ? (
                <DatePickerPopover
                  pickerYear={session.pickerYear}
                  pickerMonth={session.pickerMonth}
                  viewYear={calendarState.currentDate.getFullYear()}
                  viewMonth={calendarState.currentDate.getMonth()}
                  selectedDate={calendarState.currentDate.getDate()}
                  today={today}
                  onPrev={() =>
                    setSession((current) => movePickerMonth(current, -1))
                  }
                  onNext={() =>
                    setSession((current) => movePickerMonth(current, 1))
                  }
                  onPickToday={() => {
                    goToToday();
                    setSession(closePicker);
                  }}
                  onPickDate={(year, month, day) => {
                    const result = pickPlannerDate(session, {
                      year,
                      month,
                      day,
                      viewMode,
                      surfaceMode,
                    });
                    setSession(result.session);
                    runPlannerCalendarCommand(
                      calendarRef.current,
                      result.command,
                    );
                  }}
                />
              ) : null}
            </div>
            <div ref={createMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setSession(toggleCreateMenu)}
                className="app-text-control flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
              >
                <Plus size={16} />
                <span>{t('common:actions.add')}</span>
              </button>
              {session.createMenuOpen ? (
                <div className="absolute right-0 top-full z-30 mt-2 w-48 rounded-lg border border-app-border bg-app-surface py-1 shadow-xl">
                  <div className="app-text-overline px-3 pt-1.5 pb-1 text-app-ink/45">
                    {t('planner.create')}
                  </div>
                  <button
                    type="button"
                    onClick={() => openPlannerEventCreate()}
                    className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                  >
                    <Plus size={14} className="text-app-ink/45" />
                    <span>{t('planner.event')}</span>
                  </button>
                  {meetingWorkspaces.length > 0 || meetingWorkspacesLoading ? (
                    <>
                      {meetingWorkspaces.length > 1 ? (
                        <label className="block border-t border-app-border px-3 py-2">
                          <span className="app-text-overline mb-1 block text-app-ink/45">
                            {t('common:labels.workspace')}
                          </span>
                          <select
                            aria-label={t('common:labels.workspace')}
                            className="app-field-input w-full"
                            onChange={(event) =>
                              setMeetingWorkspaceSlug(
                                event.target.value || null,
                              )
                            }
                            value={meetingWorkspaceSlug ?? ''}
                          >
                            <option value="">
                              {t('planner.chooseMeetingWorkspace')}
                            </option>
                            {meetingWorkspaces.map((workspace) => (
                              <option key={workspace.id} value={workspace.slug}>
                                {workspace.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      <button
                        type="button"
                        disabled={!meetingEnabled || meetingWorkspacesLoading}
                        onClick={() =>
                          setSession((current) => openMeetingCreate(current))
                        }
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Plus size={14} className="text-app-ink/45" />
                        <span>{t('planner.meeting')}</span>
                      </button>
                    </>
                  ) : null}
                  {meetingWorkspaceError ? (
                    <p className="app-text-caption border-t border-app-border px-3 py-2 text-app-danger">
                      {meetingWorkspaceError}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {actionError ? (
          <div
            role="alert"
            className="rounded-md border border-app-danger/40 bg-app-danger/10 px-4 py-2 app-text-caption text-app-danger"
          >
            {actionError}
          </div>
        ) : null}

        <div className="flex-1 card p-0 overflow-hidden flex flex-col relative">
          {error ? (
            <div className="flex-1 flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <p className="text-app-danger app-text-body">{error}</p>
                <p className="text-app-ink/55 app-text-caption">
                  {t('planner.loadRetry')}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex-1 relative">
              {loading ? (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-bg/40 pointer-events-none">
                  <div className="text-app-ink/55 app-text-caption">
                    {t('common:feedback.loading')}
                  </div>
                </div>
              ) : null}
              {surfaceMode === 'timeline' ? (
                <PlannerTimelineView
                  events={events}
                  rangeStart={calendarState.rangeStart}
                  rangeEnd={calendarState.rangeEnd}
                  locale={i18n.language}
                  timeZone={timeZone}
                  onEventClick={handleEventClick}
                />
              ) : (
                <UnifiedCalendar
                  ref={calendarRef}
                  events={calendarEvents}
                  initialView={VIEW_MODE_TO_FC[viewMode]}
                  initialDate={calendarState.currentDate}
                  onDatesSet={handleDatesSet}
                  onDateSelect={handleDateSelect}
                  onEventClick={handleEventClick}
                  onEventDrop={handleEventDrop}
                  onEventResize={handleEventResize}
                  timeZone={timeZone}
                />
              )}
            </div>
          )}
        </div>

        {session.previewMeetingId ? (
          <MeetingPreviewModal
            meetingId={session.previewMeetingId}
            workspaceSlug={previewMeetingWorkspaceSlug ?? undefined}
            onClose={() => {
              setPreviewMeetingWorkspaceSlug(null);
              setSession(closePreviewMeeting);
            }}
            onChanged={refresh}
          />
        ) : null}
        {meetingEnabled ? (
          <MeetingCreateModal
            isOpen={session.meetingCreateOpen && Boolean(meetingWorkspaceSlug)}
            onClose={() => setSession(closeMeetingCreate)}
            onCreated={handleMeetingCreated}
            workspaceSlug={meetingWorkspaceSlug ?? ''}
            initialRange={session.meetingCreateRange}
          />
        ) : null}
        {meetingEnabled && session.creationChoice ? (
          <PlannerEventChoicePopover
            anchor={session.creationChoice.anchor}
            onPickEvent={handleChoicePickEvent}
            onPickMeeting={handleChoicePickMeeting}
            onDismiss={handleChoiceDismiss}
          />
        ) : null}
        <PlannerEventModal
          isOpen={plannerEventModalOpen}
          onClose={closePlannerEventModal}
          eventId={plannerEventId}
          initialRange={plannerEventRange}
          onSaved={handlePlannerEventSaved}
          onDeleted={handlePlannerEventDeleted}
        />
      </m.div>
    </LazyMotion>
  );
}
