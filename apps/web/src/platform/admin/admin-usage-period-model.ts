type Translate = (key: string) => string;

export type UsagePeriodPreset = 'day' | 'week' | 'month' | 'year';

export interface UsageDateRange {
  fromDate: string;
  toDate: string;
}

export const DEFAULT_USAGE_PERIOD_PRESET: UsagePeriodPreset = 'week';
export const USAGE_DASHBOARD_TIME_ZONE = 'Asia/Seoul';

const presetStartOffsets: Record<UsagePeriodPreset, number> = {
  day: 0,
  week: -7,
  month: -30,
  year: -365,
};

export function getUsagePeriodPresetOptions(
  t: Translate,
): { value: UsagePeriodPreset; label: string }[] {
  return [
    { value: 'day', label: t('admin.console.usage.periodPresets.day') },
    { value: 'week', label: t('admin.console.usage.periodPresets.week') },
    { value: 'month', label: t('admin.console.usage.periodPresets.month') },
    { value: 'year', label: t('admin.console.usage.periodPresets.year') },
  ];
}

function formatDateInputValue(value: Date): string {
  const year = value.getUTCFullYear();
  const month = String(value.getUTCMonth() + 1).padStart(2, '0');
  const day = String(value.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function parseDateInputValue(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  return date;
}

export function getKstDateInputValue(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    day: '2-digit',
    month: '2-digit',
    timeZone: USAGE_DASHBOARD_TIME_ZONE,
    year: 'numeric',
  }).formatToParts(now);
  const valueByType = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${valueByType.year}-${valueByType.month}-${valueByType.day}`;
}

export function addDaysToDateInputValue(value: string, days: number): string {
  const date = parseDateInputValue(value);
  if (!date) {
    return value;
  }
  date.setUTCDate(date.getUTCDate() + days);
  return formatDateInputValue(date);
}

export function buildUsageDateRangePreset(
  preset: UsagePeriodPreset,
  today = getKstDateInputValue(),
): UsageDateRange {
  return {
    fromDate: addDaysToDateInputValue(today, presetStartOffsets[preset]),
    toDate: today,
  };
}

export function normalizeUsageDateRange(
  range: UsageDateRange,
  today = getKstDateInputValue(),
): UsageDateRange {
  const todayDate = parseDateInputValue(today) ? today : getKstDateInputValue();
  const parsedToDate = parseDateInputValue(range.toDate);
  const parsedFromDate = parseDateInputValue(range.fromDate);
  const toDate =
    parsedToDate && range.toDate <= todayDate ? range.toDate : todayDate;
  const fromDate = parsedFromDate ? range.fromDate : toDate;
  if (fromDate > toDate) {
    return { fromDate: toDate, toDate };
  }
  return { fromDate, toDate };
}
