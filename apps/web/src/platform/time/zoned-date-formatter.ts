export const DEFAULT_TIME_ZONE = 'Asia/Seoul';
const DEFAULT_DATE_DISPLAY_LOCALE = 'ko-KR';
export const DATE_DISPLAY_LOCALE = DEFAULT_DATE_DISPLAY_LOCALE;
export const DEFAULT_DATE_FORMAT = 'korean';

export type DateFormatPreference =
  | 'korean'
  | 'iso'
  | 'us'
  | 'european'
  | 'locale';

export type TemporalInput = Date | number | string | null | undefined;

export interface ZonedFormatOptions extends Intl.DateTimeFormatOptions {
  dateFormat?: DateFormatPreference | string | null;
  fallback?: string;
  locale?: string;
}

export interface RelativeTimeOptions {
  dateFormat?: DateFormatPreference | string | null;
  fallback?: string;
  locale?: string;
  now?: TemporalInput;
  timeZone?: string;
}

export interface ResolvedZonedFormatOptions extends Intl.DateTimeFormatOptions {
  dateFormat: DateFormatPreference;
  fallback?: string;
  locale?: string;
}

export interface ResolvedRelativeTimeOptions {
  dateFormat: DateFormatPreference;
  fallback?: string;
  locale?: string;
  now?: TemporalInput;
  timeZone?: string;
}

export const TIME_ZONE_OPTIONS = [
  { value: 'Asia/Seoul', labelKey: 'auth:settings.timeZones.asiaSeoul' },
  { value: 'UTC', labelKey: 'auth:settings.timeZones.utc' },
  { value: 'America/Los_Angeles', labelKey: 'auth:settings.timeZones.pacific' },
  { value: 'America/Denver', labelKey: 'auth:settings.timeZones.mountain' },
  { value: 'America/Chicago', labelKey: 'auth:settings.timeZones.central' },
  { value: 'America/New_York', labelKey: 'auth:settings.timeZones.eastern' },
  { value: 'Europe/London', labelKey: 'auth:settings.timeZones.london' },
  { value: 'Europe/Berlin', labelKey: 'auth:settings.timeZones.centralEurope' },
  { value: 'Asia/Tokyo', labelKey: 'auth:settings.timeZones.asiaTokyo' },
  {
    value: 'Asia/Singapore',
    labelKey: 'auth:settings.timeZones.asiaSingapore',
  },
] as const;

export const DATE_FORMAT_OPTIONS: Array<{
  value: DateFormatPreference;
  labelKey: string;
}> = [
  { value: 'korean', labelKey: 'auth:settings.dateFormats.korean' },
  { value: 'iso', labelKey: 'auth:settings.dateFormats.iso' },
  { value: 'us', labelKey: 'auth:settings.dateFormats.us' },
  { value: 'european', labelKey: 'auth:settings.dateFormats.european' },
  { value: 'locale', labelKey: 'auth:settings.dateFormats.locale' },
];

const DATE_FORMAT_OPTION_KEYS = [
  'dateStyle',
  'day',
  'era',
  'month',
  'weekday',
  'year',
] as const;
const DATE_COMPONENT_OPTION_KEYS = [
  'day',
  'era',
  'month',
  'weekday',
  'year',
] as const;
const TIME_FORMAT_OPTION_KEYS = [
  'dayPeriod',
  'fractionalSecondDigits',
  'hour',
  'minute',
  'second',
  'timeStyle',
  'timeZoneName',
] as const;
const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const TZ_MARKER_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;
const dateTimeFormatterCache = new Map<string, Intl.DateTimeFormat>();
const relativeTimeFormatterCache = new Map<string, Intl.RelativeTimeFormat>();

function stableFormatOptionsKey(options: Intl.DateTimeFormatOptions): string {
  return JSON.stringify(
    Object.entries(options)
      .filter(
        (entry): entry is [string, string | number | boolean] =>
          entry[1] !== undefined,
      )
      .sort(([left], [right]) => left.localeCompare(right)),
  );
}

function getDateTimeFormatter(
  locale: string,
  options: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormat {
  const key = `${locale}|${stableFormatOptionsKey(options)}`;
  const cached = dateTimeFormatterCache.get(key);
  if (cached) {
    return cached;
  }
  const formatter = Intl.DateTimeFormat(locale, options);
  dateTimeFormatterCache.set(key, formatter);
  return formatter;
}

function getRelativeTimeFormatter(locale: string): Intl.RelativeTimeFormat {
  const cached = relativeTimeFormatterCache.get(locale);
  if (cached) {
    return cached;
  }
  const formatter = Reflect.construct(Intl.RelativeTimeFormat, [
    locale,
    { numeric: 'auto' },
  ]) as Intl.RelativeTimeFormat;
  relativeTimeFormatterCache.set(locale, formatter);
  return formatter;
}

export function normalizeDateFormatPreference(
  value: string | null | undefined,
): DateFormatPreference {
  return DATE_FORMAT_OPTIONS.some((option) => option.value === value)
    ? (value as DateFormatPreference)
    : DEFAULT_DATE_FORMAT;
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

function hasOwnFormatOption(
  options: Intl.DateTimeFormatOptions,
  key: keyof Intl.DateTimeFormatOptions,
): boolean {
  return (
    Object.prototype.hasOwnProperty.call(options, key) &&
    options[key] !== undefined
  );
}

function hasAnyFormatOption(
  options: Intl.DateTimeFormatOptions,
  keys: readonly (keyof Intl.DateTimeFormatOptions)[],
): boolean {
  return keys.some((key) => hasOwnFormatOption(options, key));
}

function isValidDateParts(year: number, month: number, day: number): boolean {
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return false;
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

function formatDateParts(
  parts: { year: number; month: number; day: number },
  dateFormat: DateFormatPreference,
): string {
  switch (dateFormat) {
    case 'iso':
      return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`;
    case 'us':
      return `${pad2(parts.month)}/${pad2(parts.day)}/${parts.year}`;
    case 'european':
      return `${pad2(parts.day)}/${pad2(parts.month)}/${parts.year}`;
    case 'korean':
      return `${parts.year}. ${parts.month}. ${parts.day}.`;
    case 'locale':
      return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`;
  }
}

function splitFormatOptions(options: Intl.DateTimeFormatOptions) {
  const dateOptions: Intl.DateTimeFormatOptions = {};
  const timeOptions: Intl.DateTimeFormatOptions = {};
  const otherOptions: Intl.DateTimeFormatOptions = {};

  Object.entries(options).forEach(([key, value]) => {
    if (value === undefined) return;
    const typedKey = key as keyof Intl.DateTimeFormatOptions;
    if ((DATE_FORMAT_OPTION_KEYS as readonly string[]).includes(key)) {
      (dateOptions as Record<string, unknown>)[typedKey] = value;
    } else if ((TIME_FORMAT_OPTION_KEYS as readonly string[]).includes(key)) {
      (timeOptions as Record<string, unknown>)[typedKey] = value;
    } else {
      (otherOptions as Record<string, unknown>)[typedKey] = value;
    }
  });

  return { dateOptions, otherOptions, timeOptions };
}

function resolveDateDisplayLocale(
  locale: string | undefined,
  options: Intl.DateTimeFormatOptions = {},
  defaultIncludesDate = false,
): string {
  const hasDateOption = hasAnyFormatOption(options, DATE_FORMAT_OPTION_KEYS);
  const hasTimeOption = hasAnyFormatOption(options, TIME_FORMAT_OPTION_KEYS);
  return hasDateOption || (defaultIncludesDate && !hasTimeOption) || locale
    ? (locale ?? DEFAULT_DATE_DISPLAY_LOCALE)
    : DEFAULT_DATE_DISPLAY_LOCALE;
}

export function normalizeTimeZone(value: string | null | undefined): string {
  const candidate = value?.trim() || DEFAULT_TIME_ZONE;
  try {
    getDateTimeFormatter('en-US', { timeZone: candidate }).format(new Date(0));
    return candidate;
  } catch {
    return DEFAULT_TIME_ZONE;
  }
}

export function parseApiDateTime(value: TemporalInput): Date | null {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) {
    const date = new Date(value.getTime());
    return Number.isNaN(date.getTime()) ? null : date;
  }
  if (typeof value === 'number') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const trimmed = value.trim();
  if (!trimmed) return null;
  const date = new Date(
    TZ_MARKER_RE.test(trimmed) || DATE_ONLY_RE.test(trimmed)
      ? trimmed
      : `${trimmed}Z`,
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

export function parseDateOnlyParts(
  value: string | null | undefined,
): { year: number; month: number; day: number } | null {
  const match = value?.match(DATE_ONLY_RE);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!isValidDateParts(year, month, day)) return null;
  return { year, month, day };
}

export function getZonedDateParts(
  value: TemporalInput = new Date(),
  timeZone = DEFAULT_TIME_ZONE,
): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
} | null {
  const date = parseApiDateTime(value);
  if (!date) return null;
  const parts = getDateTimeFormatter('en-US', {
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23',
    minute: '2-digit',
    month: '2-digit',
    timeZone: normalizeTimeZone(timeZone),
    year: 'numeric',
  }).formatToParts(date);
  const values = parts.reduce<Record<string, number>>((result, part) => {
    if (part.type !== 'literal') {
      result[part.type] = Number(part.value);
    }
    return result;
  }, {});
  return {
    year: values.year,
    month: values.month,
    day: values.day,
    hour: values.hour,
    minute: values.minute,
  };
}

export function zonedDateKey(
  value: TemporalInput = new Date(),
  timeZone = DEFAULT_TIME_ZONE,
): string {
  const parts = getZonedDateParts(value, timeZone);
  if (!parts) return '';
  return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`;
}

export function isSameDateInTimeZone(
  left: TemporalInput,
  right: TemporalInput = new Date(),
  timeZone = DEFAULT_TIME_ZONE,
): boolean {
  return zonedDateKey(left, timeZone) === zonedDateKey(right, timeZone);
}

export function diffDateOnlyDays(
  value: string | null | undefined,
  baseValue: string,
): number | null {
  const valueParts = parseDateOnlyParts(value);
  const baseParts = parseDateOnlyParts(baseValue);
  if (!valueParts || !baseParts) return null;
  const valueTime = Date.UTC(
    valueParts.year,
    valueParts.month - 1,
    valueParts.day,
  );
  const baseTime = Date.UTC(baseParts.year, baseParts.month - 1, baseParts.day);
  return Math.round((valueTime - baseTime) / 86_400_000);
}

export function formatDateOnlyWithPreference(
  value: string | null | undefined,
  options: ResolvedZonedFormatOptions,
): string {
  const parts = parseDateOnlyParts(value);
  if (!parts) return options.fallback ?? '';
  const {
    dateFormat,
    fallback: _fallback,
    locale = DEFAULT_DATE_DISPLAY_LOCALE,
    timeZone: _timeZone,
    ...formatOptions
  } = options;
  const hasDateComponentOption = hasAnyFormatOption(
    formatOptions,
    DATE_COMPONENT_OPTION_KEYS,
  );
  if (dateFormat !== 'locale' && !hasDateComponentOption) {
    return formatDateParts(parts, dateFormat);
  }
  const displayLocale = resolveDateDisplayLocale(locale, formatOptions, true);
  const defaultDateOptions = hasAnyFormatOption(
    formatOptions,
    DATE_FORMAT_OPTION_KEYS,
  )
    ? {}
    : ({
        day: 'numeric',
        month: 'numeric',
        year: 'numeric',
      } satisfies Intl.DateTimeFormatOptions);
  return getDateTimeFormatter(displayLocale, {
    timeZone: 'UTC',
    ...defaultDateOptions,
    ...formatOptions,
  }).format(new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12)));
}

export function formatDateTimeWithPreference(
  value: TemporalInput,
  options: ResolvedZonedFormatOptions,
): string {
  const date = parseApiDateTime(value);
  if (!date) return options.fallback ?? '';
  const {
    dateFormat,
    fallback: _fallback,
    locale = DEFAULT_DATE_DISPLAY_LOCALE,
    timeZone = DEFAULT_TIME_ZONE,
    ...formatOptions
  } = options;
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  const hasDateComponentOption = hasAnyFormatOption(
    formatOptions,
    DATE_COMPONENT_OPTION_KEYS,
  );
  if (dateFormat !== 'locale' && !hasDateComponentOption) {
    const parts = getZonedDateParts(date, resolvedTimeZone);
    if (!parts) return options.fallback ?? '';
    const { otherOptions, timeOptions } = splitFormatOptions(formatOptions);
    const dateText = formatDateParts(parts, dateFormat);
    const hasDateOption = hasAnyFormatOption(
      formatOptions,
      DATE_FORMAT_OPTION_KEYS,
    );
    const hasTimeOption = hasAnyFormatOption(
      timeOptions,
      TIME_FORMAT_OPTION_KEYS,
    );
    if (!hasTimeOption) return dateText;
    const timeText = getDateTimeFormatter(locale, {
      ...otherOptions,
      ...timeOptions,
      timeZone: resolvedTimeZone,
    }).format(date);
    return hasDateOption ? `${dateText} ${timeText}` : timeText;
  }
  const displayLocale = resolveDateDisplayLocale(locale, formatOptions, true);
  return getDateTimeFormatter(displayLocale, {
    timeZone: resolvedTimeZone,
    ...formatOptions,
  }).format(date);
}

export function formatRelativeTimeWithPreference(
  value: TemporalInput,
  options: ResolvedRelativeTimeOptions,
): string {
  const date = parseApiDateTime(value);
  if (!date) return options.fallback ?? '';

  const locale = options.locale ?? DEFAULT_DATE_DISPLAY_LOCALE;
  const timeZone = normalizeTimeZone(options.timeZone);
  const nowDate =
    options.now === undefined ? new Date() : parseApiDateTime(options.now);
  const nowMs = nowDate?.getTime() ?? Date.now();
  const diffMs = date.getTime() - nowMs;
  const absMs = Math.abs(diffMs);
  if (absMs < 60_000) {
    return locale.startsWith('ko') ? '\ubc29\uae08 \uc804' : 'just now';
  }

  const rtf = getRelativeTimeFormatter(locale);
  if (absMs < 3_600_000)
    return rtf.format(Math.round(diffMs / 60_000), 'minute');
  if (absMs < 86_400_000)
    return rtf.format(Math.round(diffMs / 3_600_000), 'hour');
  if (absMs < 604_800_000)
    return rtf.format(Math.round(diffMs / 86_400_000), 'day');

  const dateParts = getZonedDateParts(date, timeZone);
  const nowParts = getZonedDateParts(nowDate ?? new Date(), timeZone);
  return formatDateTimeWithPreference(date, {
    dateFormat: options.dateFormat,
    day: 'numeric',
    locale,
    month: 'short',
    timeZone,
    year:
      dateParts && nowParts && dateParts.year === nowParts.year
        ? undefined
        : 'numeric',
  });
}
