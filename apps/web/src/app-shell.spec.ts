import { describe, expect, it } from 'vitest';

import type { AuthUser, WorkspaceSummary } from './domains/auth/auth-api';
import { resolveShellState } from './app-shell';

function buildWorkspace(overrides: Partial<WorkspaceSummary> = {}): WorkspaceSummary {
  return {
    id: 'workspace-delivery-hub',
    slug: 'delivery-hub',
    name: 'Delivery Hub',
    role: 'member',
    enabled_apps: ['ai', 'pms', 'docs', 'planner', 'meeting'],
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
    primary_org_unit: null,
    workspaces: [buildWorkspace()],
    workspace_roles: [],
    app_access: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('resolveShellState', () => {
  it('falls back to the home shell for unauthorized PMS routes', () => {
    const userWithoutPms = buildUser({
      workspaces: [buildWorkspace({ enabled_apps: ['ai'] })],
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
    expect(resolveShellState('/tool/pms-project-demo', buildUser())).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-list-demo',
    });
  });

  it('routes the new workspace meeting path to the meeting shell', () => {
    expect(resolveShellState('/w/delivery-hub/meeting', buildUser())).toEqual({
      activeAppId: 'meeting',
      activeNavItemId: 'meeting-upcoming',
    });
  });

  it('legacy /meeting path no longer activates the meeting shell', () => {
    expect(resolveShellState('/meeting', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });
});
