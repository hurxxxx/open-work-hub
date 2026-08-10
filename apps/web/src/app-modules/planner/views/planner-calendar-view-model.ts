export type PlannerViewMode = 'Month' | 'Week' | 'Day' | 'Agenda';
export type PlannerSurfaceMode = 'calendar' | 'timeline';

export const TIMELINE_RANGE_OPTIONS = [14, 28, 56] as const;
export type TimelineRangeDays = (typeof TIMELINE_RANGE_OPTIONS)[number];

export const DEFAULT_TIMELINE_RANGE_DAYS: TimelineRangeDays = 28;

const TIMELINE_RANGE_STORAGE_KEY = 'open-work-hub:planner-timeline-range-days';
type PlannerDateFormatterKind =
  | 'timelineStartSameYear'
  | 'timelineStartWithYear'
  | 'timelineEnd'
  | 'dayHeading'
  | 'monthHeading'
  | 'monthYear'
  | 'weekdayNarrow';
const PLANNER_DATE_FORMATTERS = new Map<string, Intl.DateTimeFormat>();
const PlannerDateTimeFormat = Intl.DateTimeFormat;

export type PlannerDatePickerCell =
  | {
      kind: 'blank';
      key: string;
    }
  | {
      kind: 'day';
      key: string;
      day: number;
      date: Date;
      isSelected: boolean;
      isSunday: boolean;
      isToday: boolean;
      holidayNames: readonly string[] | null;
    };

export function formatLocalYmd(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

export function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

function startOfWeek(date: Date): Date {
  return addDays(startOfLocalDay(date), -startOfLocalDay(date).getDay());
}

function isTimelineRangeDays(value: number): value is TimelineRangeDays {
  return TIMELINE_RANGE_OPTIONS.includes(value as TimelineRangeDays);
}

export function readTimelineRangeDays(): TimelineRangeDays {
  if (typeof window === 'undefined') {
    return DEFAULT_TIMELINE_RANGE_DAYS;
  }

  try {
    const rawValue = window.localStorage.getItem(TIMELINE_RANGE_STORAGE_KEY);
    const parsedValue = rawValue ? Number(rawValue) : NaN;
    return isTimelineRangeDays(parsedValue)
      ? parsedValue
      : DEFAULT_TIMELINE_RANGE_DAYS;
  } catch {
    return DEFAULT_TIMELINE_RANGE_DAYS;
  }
}

export function persistTimelineRangeDays(days: TimelineRangeDays) {
  try {
    window.localStorage.setItem(TIMELINE_RANGE_STORAGE_KEY, String(days));
  } catch {
    // Ignore storage failures; the selected range still applies in memory.
  }
}

export function getPlannerDateFormatter(
  locale: string,
  kind: PlannerDateFormatterKind,
): Intl.DateTimeFormat {
  const key = `${locale}:${kind}`;
  const cached = PLANNER_DATE_FORMATTERS.get(key);
  if (cached) return cached;
  const options: Intl.DateTimeFormatOptions =
    kind === 'timelineStartSameYear'
      ? { day: 'numeric', month: 'short' }
      : kind === 'timelineStartWithYear' || kind === 'timelineEnd'
        ? { day: 'numeric', month: 'short', year: 'numeric' }
        : kind === 'dayHeading'
          ? { day: 'numeric', month: 'long', year: 'numeric' }
          : kind === 'monthHeading' || kind === 'monthYear'
            ? { month: 'long', year: 'numeric' }
            : { weekday: 'narrow' };
  const formatter = new PlannerDateTimeFormat(locale, options);
  PLANNER_DATE_FORMATTERS.set(key, formatter);
  return formatter;
}

export function buildInitialPlannerRange(
  currentDate: Date,
  viewMode: PlannerViewMode,
  surfaceMode: PlannerSurfaceMode,
  timelineRangeDays = DEFAULT_TIMELINE_RANGE_DAYS,
): { currentDate: Date; rangeStart: string; rangeEnd: string } {
  const current = startOfLocalDay(currentDate);
  if (surfaceMode === 'timeline') {
    const rangeStart = startOfWeek(current);
    return {
      currentDate: current,
      rangeStart: formatLocalYmd(rangeStart),
      rangeEnd: formatLocalYmd(addDays(rangeStart, timelineRangeDays)),
    };
  }
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

function parseLocalYmd(value: string): Date | null {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) {
    return null;
  }
  return new Date(year, month - 1, day);
}

function formatTimelineHeading(
  rangeStart: string,
  rangeEnd: string,
  locale: string,
): string {
  const start = parseLocalYmd(rangeStart);
  const exclusiveEnd = parseLocalYmd(rangeEnd);
  if (!start || !exclusiveEnd) {
    return '';
  }
  const end = addDays(exclusiveEnd, -1);
  const formatter = getPlannerDateFormatter(
    locale,
    start.getFullYear() === end.getFullYear()
      ? 'timelineStartSameYear'
      : 'timelineStartWithYear',
  );
  const startLabel = formatter.format(start);
  const endLabel = getPlannerDateFormatter(locale, 'timelineEnd').format(end);
  return `${startLabel} - ${endLabel}`;
}

export function formatPlannerHeading(
  viewMode: PlannerViewMode,
  currentDate: Date,
  locale: string,
  surfaceMode: PlannerSurfaceMode,
  rangeStart: string,
  rangeEnd: string,
): string {
  if (surfaceMode === 'timeline') {
    return formatTimelineHeading(rangeStart, rangeEnd, locale);
  }
  if (viewMode === 'Day') {
    return getPlannerDateFormatter(locale, 'dayHeading').format(currentDate);
  }
  return getPlannerDateFormatter(locale, 'monthHeading').format(currentDate);
}

export function buildPlannerDatePickerGrid(args: {
  pickerYear: number;
  pickerMonth: number;
  viewYear: number;
  viewMonth: number;
  selectedDate: number;
  today: Date;
  getHolidayNames: (
    year: number,
    month: number,
    day: number,
  ) => readonly string[] | null;
}): PlannerDatePickerCell[] {
  const leadingBlanks = new Date(args.pickerYear, args.pickerMonth, 1).getDay();
  const daysInMonth = new Date(args.pickerYear, args.pickerMonth + 1, 0).getDate();

  return Array.from({ length: 42 }, (_, index): PlannerDatePickerCell => {
    const day = index - leadingBlanks + 1;
    if (day < 1 || day > daysInMonth) {
      return {
        kind: 'blank',
        key: `blank-${args.pickerYear}-${args.pickerMonth}-${index}`,
      };
    }

    const date = new Date(args.pickerYear, args.pickerMonth, day);
    return {
      kind: 'day',
      key: `${args.pickerYear}-${args.pickerMonth}-${day}`,
      day,
      date,
      isSelected:
        args.pickerYear === args.viewYear
        && args.pickerMonth === args.viewMonth
        && day === args.selectedDate,
      isSunday: date.getDay() === 0,
      isToday:
        args.pickerYear === args.today.getFullYear()
        && args.pickerMonth === args.today.getMonth()
        && day === args.today.getDate(),
      holidayNames: args.getHolidayNames(args.pickerYear, args.pickerMonth, day),
    };
  });
}
