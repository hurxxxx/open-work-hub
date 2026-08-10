export function defaultTimedRange(now = new Date()): { start: Date; end: Date } {
  const start = new Date(now);
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime());
  end.setHours(end.getHours() + 1);
  return { start, end };
}

export function copyDateWithTime(date: Date, timeSource: Date): Date {
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
    timeSource.getHours(),
    timeSource.getMinutes(),
    0,
    0,
  );
}

export function defaultTimedRangeForDate(
  date: Date,
  now = new Date(),
): { start: Date; end: Date } {
  const defaultRange = defaultTimedRange(now);
  return {
    start: copyDateWithTime(date, defaultRange.start),
    end: copyDateWithTime(date, defaultRange.end),
  };
}
