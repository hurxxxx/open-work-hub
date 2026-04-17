import { beforeEach, describe, expect, it } from 'vitest';

import type { AuthUser } from '../auth/auth-api';
import { resolveRootEntryPath } from './workspace-utils';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Aidoo HQ',
        role: 'admin',
      },
    ],
    workspace_roles: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('resolveRootEntryPath', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('prefers the active workspace home when workspace membership exists', () => {
    expect(resolveRootEntryPath(buildUser())).toBe('/w/hq/home');
  });

  it('falls back to admin when the user has no workspace memberships', () => {
    expect(resolveRootEntryPath(buildUser({
      workspaces: [],
      system_roles: ['platform_admin'],
    }))).toBe('/admin/general');
  });

  it('returns null when no workspace or admin landing is available', () => {
    expect(resolveRootEntryPath(buildUser({
      workspaces: [],
      system_roles: [],
    }))).toBeNull();
  });
});
