import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { resolveShellState } from '@/src/app-shell';
import { APP_GLOBAL_ROUTES, APP_ROUTES } from '@/src/app/shell/app-registry';
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
    group_ids: [],
    managed_organization_unit_ids: [],
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
    enabledShellAppIds: [
      'home',
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
    appRoutes: APP_ROUTES,
    ...overrides,
  });
}

describe('shell chrome model', () => {
  it('keeps workspace context chrome on workspace surfaces', () => {
    expect(resolveChrome('/apps/whiteboard/boards/board-1')).toMatchObject({
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
    expect(resolveChrome('/apps/home')).toMatchObject({
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

    expect(resolveChrome('/apps/retrieval-search')).toMatchObject({
      activeAppId: 'retrieval-search',
      activeNavItemId: 'retrieval-search',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-y-auto relative',
      showSubSidebar: true,
    });

    for (const pathname of ['/apps/chatbot', '/apps/web-search']) {
      expect(resolveChrome(pathname)).toMatchObject({
        canOpenMobileAppMenu: true,
        mainClassName: 'flex-1 overflow-hidden relative',
        showSubSidebar: true,
      });
    }

    expect(resolveChrome('/apps/web-search')).toMatchObject({
      activeAppId: 'web-search',
      activeNavItemId: 'web-search',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });
  });

  it('keeps context chrome on workspace renders but not shared renders', () => {
    expect(
      resolveChrome('/apps/docs/documents/doc-1/html/page-1'),
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
    expect(resolveChrome('/apps/docs', '?view=mine')).toMatchObject({
      activeAppId: 'docs',
      activeNavItemId: 'docs-my',
      canOpenMobileAppMenu: true,
      mainClassName: 'flex-1 overflow-y-auto relative',
      routeShellAppId: 'docs',
      showSubSidebar: true,
    });
  });

  it('keeps PMS sidebar visible while PMS routes own their content scroll', () => {
    expect(resolveChrome('/apps/pms')).toMatchObject({
      activeAppId: 'pms',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });

    expect(resolveChrome('/apps/pms/lists/list-1')).toMatchObject({
      activeAppId: 'pms',
      activeNavItemId: 'pms-list-list-1',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });

    expect(resolveChrome('/apps/pms/assigned')).toMatchObject({
      activeAppId: 'pms',
      activeNavItemId: 'pms-tasks-assigned',
      mainClassName: 'flex-1 overflow-hidden relative',
      showSubSidebar: true,
    });
  });

  it('uses the route-scoped enabled app ids for active chrome', () => {
    expect(
      resolveChrome('/apps/docs', '?view=mine', {
        enabledShellAppIds: ['planner'],
      }),
    ).toMatchObject({
      activeAppId: 'launcher',
      activeNavItemId: '',
      canOpenMobileAppMenu: false,
      showSubSidebar: false,
    });
  });

  it('rejects an unregistered workspace app route', () => {
    expect(resolveChrome('/apps/typo-app')).toMatchObject({
      activeAppId: 'home',
      routeShellAppId: null,
    });
  });

  it('does not project a deleted outer container for admitted app routes', () => {
    expect(resolveChrome('/apps/docs')).not.toHaveProperty(
      'bootstrapWorkspaceSlug',
    );
  });
});
