import { describe, expect, it } from 'vitest';

import type { AuthUser, WorkspaceSummary } from '@/src/platform/auth/auth-api';
import {
  EMPTY_LAUNCHER_GLOBAL_PATHS,
  type LauncherGlobalPaths,
} from './navigation-types';
import {
  getInitials,
  resolveMobileAppLink,
  resolveThemePreference,
} from './shell-ui-model';

function workspace(
  overrides: Partial<WorkspaceSummary> = {},
): WorkspaceSummary {
  return {
    id: 'workspace-hq',
    name: 'AI-DO HQ',
    role: 'admin',
    slug: 'hq',
    ...overrides,
  };
}

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    date_format: 'korean',
    display_name: 'AI-DO Member',
    email: 'member@ai-do.local',
    full_name: 'AI-DO Member',
    id: 'user-1',
    locale: 'ko-KR',
    login_id: 'member',
    must_change_password: false,
    primary_org_unit: null,
    status: 'active',
    system_roles: [],
    theme_preference: 'system',
    time_zone: 'Asia/Seoul',
    workspace_roles: [],
    workspaces: [workspace()],
    ...overrides,
  };
}

const LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map([
  ['community', '/community'],
  ['qa-assistant', '/qa-assistant'],
]);

describe('shell ui model', () => {
  it('resolves system theme preference from media state', () => {
    expect(resolveThemePreference('system', true)).toBe('dark');
    expect(resolveThemePreference('system', false)).toBe('light');
    expect(resolveThemePreference('dark', false)).toBe('dark');
    expect(resolveThemePreference('light', true)).toBe('light');
  });

  it('builds compact initials with a fallback', () => {
    expect(getInitials('AI-DO HQ', 'WS')).toBe('AD');
    expect(getInitials('Delivery', 'WS')).toBe('D');
    expect(getInitials('   ', 'WS')).toBe('WS');
  });

  it('resolves mobile app links from current shell workspace first', () => {
    expect(
      resolveMobileAppLink(
        'docs',
        user({
          default_workspace_id: 'workspace-demo',
          workspaces: [
            workspace(),
            workspace({
              id: 'workspace-demo',
              name: 'Demo',
              role: 'member',
              slug: 'demo',
            }),
          ],
        }),
        'hq',
        EMPTY_LAUNCHER_GLOBAL_PATHS,
      ),
    ).toBe('/w/hq/docs');
  });

  it('falls back to preferred workspace', () => {
    const currentUser = user({
      default_workspace_id: 'workspace-demo',
      workspaces: [
        workspace(),
        workspace({
          id: 'workspace-demo',
          name: 'Demo',
          role: 'member',
          slug: 'demo',
        }),
      ],
    });

    expect(
      resolveMobileAppLink(
        'docs',
        currentUser,
        null,
        EMPTY_LAUNCHER_GLOBAL_PATHS,
      ),
    ).toBe('/w/demo/docs');
  });

  it('uses manifest-projected global launcher paths', () => {
    const currentUser = user();

    expect(
      resolveMobileAppLink(
        'qa-assistant',
        currentUser,
        'hq',
        LAUNCHER_GLOBAL_PATHS,
      ),
    ).toBe('/qa-assistant');
    expect(
      resolveMobileAppLink(
        'community',
        currentUser,
        'hq',
        LAUNCHER_GLOBAL_PATHS,
      ),
    ).toBe('/community');
  });
});
