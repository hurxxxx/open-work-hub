import { beforeEach, describe, expect, it } from 'vitest';

import {
  readStoredTimeZonePreference,
  syncTimeZonePreference,
  TIME_ZONE_STORAGE_KEY,
} from './time-zone-preference-store';

describe('time-zone-preference-store', () => {
  beforeEach(() => {
    window.localStorage.removeItem(TIME_ZONE_STORAGE_KEY);
  });

  it('normalizes invalid stored values to the default time zone', () => {
    window.localStorage.setItem(TIME_ZONE_STORAGE_KEY, 'unknown');

    expect(readStoredTimeZonePreference()).toBe('Asia/Seoul');
  });

  it('persists normalized explicit time zone preferences', () => {
    expect(syncTimeZonePreference('UTC')).toBe('UTC');
    expect(window.localStorage.getItem(TIME_ZONE_STORAGE_KEY)).toBe('UTC');

    expect(syncTimeZonePreference('invalid')).toBe('Asia/Seoul');
    expect(window.localStorage.getItem(TIME_ZONE_STORAGE_KEY)).toBe(
      'Asia/Seoul',
    );
  });
});
