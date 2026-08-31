import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { resolveShellState } from '@/src/app-shell';
import {
  APP_GLOBAL_ROUTES,
  APP_WORKSPACE_ROUTES,
} from '@/src/app/shell/app-registry';
import { resolveShellChromeState } from './shell-chrome-model';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    date_format: 'korean',
    display_name: 'Open Work Hub Member',
    email: 'member@open-work-hub.local',
    full_name: 'Open Work Hub Member',
    id: 'user-1',
    locale: 'ko-KR',
    login_id: 'member',
    must_change_password: false,
    status: 'active',
    system_roles: [],
    theme_preference: 'system',
    time_zone: 'Asia/Seoul',
    workspace_roles: [],
    workspaces: [
      {
        id: 'workspace-hq',
        name: 'Open Work Hub HQ',
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
      'chatbot',
      'docs',
      'planner',
      'pms',
      'retrieval-search',
      'docs',
      'web-search',
      'whiteboard',
    ],
    appGlobalRoutes: APP_GLOBAL_ROUTES,
    pathname,
    resolveShellStateForPath: resolveShellState,
    search,
    user: buildUser(),
    workspaceRoutes: APP_WORKSPACE_ROUTES,
    ...overrides,
  });
}

describe('shell chrome model', () => {
  it('keeps workspace context chrome on workspace surfaces', () => {
    expect(
      resolveChrome('/apps/whiteboard/workspaces/hq/boards/board-1'),
    ).toMatchObject({
      activeAppId: 'whiteboard',
      activeNavItemId: 'whiteboard-all',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });

    expect(resolveChrome('/apps/planner')).toMatchObject({
      activeAppId: 'planner',
      activeNavItemId: 'planner-calendar',
      canOpenMobileAppMenu: false,
      showSubSidebar: false,
    });
  });

  it('uses generated route chrome for home and workspace search apps', () => {
    expect(resolveChrome('/apps/home/workspaces/hq')).toMatchObject({
      activeAppId: 'home',
      canOpenMobileAppMenu: false,
      mainClassName: 'flex-1 overflow-hidden relative',
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

    expect(resolveChrome('/apps/retrieval-search/workspaces/hq')).toMatchObject(
      {
        activeAppId: 'retrieval-search',
        activeNavItemId: 'retrieval-search',
        canOpenMobileAppMenu: true,
        mainClassName: 'flex-1 overflow-y-auto relative',
        showSubSidebar: true,
      },
    );

    for (const pathname of [
      '/apps/chatbot/workspaces/hq',
      '/apps/web-search/workspaces/hq',
    ]) {
      expect(resolveChrome(pathname)).toMatchObject({
        canOpenMobileAppMenu: true,
        mainClassName: 'flex-1 overflow-hidden relative',
        showSubSidebar: true,
      });
    }

    expect(resolveChrome('/apps/web-search/workspaces/hq')).toMatchObject({
      activeAppId: 'web-search',
      activeNavItemId: 'web-search',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });
  });

  it('keeps context chrome on workspace renders but not shared renders', () => {
    expect(
      resolveChrome('/apps/docs/workspaces/hq/documents/doc-1/html/page-1'),
    ).toMatchObject({
      activeAppId: 'docs',
      canOpenMobileAppMenu: true,
      showSubSidebar: true,
    });
    expect(resolveChrome('/apps/docs/shared/link/html/page-1')).toMatchObject({
      activeAppId: 'docs',
      canOpenMobileAppMenu: false,
      showSubSidebar: false,
    });
  });

  it('keeps community eligible for app submenus without switching to full-surface chrome', () => {
    expect(resolveChrome('/apps/community')).toMatchObject({
      activeAppId: 'community',
      activeNavItemId: '',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: true,
    });
  });

  it('keeps normal workspace routes scrollable and eligible for mobile app menu', () => {
    expect(
      resolveChrome('/apps/docs/workspaces/hq', '?view=mine'),
    ).toMatchObject({
      activeAppId: 'docs',
      activeNavItemId: 'docs-my',
      bootstrapWorkspaceSlug: 'hq',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-y-auto relative',
      routeWorkspaceAppId: 'docs',
      routeWorkspaceSlug: 'hq',
      showSubSidebar: true,
    });
  });

  it('keeps PMS sidebar visible while PMS routes own their content scroll', () => {
    expect(resolveChrome('/apps/pms/workspaces/hq')).toMatchObject({
      activeAppId: 'pms',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });

    expect(resolveChrome('/apps/pms/workspaces/hq/lists/list-1')).toMatchObject(
      {
        activeAppId: 'pms',
        activeNavItemId: 'pms-list-list-1',
        mainClassName: 'flex-1 overflow-hidden relative',
        showSubSidebar: true,
      },
    );

    expect(resolveChrome('/apps/pms/workspaces/hq/assigned')).toMatchObject({
      activeAppId: 'pms',
      activeNavItemId: 'pms-tasks-assigned',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });
  });

  it('uses the route-scoped enabled app ids for active chrome', () => {
    expect(
      resolveChrome('/apps/docs/workspaces/hq', '?view=mine', {
        enabledWorkspaceAppIds: ['planner'],
      }),
    ).toMatchObject({
      activeAppId: 'home',
      activeNavItemId: '',
      canOpenMobileAppMenu: true,
      showSubSidebar: true,
    });
  });

  it('rejects an unregistered workspace app route', () => {
    expect(resolveChrome('/apps/typo-app/workspaces/hq')).toMatchObject({
      activeAppId: 'home',
      routeWorkspaceAppId: null,
    });
  });

  it('does not bootstrap a workspace that is not a membership', () => {
    expect(resolveChrome('/apps/docs/workspaces/demo')).toMatchObject({
      bootstrapWorkspaceSlug: null,
      routeWorkspaceSlug: 'demo',
    });
  });
});
