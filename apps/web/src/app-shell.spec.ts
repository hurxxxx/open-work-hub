import { describe, expect, it } from 'vitest';

import type { AuthUser, WorkspaceSummary } from './platform/auth/auth-api';
import { resolveShellState } from './app-shell';

function buildWorkspace(overrides: Partial<WorkspaceSummary> = {}): WorkspaceSummary {
  return {
    id: 'workspace-delivery-hub',
    slug: 'delivery-hub',
    name: 'Delivery Hub',
    role: 'member',
    ...overrides,
  };
}

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    primary_org_unit: null,
    workspaces: [buildWorkspace()],
    workspace_roles: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('resolveShellState', () => {
  it('falls back to the home shell for users without workspace membership', () => {
    const userWithoutPms = buildUser({
      workspaces: [],
    });
    expect(resolveShellState('/w/delivery-hub/pms', userWithoutPms)).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(resolveShellState('/tool/pms-list-demo', userWithoutPms)).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('keeps PMS shell state for authorized PMS routes', () => {
    expect(resolveShellState('/w/delivery-hub/pms', buildUser())).toEqual({
      activeAppId: 'pms',
      activeNavItemId: '',
    });
    expect(resolveShellState('/w/delivery-hub/pms/assigned', buildUser())).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-tasks-assigned',
    });
    expect(resolveShellState('/tool/pms-list-demo', buildUser())).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-list-demo',
    });
  });

  it('routes the new workspace meeting path to the meeting shell', () => {
    expect(resolveShellState('/w/delivery-hub/meeting', buildUser())).toEqual({
      activeAppId: 'meeting',
      activeNavItemId: 'meeting-upcoming',
    });
    expect(resolveShellState('/w/delivery-hub/home', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses planner query views for the active planner navigation item', () => {
    expect(resolveShellState('/w/delivery-hub/planner', buildUser())).toEqual({
      activeAppId: 'planner',
      activeNavItemId: 'planner-calendar',
    });
    expect(
      resolveShellState('/w/delivery-hub/planner?view=timeline', buildUser()),
    ).toEqual({
      activeAppId: 'planner',
      activeNavItemId: 'planner-timeline',
    });
  });

  it('uses recording query filters for the active recording navigation item', () => {
    expect(resolveShellState('/w/delivery-hub/recording', buildUser())).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-quick',
    });
    expect(resolveShellState('/w/delivery-hub/recording?view=mine', buildUser())).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-mine',
    });
    expect(resolveShellState('/w/delivery-hub/recording?view=mine&category=meeting', buildUser())).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-meeting',
    });
    expect(resolveShellState('/w/delivery-hub/recording?view=processing', buildUser())).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-processing',
    });
    expect(resolveShellState('/w/delivery-hub/recording?view=failed', buildUser())).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-failed',
    });
    expect(resolveShellState('/w/delivery-hub/recording?view=archived', buildUser())).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-archived',
    });
  });

  it('legacy /meeting path no longer activates the meeting shell', () => {
    expect(resolveShellState('/meeting', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    for (const legacyPath of ['/docs', '/pms', '/planner', '/ai']) {
      expect(resolveShellState(legacyPath, buildUser())).toEqual({
        activeAppId: 'home',
        activeNavItemId: '',
      });
    }
  });

  it('falls back to home when the workspace bootstrap disables the app', () => {
    expect(
      resolveShellState('/w/delivery-hub/ai', buildUser(), ['home', 'pms', 'docs']),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });
});
