import { describe, expect, it } from 'vitest';

import {
  canAccessCoreWorkspaceApp,
  getCoreEnabledWorkspaceAppIds,
  hasCoreWorkspaceMembership,
  isCoreWorkspaceAppEnabled,
  resolveCoreWorkspaceAppGate,
  type CoreWorkspaceMembershipUser,
} from './workspace-access';

function buildUser(
  overrides: Partial<CoreWorkspaceMembershipUser> = {},
): CoreWorkspaceMembershipUser {
  return {
    workspaces: [{ slug: 'hq' }],
    ...overrides,
  };
}

describe('core workspace access', () => {
  it('checks workspace membership with and without an explicit slug', () => {
    expect(hasCoreWorkspaceMembership(buildUser())).toBe(true);
    expect(hasCoreWorkspaceMembership(buildUser(), 'hq')).toBe(true);
    expect(hasCoreWorkspaceMembership(buildUser(), 'other')).toBe(false);
    expect(hasCoreWorkspaceMembership({ workspaces: [] })).toBe(false);
  });

  it('collects enabled workspace apps from bootstrap apps', () => {
    expect([
      ...getCoreEnabledWorkspaceAppIds([
        { app_id: 'research', enabled: true },
        { app_id: 'meeting', enabled: false },
        { app_id: 'docs', enabled: true },
      ]),
    ]).toEqual(['research', 'docs']);

    expect(
      isCoreWorkspaceAppEnabled(
        [
          { app_id: 'research', enabled: true },
          { app_id: 'meeting', enabled: false },
        ],
        'meeting',
      ),
    ).toBe(false);
  });

  it('allows workspace members when no bootstrap app list is available', () => {
    expect(
      canAccessCoreWorkspaceApp({
        appId: 'research',
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toBe(true);
  });

  it('blocks app chrome when membership or app enablement is missing', () => {
    expect(
      canAccessCoreWorkspaceApp({
        appId: 'research',
        enabledWorkspaceAppIds: ['home', 'docs'],
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toBe(false);

    expect(
      canAccessCoreWorkspaceApp({
        appId: 'research',
        enabledWorkspaceAppIds: ['home', 'research'],
        user: buildUser({ workspaces: [] }),
        workspaceSlug: 'hq',
      }),
    ).toBe(false);
  });

  it('resolves workspace app gate state in deterministic order', () => {
    expect(
      resolveCoreWorkspaceAppGate({
        appId: 'research',
        bootstrapAppIds: ['home', 'research'],
        bootstrapError: null,
        bootstrapLoading: false,
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'allowed' });

    expect(
      resolveCoreWorkspaceAppGate({
        appId: 'research',
        bootstrapAppIds: null,
        bootstrapError: null,
        bootstrapLoading: false,
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'loading' });

    expect(
      resolveCoreWorkspaceAppGate({
        appId: 'research',
        bootstrapAppIds: null,
        bootstrapError: 'bootstrap failed',
        bootstrapLoading: true,
        user: buildUser({ workspaces: [] }),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'workspace_denied' });
  });
});
