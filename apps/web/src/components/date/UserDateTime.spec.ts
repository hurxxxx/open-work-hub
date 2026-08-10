import { describe, expect, it } from 'vitest';

import { createUserDateTimeFormatter } from './UserDateTime';

describe('UserDateTime formatter', () => {
  it('formats API timestamps with the user timezone and date format', () => {
    const kst = createUserDateTimeFormatter({
      dateFormat: 'iso',
      locale: 'ko-KR',
      timeZone: 'Asia/Seoul',
    });
    const utc = createUserDateTimeFormatter({
      dateFormat: 'iso',
      locale: 'ko-KR',
      timeZone: 'UTC',
    });
    const formatOptions = {
      hour: '2-digit',
      hourCycle: 'h23',
      minute: '2-digit',
    } satisfies Intl.DateTimeFormatOptions;

    expect(kst.formatDateTime('2026-05-01T18:30:00Z', formatOptions)).toBe(
      '2026-05-02 03:30',
    );
    expect(utc.formatDateTime('2026-05-01T18:30:00Z', formatOptions)).toBe(
      '2026-05-01 18:30',
    );
  });

  it('can render time-only labels without losing the user timezone', () => {
    const formatter = createUserDateTimeFormatter({
      dateFormat: 'korean',
      locale: 'ko-KR',
      timeZone: 'Asia/Seoul',
    });

    expect(
      formatter.formatTime('2026-05-01T18:30:00Z', { hourCycle: 'h23' }),
    ).toBe('03:30');
  });

  it('uses caller fallbacks for invalid values', () => {
    const formatter = createUserDateTimeFormatter();

    expect(formatter.formatDateTime('not-a-date', { fallback: '-' })).toBe('-');
  });
});
