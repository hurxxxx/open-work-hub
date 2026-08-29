import { describe, expect, it, vi } from 'vitest';

import { resolveAppSidebarConfig } from './sub-sidebar-app-gate';

describe('resolveAppSidebarConfig', () => {
  it('does not mount workspace app UI before bootstrap enables the app', () => {
    const load = vi.fn(() => ({ id: 'pms-sidebar' }));

    expect(
      resolveAppSidebarConfig({
        activeAppId: 'pms',
        canReadWorkspace: true,
        enabledWorkspaceAppIds: [],
        globalAppIds: [],
        load,
      }),
    ).toBeNull();
    expect(load).not.toHaveBeenCalled();
  });

  it('allows enabled workspace apps and available global apps', () => {
    const load = vi.fn((appId: string) => ({ id: `${appId}-sidebar` }));

    expect(
      resolveAppSidebarConfig({
        activeAppId: 'pms',
        canReadWorkspace: true,
        enabledWorkspaceAppIds: ['pms'],
        globalAppIds: [],
        load,
      }),
    ).toEqual({ id: 'pms-sidebar' });
    expect(
      resolveAppSidebarConfig({
        activeAppId: 'community',
        canReadWorkspace: false,
        enabledWorkspaceAppIds: [],
        globalAppIds: ['community'],
        load,
      }),
    ).toEqual({ id: 'community-sidebar' });
  });
});
