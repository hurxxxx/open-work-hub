import { describe, expect, it, vi } from 'vitest';

import { getKoreanHolidayNames } from './korean-holidays';

describe('korean holidays', () => {
  it('includes the 2027 holiday dataset', () => {
    expect(getKoreanHolidayNames(2027, 0, 1)).toEqual(['1월 1일']);
    expect(getKoreanHolidayNames(2027, 1, 9)).toEqual([
      '대체공휴일(설날)',
    ]);
  });

  it('does not warn for supported 2027 lookups', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    getKoreanHolidayNames(2027, 4, 5);

    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
