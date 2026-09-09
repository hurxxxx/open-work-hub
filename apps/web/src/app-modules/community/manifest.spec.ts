import { describe, expect, it } from 'vitest';

import { communityManifest } from './manifest';
import { communitySidebarConfig } from './sidebar';

describe('community shell registration', () => {
  it('declares the bootstrap root nav item without rendering a duplicate category', () => {
    expect(communityManifest.navItems).toMatchObject([
      { id: 'community', appId: 'community' },
    ]);
    expect(
      communitySidebarConfig.extendCategories?.(['community'], {
        canReadApp: true,
      }),
    ).toEqual([]);
  });
});
