import { describe, expect, it } from 'vitest';

import {
  addDaysToDateInputValue,
  buildUsageDateRangePreset,
  DEFAULT_USAGE_PERIOD_PRESET,
  getKstDateInputValue,
  getUsagePeriodPresetOptions,
  normalizeUsageDateRange,
} from './admin-usage-period-model';

describe('admin usage period model', () => {
  it('offers day, week, month, and year presets in the usage dashboard filter', () => {
    const options = getUsagePeriodPresetOptions((key) => `translated:${key}`);

    expect(options).toEqual([
      {
        value: 'day',
        label: 'translated:admin.console.usage.periodPresets.day',
      },
      {
        value: 'week',
        label: 'translated:admin.console.usage.periodPresets.week',
      },
      {
        value: 'month',
        label: 'translated:admin.console.usage.periodPresets.month',
      },
      {
        value: 'year',
        label: 'translated:admin.console.usage.periodPresets.year',
      },
    ]);
  });

  it('defaults the dashboard period to a one-week date range', () => {
    expect(DEFAULT_USAGE_PERIOD_PRESET).toBe('week');
    expect(buildUsageDateRangePreset(DEFAULT_USAGE_PERIOD_PRESET, '2026-06-19')).toEqual({
      fromDate: '2026-06-12',
      toDate: '2026-06-19',
    });
  });

  it('builds dashboard date ranges from presets', () => {
    expect(buildUsageDateRangePreset('day', '2026-06-19')).toEqual({
      fromDate: '2026-06-19',
      toDate: '2026-06-19',
    });
    expect(buildUsageDateRangePreset('month', '2026-06-19')).toEqual({
      fromDate: '2026-05-20',
      toDate: '2026-06-19',
    });
    expect(buildUsageDateRangePreset('year', '2026-06-19')).toEqual({
      fromDate: '2025-06-19',
      toDate: '2026-06-19',
    });
  });

  it('uses KST when formatting today for date inputs', () => {
    expect(getKstDateInputValue(new Date('2026-06-18T15:10:00.000Z'))).toBe(
      '2026-06-19',
    );
  });

  it('adds days using date input semantics', () => {
    expect(addDaysToDateInputValue('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('normalizes invalid or future date ranges', () => {
    expect(
      normalizeUsageDateRange(
        { fromDate: '2026-06-20', toDate: '2026-06-19' },
        '2026-06-19',
      ),
    ).toEqual({
      fromDate: '2026-06-19',
      toDate: '2026-06-19',
    });
    expect(
      normalizeUsageDateRange(
        { fromDate: 'invalid', toDate: '2026-06-25' },
        '2026-06-19',
      ),
    ).toEqual({
      fromDate: '2026-06-19',
      toDate: '2026-06-19',
    });
  });
});
