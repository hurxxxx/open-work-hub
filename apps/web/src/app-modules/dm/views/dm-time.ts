import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

export function formatDmMessageTime(
  value: string,
  locale: string,
  timeZone: string | null | undefined,
): string {
  return formatDateTime(value, {
    fallback: value,
    hour: '2-digit',
    locale,
    minute: '2-digit',
    timeZone: normalizeTimeZone(timeZone),
  });
}
