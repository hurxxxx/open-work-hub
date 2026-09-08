import { describe, expect, it } from 'vitest';

import { formatDmMessageTime } from './dm-time';

describe('formatDmMessageTime', () => {
  it('treats timezone-less API timestamps as UTC and displays them in KST by default', () => {
    const formatted = formatDmMessageTime(
      '2026-05-19T02:46:00',
      'ko-KR',
      undefined,
    );

    expect(formatted).toContain('11:46');
    expect(formatted).not.toContain('02:46');
  });

  it('uses the signed-in user timezone when provided', () => {
    expect(formatDmMessageTime('2026-05-19T02:46:00', 'en-US', 'UTC')).toBe(
      '02:46 AM',
    );
  });
});
