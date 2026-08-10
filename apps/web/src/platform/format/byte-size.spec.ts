import { describe, expect, it } from 'vitest';

import { formatByteSize } from './byte-size';

describe('formatByteSize', () => {
  it('keeps byte values below the binary kilobyte threshold', () => {
    expect(formatByteSize(1023)).toBe('1023 B');
    expect(formatByteSize(1024)).toBe('1.0 KB');
  });

  it('switches from KB to MB at the binary megabyte threshold', () => {
    expect(formatByteSize(1024 * 1024 - 1)).toBe('1024.0 KB');
    expect(formatByteSize(1024 * 1024)).toBe('1.0 MB');
  });

  it('supports compact fixed-width formatting with larger units', () => {
    const options = {
      fractionDigits: 'compact' as const,
      units: ['KB', 'MB', 'GB', 'TB'] as const,
    };

    expect(formatByteSize(1536, options)).toBe('1.5 KB');
    expect(formatByteSize(12 * 1024, options)).toBe('12 KB');
    expect(formatByteSize(5 * 1024 * 1024, options)).toBe('5.0 MB');
    expect(formatByteSize(1024 ** 4, options)).toBe('1.0 TB');
  });

  it('supports locale-aware compact formatting without trailing zeros', () => {
    const options = {
      fractionDigits: 'compact' as const,
      locale: 'de-DE',
      trailingZeros: 'trim' as const,
      units: ['KB', 'MB', 'GB'] as const,
    };

    expect(formatByteSize(1536, options)).toBe('1,5 KB');
    expect(formatByteSize(12 * 1024 * 1024, options)).toBe('12 MB');
  });
});
