import { describe, expect, it } from 'vitest';

import {
  diffDateOnlyDays,
  formatDateOnly,
  formatDateTime,
  formatRelativeTime,
  isSameDateInTimeZone,
  parseApiDateTime,
} from './time-utils';

describe('time-utils', () => {
  it('parses timezone-less API datetimes as UTC', () => {
    expect(parseApiDateTime('2026-05-02T03:00:00')?.toISOString()).toBe('2026-05-02T03:00:00.000Z');
    expect(formatRelativeTime('2026-05-02T03:00:00', {
      now: '2026-05-02T03:00:30Z',
      timeZone: 'Asia/Seoul',
    })).toBe('just now');
  });

  it('formats API datetimes in the requested timezone', () => {
    expect(formatDateTime('2026-05-02T03:00:00', {
      hour: '2-digit',
      hourCycle: 'h23',
      locale: 'ko-KR',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
    })).toBe('12:00');
  });

  it('keeps date-only values on their calendar date', () => {
    expect(formatDateOnly('2026-05-02', {
      day: 'numeric',
      locale: 'en-US',
      month: 'short',
      timeZone: 'America/Los_Angeles',
    })).toBe('May 2');
    expect(diffDateOnlyDays('2026-05-02', '2026-05-01')).toBe(1);
  });

  it('compares instants by a named timezone calendar day', () => {
    expect(isSameDateInTimeZone(
      '2026-05-01T16:00:00Z',
      '2026-05-02T01:00:00+09:00',
      'Asia/Seoul',
    )).toBe(true);
  });
});
