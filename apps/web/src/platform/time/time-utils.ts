export const DEFAULT_TIME_ZONE = 'Asia/Seoul';

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
  { value: 'Asia/Singapore', labelKey: 'auth:settings.timeZones.asiaSingapore' },
] as const;

type TemporalInput = Date | number | string | null | undefined;

interface ZonedFormatOptions extends Intl.DateTimeFormatOptions {
  fallback?: string;
  locale?: string;
}

interface RelativeTimeOptions {
  fallback?: string;
  locale?: string;
  now?: TemporalInput;
  timeZone?: string;
}

const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const TZ_MARKER_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

export function normalizeTimeZone(value: string | null | undefined): string {
  const candidate = value?.trim() || DEFAULT_TIME_ZONE;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: candidate }).format(new Date(0));
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
  const date = new Date(TZ_MARKER_RE.test(trimmed) || DATE_ONLY_RE.test(trimmed) ? trimmed : `${trimmed}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function parseDateOnlyParts(value: string | null | undefined): { year: number; month: number; day: number } | null {
  const match = value?.match(DATE_ONLY_RE);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

export function getZonedDateParts(
  value: TemporalInput = new Date(),
  timeZone = DEFAULT_TIME_ZONE,
): { year: number; month: number; day: number; hour: number; minute: number } | null {
  const date = parseApiDateTime(value);
  if (!date) return null;
  const parts = new Intl.DateTimeFormat('en-US', {
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23',
    minute: '2-digit',
    month: '2-digit',
    timeZone: normalizeTimeZone(timeZone),
    year: 'numeric',
  }).formatToParts(date);
  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, Number(part.value)]),
  );
  return {
    year: values.year,
    month: values.month,
    day: values.day,
    hour: values.hour,
    minute: values.minute,
  };
}

export function zonedDateKey(value: TemporalInput = new Date(), timeZone = DEFAULT_TIME_ZONE): string {
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
  const valueTime = Date.UTC(valueParts.year, valueParts.month - 1, valueParts.day);
  const baseTime = Date.UTC(baseParts.year, baseParts.month - 1, baseParts.day);
  return Math.round((valueTime - baseTime) / 86_400_000);
}

export function formatDateOnly(
  value: string | null | undefined,
  options: ZonedFormatOptions = {},
): string {
  const parts = parseDateOnlyParts(value);
  if (!parts) return options.fallback ?? '';
  const {
    fallback: _fallback,
    locale = 'ko-KR',
    timeZone: _timeZone,
    ...formatOptions
  } = options;
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
    ...formatOptions,
  }).format(new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12)));
}

export function formatDateTime(
  value: TemporalInput,
  options: ZonedFormatOptions = {},
): string {
  const date = parseApiDateTime(value);
  if (!date) return options.fallback ?? '';
  const {
    fallback: _fallback,
    locale = 'ko-KR',
    timeZone = DEFAULT_TIME_ZONE,
    ...formatOptions
  } = options;
  return new Intl.DateTimeFormat(locale, {
    timeZone: normalizeTimeZone(timeZone),
    ...formatOptions,
  }).format(date);
}

export function formatRelativeTime(value: TemporalInput, options: RelativeTimeOptions = {}): string {
  const date = parseApiDateTime(value);
  if (!date) return options.fallback ?? '';

  const locale = options.locale ?? 'en';
  const timeZone = normalizeTimeZone(options.timeZone);
  const nowDate = options.now === undefined ? new Date() : parseApiDateTime(options.now);
  const nowMs = nowDate?.getTime() ?? Date.now();
  const diffMs = date.getTime() - nowMs;
  const absMs = Math.abs(diffMs);
  if (absMs < 60_000) {
    return locale.startsWith('ko') ? '\ubc29\uae08 \uc804' : 'just now';
  }

  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (absMs < 3_600_000) return rtf.format(Math.round(diffMs / 60_000), 'minute');
  if (absMs < 86_400_000) return rtf.format(Math.round(diffMs / 3_600_000), 'hour');
  if (absMs < 604_800_000) return rtf.format(Math.round(diffMs / 86_400_000), 'day');

  const dateParts = getZonedDateParts(date, timeZone);
  const nowParts = getZonedDateParts(nowDate ?? new Date(), timeZone);
  return formatDateTime(date, {
    day: 'numeric',
    locale,
    month: 'short',
    timeZone,
    year: dateParts && nowParts && dateParts.year === nowParts.year ? undefined : 'numeric',
  });
}
