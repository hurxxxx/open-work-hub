import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'motion/react';
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { useCalendarEvents } from '@/src/domains/calendar/use-calendar-events';
import type { CalendarEvent } from '@/src/domains/calendar/calendar-types';
import { updateMeeting } from '@/src/domains/meeting/meeting-api';
import { updateIssue } from '@/src/domains/pms/pms-api';
import { updatePlannerEvent } from '@/src/domains/planner/planner-api';
import {
  UnifiedCalendar,
  type UnifiedCalendarHandle,
  type UnifiedCalendarView,
} from '@/src/components/calendar/UnifiedCalendar';
import { MeetingPreviewModal } from '@/src/components/calendar/MeetingPreviewModal';
import { MeetingCreateModal } from '@/src/components/views/MeetingView/MeetingCreateModal';
import { PlannerEventModal } from '@/src/components/views/PlannerEventModal';
import { PlannerEventChoicePopover } from '@/src/components/views/PlannerEventChoicePopover';

const MONTH_NAMES_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PICKER_DAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

type PlannerViewMode = 'Month' | 'Week' | 'Day' | 'Agenda';

const VIEW_MODE_TO_FC: Record<PlannerViewMode, UnifiedCalendarView> = {
  Month: 'dayGridMonth',
  Week: 'timeGridWeek',
  Day: 'timeGridDay',
  Agenda: 'listWeek',
};

const FC_VIEW_TO_MODE: Record<UnifiedCalendarView, PlannerViewMode> = {
  dayGridMonth: 'Month',
  timeGridWeek: 'Week',
  timeGridDay: 'Day',
  listWeek: 'Agenda',
};

/** Subtract one day from a "YYYY-MM-DD" string. Used to convert FullCalendar's
 *  exclusive all-day end (next day 00:00) into the stored inclusive due_date. */
function decrementYmd(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function formatLocalYmd(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

function startOfWeek(date: Date): Date {
  return addDays(startOfLocalDay(date), -startOfLocalDay(date).getDay());
}

function buildInitialPlannerRange(
  currentDate: Date,
  viewMode: PlannerViewMode,
): { currentDate: Date; rangeStart: string; rangeEnd: string } {
  const current = startOfLocalDay(currentDate);
  if (viewMode === 'Month') {
    const monthStart = new Date(current.getFullYear(), current.getMonth(), 1);
    const rangeStart = startOfWeek(monthStart);
    const rangeEnd = addDays(rangeStart, 42);
    return {
      currentDate: current,
      rangeStart: formatLocalYmd(rangeStart),
      rangeEnd: formatLocalYmd(rangeEnd),
    };
  }
  if (viewMode === 'Day') {
    return {
      currentDate: current,
      rangeStart: formatLocalYmd(current),
      rangeEnd: formatLocalYmd(addDays(current, 1)),
    };
  }
  const rangeStart = startOfWeek(current);
  return {
    currentDate: current,
    rangeStart: formatLocalYmd(rangeStart),
    rangeEnd: formatLocalYmd(addDays(rangeStart, 7)),
  };
}

function formatPlannerHeading(viewMode: PlannerViewMode, currentDate: Date): string {
  if (viewMode === 'Day') {
    return `${MONTH_NAMES_LONG[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;
  }
  return `${MONTH_NAMES_LONG[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
}

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
  // 6×7 grid: leading blanks for the days before the 1st (Sun-start, per user
  // pref). Always render 42 cells so popover height never jumps as the user
  // browses across months.
  const leadingBlanks = new Date(pickerYear, pickerMonth, 1).getDay();
  const daysInMonth = new Date(pickerYear, pickerMonth + 1, 0).getDate();
  const cells = Array.from({ length: 42 }, (_, i) => {
    const dayNumber = i - leadingBlanks + 1;
    return dayNumber >= 1 && dayNumber <= daysInMonth ? dayNumber : 0;
  });

  return (
    <div
      role="dialog"
      aria-label="Choose a date"
      className="absolute right-0 top-full mt-2 z-40 w-72 rounded-lg border border-app-border bg-app-surface p-3 shadow-xl"
    >
      <div className="flex items-center justify-between mb-2">
        <button
          type="button"
          onClick={onPrev}
          aria-label="Previous month"
          className="flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
        >
          <ChevronLeft size={14} />
        </button>
        <div className="app-text-control text-app-ink tabular-nums">
          {MONTH_NAMES_LONG[pickerMonth]} {pickerYear}
        </div>
        <button
          type="button"
          onClick={onNext}
          aria-label="Next month"
          className="flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="grid grid-cols-7 mb-1">
        {PICKER_DAYS.map((day, i) => (
          <div
            key={i}
            className={cn(
              'app-text-overline py-1 text-center',
              // Sun-start: index 0 is Sunday (red).
              i === 0 ? 'text-red-500' : 'text-gray-500',
            )}
          >
            {day}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day, i) => {
          if (day === 0) {
            return <div key={i} className="h-8" />;
          }
          const isToday =
            pickerYear === today.getFullYear() &&
            pickerMonth === today.getMonth() &&
            day === today.getDate();
          const isSelected =
            pickerYear === viewYear &&
            pickerMonth === viewMonth &&
            day === selectedDate;
          const cellDate = new Date(pickerYear, pickerMonth, day);
          const isSunday = cellDate.getDay() === 0;
          const holidayNames = getKoreanHolidayNames(pickerYear, pickerMonth, day);
          return (
            <button
              type="button"
              key={i}
              onClick={() => onPickDate(pickerYear, pickerMonth, day)}
              title={holidayNames ? holidayNames.join(', ') : undefined}
              className={cn(
                'app-text-control-sm flex h-8 items-center justify-center rounded transition-colors tabular-nums',
                isSelected
                  ? 'bg-app-accent text-app-bg font-semibold'
                  : isToday
                    ? 'border border-app-accent text-app-accent font-semibold hover:bg-app-surface-hover'
                    : holidayNames || isSunday
                      ? 'text-red-500 hover:bg-app-surface-hover'
                      : 'text-app-ink hover:bg-app-surface-hover',
              )}
            >
              {day}
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
          Today
        </button>
      </div>
    </div>
  );
}

interface PlannerEventDraftRange {
  start: Date;
  end: Date;
  allDay: boolean;
}

function buildDefaultPlannerEventRange(currentDate: Date): PlannerEventDraftRange {
  const start = new Date(
    currentDate.getFullYear(),
    currentDate.getMonth(),
    currentDate.getDate(),
    9,
    0,
    0,
    0,
  );
  const end = new Date(start.getTime());
  end.setHours(end.getHours() + 1);
  return { start, end, allDay: false };
}

export const PlannerView = () => {
  const today = new Date();
  const navigate = useNavigate();
  const { token } = useAuth();
  const { workspaceSlug } = useParams();
  const [viewMode, setViewMode] = useState<PlannerViewMode>('Month');
  const [calendarState, setCalendarState] = useState(() =>
    buildInitialPlannerRange(today, 'Month'),
  );

  const calendarRef = useRef<UnifiedCalendarHandle | null>(null);

  const { events, loading, error, refresh } = useCalendarEvents({
    workspaceSlug,
    from: calendarState.rangeStart,
    to: calendarState.rangeEnd,
    useMockData: false,
  });

  // Mini date-picker popover. The picker has its own (year, month) cursor so
  // the user can browse without committing — the main view only updates when
  // they actually click a day.
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(today.getFullYear());
  const [pickerMonth, setPickerMonth] = useState(today.getMonth());
  const pickerRef = useRef<HTMLDivElement>(null);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const createMenuRef = useRef<HTMLDivElement>(null);
  const [plannerEventModalOpen, setPlannerEventModalOpen] = useState(false);
  const [plannerEventId, setPlannerEventId] = useState<string | null>(null);
  const [plannerEventRange, setPlannerEventRange] = useState<PlannerEventDraftRange | null>(null);
  const [meetingCreateOpen, setMeetingCreateOpen] = useState(false);
  const [meetingCreateRange, setMeetingCreateRange] = useState<PlannerEventDraftRange | null>(null);
  const [creationChoice, setCreationChoice] = useState<
    | {
        range: PlannerEventDraftRange;
        anchor: { x: number; y: number } | null;
      }
    | null
  >(null);

  useEffect(() => {
    if (!pickerOpen) return;
    function onMouseDown(event: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setPickerOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setPickerOpen(false);
    }
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [pickerOpen]);

  useEffect(() => {
    if (!createMenuOpen) return;
    function onMouseDown(event: MouseEvent) {
      if (createMenuRef.current && !createMenuRef.current.contains(event.target as Node)) {
        setCreateMenuOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setCreateMenuOpen(false);
    }
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [createMenuOpen]);

  // When the popover opens, sync its cursor to whatever the main view is showing.
  const openPicker = () => {
    setPickerYear(calendarState.currentDate.getFullYear());
    setPickerMonth(calendarState.currentDate.getMonth());
    setPickerOpen(true);
  };

  const setMode = (mode: PlannerViewMode) => {
    setViewMode(mode);
    calendarRef.current?.changeView(VIEW_MODE_TO_FC[mode]);
  };

  const goToPreviousPeriod = () => {
    calendarRef.current?.prev();
  };

  const goToNextPeriod = () => {
    calendarRef.current?.next();
  };

  const goToToday = () => {
    calendarRef.current?.today();
    setPickerOpen(false);
  };
  const openPlannerEventCreate = useCallback((range?: PlannerEventDraftRange) => {
    setPlannerEventId(null);
    setPlannerEventRange(range ?? buildDefaultPlannerEventRange(calendarState.currentDate));
    setPlannerEventModalOpen(true);
    setCreateMenuOpen(false);
  }, [calendarState.currentDate]);
  const openPlannerEventEdit = useCallback((eventId: string) => {
    setPlannerEventId(eventId);
    setPlannerEventRange(null);
    setPlannerEventModalOpen(true);
  }, []);

  const [actionError, setActionError] = useState<string | null>(null);
  const [previewMeetingId, setPreviewMeetingId] = useState<string | null>(null);
  useEffect(() => {
    if (!actionError) return;
    const id = window.setTimeout(() => setActionError(null), 4000);
    return () => window.clearTimeout(id);
  }, [actionError]);

  useEffect(() => {
    function handlePlannerCreateEvent() {
      openPlannerEventCreate();
    }
    function handlePlannerCreateMeeting() {
      setCreateMenuOpen(false);
      setMeetingCreateRange(null);
      setMeetingCreateOpen(true);
    }
    window.addEventListener('planner:create-event', handlePlannerCreateEvent);
    window.addEventListener('planner:create-meeting', handlePlannerCreateMeeting);
    return () => {
      window.removeEventListener('planner:create-event', handlePlannerCreateEvent);
      window.removeEventListener('planner:create-meeting', handlePlannerCreateMeeting);
    };
  }, [openPlannerEventCreate]);

  const handleDatesSet = useCallback(
    (nextState: {
      view: UnifiedCalendarView;
      currentDate: Date;
      rangeStart: Date;
      rangeEnd: Date;
    }) => {
      const nextMode = FC_VIEW_TO_MODE[nextState.view];
      setViewMode((current) => (current === nextMode ? current : nextMode));
      setCalendarState((current) => {
        const nextCurrentDate = startOfLocalDay(nextState.currentDate);
        const nextRangeStart = formatLocalYmd(nextState.rangeStart);
        const nextRangeEnd = formatLocalYmd(nextState.rangeEnd);
        if (
          current.currentDate.getTime() === nextCurrentDate.getTime()
          && current.rangeStart === nextRangeStart
          && current.rangeEnd === nextRangeEnd
        ) {
          return current;
        }
        return {
          currentDate: nextCurrentDate,
          rangeStart: nextRangeStart,
          rangeEnd: nextRangeEnd,
        };
      });
    },
    [],
  );

  const handleEventClick = (event: CalendarEvent) => {
    if (!workspaceSlug) return;
    if (event.sourceType === 'planner_event') {
      openPlannerEventEdit(event.sourceId);
      return;
    }
    if (event.sourceType === 'meeting') {
      // Open inline preview modal instead of navigating away — keeps user's
      // place on the calendar. Modal has a "전체 열기" link for deep edits.
      setPreviewMeetingId(event.sourceId);
      return;
    }
    // pms_due / pms_block — both navigate to the task list with the issue panel open.
    const listId = event.metadata.taskListId;
    if (!listId) {
      setActionError('태스크 위치를 찾을 수 없습니다.');
      return;
    }
    navigate(`/tool/pms-list-${listId}?issue=${encodeURIComponent(event.sourceId)}`);
  };

  const handleEventDrop = async (
    event: CalendarEvent,
    newStartIso: string,
    newEndIso: string,
    newAllDay: boolean,
    revert: () => void,
  ) => {
    if (!token || !workspaceSlug) {
      revert();
      return;
    }
    if (event.sourceType === 'planner_event') {
      try {
        await updatePlannerEvent(token, workspaceSlug, event.sourceId, {
          allDay: newAllDay,
          start: newStartIso,
          end: newEndIso,
        });
        refresh();
      } catch (err) {
        revert();
        setActionError(
          err instanceof Error ? err.message : '일정을 변경할 수 없습니다.',
        );
      }
      return;
    }
    if (event.sourceType === 'meeting') {
      if (newAllDay) {
        revert();
        setActionError('미팅은 종일 일정으로 변경할 수 없습니다.');
        return;
      }
      try {
        // FullCalendar already formatted these in the calendar's named timezone
        // (Asia/Seoul). Backend stores naive UTC — meeting-api accepts the
        // offset-prefixed string and the request pipeline normalizes it.
        await updateMeeting(token, workspaceSlug, event.sourceId, {
          start_at: newStartIso,
          end_at: newEndIso,
        });
        refresh();
      } catch (err) {
        revert();
        setActionError(
          err instanceof Error ? err.message : '미팅 시간을 변경할 수 없습니다.',
        );
      }
      return;
    }
    if (!newAllDay) {
      revert();
      setActionError('태스크 일정은 종일 일정으로만 이동할 수 있습니다.');
      return;
    }
    // PMS issues — extract date portion only (all-day, no time component).
    const newStartYmd = newStartIso.slice(0, 10);
    // Exclusive end: FullCalendar's all-day end is the day AFTER the visible
    // last day, so subtract one day for the stored due_date.
    const newDueYmd = decrementYmd(newEndIso.slice(0, 10));
    const payload: { due_date?: string | null; start_date?: string | null } = {
      due_date: newDueYmd,
    };
    if (event.sourceType === 'pms_block') {
      payload.start_date = newStartYmd;
    }
    try {
      await updateIssue(token, event.sourceId, payload);
      refresh();
    } catch (err) {
      revert();
      setActionError(
        err instanceof Error ? err.message : '태스크 일정을 변경할 수 없습니다.',
      );
    }
  };

  const handleEventResize = async (
    event: CalendarEvent,
    newEndIso: string,
    revert: () => void,
  ) => {
    if (!token || !workspaceSlug) {
      revert();
      return;
    }
    if (event.sourceType === 'meeting') {
      try {
        await updateMeeting(token, workspaceSlug, event.sourceId, {
          end_at: newEndIso,
        });
        refresh();
      } catch (err) {
        revert();
        setActionError(
          err instanceof Error ? err.message : '미팅 시간을 변경할 수 없습니다.',
        );
      }
      return;
    }
    if (event.sourceType === 'planner_event') {
      try {
        await updatePlannerEvent(token, workspaceSlug, event.sourceId, {
          allDay: event.allDay,
          start: event.start,
          end: newEndIso,
        });
        refresh();
      } catch (err) {
        revert();
        setActionError(
          err instanceof Error ? err.message : '일정을 변경할 수 없습니다.',
        );
      }
      return;
    }
    if (event.sourceType === 'pms_block') {
      const newDueYmd = decrementYmd(newEndIso.slice(0, 10));
      try {
        await updateIssue(token, event.sourceId, { due_date: newDueYmd });
        refresh();
      } catch (err) {
        revert();
        setActionError(
          err instanceof Error ? err.message : '태스크 일정을 변경할 수 없습니다.',
        );
      }
      return;
    }
    // pms_due (single-day) — resize is meaningless. Revert.
    revert();
  };
  const handleDateSelect = useCallback(
    (range: {
      start: Date;
      end: Date;
      allDay: boolean;
      anchor: { x: number; y: number } | null;
    }) => {
      setCreationChoice({
        range: { start: range.start, end: range.end, allDay: range.allDay },
        anchor: range.anchor,
      });
    },
    [],
  );
  const handleChoicePickEvent = useCallback(() => {
    if (!creationChoice) return;
    openPlannerEventCreate(creationChoice.range);
    setCreationChoice(null);
  }, [creationChoice, openPlannerEventCreate]);
  const handleChoicePickMeeting = useCallback(() => {
    if (!creationChoice) return;
    setMeetingCreateRange(creationChoice.range);
    setMeetingCreateOpen(true);
    setCreationChoice(null);
  }, [creationChoice]);
  const handleChoiceDismiss = useCallback(() => {
    setCreationChoice(null);
  }, []);
  const handlePlannerEventSaved = useCallback(() => {
    setPlannerEventModalOpen(false);
    setPlannerEventId(null);
    setPlannerEventRange(null);
    refresh();
  }, [refresh]);
  const handlePlannerEventDeleted = useCallback(() => {
    setPlannerEventModalOpen(false);
    setPlannerEventId(null);
    setPlannerEventRange(null);
    refresh();
  }, [refresh]);
  const handleMeetingCreated = useCallback((meetingId: string) => {
    setMeetingCreateOpen(false);
    setMeetingCreateRange(null);
    setPreviewMeetingId(meetingId);
    refresh();
  }, [refresh]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="p-8 h-full flex flex-col space-y-6 relative"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="app-text-title-lg text-app-ink">Planner</h1>
          <div className="flex items-center bg-app-surface-sidebar border border-app-border rounded-md p-1">
            {(['Month', 'Week', 'Day', 'Agenda'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setMode(mode)}
                className={cn(
                  'app-text-control-sm rounded px-3 py-1 transition-all',
                  viewMode === mode
                    ? 'bg-app-surface-hover text-app-ink shadow-sm'
                    : 'text-gray-500 hover:text-app-ink',
                )}
              >
                {mode}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={goToToday}
            className="app-text-control-sm rounded-md border border-app-border px-3 py-1 text-gray-500 transition-colors hover:text-app-ink"
          >
            Today
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div ref={pickerRef} className="relative flex items-center gap-1">
            <button
              type="button"
              onClick={goToPreviousPeriod}
              aria-label="Previous period"
              className="flex h-8 w-8 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => (pickerOpen ? setPickerOpen(false) : openPicker())}
              aria-haspopup="dialog"
              aria-expanded={pickerOpen}
              className="app-text-control flex h-8 min-w-[180px] items-center justify-center rounded-md text-app-ink tabular-nums transition-colors hover:bg-app-surface-hover"
            >
              {formatPlannerHeading(viewMode, calendarState.currentDate)}
            </button>
            <button
              type="button"
              onClick={goToNextPeriod}
              aria-label="Next period"
              className="flex h-8 w-8 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            >
              <ChevronRight size={16} />
            </button>
            {pickerOpen ? (
              <DatePickerPopover
                pickerYear={pickerYear}
                pickerMonth={pickerMonth}
                viewYear={calendarState.currentDate.getFullYear()}
                viewMonth={calendarState.currentDate.getMonth()}
                selectedDate={calendarState.currentDate.getDate()}
                today={today}
                onPrev={() => {
                  const next = new Date(pickerYear, pickerMonth - 1, 1);
                  setPickerYear(next.getFullYear());
                  setPickerMonth(next.getMonth());
                }}
                onNext={() => {
                  const next = new Date(pickerYear, pickerMonth + 1, 1);
                  setPickerYear(next.getFullYear());
                  setPickerMonth(next.getMonth());
                }}
                onPickToday={() => {
                  goToToday();
                  setPickerOpen(false);
                }}
                onPickDate={(year, month, day) => {
                  calendarRef.current?.gotoDate(new Date(year, month, day));
                  setPickerOpen(false);
                }}
              />
            ) : null}
          </div>
          <div ref={createMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setCreateMenuOpen((open) => !open)}
              className="app-text-control flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <Plus size={16} />
              <span>Add</span>
            </button>
            {createMenuOpen ? (
              <div className="absolute right-0 top-full z-30 mt-2 w-48 rounded-lg border border-app-border bg-app-surface py-1 shadow-xl">
                <div className="app-text-overline px-3 pt-1.5 pb-1 text-app-ink/45">Create</div>
                <button
                  type="button"
                  onClick={() => openPlannerEventCreate()}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                >
                  <Plus size={14} className="text-app-ink/45" />
                  <span>Event</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreateMenuOpen(false);
                    setMeetingCreateRange(null);
                    setMeetingCreateOpen(true);
                  }}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                >
                  <Plus size={14} className="text-app-ink/45" />
                  <span>Meeting</span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {actionError ? (
        <div
          role="alert"
          className="rounded-md border border-red-500/40 bg-red-500/10 px-4 py-2 app-text-caption text-red-500"
        >
          {actionError}
        </div>
      ) : null}

      <div className="flex-1 card p-0 overflow-hidden flex flex-col relative">
        {error ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="text-center space-y-2">
              <p className="text-red-500 app-text-body">{error}</p>
              <p className="text-gray-500 app-text-caption">
                일정을 불러올 수 없습니다. 새로고침 후 다시 시도하세요.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex-1 relative">
            {loading ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-bg/40 pointer-events-none">
                <div className="text-gray-500 app-text-caption">불러오는 중...</div>
              </div>
            ) : null}
            <UnifiedCalendar
              ref={calendarRef}
              events={events}
              initialView={VIEW_MODE_TO_FC[viewMode]}
              initialDate={calendarState.currentDate}
              onDatesSet={handleDatesSet}
              onDateSelect={handleDateSelect}
              onEventClick={handleEventClick}
              onEventDrop={handleEventDrop}
              onEventResize={handleEventResize}
            />
          </div>
        )}
      </div>

      <MeetingPreviewModal
        meetingId={previewMeetingId}
        workspaceSlug={workspaceSlug}
        onClose={() => setPreviewMeetingId(null)}
        onChanged={refresh}
      />
      <MeetingCreateModal
        isOpen={meetingCreateOpen && Boolean(workspaceSlug)}
        onClose={() => {
          setMeetingCreateOpen(false);
          setMeetingCreateRange(null);
        }}
        onCreated={handleMeetingCreated}
        workspaceSlug={workspaceSlug ?? ''}
        initialRange={meetingCreateRange}
      />
      {creationChoice ? (
        <PlannerEventChoicePopover
          anchor={creationChoice.anchor}
          onPickEvent={handleChoicePickEvent}
          onPickMeeting={handleChoicePickMeeting}
          onDismiss={handleChoiceDismiss}
        />
      ) : null}
      <PlannerEventModal
        isOpen={plannerEventModalOpen}
        onClose={() => {
          setPlannerEventModalOpen(false);
          setPlannerEventId(null);
          setPlannerEventRange(null);
        }}
        workspaceSlug={workspaceSlug}
        eventId={plannerEventId}
        initialRange={plannerEventRange}
        onSaved={handlePlannerEventSaved}
        onDeleted={handlePlannerEventDeleted}
      />
    </motion.div>
  );
};
