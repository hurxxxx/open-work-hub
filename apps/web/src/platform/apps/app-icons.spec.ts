import { describe, expect, it } from 'vitest';

import {
  APP_ICON_KEYS,
  APP_ICON_PICKER_GROUPS,
  appIconForKey,
} from './app-icons';

describe('app icons', () => {
  it('maps every picker group key to a concrete icon', () => {
    const knownKeys = new Set(APP_ICON_KEYS);

    for (const group of APP_ICON_PICKER_GROUPS) {
      for (const iconKey of group.iconKeys) {
        expect(knownKeys.has(iconKey), `${group.id}:${iconKey}`).toBe(true);
        expect(appIconForKey(iconKey).displayName ?? iconKey).toBeTruthy();
      }
    }
  });

  it('includes laboratory icons for lab-style categories', () => {
    const labGroup = APP_ICON_PICKER_GROUPS.find((group) => group.id === 'lab');

    expect(labGroup?.iconKeys).toEqual(
      expect.arrayContaining(['flask-conical', 'microscope', 'test-tube']),
    );
  });
});
