import {
  DEFAULT_TIME_ZONE,
  normalizeTimeZone,
} from './zoned-date-formatter';

export const TIME_ZONE_STORAGE_KEY = 'ai-do:time-zone';

export function readStoredTimeZonePreference(): string {
  if (typeof window === 'undefined') return DEFAULT_TIME_ZONE;
  try {
    return normalizeTimeZone(window.localStorage.getItem(TIME_ZONE_STORAGE_KEY));
  } catch {
    return DEFAULT_TIME_ZONE;
  }
}

function persistTimeZonePreference(timeZone: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TIME_ZONE_STORAGE_KEY, timeZone);
  } catch {
    return;
  }
}

export function syncTimeZonePreference(
  value: string | null | undefined,
): string {
  const normalized = normalizeTimeZone(value);
  persistTimeZonePreference(normalized);
  return normalized;
}
