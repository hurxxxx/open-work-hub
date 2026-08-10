import { describe, expect, it } from 'vitest';

import {
  DEFAULT_TIME_ZONE,
  formatDateTimeWithPreference,
  formatRelativeTimeWithPreference,
  formatDateOnlyWithPreference,
  normalizeTimeZone,
} from './zoned-date-formatter';

describe('zoned-date-formatter', () => {
  it('falls back to the default timezone for invalid timezone names', () => {
    expect(normalizeTimeZone('not-a-zone')).toBe(DEFAULT_TIME_ZONE);
  });

  it('formats without reading browser date format preferences', () => {
    expect(
      formatDateOnlyWithPreference('2026-05-02', {
        dateFormat: 'iso',
      }),
    ).toBe('2026-05-02');
    expect(
      formatDateTimeWithPreference('2026-05-01T18:30:00Z', {
        dateFormat: 'us',
        timeZone: 'Asia/Seoul',
      }),
    ).toBe('05/02/2026');
  });

  it('includes the year for relative fallback dates outside the current year', () => {
    expect(
      formatRelativeTimeWithPreference('2025-12-31T15:00:00Z', {
        dateFormat: 'locale',
        locale: 'en-US',
        now: '2026-01-10T00:00:00Z',
        timeZone: 'UTC',
      }),
    ).toBe('Dec 31, 2025');
  });
});
