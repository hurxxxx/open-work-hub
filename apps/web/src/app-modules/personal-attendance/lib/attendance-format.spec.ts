import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  businessDays,
  calendarDateParts,
  datesInRange,
  isWeekend,
  todayYmd,
  weekStartKey,
} from './attendance-format';

describe('attendance calendar date helpers', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps date-only values stable across runtime timezones', () => {
    expect(calendarDateParts('2026-07-30')).toEqual({
      year: 2026,
      month: 7,
      day: 30,
      weekday: 4,
    });
    expect(weekStartKey('2026-07-30')).toBe('2026-7-26');
    expect(datesInRange('2026-07-30', '2026-08-02')).toEqual([
      '2026-07-30',
      '2026-07-31',
      '2026-08-01',
      '2026-08-02',
    ]);
    expect(isWeekend('2026-08-01')).toBe(true);
    expect(isWeekend('2026-08-03')).toBe(false);
    expect(businessDays('2026-07-30', '2026-08-03')).toBe(3);
  });

  it('uses the Korea business date at the UTC day boundary', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-30T15:30:00Z'));

    expect(todayYmd()).toBe('2026-07-31');
  });
});
