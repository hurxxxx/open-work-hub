import {
  DEFAULT_DATE_FORMAT,
  type DateFormatPreference,
  normalizeDateFormatPreference,
} from './zoned-date-formatter';

export const DATE_FORMAT_STORAGE_KEY = 'open-work-hub:date-format';

export function readStoredDateFormatPreference(): DateFormatPreference {
  if (typeof window === 'undefined') return DEFAULT_DATE_FORMAT;
  try {
    return normalizeDateFormatPreference(
      window.localStorage.getItem(DATE_FORMAT_STORAGE_KEY),
    );
  } catch {
    return DEFAULT_DATE_FORMAT;
  }
}

function persistDateFormatPreference(dateFormat: DateFormatPreference): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, dateFormat);
  } catch {
    return;
  }
}

export function syncDateFormatPreference(
  value: string | null | undefined,
): DateFormatPreference {
  const normalized = normalizeDateFormatPreference(value);
  persistDateFormatPreference(normalized);
  return normalized;
}
