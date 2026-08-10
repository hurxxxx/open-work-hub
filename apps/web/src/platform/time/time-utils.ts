import {
  formatDateOnlyWithPreference,
  formatDateTimeWithPreference,
  formatRelativeTimeWithPreference,
  normalizeDateFormatPreference,
  normalizeTimeZone,
  type DateFormatPreference,
  type RelativeTimeOptions,
  type TemporalInput,
  type ZonedFormatOptions,
} from './zoned-date-formatter';
import { readStoredDateFormatPreference } from './date-format-preference-store';
import { readStoredTimeZonePreference } from './time-zone-preference-store';

export {
  DATE_DISPLAY_LOCALE,
  DATE_FORMAT_OPTIONS,
  DEFAULT_TIME_ZONE,
  TIME_ZONE_OPTIONS,
  diffDateOnlyDays,
  getZonedDateParts,
  isSameDateInTimeZone,
  normalizeDateFormatPreference,
  normalizeTimeZone,
  parseApiDateTime,
  parseDateOnlyParts,
  zonedDateKey,
} from './zoned-date-formatter';
export type {
  DateFormatPreference,
  RelativeTimeOptions,
  TemporalInput,
  ZonedFormatOptions,
} from './zoned-date-formatter';
export {
  DATE_FORMAT_STORAGE_KEY,
  readStoredDateFormatPreference,
  syncDateFormatPreference,
} from './date-format-preference-store';
export {
  readStoredTimeZonePreference,
  syncTimeZonePreference,
  TIME_ZONE_STORAGE_KEY,
} from './time-zone-preference-store';

function resolveDateFormat(
  value: string | null | undefined,
): DateFormatPreference {
  return value === null || value === undefined
    ? readStoredDateFormatPreference()
    : normalizeDateFormatPreference(value);
}

function resolveTimeZone(value: string | null | undefined): string {
  return value === null || value === undefined
    ? readStoredTimeZonePreference()
    : normalizeTimeZone(value);
}

export function formatDateOnly(
  value: string | null | undefined,
  options: ZonedFormatOptions = {},
): string {
  return formatDateOnlyWithPreference(value, {
    ...options,
    dateFormat: resolveDateFormat(options.dateFormat),
  });
}

export function formatDateTime(
  value: TemporalInput,
  options: ZonedFormatOptions = {},
): string {
  return formatDateTimeWithPreference(value, {
    ...options,
    dateFormat: resolveDateFormat(options.dateFormat),
    timeZone: resolveTimeZone(options.timeZone),
  });
}

export function formatRelativeTime(
  value: TemporalInput,
  options: RelativeTimeOptions = {},
): string {
  return formatRelativeTimeWithPreference(value, {
    ...options,
    dateFormat: resolveDateFormat(options.dateFormat),
    timeZone: resolveTimeZone(options.timeZone),
  });
}
