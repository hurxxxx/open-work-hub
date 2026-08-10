import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { resolveShellState } from '@/src/app-shell';
import {
  APP_GLOBAL_ROUTES,
  APP_WORKSPACE_ROUTES,
} from '@/src/app/shell/app-registry';
import {
  buildShellWorkspaceSelectionKey,
  resolveInitialShellWorkspaceSlug,
  resolveShellChromeState,
} from './shell-chrome-model';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    date_format: 'korean',
    display_name: 'Open ALM Member',
    email: 'member@open-alm.local',
    full_name: 'Open ALM Member',
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
    workspaces: [
      {
        id: 'workspace-hq',
        name: 'Open ALM HQ',
        role: 'admin',
        slug: 'hq',
      },
    ],
    ...overrides,
  };
}

function resolveChrome(
  pathname: string,
  search = '',
  overrides: Partial<Parameters<typeof resolveShellChromeState>[0]> = {},
) {
  return resolveShellChromeState({
    enabledWorkspaceAppIds: [
      'community',
      'docs',
      'planner',
      'pms',
      'qa-assistant',
      'research-trends',
      'standards-monitor',
      'web-search',
      'whiteboard',
    ],
    appGlobalRoutes: APP_GLOBAL_ROUTES,
    pathname,
    resolveShellStateForPath: resolveShellState,
    search,
    shellWorkspaceSlug: 'hq',
    user: buildUser(),
    workspaceRoutes: APP_WORKSPACE_ROUTES,
    ...overrides,
  });
}

describe('shell chrome model', () => {
  it('builds a workspace selection key that changes with memberships', () => {
    expect(buildShellWorkspaceSelectionKey(null, 'hq')).toBe('anonymous:hq');
    expect(buildShellWorkspaceSelectionKey(buildUser(), 'hq')).toBe(
      ['user-1', '', 'hq', 'workspace-hq:hq'].join('\u0000'),
    );
  });

  it('resolves the initial shell workspace from route or user preference', () => {
    expect(resolveInitialShellWorkspaceSlug(buildUser(), 'hq')).toBe('hq');
    expect(
      resolveInitialShellWorkspaceSlug(
        buildUser({
          default_workspace_id: 'workspace-demo',
          workspaces: [
            {
              id: 'workspace-hq',
              name: 'Open ALM HQ',
              role: 'admin',
              slug: 'hq',
            },
            {
              id: 'workspace-demo',
              name: 'Open ALM Demo',
              role: 'member',
              slug: 'demo',
            },
          ],
        }),
        'missing',
      ),
    ).toBe('demo');
  });

  it('hides sidebar chrome for full-surface routes', () => {
    expect(resolveChrome('/w/hq/whiteboard/board-1')).toMatchObject({
      activeAppId: 'collaboration',
      activeNavItemId: 'whiteboard-all',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/planner')).toMatchObject({
      activeAppId: 'planner',
      activeNavItemId: 'planner-calendar',
      canOpenMobileAppMenu: false,
      showSubSidebar: false,
    });
  });

  it('uses subSidebar route options for home and integrated search', () => {
    expect(resolveChrome('/w/hq/home')).toMatchObject({
      activeAppId: 'home',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/help')).toMatchObject({
      activeAppId: 'home',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/help/pms')).toMatchObject({
      activeAppId: 'home',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/tool/search', '?workspace=hq')).toMatchObject({
      activeAppId: 'search',
      activeNavItemId: 'search',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/qa-assistant')).toMatchObject({
      activeAppId: 'ai',
      activeNavItemId: 'qa-assistant',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/qa-assistant')).toMatchObject({
      activeAppId: 'ai',
      activeNavItemId: 'qa-assistant',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/w/hq/web-search')).toMatchObject({
      activeAppId: 'ai',
      activeNavItemId: 'web-search',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/w/hq/research-trends')).toMatchObject({
      activeAppId: 'ai',
      activeNavItemId: 'research-trends',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: false,
    });

    expect(resolveChrome('/w/hq/standards-monitor')).toMatchObject({
      activeAppId: 'ai',
      activeNavItemId: 'standards-monitor',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: false,
    });
  });

  it('hides sidebar chrome for document render routes', () => {
    expect(resolveChrome('/w/hq/docs/doc-1/html/page-1')).toMatchObject({
      activeAppId: 'collaboration',
      canOpenMobileAppMenu: false,
      showSubSidebar: false,
    });
    expect(resolveChrome('/docs/shared/link/html/page-1')).toMatchObject({
      activeAppId: 'collaboration',
      canOpenMobileAppMenu: false,
      showSubSidebar: false,
    });
  });

  it('keeps community eligible for app submenus without switching to full-surface chrome', () => {
    expect(resolveChrome('/community')).toMatchObject({
      activeAppId: 'community',
      activeNavItemId: '',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: true,
    });
  });

  it('keeps normal workspace routes scrollable and eligible for mobile app menu', () => {
    expect(resolveChrome('/w/hq/docs', '?view=mine')).toMatchObject({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-my',
      bootstrapWorkspaceSlug: 'hq',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-y-auto relative',
      routeStorageSelection: { appId: 'docs', workspaceSlug: 'hq' },
      routeWorkspaceAppId: 'docs',
      routeWorkspaceSlug: 'hq',
      showSubSidebar: true,
    });
  });

  it('keeps PMS sidebar visible while PMS routes own their content scroll', () => {
    expect(resolveChrome('/w/hq/pms')).toMatchObject({
      activeAppId: 'collaboration',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });

    expect(resolveChrome('/w/hq/pms/lists/list-1')).toMatchObject({
      activeAppId: 'collaboration',
      activeNavItemId: 'pms-list-list-1',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });

    expect(resolveChrome('/w/hq/pms/assigned')).toMatchObject({
      activeAppId: 'collaboration',
      activeNavItemId: 'pms-tasks-assigned',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });
  });

  it('uses enabled app ids for active chrome but still identifies route storage', () => {
    expect(
      resolveChrome('/w/hq/docs', '?view=mine', {
        enabledWorkspaceAppIds: ['planner'],
      }),
    ).toMatchObject({
      activeAppId: 'home',
      activeNavItemId: '',
      canOpenMobileAppMenu: false,
      routeStorageSelection: null,
      showSubSidebar: true,
    });
  });

  it('does not persist an unregistered workspace app segment', () => {
    expect(resolveChrome('/w/hq/typo-app')).toMatchObject({
      activeAppId: 'home',
      routeStorageSelection: null,
      routeWorkspaceAppId: 'typo-app',
    });
  });

  it('does not persist route storage when the workspace is not a membership', () => {
    expect(
      resolveChrome('/w/demo/docs', '', {
        shellWorkspaceSlug: 'hq',
        user: buildUser(),
      }).routeStorageSelection,
    ).toBeNull();
  });
});
