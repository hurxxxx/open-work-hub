import { describe, expect, it } from 'vitest';

import {
  WORKSPACE_APP_ICON_KEYS,
  WORKSPACE_APP_ICON_PICKER_GROUPS,
  workspaceAppIconForKey,
} from './workspace-app-icons';

describe('workspace app icons', () => {
  it('maps every picker group key to a concrete icon', () => {
    const knownKeys = new Set(WORKSPACE_APP_ICON_KEYS);

    for (const group of WORKSPACE_APP_ICON_PICKER_GROUPS) {
      for (const iconKey of group.iconKeys) {
        expect(knownKeys.has(iconKey), `${group.id}:${iconKey}`).toBe(true);
        expect(
          workspaceAppIconForKey(iconKey).displayName ?? iconKey,
        ).toBeTruthy();
      }
    }
  });

  it('includes laboratory icons for lab-style categories', () => {
    const labGroup = WORKSPACE_APP_ICON_PICKER_GROUPS.find(
      (group) => group.id === 'lab',
    );

    expect(labGroup?.iconKeys).toEqual(
      expect.arrayContaining(['flask-conical', 'microscope', 'test-tube']),
    );
  });
});
