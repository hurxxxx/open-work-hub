export interface NativeDateInputParts {
  day: number;
  month: number;
  year: number;
}

export const NATIVE_DATE_INPUT_VALUE_RE = /^\d{4}-\d{2}-\d{2}$/;
export const NATIVE_DATE_TIME_INPUT_VALUE_RE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

function padNativeInputPart(value: number): string {
  return String(value).padStart(2, '0');
}

export function formatNativeDateInputParts(
  parts: NativeDateInputParts,
): string {
  return `${parts.year}-${padNativeInputPart(parts.month)}-${padNativeInputPart(parts.day)}`;
}

export function formatNativeDateInputValue(date: Date): string {
  return formatNativeDateInputParts({
    day: date.getDate(),
    month: date.getMonth() + 1,
    year: date.getFullYear(),
  });
}

export function formatNativeDateTimeInputValue(date: Date): string {
  return `${formatNativeDateInputValue(date)}T${padNativeInputPart(date.getHours())}:${padNativeInputPart(date.getMinutes())}`;
}

export function parseNativeDateInputValue(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function addLocalCalendarDays(date: Date, days: number): Date {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

export function addNativeDateInputDays(value: string, days: number): string {
  return formatNativeDateInputValue(
    addLocalCalendarDays(parseNativeDateInputValue(value), days),
  );
}

export function normalizeNativeDateInputValue(
  value: string | null | undefined,
): string {
  return value?.match(NATIVE_DATE_INPUT_VALUE_RE) ? value : '';
}

export function normalizeNativeDateTimeInputValue(
  value: string | null | undefined,
): string {
  return value?.match(NATIVE_DATE_TIME_INPUT_VALUE_RE) ? value : '';
}

export function nativeDateTimeInputValueToIso(value: string): string {
  return new Date(value).toISOString();
}
