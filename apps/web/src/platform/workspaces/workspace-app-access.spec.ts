import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  canAccessWorkspaceApp,
  getEnabledWorkspaceAppIds,
  isWorkspaceAppEnabled,
  resolveWorkspaceAppGate,
} from './workspace-app-access';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    login_id: 'user',
    email: 'user@open-work-hub.local',
    full_name: 'Open Work Hub User',
    display_name: 'Open Work Hub User',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Open Work Hub HQ',
        role: 'admin',
      },
    ],
    workspace_roles: [],
    system_roles: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('workspace-app-access', () => {
  it('collects enabled workspace apps from bootstrap apps', () => {
    expect([
      ...getEnabledWorkspaceAppIds([
        { app_id: 'chatbot', enabled: true },
        { app_id: 'meeting', enabled: false },
        { app_id: 'docs', enabled: true },
      ]),
    ]).toEqual(['chatbot', 'docs']);

    expect(
      isWorkspaceAppEnabled(
        [
          { app_id: 'chatbot', enabled: true },
          { app_id: 'meeting', enabled: false },
        ],
        'meeting',
      ),
    ).toBe(false);
  });

  it('allows workspace members when no bootstrap app list is available', () => {
    expect(
      canAccessWorkspaceApp({
        appId: 'chatbot',
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toBe(true);
  });

  it('blocks app chrome when the user lacks membership or bootstrap disables the app', () => {
    expect(
      canAccessWorkspaceApp({
        appId: 'chatbot',
        enabledWorkspaceAppIds: ['home', 'docs'],
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toBe(false);

    expect(
      canAccessWorkspaceApp({
        appId: 'chatbot',
        enabledWorkspaceAppIds: ['home', 'chatbot'],
        user: buildUser({ workspaces: [] }),
        workspaceSlug: 'hq',
      }),
    ).toBe(false);
  });

  it('resolves the workspace route gate state in the same order as WorkspaceGate', () => {
    expect(
      resolveWorkspaceAppGate({
        appId: 'chatbot',
        bootstrapAppIds: ['home', 'chatbot'],
        bootstrapError: null,
        bootstrapLoading: false,
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'allowed' });

    expect(
      resolveWorkspaceAppGate({
        appId: 'chatbot',
        bootstrapAppIds: null,
        bootstrapError: null,
        bootstrapLoading: false,
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'loading' });

    expect(
      resolveWorkspaceAppGate({
        appId: 'chatbot',
        bootstrapAppIds: ['home', 'docs'],
        bootstrapError: null,
        bootstrapLoading: false,
        user: buildUser(),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'app_disabled' });
  });

  it('blocks workspace routes before reading bootstrap state when membership is missing', () => {
    expect(
      resolveWorkspaceAppGate({
        appId: 'chatbot',
        bootstrapAppIds: null,
        bootstrapError: 'bootstrap failed',
        bootstrapLoading: true,
        user: buildUser({ workspaces: [] }),
        workspaceSlug: 'hq',
      }),
    ).toEqual({ status: 'workspace_denied' });
  });
});
