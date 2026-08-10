import { beforeEach, describe, expect, it } from 'vitest';

import {
  DATE_FORMAT_STORAGE_KEY,
  TIME_ZONE_STORAGE_KEY,
  diffDateOnlyDays,
  formatDateOnly,
  formatDateTime,
  formatRelativeTime,
  isSameDateInTimeZone,
  parseApiDateTime,
} from './time-utils';

describe('time-utils', () => {
  beforeEach(() => {
    window.localStorage.removeItem(DATE_FORMAT_STORAGE_KEY);
    window.localStorage.removeItem(TIME_ZONE_STORAGE_KEY);
  });

  it('parses timezone-less API datetimes as UTC', () => {
    expect(parseApiDateTime('2026-05-02T03:00:00')?.toISOString()).toBe('2026-05-02T03:00:00.000Z');
    expect(formatRelativeTime('2026-05-02T03:00:00', {
      locale: 'en-US',
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

  it('keeps date labels on the requested timezone day', () => {
    expect(formatDateTime('2026-05-01T18:30:00Z', {
      dateStyle: 'medium',
      locale: 'en-US',
      timeZone: 'America/New_York',
    })).toBe('2026. 5. 1.');

    expect(formatDateTime('2026-05-01T18:30:00Z', {
      dateStyle: 'medium',
      locale: 'en-US',
      timeZone: 'Asia/Seoul',
    })).toBe('2026. 5. 2.');
  });

  it('formats relative times with the requested locale', () => {
    expect(formatRelativeTime('2026-05-02T02:55:00Z', {
      locale: 'ko-KR',
      now: '2026-05-02T03:00:00Z',
      timeZone: 'Asia/Seoul',
    })).toBe('5분 전');

    expect(formatRelativeTime('2026-05-02T02:55:00Z', {
      locale: 'en-US',
      now: '2026-05-02T03:00:00Z',
      timeZone: 'Asia/Seoul',
    })).toBe('5 minutes ago');
  });

  it('keeps date-only values on their calendar date', () => {
    expect(formatDateOnly('2026-05-02', {
      dateFormat: 'locale',
      day: 'numeric',
      locale: 'en-US',
      month: 'short',
      timeZone: 'America/Los_Angeles',
    })).toBe('May 2');
    expect(formatDateOnly('2026-05-02')).toBe('2026. 5. 2.');
    expect(diffDateOnlyDays('2026-05-02', '2026-05-01')).toBe(1);
  });

  it('preserves caller date shape options when date preferences are enabled', () => {
    expect(formatDateOnly('2026-05-02', {
      day: 'numeric',
      locale: 'en-US',
      month: 'short',
    })).toBe('May 2');

    expect(formatDateTime('2026-05-02T03:00:00Z', {
      day: 'numeric',
      locale: 'en-US',
      month: 'short',
      timeZone: 'Asia/Seoul',
      weekday: 'short',
    })).toBe('Sat, May 2');
  });

  it('applies explicit date format preferences', () => {
    expect(formatDateOnly('2026-05-02', { dateFormat: 'iso' })).toBe('2026-05-02');
    expect(formatDateOnly('2026-05-02', { dateFormat: 'us' })).toBe('05/02/2026');
    expect(formatDateOnly('2026-05-02', { dateFormat: 'european' })).toBe('02/05/2026');
    expect(formatDateTime('2026-05-02T03:00:00Z', {
      dateFormat: 'iso',
      dateStyle: 'medium',
      hour: '2-digit',
      hourCycle: 'h23',
      locale: 'ko-KR',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
    })).toBe('2026-05-02 12:00');
  });

  it('applies stored date format preferences through the public facade', () => {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, 'iso');

    expect(formatDateOnly('2026-05-02')).toBe('2026-05-02');
    expect(formatDateTime('2026-05-02T03:00:00Z', {
      dateStyle: 'medium',
      hour: '2-digit',
      hourCycle: 'h23',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
    })).toBe('2026-05-02 12:00');
  });

  it('applies stored time zone preferences through the public facade', () => {
    window.localStorage.setItem(TIME_ZONE_STORAGE_KEY, 'UTC');

    expect(formatDateTime('2026-05-01T18:30:00Z', {
      dateStyle: 'medium',
      hour: '2-digit',
      hourCycle: 'h23',
      minute: '2-digit',
    })).toBe('2026. 5. 1. 18:30');
  });

  it('lets explicit date format options override stored preferences', () => {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, 'iso');

    expect(formatDateOnly('2026-05-02', { dateFormat: 'us' })).toBe('05/02/2026');
  });

  it('falls back to the default date format when stored preferences are invalid', () => {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, 'unknown');

    expect(formatDateOnly('2026-05-02')).toBe('2026. 5. 2.');
  });

  it('compares instants by a named timezone calendar day', () => {
    expect(isSameDateInTimeZone(
      '2026-05-01T16:00:00Z',
      '2026-05-02T01:00:00+09:00',
      'Asia/Seoul',
    )).toBe(true);
  });
});
