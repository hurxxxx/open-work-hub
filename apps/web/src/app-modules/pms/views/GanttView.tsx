import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentRef,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  CornerDownRight,
  GitBranch,
  Palette,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  RangeSlider,
  RangeSliderRange,
  RangeSliderThumb,
  RangeSliderTrack,
} from '@open-alm/ui';
import { cn } from '@/src/lib/utils';
import type { PmsTask, PmsTaskListStatus } from '../api/pms-api';
import {
  addGanttDays,
  applyGanttScheduleOverride,
  diffGanttDays,
  getGanttBarStyle,
  getGanttDragPreviewRange,
  getGanttStatusBarStyle,
  getGanttTaskDateRange,
  parseGanttDateOnly,
  toGanttDateOnly,
  type GanttDragMode,
  type GanttScheduleOverride,
} from './gantt-view-model';
import { getStatusLabel } from './pms-constants';
import { StatusIconGlyph } from './StatusIcon';
import { buildTaskHierarchy, sortTasksByHierarchy } from './pms-task-hierarchy';

const DAY_WIDTH = 40;
const MIN_DAY_WIDTH = 14;
const TASK_COLUMN_WIDTH = 288;
const MAX_GANTT_RANGE_MONTHS = 6;
const GANTT_SLIDER_WINDOW_MONTHS = MAX_GANTT_RANGE_MONTHS * 3;
const GANTT_MONTH_PRESETS = [1, 2, 3, 6] as const;
const GANTT_DATE_INPUT_CLASS =
  'app-text-body-sm h-9 w-full rounded-md border border-app-border bg-app-surface px-2 text-app-ink outline-none transition focus:border-app-accent focus:ring-2 focus:ring-app-accent/20';

type GanttInputDateRange = {
  fromDate: string;
  toDate: string;
};

type GanttRangeOverflowAnchor = 'end' | 'start';

function getMonthDateRange(value = new Date()): GanttInputDateRange {
  return getMonthSpanDateRange(1, value);
}

function getMonthSpanDateRange(
  months: number,
  value = new Date(),
): GanttInputDateRange {
  const start = new Date(value.getFullYear(), value.getMonth(), 1);
  const end = new Date(value.getFullYear(), value.getMonth() + months, 0);
  return {
    fromDate: toGanttDateOnly(start),
    toDate: toGanttDateOnly(end),
  };
}

function getDaysInMonth(year: number, monthIndex: number): number {
  return new Date(year, monthIndex + 1, 0).getDate();
}

function startOfLocalMonth(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addCalendarMonths(value: Date, months: number): Date {
  const targetYear = value.getFullYear();
  const targetMonth = value.getMonth() + months;
  const firstOfTarget = new Date(targetYear, targetMonth, 1);
  const targetDay = Math.min(
    value.getDate(),
    getDaysInMonth(firstOfTarget.getFullYear(), firstOfTarget.getMonth()),
  );
  return new Date(
    firstOfTarget.getFullYear(),
    firstOfTarget.getMonth(),
    targetDay,
  );
}

function getMaxRangeEnd(start: Date): Date {
  return addGanttDays(addCalendarMonths(start, MAX_GANTT_RANGE_MONTHS), -1);
}

function getMaxRangeStart(end: Date): Date {
  return addCalendarMonths(addGanttDays(end, 1), -MAX_GANTT_RANGE_MONTHS);
}

function getGanttSliderWindowStart(anchor: Date): Date {
  return startOfLocalMonth(addCalendarMonths(anchor, -MAX_GANTT_RANGE_MONTHS));
}

function getGanttSliderWindowEnd(start: Date): Date {
  return addGanttDays(addCalendarMonths(start, GANTT_SLIDER_WINDOW_MONTHS), -1);
}

function normalizeInputDateRange(
  range: GanttInputDateRange,
  fallback: GanttInputDateRange,
  overflowAnchor: GanttRangeOverflowAnchor = 'start',
): GanttInputDateRange {
  const fallbackStart = parseGanttDateOnly(fallback.fromDate) ?? new Date();
  const fallbackEnd = parseGanttDateOnly(fallback.toDate) ?? fallbackStart;
  const parsedStart = parseGanttDateOnly(range.fromDate) ?? fallbackStart;
  const parsedEnd = parseGanttDateOnly(range.toDate) ?? fallbackEnd;
  const start = parsedStart <= parsedEnd ? parsedStart : parsedEnd;
  const end = parsedStart <= parsedEnd ? parsedEnd : parsedStart;
  const maxEnd = getMaxRangeEnd(start);
  if (end > maxEnd && overflowAnchor === 'end') {
    return {
      fromDate: toGanttDateOnly(getMaxRangeStart(end)),
      toDate: toGanttDateOnly(end),
    };
  }

  return {
    fromDate: toGanttDateOnly(start),
    toDate: toGanttDateOnly(end > maxEnd ? maxEnd : end),
  };
}

function buildVisibleDates(start: Date, end: Date): Date[] {
  const dates: Date[] = [];
  for (
    let cursor = new Date(
      start.getFullYear(),
      start.getMonth(),
      start.getDate(),
    );
    cursor <= end;
    cursor = new Date(
      cursor.getFullYear(),
      cursor.getMonth(),
      cursor.getDate() + 1,
    )
  ) {
    dates.push(cursor);
  }
  return dates;
}

function clampGanttOffset(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function snapGanttSliderOffset(
  value: number,
  sliderStart: Date,
  sliderEnd: Date,
): number {
  const maxOffset = diffGanttDays(sliderEnd, sliderStart);
  let bestOffset = clampGanttOffset(value, 0, maxOffset);
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const date of buildVisibleDates(sliderStart, sliderEnd)) {
    const snapTarget = date.getDate() === 1 || date.getDay() === 1;
    if (!snapTarget) continue;
    const offset = diffGanttDays(date, sliderStart);
    const distance = Math.abs(offset - value);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestOffset = offset;
    }
  }

  return bestDistance <= 2 ? bestOffset : clampGanttOffset(value, 0, maxOffset);
}

type DragState = {
  deltaDays: number;
  end: Date;
  mode: GanttDragMode;
  taskId: string;
  start: Date;
  startX: number;
};

type GanttSliderRangeDragState = {
  endOffset: number;
  pointerOffset: number;
  startOffset: number;
};

export const GanttView = ({
  canEdit = false,
  onSelectIssue,
  onOpenStatusSettings,
  tasks,
  onUpdateIssue,
  taskListStatuses,
}: {
  canEdit?: boolean;
  onSelectIssue?: (task: PmsTask) => void;
  onOpenStatusSettings?: () => void;
  tasks: PmsTask[];
  onUpdateIssue?: (
    taskId: string,
    payload: Record<string, unknown>,
  ) => Promise<void> | void;
  taskListStatuses?: PmsTaskListStatus[];
}) => {
  const { i18n, t } = useTranslation('apps');
  const [visibleRange, setVisibleRange] = useState(getMonthDateRange);
  const [draftRange, setDraftRange] = useState(getMonthDateRange);
  const [customRangeOpen, setCustomRangeOpen] = useState(false);
  const [sliderBaseDateOnly, setSliderBaseDateOnly] = useState(() =>
    toGanttDateOnly(getGanttSliderWindowStart(new Date())),
  );
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [collapsedTaskIds, setCollapsedTaskIds] = useState<Set<string>>(
    new Set(),
  );
  const [pendingSchedules, setPendingSchedules] = useState<
    Map<string, GanttScheduleOverride>
  >(new Map());
  const [scrollViewportWidth, setScrollViewportWidth] = useState(0);
  const scrollViewportRef = useRef<HTMLDivElement | null>(null);
  const rangeSliderRootRef = useRef<ComponentRef<typeof RangeSlider> | null>(
    null,
  );
  const sliderRangeDragRef = useRef<GanttSliderRangeDragState | null>(null);
  const suppressNextBarClickRef = useRef(false);

  const normalizedVisibleRange = useMemo(
    () => normalizeInputDateRange(visibleRange, getMonthDateRange()),
    [visibleRange],
  );
  const { dates, monthTitle, visibleEnd, visibleStart } = useMemo(() => {
    const start =
      parseGanttDateOnly(normalizedVisibleRange.fromDate) ?? new Date();
    const end = parseGanttDateOnly(normalizedVisibleRange.toDate) ?? start;
    const sameMonth =
      start.getFullYear() === end.getFullYear() &&
      start.getMonth() === end.getMonth() &&
      start.getDate() === 1 &&
      end.getDate() === getDaysInMonth(end.getFullYear(), end.getMonth());
    const fullMonthFormatter = new Intl.DateTimeFormat(i18n.language, {
      month: 'long',
      year: 'numeric',
    });
    const dateFormatter = new Intl.DateTimeFormat(i18n.language, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
    return {
      dates: buildVisibleDates(start, end),
      monthTitle: sameMonth
        ? fullMonthFormatter.format(start)
        : `${dateFormatter.format(start)} - ${dateFormatter.format(end)}`,
      visibleEnd: end,
      visibleStart: start,
    };
  }, [i18n.language, normalizedVisibleRange]);

  const todayDateOnly = toGanttDateOnly(new Date());
  const availableTimelineWidth = Math.max(
    0,
    scrollViewportWidth - TASK_COLUMN_WIDTH,
  );
  const dayWidth = useMemo(() => {
    if (dates.length === 0 || availableTimelineWidth <= 0) return DAY_WIDTH;
    return Math.max(
      MIN_DAY_WIDTH,
      Math.min(DAY_WIDTH, availableTimelineWidth / dates.length),
    );
  }, [availableTimelineWidth, dates.length]);
  const timelineWidth = dates.length * dayWidth;
  const chartWidth = Math.max(
    scrollViewportWidth,
    TASK_COLUMN_WIDTH + timelineWidth,
  );
  const todayOffset = useMemo(() => {
    const today = parseGanttDateOnly(todayDateOnly);
    if (!today || today < visibleStart || today > visibleEnd) return null;
    return `${diffGanttDays(today, visibleStart) * dayWidth + dayWidth / 2}px`;
  }, [dayWidth, todayDateOnly, visibleEnd, visibleStart]);
  const activeMonthPreset = useMemo(() => {
    if (visibleStart.getDate() !== 1) return null;
    return (
      GANTT_MONTH_PRESETS.find((months) => {
        const presetEnd = new Date(
          visibleStart.getFullYear(),
          visibleStart.getMonth() + months,
          0,
        );
        return toGanttDateOnly(presetEnd) === toGanttDateOnly(visibleEnd);
      }) ?? null
    );
  }, [visibleEnd, visibleStart]);
  const monthLabelFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        month: 'short',
      }),
    [i18n.language],
  );
  const normalizedDraftRange = useMemo(
    () => normalizeInputDateRange(draftRange, normalizedVisibleRange),
    [draftRange, normalizedVisibleRange],
  );
  const draftStart =
    parseGanttDateOnly(normalizedDraftRange.fromDate) ?? visibleStart;
  const draftEnd =
    parseGanttDateOnly(normalizedDraftRange.toDate) ?? draftStart;
  const sliderBaseDate = useMemo(
    () =>
      parseGanttDateOnly(sliderBaseDateOnly) ?? startOfLocalMonth(visibleStart),
    [sliderBaseDateOnly, visibleStart],
  );
  const sliderEndDate = useMemo(
    () => getGanttSliderWindowEnd(sliderBaseDate),
    [sliderBaseDate],
  );
  const sliderMaxOffset = diffGanttDays(sliderEndDate, sliderBaseDate);
  const sliderStartOffset = clampGanttOffset(
    diffGanttDays(draftStart, sliderBaseDate),
    0,
    sliderMaxOffset,
  );
  const sliderEndOffset = clampGanttOffset(
    diffGanttDays(draftEnd, sliderBaseDate),
    sliderStartOffset,
    sliderMaxOffset,
  );
  const sliderMarks = useMemo(
    () =>
      buildVisibleDates(sliderBaseDate, sliderEndDate)
        .filter((date) => date.getDate() === 1 || date.getDay() === 1)
        .map((date) => ({
          date,
          label: date.getDate() === 1 ? monthLabelFormatter.format(date) : null,
          major: date.getDate() === 1,
          offset: diffGanttDays(date, sliderBaseDate),
        })),
    [monthLabelFormatter, sliderBaseDate, sliderEndDate],
  );
  const draftRangeMaxToDate = useMemo(() => {
    const draftStart = parseGanttDateOnly(draftRange.fromDate);
    return draftStart ? toGanttDateOnly(getMaxRangeEnd(draftStart)) : undefined;
  }, [draftRange.fromDate]);

  function commitVisibleRange(
    range: GanttInputDateRange,
    options: {
      closeCustom?: boolean;
      syncSliderBase?: boolean;
    } = {},
  ) {
    const nextRange = normalizeInputDateRange(range, visibleRange);
    setDraftRange(nextRange);
    setVisibleRange(nextRange);
    if (options.syncSliderBase !== false) {
      const nextStart = parseGanttDateOnly(nextRange.fromDate);
      if (nextStart) {
        setSliderBaseDateOnly(
          toGanttDateOnly(getGanttSliderWindowStart(nextStart)),
        );
      }
    }
    if (options.closeCustom !== false) setCustomRangeOpen(false);
  }

  function shiftVisibleRange(months: number) {
    const normalizedRange = normalizeInputDateRange(
      visibleRange,
      getMonthDateRange(),
    );
    const currentStart =
      parseGanttDateOnly(normalizedRange.fromDate) ?? new Date();
    const currentEnd =
      parseGanttDateOnly(normalizedRange.toDate) ?? currentStart;
    const nextRange = {
      fromDate: toGanttDateOnly(addCalendarMonths(currentStart, months)),
      toDate: toGanttDateOnly(addCalendarMonths(currentEnd, months)),
    };
    commitVisibleRange(nextRange);
  }

  function applyMonthPreset(months: number) {
    const start = parseGanttDateOnly(normalizedVisibleRange.fromDate);
    commitVisibleRange(getMonthSpanDateRange(months, start ?? new Date()));
  }

  function resetVisibleRange() {
    commitVisibleRange(getMonthDateRange());
  }

  function toggleCustomRangeControls() {
    if (customRangeOpen) {
      setCustomRangeOpen(false);
      return;
    }
    setDraftRange(normalizedVisibleRange);
    setSliderBaseDateOnly(
      toGanttDateOnly(getGanttSliderWindowStart(visibleStart)),
    );
    setCustomRangeOpen(true);
  }

  function handleDateRangeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    commitVisibleRange(draftRange);
  }

  function updateDraftRangeFromSliderOffsets({
    endOffset,
    overflowAnchor = 'start',
    preserveSpan = false,
    snap,
    startOffset,
  }: {
    endOffset: number;
    overflowAnchor?: GanttRangeOverflowAnchor;
    preserveSpan?: boolean;
    snap: boolean;
    startOffset: number;
  }) {
    const clampedStartOffset = clampGanttOffset(
      startOffset,
      0,
      sliderMaxOffset,
    );
    const clampedEndOffset = clampGanttOffset(endOffset, 0, sliderMaxOffset);
    const rangeSpan = Math.abs(clampedEndOffset - clampedStartOffset);
    let orderedStartOffset = Math.min(clampedStartOffset, clampedEndOffset);
    let orderedEndOffset = Math.max(clampedStartOffset, clampedEndOffset);

    if (preserveSpan) {
      const nextStartOffset = snap
        ? snapGanttSliderOffset(
            orderedStartOffset,
            sliderBaseDate,
            sliderEndDate,
          )
        : orderedStartOffset;
      orderedStartOffset = clampGanttOffset(
        nextStartOffset,
        0,
        Math.max(0, sliderMaxOffset - rangeSpan),
      );
      orderedEndOffset = orderedStartOffset + rangeSpan;
    } else if (snap) {
      const nextStartOffset = snapGanttSliderOffset(
        orderedStartOffset,
        sliderBaseDate,
        sliderEndDate,
      );
      const nextEndOffset = snapGanttSliderOffset(
        orderedEndOffset,
        sliderBaseDate,
        sliderEndDate,
      );
      orderedStartOffset = Math.min(nextStartOffset, nextEndOffset);
      orderedEndOffset = Math.max(nextStartOffset, nextEndOffset);
    }

    setDraftRange(
      normalizeInputDateRange(
        {
          fromDate: toGanttDateOnly(
            addGanttDays(sliderBaseDate, orderedStartOffset),
          ),
          toDate: toGanttDateOnly(
            addGanttDays(sliderBaseDate, orderedEndOffset),
          ),
        },
        normalizedDraftRange,
        overflowAnchor,
      ),
    );
  }

  function getSliderOverflowAnchor(value: number[]): GanttRangeOverflowAnchor {
    const nextStartOffset = value[0] ?? sliderStartOffset;
    const nextEndOffset = value[1] ?? sliderEndOffset;
    return Math.abs(nextEndOffset - sliderEndOffset) >
      Math.abs(nextStartOffset - sliderStartOffset)
      ? 'end'
      : 'start';
  }

  function handleSliderRangeChange(value: number[]) {
    updateDraftRangeFromSliderOffsets({
      endOffset: value[1] ?? sliderEndOffset,
      overflowAnchor: getSliderOverflowAnchor(value),
      snap: false,
      startOffset: value[0] ?? sliderStartOffset,
    });
  }

  function handleSliderRangeCommit(value: number[]) {
    updateDraftRangeFromSliderOffsets({
      endOffset: value[1] ?? sliderEndOffset,
      overflowAnchor: getSliderOverflowAnchor(value),
      snap: true,
      startOffset: value[0] ?? sliderStartOffset,
    });
  }

  function getSliderPointerOffset(clientX: number): number | null {
    if (!Number.isFinite(clientX)) return null;
    const rect = rangeSliderRootRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return null;
    const pointerRatio = clampGanttOffset(
      (clientX - rect.left) / rect.width,
      0,
      1,
    );
    return Math.round(pointerRatio * sliderMaxOffset);
  }

  function updateDraftRangeFromSliderRangeDrag(clientX: number, snap: boolean) {
    const dragState = sliderRangeDragRef.current;
    const pointerOffset = getSliderPointerOffset(clientX);
    if (!dragState || pointerOffset === null) return;

    const rangeSpan = dragState.endOffset - dragState.startOffset;
    const nextStartOffset = clampGanttOffset(
      dragState.startOffset + pointerOffset - dragState.pointerOffset,
      0,
      Math.max(0, sliderMaxOffset - rangeSpan),
    );
    updateDraftRangeFromSliderOffsets({
      endOffset: nextStartOffset + rangeSpan,
      preserveSpan: true,
      snap,
      startOffset: nextStartOffset,
    });
  }

  function handleSliderRangeDragMove(event: PointerEvent) {
    updateDraftRangeFromSliderRangeDrag(event.clientX, false);
  }

  function handleSliderRangeDragEnd(event: PointerEvent) {
    updateDraftRangeFromSliderRangeDrag(event.clientX, true);
    sliderRangeDragRef.current = null;
    window.removeEventListener('pointermove', handleSliderRangeDragMove);
  }

  function handleSliderRangePointerDown(
    event: ReactPointerEvent<HTMLSpanElement>,
  ) {
    if (event.button !== 0) return;
    const pointerOffset = getSliderPointerOffset(event.clientX);
    if (pointerOffset === null) return;

    event.preventDefault();
    event.stopPropagation();
    sliderRangeDragRef.current = {
      endOffset: sliderEndOffset,
      pointerOffset,
      startOffset: sliderStartOffset,
    };
    window.addEventListener('pointermove', handleSliderRangeDragMove);
    window.addEventListener('pointerup', handleSliderRangeDragEnd, {
      once: true,
    });
  }
  const hierarchy = useMemo(() => buildTaskHierarchy(tasks), [tasks]);
  const orderedTasks = useMemo(() => sortTasksByHierarchy(tasks), [tasks]);
  const editable = canEdit && Boolean(onUpdateIssue);
  const taskIdSet = useMemo(
    () => new Set(tasks.map((task) => task.id)),
    [tasks],
  );
  const visibleOrderedTasks = useMemo(
    () =>
      orderedTasks.filter((task) => {
        let parent = hierarchy.get(task.id)?.parent ?? null;
        while (parent) {
          if (collapsedTaskIds.has(parent.id)) return false;
          parent = hierarchy.get(parent.id)?.parent ?? null;
        }
        return true;
      }),
    [collapsedTaskIds, hierarchy, orderedTasks],
  );

  useEffect(() => {
    const element = scrollViewportRef.current;
    if (!element) return;

    const updateWidth = () => setScrollViewportWidth(element.clientWidth);
    updateWidth();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateWidth);
      return () => window.removeEventListener('resize', updateWidth);
    }

    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    scrollViewportRef.current?.scrollTo?.({ left: 0 });
  }, [normalizedVisibleRange.fromDate, normalizedVisibleRange.toDate]);

  useEffect(() => {
    if (!customRangeOpen) return;

    const nextDraftStart = parseGanttDateOnly(normalizedDraftRange.fromDate);
    const currentSliderStart = parseGanttDateOnly(sliderBaseDateOnly);
    if (!nextDraftStart || !currentSliderStart) return;

    const currentSliderEnd = getGanttSliderWindowEnd(currentSliderStart);
    if (
      nextDraftStart >= currentSliderStart &&
      nextDraftStart <= currentSliderEnd
    ) {
      return;
    }

    setSliderBaseDateOnly(
      toGanttDateOnly(getGanttSliderWindowStart(nextDraftStart)),
    );
  }, [customRangeOpen, normalizedDraftRange.fromDate, sliderBaseDateOnly]);

  useEffect(() => {
    setCollapsedTaskIds((current) => {
      const next = new Set<string>();
      for (const taskId of current) {
        if (taskIdSet.has(taskId)) next.add(taskId);
      }
      return next.size === current.size ? current : next;
    });
    setPendingSchedules((current) => {
      const next = new Map<string, GanttScheduleOverride>();
      for (const [taskId, schedule] of current) {
        if (taskIdSet.has(taskId)) next.set(taskId, schedule);
      }
      return next.size === current.size ? current : next;
    });
  }, [taskIdSet]);

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (event: MouseEvent) => {
      setDragging((current) =>
        current
          ? (() => {
              const deltaDays = Math.round(
                (event.clientX - current.startX) / dayWidth,
              );
              if (deltaDays !== 0) suppressNextBarClickRef.current = true;
              return {
                ...current,
                deltaDays,
              };
            })()
          : current,
      );
    };
    const handleMouseUp = () => {
      setDragging((current) => {
        if (current && current.deltaDays !== 0) {
          const { end: nextEnd, start: nextStart } =
            getGanttDragPreviewRange(current);
          const nextSchedule = {
            due_date: toGanttDateOnly(nextEnd),
            start_date: toGanttDateOnly(nextStart),
          };
          setPendingSchedules((schedules) => {
            const next = new Map(schedules);
            next.set(current.taskId, nextSchedule);
            return next;
          });
          void Promise.resolve(onUpdateIssue?.(current.taskId, nextSchedule))
            .catch(() => undefined)
            .finally(() => {
              setPendingSchedules((schedules) => {
                const next = new Map(schedules);
                const schedule = next.get(current.taskId);
                if (schedule === nextSchedule) next.delete(current.taskId);
                return next.size === schedules.size ? schedules : next;
              });
            });
        }
        return null;
      });
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dayWidth, dragging, onUpdateIssue]);

  function handleBarMouseDown(
    event: React.MouseEvent,
    task: PmsTask,
    mode: GanttDragMode,
  ) {
    if (!editable) return;
    const issueDates = getGanttTaskDateRange(task);
    if (!issueDates) return;
    event.preventDefault();
    event.stopPropagation();
    suppressNextBarClickRef.current = false;
    setDragging({
      deltaDays: 0,
      end: issueDates.end,
      mode,
      taskId: task.id,
      start: issueDates.start,
      startX: event.clientX,
    });
  }

  function handleBarClick(event: React.MouseEvent, task: PmsTask) {
    if (suppressNextBarClickRef.current) {
      event.preventDefault();
      event.stopPropagation();
      suppressNextBarClickRef.current = false;
      return;
    }
    onSelectIssue?.(task);
  }

  function stopResizeHandleClick(event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
  }

  function toggleTaskCollapse(taskId: string) {
    setCollapsedTaskIds((current) => {
      const next = new Set(current);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <div className="border-b border-app-border bg-app-surface-sidebar/30">
        <div className="flex flex-col gap-3 px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            <CalendarDays size={16} className="mr-1 text-app-accent" />
            <Button
              aria-label={t('pms.gantt.previousYear')}
              onClick={() => shiftVisibleRange(-12)}
              size="icon"
              title={t('pms.gantt.previousYear')}
              variant="ghost"
            >
              <ChevronsLeft size={16} />
            </Button>
            <Button
              aria-label={t('pms.gantt.previousMonth')}
              onClick={() => shiftVisibleRange(-1)}
              size="icon"
              title={t('pms.gantt.previousMonth')}
              variant="ghost"
            >
              <ChevronLeft size={16} />
            </Button>
            <h3 className="app-text-title-md mx-2 min-w-0 truncate text-app-ink">
              {monthTitle}
            </h3>
            <Button
              aria-label={t('pms.gantt.nextMonth')}
              onClick={() => shiftVisibleRange(1)}
              size="icon"
              title={t('pms.gantt.nextMonth')}
              variant="ghost"
            >
              <ChevronRight size={16} />
            </Button>
            <Button
              aria-label={t('pms.gantt.nextYear')}
              onClick={() => shiftVisibleRange(12)}
              size="icon"
              title={t('pms.gantt.nextYear')}
              variant="ghost"
            >
              <ChevronsRight size={16} />
            </Button>
          </div>
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
            <div
              aria-label={t('pms.gantt.monthPresetsLabel')}
              className="flex flex-wrap gap-1"
              role="group"
            >
              {GANTT_MONTH_PRESETS.map((months) => (
                <Button
                  key={months}
                  onClick={() => applyMonthPreset(months)}
                  size="dense"
                  variant={
                    activeMonthPreset === months ? 'primary' : 'secondary'
                  }
                >
                  {t('pms.gantt.monthPreset', { count: months })}
                </Button>
              ))}
            </div>
            <div className="relative">
              <Button
                aria-controls="pms-gantt-custom-range-panel"
                aria-expanded={customRangeOpen}
                aria-haspopup="dialog"
                onClick={toggleCustomRangeControls}
                size="dense"
                variant={customRangeOpen ? 'primary' : 'secondary'}
              >
                {t('pms.gantt.customRange')}
              </Button>
              {customRangeOpen ? (
                <form
                  className="absolute right-0 top-full z-50 mt-2 flex w-[560px] max-w-[calc(100vw-2rem)] flex-col gap-4 rounded-lg border border-app-border bg-app-surface p-3 shadow-xl"
                  id="pms-gantt-custom-range-panel"
                  noValidate
                  onSubmit={handleDateRangeSubmit}
                >
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="flex flex-col gap-1.5">
                      <span className="app-text-overline text-app-ink/55">
                        {t('pms.gantt.fromDateLabel')}
                      </span>
                      <input
                        className={GANTT_DATE_INPUT_CLASS}
                        max={draftRange.toDate || undefined}
                        onChange={(event) =>
                          setDraftRange((current) => ({
                            ...current,
                            fromDate: event.target.value,
                          }))
                        }
                        type="date"
                        value={draftRange.fromDate}
                      />
                    </label>
                    <label className="flex flex-col gap-1.5">
                      <span className="app-text-overline text-app-ink/55">
                        {t('pms.gantt.toDateLabel')}
                      </span>
                      <input
                        className={GANTT_DATE_INPUT_CLASS}
                        max={draftRangeMaxToDate}
                        min={draftRange.fromDate || undefined}
                        onChange={(event) =>
                          setDraftRange((current) => ({
                            ...current,
                            toDate: event.target.value,
                          }))
                        }
                        type="date"
                        value={draftRange.toDate}
                      />
                    </label>
                  </div>
                  <div
                    aria-label={t('pms.gantt.dateSliderLabel')}
                    className="rounded-md border border-app-border bg-app-surface-sidebar/40 px-3 pb-2 pt-3"
                    role="group"
                  >
                    <div className="flex items-center gap-3">
                      <span className="app-text-overline w-12 shrink-0 text-app-ink/55">
                        {t('pms.gantt.dateSliderLabel')}
                      </span>
                      <div className="relative h-14 min-w-0 flex-1">
                        {sliderMarks.map((mark) => {
                          const left =
                            sliderMaxOffset > 0
                              ? (mark.offset / sliderMaxOffset) * 100
                              : 0;
                          return (
                            <div
                              key={toGanttDateOnly(mark.date)}
                              className={cn(
                                'pointer-events-none absolute top-4 -translate-x-1/2 text-center',
                                mark.major ? 'z-10' : 'z-0',
                              )}
                              style={{ left: `${left}%` }}
                            >
                              <div
                                className={cn(
                                  'mx-auto w-px rounded-full bg-app-ink/20',
                                  mark.major ? 'h-5 bg-app-ink/45' : 'h-3',
                                )}
                              />
                              {mark.label ? (
                                <div className="mt-1 hidden whitespace-nowrap text-[10px] font-semibold leading-3 text-app-ink/55 sm:block">
                                  {mark.label}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                        <RangeSlider
                          aria-label={t('pms.gantt.dateSliderLabel')}
                          className="relative z-20 flex h-10 w-full touch-none select-none items-center"
                          data-testid="pms-gantt-date-slider"
                          max={sliderMaxOffset}
                          min={0}
                          minStepsBetweenThumbs={0}
                          onValueChange={handleSliderRangeChange}
                          onValueCommit={handleSliderRangeCommit}
                          ref={rangeSliderRootRef}
                          step={1}
                          value={[sliderStartOffset, sliderEndOffset]}
                        >
                          <RangeSliderTrack className="relative h-2 grow rounded-full bg-app-border/70">
                            <RangeSliderRange
                              className="absolute h-full cursor-grab rounded-full bg-app-accent shadow-sm before:absolute before:-inset-y-4 before:inset-x-0 before:content-[''] active:cursor-grabbing"
                              data-testid="pms-gantt-range-drag-handle"
                              onPointerDown={handleSliderRangePointerDown}
                            />
                          </RangeSliderTrack>
                          <RangeSliderThumb
                            aria-label={t('pms.gantt.sliderStartLabel')}
                            className="block size-5 rounded-full border-[3px] border-app-accent bg-app-surface shadow-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/30"
                          />
                          <RangeSliderThumb
                            aria-label={t('pms.gantt.sliderEndLabel')}
                            className="block size-5 rounded-full border-[3px] border-app-accent bg-app-surface shadow-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/30"
                          />
                        </RangeSlider>
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <Button size="dense" type="submit" variant="secondary">
                      {t('pms.gantt.applyDateRange')}
                    </Button>
                  </div>
                </form>
              ) : null}
            </div>
            <div className="flex items-center gap-1">
              {onOpenStatusSettings ? (
                <Button
                  aria-label={t('pms.gantt.editStatusColors')}
                  onClick={onOpenStatusSettings}
                  size="icon"
                  title={t('pms.gantt.editStatusColors')}
                  variant="ghost"
                >
                  <Palette size={16} />
                </Button>
              ) : null}
              <Button onClick={resetVisibleRange} size="dense" variant="ghost">
                {t('pms.gantt.resetRange')}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div
        ref={scrollViewportRef}
        className="flex-1 overflow-auto custom-scrollbar"
        data-testid="pms-gantt-scroll-viewport"
      >
        <div className="min-h-full" style={{ minWidth: `${chartWidth}px` }}>
          <div className="sticky top-0 z-40 flex border-b border-app-border bg-app-surface-sidebar/95 backdrop-blur">
            <div className="app-text-overline sticky left-0 z-50 w-72 shrink-0 border-r border-app-border bg-app-surface-sidebar/95 p-4 text-app-ink/55 backdrop-blur">
              {t('pms.taskName')}
            </div>
            <div
              className="relative flex shrink-0"
              style={{ width: `${timelineWidth}px` }}
            >
              {dates.map((date, index) => {
                const showMonthLabel = index === 0 || date.getDate() === 1;
                const isToday = toGanttDateOnly(date) === todayDateOnly;
                return (
                  <div
                    key={toGanttDateOnly(date)}
                    className={cn(
                      'flex-shrink-0 border-r border-app-border py-2 text-center last:border-r-0',
                      showMonthLabel &&
                        index > 0 &&
                        'border-l border-l-app-border',
                      isToday && 'bg-app-danger/10',
                    )}
                    style={{ width: `${dayWidth}px` }}
                  >
                    <div
                      className={cn(
                        'app-text-micro font-bold text-app-ink',
                        isToday && 'text-app-danger',
                      )}
                    >
                      {date.getDate()}
                    </div>
                    <div className="h-3 text-[10px] leading-3 text-app-ink/45">
                      {showMonthLabel ? monthLabelFormatter.format(date) : null}
                    </div>
                  </div>
                );
              })}
              {todayOffset ? (
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute bottom-0 top-0 z-20 w-0.5 bg-app-danger"
                  style={{ left: todayOffset }}
                />
              ) : null}
            </div>
          </div>

          {visibleOrderedTasks.map((task) => {
            const taskHierarchy = hierarchy.get(task.id);
            const depth = taskHierarchy?.depth ?? 0;
            const childCount = taskHierarchy?.childCount ?? 0;
            const collapsed = collapsedTaskIds.has(task.id);
            const effectiveTask = applyGanttScheduleOverride(
              task,
              pendingSchedules.get(task.id),
            );
            const barStyle = getGanttBarStyle({
              dayWidth,
              dragging,
              visibleEnd,
              visibleStart,
              task: effectiveTask,
            });
            const statusLabel = getStatusLabel(task.status, taskListStatuses);
            const statusBarStyle = getGanttStatusBarStyle({
              status: task.status,
              taskListStatuses,
            });
            const taskDetailLabel = t('pms.list.viewDetails', {
              reference: task.title,
            });
            const taskNameContent = (
              <>
                <StatusIconGlyph
                  label={statusLabel}
                  status={task.status}
                  taskListStatuses={taskListStatuses}
                />
                <span
                  className={cn(
                    'app-text-body-sm min-w-0 truncate text-app-ink transition-colors group-hover/task-name:text-app-accent',
                    childCount > 0 ? 'font-semibold' : 'font-medium',
                  )}
                >
                  {task.title}
                </span>
                {childCount > 0 ? (
                  <span
                    className="app-text-micro inline-flex shrink-0 items-center gap-1 rounded bg-app-surface-sidebar px-1.5 py-0.5 font-semibold text-app-ink/45"
                    title={t('pms.gantt.childTasks', {
                      count: childCount,
                    })}
                  >
                    <GitBranch size={10} />
                    {childCount}
                  </span>
                ) : null}
              </>
            );
            return (
              <div
                key={task.id}
                className={cn(
                  'group/gantt-row flex border-b border-app-border transition-colors hover:bg-app-surface-hover',
                  depth > 0 && 'bg-app-surface-sidebar/20',
                )}
              >
                <div
                  className={cn(
                    'sticky left-0 z-30 flex w-72 shrink-0 items-center border-r border-app-border px-4 py-3 transition-colors group-hover/gantt-row:bg-app-surface-hover',
                    depth > 0 ? 'bg-app-surface-sidebar' : 'bg-app-surface',
                  )}
                >
                  <div
                    className="flex min-w-0 flex-1 items-center gap-2"
                    style={{ paddingLeft: `${Math.min(depth, 5) * 18}px` }}
                  >
                    {depth > 0 ? (
                      <CornerDownRight
                        size={13}
                        className="shrink-0 text-app-ink/35"
                      />
                    ) : childCount > 0 ? (
                      <button
                        aria-label={t(
                          collapsed
                            ? 'pms.gantt.expandSubtasks'
                            : 'pms.gantt.collapseSubtasks',
                          { title: task.title },
                        )}
                        className="flex size-[18px] shrink-0 items-center justify-center rounded text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleTaskCollapse(task.id);
                        }}
                        title={t(
                          collapsed
                            ? 'pms.gantt.expandSubtasks'
                            : 'pms.gantt.collapseSubtasks',
                          { title: task.title },
                        )}
                        type="button"
                      >
                        {collapsed ? (
                          <ChevronRight size={14} />
                        ) : (
                          <ChevronDown size={14} />
                        )}
                      </button>
                    ) : (
                      <span className="w-[13px] shrink-0" />
                    )}
                    {onSelectIssue ? (
                      <button
                        className="group/task-name flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded text-left transition-colors hover:text-app-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/40"
                        onClick={() => onSelectIssue(effectiveTask)}
                        title={taskDetailLabel}
                        type="button"
                      >
                        {taskNameContent}
                      </button>
                    ) : (
                      <div className="flex min-w-0 flex-1 items-center gap-2">
                        {taskNameContent}
                      </div>
                    )}
                  </div>
                </div>
                <div
                  className="relative flex shrink-0"
                  style={{ width: `${timelineWidth}px` }}
                >
                  {todayOffset ? (
                    <div
                      aria-hidden="true"
                      className="pointer-events-none absolute bottom-0 top-0 z-20 w-0.5 bg-app-danger"
                      style={{ left: todayOffset }}
                    />
                  ) : null}
                  {barStyle ? (
                    <button
                      type="button"
                      aria-label={taskDetailLabel}
                      className={cn(
                        'app-text-micro group/gantt-bar absolute top-1/2 z-10 flex h-6 -translate-y-1/2 items-center overflow-hidden rounded-full border bg-app-accent px-2 font-bold text-app-accent-fg shadow-sm',
                        editable && 'cursor-grab active:cursor-grabbing',
                        !editable && onSelectIssue && 'cursor-pointer',
                        dragging?.taskId === task.id &&
                          'ring-2 ring-app-accent/40',
                      )}
                      onClick={(event) => handleBarClick(event, effectiveTask)}
                      onMouseDown={(event) =>
                        handleBarMouseDown(event, effectiveTask, 'move')
                      }
                      title={taskDetailLabel}
                      style={{ ...barStyle, ...statusBarStyle }}
                    >
                      {editable ? (
                        <span
                          aria-label={t('pms.gantt.resizeStart', {
                            title: task.title,
                          })}
                          className="absolute inset-y-0 left-0 w-2 cursor-ew-resize rounded-l-full bg-white/0 transition-colors group-hover/gantt-bar:bg-white/35"
                          onMouseDown={(event) =>
                            handleBarMouseDown(
                              event,
                              effectiveTask,
                              'resize-start',
                            )
                          }
                          onClick={stopResizeHandleClick}
                          role="separator"
                          title={t('pms.gantt.resizeStart', {
                            title: task.title,
                          })}
                        />
                      ) : null}
                      <span className="min-w-0 truncate px-1">
                        {statusLabel}
                      </span>
                      {editable ? (
                        <span
                          aria-label={t('pms.gantt.resizeEnd', {
                            title: task.title,
                          })}
                          className="absolute inset-y-0 right-0 w-2 cursor-ew-resize rounded-r-full bg-white/0 transition-colors group-hover/gantt-bar:bg-white/35"
                          onMouseDown={(event) =>
                            handleBarMouseDown(
                              event,
                              effectiveTask,
                              'resize-end',
                            )
                          }
                          onClick={stopResizeHandleClick}
                          role="separator"
                          title={t('pms.gantt.resizeEnd', {
                            title: task.title,
                          })}
                        />
                      ) : null}
                    </button>
                  ) : null}
                  {dates.map((date) => (
                    <div
                      key={toGanttDateOnly(date)}
                      className={cn(
                        'h-12 flex-shrink-0 border-r border-app-border last:border-r-0',
                        toGanttDateOnly(date) === todayDateOnly &&
                          'bg-app-danger/5',
                      )}
                      style={{ width: `${dayWidth}px` }}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
