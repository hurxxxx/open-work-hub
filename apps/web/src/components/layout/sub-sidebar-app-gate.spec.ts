import { describe, expect, it, vi } from 'vitest';

import { resolveAppSidebarConfig } from './sub-sidebar-app-gate';

describe('resolveAppSidebarConfig', () => {
  it('does not mount workspace app UI before bootstrap enables the app', () => {
    const load = vi.fn(() => ({ id: 'pms-sidebar' }));

    expect(
      resolveAppSidebarConfig({
        activeAppId: 'pms',
        canReadApp: true,
        enabledShellAppIds: [],
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
        canReadApp: true,
        enabledShellAppIds: ['pms'],
        globalAppIds: [],
        load,
      }),
    ).toEqual({ id: 'pms-sidebar' });
    expect(
      resolveAppSidebarConfig({
        activeAppId: 'community',
        canReadApp: false,
        enabledShellAppIds: [],
        globalAppIds: ['community'],
        load,
      }),
    ).toEqual({ id: 'community-sidebar' });
  });
});
