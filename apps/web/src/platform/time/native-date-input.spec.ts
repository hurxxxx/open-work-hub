import { describe, expect, it } from 'vitest';

import {
  addLocalCalendarDays,
  addNativeDateInputDays,
  formatNativeDateInputParts,
  formatNativeDateInputValue,
  formatNativeDateTimeInputValue,
  nativeDateTimeInputValueToIso,
  normalizeNativeDateInputValue,
  normalizeNativeDateTimeInputValue,
  parseNativeDateInputValue,
} from './native-date-input';

describe('native-date-input', () => {
  it('formats native date and datetime input values from local date parts', () => {
    expect(formatNativeDateInputParts({ day: 3, month: 2, year: 2026 })).toBe(
      '2026-02-03',
    );
    expect(formatNativeDateInputValue(new Date(2026, 3, 8, 0, 30))).toBe(
      '2026-04-08',
    );
    expect(formatNativeDateTimeInputValue(new Date(2026, 1, 3, 9, 5))).toBe(
      '2026-02-03T09:05',
    );
  });

  it('parses and shifts native date input values by local calendar days', () => {
    expect(parseNativeDateInputValue('2026-02-03')).toEqual(
      new Date(2026, 1, 3),
    );
    expect(addLocalCalendarDays(new Date(2026, 1, 28, 23, 30), 1)).toEqual(
      new Date(2026, 2, 1),
    );
    expect(addNativeDateInputDays('2026-02-28', 1)).toBe('2026-03-01');
    expect(addNativeDateInputDays('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('normalizes native values by input syntax', () => {
    expect(normalizeNativeDateInputValue('2026-05-26')).toBe('2026-05-26');
    expect(normalizeNativeDateInputValue('2026-5-26')).toBe('');
    expect(normalizeNativeDateTimeInputValue('2026-05-26T09:05')).toBe(
      '2026-05-26T09:05',
    );
    expect(normalizeNativeDateTimeInputValue('2026-05-26 09:05')).toBe('');
  });

  it('converts native datetime input values from local time to ISO instants', () => {
    expect(nativeDateTimeInputValueToIso('2026-03-10T09:30')).toBe(
      new Date('2026-03-10T09:30').toISOString(),
    );
  });
});
