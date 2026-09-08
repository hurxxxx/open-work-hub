import {
  formatNativeDateInputParts,
  formatNativeDateTimeInputValue,
  NATIVE_DATE_INPUT_VALUE_RE,
  normalizeNativeDateInputValue,
  normalizeNativeDateTimeInputValue,
  parseNativeDateInputValue,
} from '@/src/platform/time/native-date-input';
import {
  type DateFormatPreference,
  formatDateOnly,
  normalizeDateFormatPreference,
  readStoredDateFormatPreference,
} from '@/src/platform/time/time-utils';

interface DateParts {
  day: number;
  month: number;
  year: number;
}

const COMPACT_DATE_RE = /^(\d{4})(\d{2})(\d{2})$/;
const TIME_RE = /^(\d{1,2}):(\d{2})$/;
const YEAR_FIRST_DATE_RE =
  /^(\d{4})\s*(?:[-/.]|\s|\uB144)\s*(\d{1,2})\s*(?:[-/.]|\s|\uC6D4)\s*(\d{1,2})\s*(?:[.]|\uC77C)?$/;

function isValidDateParts(parts: DateParts): boolean {
  const date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  return (
    parts.year > 0 &&
    date.getUTCFullYear() === parts.year &&
    date.getUTCMonth() === parts.month - 1 &&
    date.getUTCDate() === parts.day
  );
}

function toIsoDate(parts: DateParts): string | null {
  if (!isValidDateParts(parts)) return null;
  return formatNativeDateInputParts(parts);
}

function parseDateParts(match: RegExpMatchArray): DateParts {
  return {
    day: Number(match[3]),
    month: Number(match[2]),
    year: Number(match[1]),
  };
}

export function normalizeDateFormat(
  value: DateFormatPreference | string | null | undefined,
): DateFormatPreference {
  return value === null || value === undefined
    ? readStoredDateFormatPreference()
    : normalizeDateFormatPreference(value);
}

export function normalizeDateInputText(
  input: string,
  dateFormat: DateFormatPreference,
  locale: string,
): string | null {
  const trimmed = input.trim();
  if (!trimmed) return '';

  const compactMatch = trimmed.match(COMPACT_DATE_RE);
  if (compactMatch) return toIsoDate(parseDateParts(compactMatch));

  const yearFirstMatch = trimmed.match(YEAR_FIRST_DATE_RE);
  if (yearFirstMatch) return toIsoDate(parseDateParts(yearFirstMatch));

  const slashParts = trimmed.split('/');
  if (slashParts.length === 3 && slashParts.every(Boolean)) {
    const left = Number(slashParts[0]);
    const middle = Number(slashParts[1]);
    const year = Number(slashParts[2]);
    const preferEuropean =
      dateFormat === 'european' ||
      (dateFormat === 'locale' && !locale.startsWith('en-US'));
    const day = preferEuropean ? left : middle;
    const month = preferEuropean ? middle : left;
    return toIsoDate({ day, month, year });
  }

  return null;
}

export function normalizeDateTimeInputText(
  input: string,
  dateFormat: DateFormatPreference,
  locale: string,
): string | null {
  const trimmed = input.trim();
  if (!trimmed) return '';

  const dateTimeMatch = trimmed
    .replace('T', ' ')
    .match(/^(.*)\s+(\d{1,2}:\d{2})$/);
  if (!dateTimeMatch) return null;
  const [, datePart, timePart] = dateTimeMatch;
  const normalizedDate = normalizeDateInputText(datePart, dateFormat, locale);
  const timeMatch = timePart?.match(TIME_RE);
  if (normalizedDate === null || !timeMatch) return null;

  const hour = Number(timeMatch[1]);
  const minute = Number(timeMatch[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  const date = parseNativeDateInputValue(normalizedDate);
  date.setHours(hour, minute, 0, 0);
  return formatNativeDateTimeInputValue(date);
}

export function formatDateInputText(
  value: string | null | undefined,
  dateFormat: DateFormatPreference,
  locale: string,
): string {
  if (!value?.match(NATIVE_DATE_INPUT_VALUE_RE)) return '';
  return formatDateOnly(value, {
    dateFormat,
    fallback: '',
    locale,
  });
}

export function formatDateTimeInputText(
  value: string | null | undefined,
  dateFormat: DateFormatPreference,
  locale: string,
): string {
  if (!value) return '';
  const [datePart, timePart] = value.split('T');
  if (!datePart || !timePart?.match(TIME_RE)) return '';
  return `${formatDateInputText(datePart, dateFormat, locale)} ${timePart}`;
}

export function datePlaceholderForFormat(
  dateFormat: DateFormatPreference,
  locale: string,
): string {
  switch (dateFormat) {
    case 'iso':
      return 'YYYY-MM-DD';
    case 'us':
      return 'MM/DD/YYYY';
    case 'european':
      return 'DD/MM/YYYY';
    case 'locale':
      return locale.startsWith('en-US') ? 'MM/DD/YYYY' : 'YYYY. M. D.';
    case 'korean':
      return 'YYYY. M. D.';
  }
}

export function dateTimePlaceholderForFormat(
  dateFormat: DateFormatPreference,
  locale: string,
): string {
  return `${datePlaceholderForFormat(dateFormat, locale)} HH:mm`;
}

export function normalizeDateValue(value: string | null | undefined): string {
  return normalizeNativeDateInputValue(value);
}

export function normalizeDateTimeValue(
  value: string | null | undefined,
): string {
  return normalizeNativeDateTimeInputValue(value);
}
