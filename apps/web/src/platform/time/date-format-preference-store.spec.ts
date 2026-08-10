import { beforeEach, describe, expect, it } from 'vitest';

import {
  DATE_FORMAT_STORAGE_KEY,
  readStoredDateFormatPreference,
  syncDateFormatPreference,
} from './date-format-preference-store';

describe('date-format-preference-store', () => {
  beforeEach(() => {
    window.localStorage.removeItem(DATE_FORMAT_STORAGE_KEY);
  });

  it('normalizes invalid stored values to the default date format', () => {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, 'unknown');

    expect(readStoredDateFormatPreference()).toBe('korean');
  });

  it('persists normalized explicit date format preferences', () => {
    expect(syncDateFormatPreference('iso')).toBe('iso');
    expect(window.localStorage.getItem(DATE_FORMAT_STORAGE_KEY)).toBe('iso');

    expect(syncDateFormatPreference('invalid')).toBe('korean');
    expect(window.localStorage.getItem(DATE_FORMAT_STORAGE_KEY)).toBe('korean');
  });
});
