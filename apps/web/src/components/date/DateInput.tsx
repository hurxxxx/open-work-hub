import type {
  ChangeEvent,
  CSSProperties,
  FocusEvent,
  InputHTMLAttributes,
  KeyboardEvent,
} from 'react';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import {
  formatNativeDateInputParts,
  parseNativeDateInputValue,
} from '@/src/platform/time/native-date-input';
import {
  DATE_DISPLAY_LOCALE,
  type DateFormatPreference,
} from '@/src/platform/time/time-utils';
import {
  datePlaceholderForFormat,
  dateTimePlaceholderForFormat,
  formatDateInputText,
  formatDateTimeInputText,
  normalizeDateFormat,
  normalizeDateInputText,
  normalizeDateTimeInputText,
  normalizeDateTimeValue,
  normalizeDateValue,
} from './date-input-model';

interface BaseDateInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    'inputMode' | 'onChange' | 'placeholder' | 'type' | 'value'
  > {
  dateFormat?: DateFormatPreference | string | null;
  locale?: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  value: string | null | undefined;
}

interface CalendarCell {
  day: number;
  isoDate: string;
}

interface CalendarPosition {
  left: number;
  top: number;
}

interface CalendarPickerPositionInput {
  anchorRect: Pick<DOMRect, 'bottom' | 'right' | 'top'>;
  calendarHeight: number;
  viewportHeight: number;
  viewportWidth: number;
}

type CalendarPickerMode = 'date' | 'datetime';

const CALENDAR_WIDTH = 288;
const DATE_CALENDAR_ESTIMATED_HEIGHT = 340;
const DATE_TIME_CALENDAR_ESTIMATED_HEIGHT = 408;
const CALENDAR_GUTTER = 4;
const VIEWPORT_PADDING = 8;
const DATE_PICKER_LAYER_SELECTOR = '[data-ai-do-date-picker]';
const DEFAULT_TIME_VALUE = '09:00';

function isDatePickerLayerTarget(target: Node | null): boolean {
  return (
    target instanceof Element &&
    target.closest(DATE_PICKER_LAYER_SELECTOR) !== null
  );
}

export function resolveCalendarPickerPosition({
  anchorRect,
  calendarHeight,
  viewportHeight,
  viewportWidth,
}: CalendarPickerPositionInput): CalendarPosition {
  const maxLeft = Math.max(
    VIEWPORT_PADDING,
    viewportWidth - CALENDAR_WIDTH - VIEWPORT_PADDING,
  );
  const left = Math.min(
    Math.max(VIEWPORT_PADDING, anchorRect.right - CALENDAR_WIDTH),
    maxLeft,
  );
  const belowTop = anchorRect.bottom + CALENDAR_GUTTER;
  const aboveTop = anchorRect.top - calendarHeight - CALENDAR_GUTTER;
  const preferredTop =
    belowTop + calendarHeight <= viewportHeight - VIEWPORT_PADDING ||
    aboveTop < VIEWPORT_PADDING
      ? belowTop
      : aboveTop;
  const maxTop = Math.max(
    VIEWPORT_PADDING,
    viewportHeight - calendarHeight - VIEWPORT_PADDING,
  );
  return {
    left,
    top: Math.min(Math.max(VIEWPORT_PADDING, preferredTop), maxTop),
  };
}

function DatePickerShell({
  className,
  disabled,
  displayValue,
  inputProps,
  mode,
  selectedDateValue,
  selectedTimeValue,
  onBlur,
  onCalendarSelect,
  onDisplayCommit,
  onDisplayChange,
  onFocus,
  pickerLabel,
  placeholder,
  resolvedLocale,
  labels,
}: {
  className?: string;
  disabled?: boolean;
  displayValue: string;
  inputProps: Omit<
    BaseDateInputProps,
    'dateFormat' | 'locale' | 'onValueChange' | 'placeholder' | 'value'
  >;
  mode: CalendarPickerMode;
  selectedDateValue: string;
  selectedTimeValue?: string;
  onBlur: (event: FocusEvent<HTMLInputElement>) => void;
  onCalendarSelect: (value: string) => void;
  onDisplayCommit: () => void;
  onDisplayChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onFocus?: (event: FocusEvent<HTMLInputElement>) => void;
  pickerLabel: string;
  placeholder: string;
  resolvedLocale: string;
  labels: {
    done: string;
    hour: string;
    minute: string;
    nextHour: string;
    nextMinute: string;
    month: string;
    previousHour: string;
    previousMinute: string;
    nextMonth: string;
    previousMonth: string;
    year: string;
  };
}) {
  const rootRef = useRef<HTMLSpanElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() =>
    initialCalendarMonth(selectedDateValue),
  );
  const [draftDateValue, setDraftDateValue] = useState(selectedDateValue);
  const [draftTimeValue, setDraftTimeValue] = useState(() =>
    normalizeTimeValue(selectedTimeValue),
  );
  const [calendarPosition, setCalendarPosition] = useState<CalendarPosition>({
    left: VIEWPORT_PADDING,
    top: VIEWPORT_PADDING,
  });
  const calendarCells = useMemo(
    () => buildCalendarCells(visibleMonth),
    [visibleMonth],
  );
  const monthLabels = useMemo(
    () => buildMonthLabels(resolvedLocale),
    [resolvedLocale],
  );
  const weekdayLabels = useMemo(
    () => buildWeekdayLabels(resolvedLocale),
    [resolvedLocale],
  );
  const todayValue = useMemo(() => localDateToNativeValue(new Date()), []);

  const updateCalendarPosition = useCallback(() => {
    const root = rootRef.current;
    if (!root || typeof window === 'undefined') return;
    const rect = root.getBoundingClientRect();
    const viewportWidth =
      window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight;
    const estimatedHeight =
      mode === 'datetime'
        ? DATE_TIME_CALENDAR_ESTIMATED_HEIGHT
        : DATE_CALENDAR_ESTIMATED_HEIGHT;
    const calendarHeight =
      calendarRef.current?.getBoundingClientRect().height ?? estimatedHeight;
    setCalendarPosition({
      ...resolveCalendarPickerPosition({
        anchorRect: rect,
        calendarHeight,
        viewportHeight,
        viewportWidth,
      }),
    });
  }, [mode]);

  const toggleCalendar = () => {
    if (disabled) return;
    setVisibleMonth(initialCalendarMonth(selectedDateValue));
    setDraftDateValue(selectedDateValue);
    setDraftTimeValue(normalizeTimeValue(selectedTimeValue));
    setPickerOpen((open) => !open);
  };
  const calendarStyle: CSSProperties = {
    left: calendarPosition.left,
    pointerEvents: 'auto',
    top: calendarPosition.top,
    width: CALENDAR_WIDTH,
  };

  useLayoutEffect(() => {
    if (!pickerOpen) return undefined;
    updateCalendarPosition();
    window.addEventListener('resize', updateCalendarPosition);
    document.addEventListener('scroll', updateCalendarPosition, true);
    return () => {
      window.removeEventListener('resize', updateCalendarPosition);
      document.removeEventListener('scroll', updateCalendarPosition, true);
    };
  }, [pickerOpen, updateCalendarPosition]);

  useEffect(() => {
    if (!pickerOpen) return undefined;
    function closeOnOutsideMouseDown(event: MouseEvent) {
      const target = event.target as Node | null;
      if (
        target &&
        (rootRef.current?.contains(target) || isDatePickerLayerTarget(target))
      ) {
        return;
      }
      setPickerOpen(false);
    }
    document.addEventListener('mousedown', closeOnOutsideMouseDown);
    return () =>
      document.removeEventListener('mousedown', closeOnOutsideMouseDown);
  }, [pickerOpen]);

  return (
    <span ref={rootRef} className="relative block w-full">
      <input
        {...inputProps}
        className={cn(
          'w-full pr-9 placeholder:text-app-ink/35 disabled:cursor-not-allowed disabled:opacity-60',
          className,
        )}
        disabled={disabled}
        inputMode="numeric"
        onBlur={onBlur}
        onChange={onDisplayChange}
        onFocus={onFocus}
        onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
          inputProps.onKeyDown?.(event);
          if (event.defaultPrevented) return;
          if (event.key === 'Escape' && pickerOpen) {
            event.preventDefault();
            setPickerOpen(false);
            return;
          }
          if (event.key !== 'Enter') return;
          event.preventDefault();
          onDisplayCommit();
        }}
        placeholder={placeholder}
        type="text"
        value={displayValue}
      />
      <button
        aria-expanded={pickerOpen}
        aria-label={pickerLabel}
        className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-md text-app-ink/45 transition-colors hover:text-app-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent disabled:cursor-not-allowed disabled:opacity-60"
        disabled={disabled}
        onClick={toggleCalendar}
        title={pickerLabel}
        type="button"
      >
        <CalendarDays aria-hidden="true" className="size-4" />
      </button>
      {pickerOpen && typeof document !== 'undefined'
        ? createPortal(
            <div
              aria-label={pickerLabel}
              className="fixed z-[10000] w-72 rounded-lg border border-app-border bg-app-bg p-3 text-app-ink shadow-xl"
              data-ai-do-date-picker=""
              data-ui-floating-layer=""
              ref={calendarRef}
              onKeyDown={(event) => {
                if (event.key !== 'Escape') return;
                event.preventDefault();
                setPickerOpen(false);
              }}
              role="dialog"
              style={calendarStyle}
            >
              <div className="mb-3 flex items-center gap-1">
                <button
                  aria-label={labels.previousMonth}
                  className="flex size-8 shrink-0 items-center justify-center rounded-md text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
                  onClick={() =>
                    setVisibleMonth(addCalendarMonths(visibleMonth, -1))
                  }
                  title={labels.previousMonth}
                  type="button"
                >
                  <ChevronLeft aria-hidden="true" className="size-4" />
                </button>
                <select
                  aria-label={labels.month}
                  className="app-field-input-sm min-w-0 flex-1"
                  onChange={(event) =>
                    setVisibleMonth(
                      new Date(
                        visibleMonth.getFullYear(),
                        Number(event.target.value),
                        1,
                      ),
                    )
                  }
                  value={visibleMonth.getMonth()}
                >
                  {monthLabels.map((label, month) => (
                    <option key={month} value={month}>
                      {label}
                    </option>
                  ))}
                </select>
                <input
                  aria-label={labels.year}
                  className="app-text-body-sm w-20 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5 text-app-ink focus:border-app-accent focus:outline-none"
                  max={9999}
                  min={1}
                  onChange={(event) => {
                    const year = Number(event.target.value);
                    if (!Number.isInteger(year) || year < 1 || year > 9999)
                      return;
                    setVisibleMonth(new Date(year, visibleMonth.getMonth(), 1));
                  }}
                  type="number"
                  value={visibleMonth.getFullYear()}
                />
                <button
                  aria-label={labels.nextMonth}
                  className="flex size-8 shrink-0 items-center justify-center rounded-md text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
                  onClick={() =>
                    setVisibleMonth(addCalendarMonths(visibleMonth, 1))
                  }
                  title={labels.nextMonth}
                  type="button"
                >
                  <ChevronRight aria-hidden="true" className="size-4" />
                </button>
              </div>
              <div className="grid grid-cols-7 gap-1">
                {weekdayLabels.map((label) => (
                  <div
                    className="app-text-caption flex h-7 items-center justify-center text-app-ink/65"
                    key={label}
                  >
                    {label}
                  </div>
                ))}
                {calendarCells.map((cell, index) =>
                  cell ? (
                    <button
                      aria-label={formatCalendarDayLabel(
                        cell.isoDate,
                        resolvedLocale,
                      )}
                      className={cn(
                        'app-text-caption flex size-8 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent',
                        cell.isoDate === draftDateValue
                          ? 'bg-app-accent text-app-accent-fg hover:bg-app-accent-hover'
                          : cell.isoDate === todayValue
                            ? 'border border-app-accent text-app-accent hover:bg-app-accent/10'
                            : 'text-app-ink hover:bg-app-surface-hover',
                      )}
                      key={cell.isoDate}
                      onClick={() => {
                        if (mode === 'date') {
                          onCalendarSelect(cell.isoDate);
                          setPickerOpen(false);
                          return;
                        }
                        setDraftDateValue(cell.isoDate);
                      }}
                      type="button"
                    >
                      {cell.day}
                    </button>
                  ) : (
                    <span
                      aria-hidden="true"
                      className="size-8"
                      key={`blank-${index}`}
                    />
                  ),
                )}
              </div>
              {mode === 'datetime' ? (
                <div className="mt-3 border-t border-app-border pt-3">
                  <div className="grid gap-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="grid gap-1">
                        <span className="app-text-caption text-app-ink/70">
                          {labels.hour}
                        </span>
                        <div className="grid grid-cols-[2rem_1fr_2rem] overflow-hidden rounded-md border border-app-border bg-app-surface-sidebar">
                          <button
                            aria-label={labels.previousHour}
                            className="flex items-center justify-center text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                            onClick={() =>
                              setDraftTimeValue(
                                addTimeHours(draftTimeValue, -1),
                              )
                            }
                            type="button"
                          >
                            <ChevronDown
                              aria-hidden="true"
                              className="size-4"
                            />
                          </button>
                          <div className="app-text-body-sm flex h-8 items-center justify-center text-app-ink">
                            {draftTimeValue.slice(0, 2)}
                          </div>
                          <button
                            aria-label={labels.nextHour}
                            className="flex items-center justify-center text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                            onClick={() =>
                              setDraftTimeValue(addTimeHours(draftTimeValue, 1))
                            }
                            type="button"
                          >
                            <ChevronUp aria-hidden="true" className="size-4" />
                          </button>
                        </div>
                      </div>
                      <div className="grid gap-1">
                        <span className="app-text-caption text-app-ink/70">
                          {labels.minute}
                        </span>
                        <div className="grid grid-cols-[2rem_1fr_2rem] overflow-hidden rounded-md border border-app-border bg-app-surface-sidebar">
                          <button
                            aria-label={labels.previousMinute}
                            className="flex items-center justify-center text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                            onClick={() =>
                              setDraftTimeValue(
                                addTimeMinutes(draftTimeValue, -5),
                              )
                            }
                            type="button"
                          >
                            <ChevronDown
                              aria-hidden="true"
                              className="size-4"
                            />
                          </button>
                          <div className="app-text-body-sm flex h-8 items-center justify-center text-app-ink">
                            {draftTimeValue.slice(3, 5)}
                          </div>
                          <button
                            aria-label={labels.nextMinute}
                            className="flex items-center justify-center text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                            onClick={() =>
                              setDraftTimeValue(
                                addTimeMinutes(draftTimeValue, 5),
                              )
                            }
                            type="button"
                          >
                            <ChevronUp aria-hidden="true" className="size-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                    <button
                      className="app-text-control-sm rounded-md bg-app-accent px-3 py-2 text-app-accent-fg transition-colors hover:bg-app-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={!draftDateValue}
                      onClick={() => {
                        if (!draftDateValue) return;
                        onCalendarSelect(`${draftDateValue}T${draftTimeValue}`);
                        setPickerOpen(false);
                      }}
                      type="button"
                    >
                      {labels.done}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

function initialCalendarMonth(nativeValue: string): Date {
  const date = nativeValue
    ? parseNativeDateInputValue(nativeValue)
    : new Date();
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addCalendarMonths(month: Date, offset: number): Date {
  return new Date(month.getFullYear(), month.getMonth() + offset, 1);
}

function localDateToNativeValue(date: Date): string {
  return formatNativeDateInputParts({
    day: date.getDate(),
    month: date.getMonth() + 1,
    year: date.getFullYear(),
  });
}

function buildCalendarCells(month: Date): Array<CalendarCell | null> {
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const firstDay = new Date(year, monthIndex, 1).getDay();
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const cells: Array<CalendarCell | null> = [];
  for (let index = 0; index < firstDay; index += 1) {
    cells.push(null);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({
      day,
      isoDate: localDateToNativeValue(new Date(year, monthIndex, day)),
    });
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  return cells;
}

function buildMonthLabels(locale: string): string[] {
  const formatter = new Intl.DateTimeFormat(locale, { month: 'short' });
  return Array.from({ length: 12 }, (_, month) =>
    formatter.format(new Date(2026, month, 1)),
  );
}

function buildWeekdayLabels(locale: string): string[] {
  const formatter = new Intl.DateTimeFormat(locale, { weekday: 'short' });
  return Array.from({ length: 7 }, (_, day) =>
    formatter.format(new Date(2026, 5, 7 + day)),
  );
}

function formatCalendarDayLabel(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'full' }).format(
    parseNativeDateInputValue(value),
  );
}

function normalizeTimeValue(value: string | undefined): string {
  return value?.match(/^\d{2}:\d{2}$/) ? value : DEFAULT_TIME_VALUE;
}

function addTimeHours(value: string, offset: number): string {
  const hour = (Number(value.slice(0, 2)) + offset + 24) % 24;
  return `${String(hour).padStart(2, '0')}:${value.slice(3, 5)}`;
}

function addTimeMinutes(value: string, offset: number): string {
  const totalMinutes =
    (Number(value.slice(0, 2)) * 60 +
      Number(value.slice(3, 5)) +
      offset +
      24 * 60) %
    (24 * 60);
  const hour = Math.floor(totalMinutes / 60);
  const minute = totalMinutes % 60;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function splitDateTimeValue(value: string): { date: string; time: string } {
  const [date = '', time] = value.split('T');
  return {
    date,
    time: normalizeTimeValue(time),
  };
}

export function DateInput({
  className,
  dateFormat,
  disabled,
  locale,
  onBlur,
  onFocus,
  onValueChange,
  placeholder,
  value,
  ...inputProps
}: BaseDateInputProps) {
  const { i18n, t } = useTranslation('common');
  const resolvedLocale = locale ?? i18n.language ?? DATE_DISPLAY_LOCALE;
  const resolvedDateFormat = normalizeDateFormat(dateFormat);
  const nativeValue = normalizeDateValue(value);
  const externalDisplayValue = useMemo(
    () => formatDateInputText(nativeValue, resolvedDateFormat, resolvedLocale),
    [nativeValue, resolvedDateFormat, resolvedLocale],
  );

  return (
    <DateInputDraft
      key={`${nativeValue}:${resolvedDateFormat}:${resolvedLocale}`}
      className={className}
      disabled={disabled}
      initialDisplayValue={externalDisplayValue}
      inputProps={inputProps}
      nativeValue={nativeValue}
      onBlur={onBlur}
      onFocus={onFocus}
      onValueChange={onValueChange}
      placeholder={
        placeholder ??
        datePlaceholderForFormat(resolvedDateFormat, resolvedLocale)
      }
      resolvedDateFormat={resolvedDateFormat}
      resolvedLocale={resolvedLocale}
      labels={{
        done: t('actions.done'),
        hour: t('date.hour'),
        minute: t('date.minute'),
        nextHour: t('date.nextHour'),
        nextMinute: t('date.nextMinute'),
        month: t('date.month'),
        previousHour: t('date.previousHour'),
        previousMinute: t('date.previousMinute'),
        nextMonth: t('date.nextMonth'),
        previousMonth: t('date.previousMonth'),
        year: t('date.year'),
      }}
      pickerLabel={t('date.chooseDate')}
    />
  );
}

function DateInputDraft({
  className,
  disabled,
  initialDisplayValue,
  inputProps,
  nativeValue,
  onBlur,
  onFocus,
  onValueChange,
  pickerLabel,
  placeholder,
  resolvedDateFormat,
  resolvedLocale,
  labels,
}: {
  className?: string;
  disabled?: boolean;
  initialDisplayValue: string;
  inputProps: Omit<
    BaseDateInputProps,
    'dateFormat' | 'locale' | 'onValueChange' | 'placeholder' | 'value'
  >;
  nativeValue: string;
  onBlur?: (event: FocusEvent<HTMLInputElement>) => void;
  onFocus?: (event: FocusEvent<HTMLInputElement>) => void;
  onValueChange: (value: string) => void;
  pickerLabel: string;
  placeholder: string;
  resolvedDateFormat: DateFormatPreference;
  resolvedLocale: string;
  labels: {
    done: string;
    hour: string;
    minute: string;
    nextHour: string;
    nextMinute: string;
    month: string;
    previousHour: string;
    previousMinute: string;
    nextMonth: string;
    previousMonth: string;
    year: string;
  };
}) {
  const [draft, setDraft] = useState(initialDisplayValue);

  const commitDraft = () => {
    const normalized = normalizeDateInputText(
      draft,
      resolvedDateFormat,
      resolvedLocale,
    );
    setDraft(
      formatDateInputText(
        normalized ?? nativeValue,
        resolvedDateFormat,
        resolvedLocale,
      ),
    );
    if (normalized !== null && normalized !== nativeValue)
      onValueChange(normalized);
  };

  return (
    <DatePickerShell
      className={className}
      disabled={disabled}
      displayValue={draft}
      inputProps={inputProps}
      mode="date"
      selectedDateValue={nativeValue}
      onBlur={(event) => {
        commitDraft();
        onBlur?.(event);
      }}
      onCalendarSelect={(value) => {
        onValueChange(value);
        setDraft(
          formatDateInputText(value, resolvedDateFormat, resolvedLocale),
        );
      }}
      onDisplayCommit={commitDraft}
      onDisplayChange={(event) => {
        setDraft(event.target.value);
      }}
      onFocus={onFocus}
      pickerLabel={pickerLabel}
      placeholder={placeholder}
      resolvedLocale={resolvedLocale}
      labels={labels}
    />
  );
}

export function DateTimeInput({
  className,
  dateFormat,
  disabled,
  locale,
  onBlur,
  onFocus,
  onValueChange,
  placeholder,
  value,
  ...inputProps
}: BaseDateInputProps) {
  const { i18n, t } = useTranslation('common');
  const resolvedLocale = locale ?? i18n.language ?? DATE_DISPLAY_LOCALE;
  const resolvedDateFormat = normalizeDateFormat(dateFormat);
  const nativeValue = normalizeDateTimeValue(value);
  const externalDisplayValue = useMemo(
    () =>
      formatDateTimeInputText(nativeValue, resolvedDateFormat, resolvedLocale),
    [nativeValue, resolvedDateFormat, resolvedLocale],
  );

  return (
    <DateTimeInputDraft
      key={`${nativeValue}:${resolvedDateFormat}:${resolvedLocale}`}
      className={className}
      disabled={disabled}
      initialDisplayValue={externalDisplayValue}
      inputProps={inputProps}
      nativeValue={nativeValue}
      onBlur={onBlur}
      onFocus={onFocus}
      onValueChange={onValueChange}
      placeholder={
        placeholder ??
        dateTimePlaceholderForFormat(resolvedDateFormat, resolvedLocale)
      }
      resolvedDateFormat={resolvedDateFormat}
      resolvedLocale={resolvedLocale}
      labels={{
        done: t('actions.done'),
        hour: t('date.hour'),
        minute: t('date.minute'),
        nextHour: t('date.nextHour'),
        nextMinute: t('date.nextMinute'),
        month: t('date.month'),
        previousHour: t('date.previousHour'),
        previousMinute: t('date.previousMinute'),
        nextMonth: t('date.nextMonth'),
        previousMonth: t('date.previousMonth'),
        year: t('date.year'),
      }}
      pickerLabel={t('date.chooseDateTime')}
    />
  );
}

function DateTimeInputDraft({
  className,
  disabled,
  initialDisplayValue,
  inputProps,
  nativeValue,
  onBlur,
  onFocus,
  onValueChange,
  pickerLabel,
  placeholder,
  resolvedDateFormat,
  resolvedLocale,
  labels,
}: {
  className?: string;
  disabled?: boolean;
  initialDisplayValue: string;
  inputProps: Omit<
    BaseDateInputProps,
    'dateFormat' | 'locale' | 'onValueChange' | 'placeholder' | 'value'
  >;
  nativeValue: string;
  onBlur?: (event: FocusEvent<HTMLInputElement>) => void;
  onFocus?: (event: FocusEvent<HTMLInputElement>) => void;
  onValueChange: (value: string) => void;
  pickerLabel: string;
  placeholder: string;
  resolvedDateFormat: DateFormatPreference;
  resolvedLocale: string;
  labels: {
    done: string;
    hour: string;
    minute: string;
    nextHour: string;
    nextMinute: string;
    month: string;
    previousHour: string;
    previousMinute: string;
    nextMonth: string;
    previousMonth: string;
    year: string;
  };
}) {
  const [draft, setDraft] = useState(initialDisplayValue);
  const dateTimeParts = splitDateTimeValue(nativeValue);

  const commitDraft = () => {
    const normalized = normalizeDateTimeInputText(
      draft,
      resolvedDateFormat,
      resolvedLocale,
    );
    setDraft(
      formatDateTimeInputText(
        normalized ?? nativeValue,
        resolvedDateFormat,
        resolvedLocale,
      ),
    );
    if (normalized !== null && normalized !== nativeValue)
      onValueChange(normalized);
  };

  return (
    <DatePickerShell
      className={className}
      disabled={disabled}
      displayValue={draft}
      inputProps={inputProps}
      mode="datetime"
      selectedDateValue={dateTimeParts.date}
      selectedTimeValue={dateTimeParts.time}
      onBlur={(event) => {
        commitDraft();
        onBlur?.(event);
      }}
      onCalendarSelect={(value) => {
        onValueChange(value);
        setDraft(
          formatDateTimeInputText(value, resolvedDateFormat, resolvedLocale),
        );
      }}
      onDisplayCommit={commitDraft}
      onDisplayChange={(event) => {
        setDraft(event.target.value);
      }}
      onFocus={onFocus}
      pickerLabel={pickerLabel}
      placeholder={placeholder}
      resolvedLocale={resolvedLocale}
      labels={labels}
    />
  );
}
