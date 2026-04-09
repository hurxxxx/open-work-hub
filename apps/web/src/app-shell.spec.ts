import { describe, expect, it } from 'vitest';

import type { AuthUser } from './domains/auth/auth-api';
import { resolveShellState } from './app-shell';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspace_roles: [],
    app_access: [
      { app: 'ai', workspace_id: 'workspace-ai', workspace_key: 'ai', workspace_name: 'AI Workspace', role: 'member' },
      { app: 'pms', workspace_id: 'workspace-pms', workspace_key: 'pms', workspace_name: 'PMS Workspace', role: 'member' },
    ],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('resolveShellState', () => {
  it('falls back to the home shell for unauthorized PMS routes', () => {
    expect(resolveShellState('/pms', buildUser({ app_access: [] }))).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(resolveShellState('/tool/pms-list-demo', buildUser({ app_access: [] }))).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('keeps PMS shell state for authorized PMS routes', () => {
    expect(resolveShellState('/pms', buildUser())).toEqual({
      activeAppId: 'pms',
      activeNavItemId: '',
    });
    expect(resolveShellState('/tool/pms-project-demo', buildUser())).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-list-demo',
    });
  });
});
