import { describe, expect, it } from 'vitest';
import { Home } from 'lucide-react';

import type {
  AppBarItem,
  LauncherGlobalPaths,
} from '@/src/app/shell/navigation-types';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import type {
  WorkspaceBootstrapAppBarCategory,
  WorkspaceBootstrapApp,
} from '@/src/platform/workspaces/workspaces-api';
import {
  INITIAL_APP_BAR_STATE,
  appBarReducer,
  buildAppBarItemsProjection,
  buildAppLink,
  buildNotificationIssueHref,
  buildVisibleAppBarItems,
  buildWorkspaceSearchHref,
  resolvePinnedAppIds,
  type AppBarTranslator,
} from './app-bar-model';

type Workspace = AuthUser['workspaces'][number];

function workspace(overrides: Partial<Workspace>): Workspace {
  return {
    id: 'workspace-hq',
    slug: 'hq',
    name: 'Open Work Hub HQ',
    role: 'owner',
    ...overrides,
  };
}

function app(overrides: Partial<WorkspaceBootstrapApp>): WorkspaceBootstrapApp {
  return {
    app_id: 'home',
    title: 'HOME',
    route_base: '/apps/home',
    icon_key: 'home',
    enabled: true,
    nav_items: [],
    ...overrides,
  };
}

const translate: AppBarTranslator = (key, options) =>
  String(options?.defaultValue ?? key);

const APP_BAR_ITEMS: readonly AppBarItem[] = [
  { id: 'home', title: 'HOME', icon: Home },
];

const LAUNCHER_POLICY = {
  fixedAppIds: new Set(['home']),
  pinnedByDefaultAppIds: ['pms', 'docs', 'whiteboard'],
} as const;

const LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map([
  ['community', '/apps/community'],
  ['planner', '/apps/planner'],
]);

const APP_BAR_CATEGORIES: WorkspaceBootstrapAppBarCategory[] = [
  {
    id: 'category-assistants',
    key: 'assistants',
    title: 'Assistants',
    icon_key: 'sparkles',
    position: 0,
    items: [
      {
        app_id: 'chatbot',
        title: 'AI 어시스턴트 챗봇',
        route_base: '/apps/chatbot',
        icon_key: 'chat',
        enabled: true,
      },
      {
        app_id: 'web-search',
        title: '웹 검색 봇',
        route_base: '/apps/web-search',
        icon_key: 'globe-2',
        enabled: true,
      },
    ],
  },
  {
    id: 'category-teamwork',
    key: 'teamwork',
    title: 'Teamwork',
    icon_key: 'users',
    position: 1,
    items: [
      {
        app_id: 'pms',
        title: 'PMS',
        route_base: '/apps/pms',
        icon_key: 'clipboard-list',
        enabled: true,
      },
      {
        app_id: 'docs',
        title: '문서',
        route_base: '/apps/docs',
        icon_key: 'copy',
        enabled: true,
      },
      {
        app_id: 'mail',
        title: '메일',
        route_base: '/apps/mail',
        icon_key: 'mail',
        enabled: true,
      },
      {
        app_id: 'whiteboard',
        title: '화이트보드',
        route_base: '/apps/whiteboard',
        icon_key: 'wrench',
        enabled: true,
      },
    ],
  },
  {
    id: 'category-operations',
    key: 'operations',
    title: 'Operations',
    icon_key: 'briefcase',
    position: 2,
    items: [
      {
        app_id: 'workspace-tool',
        title: 'Workspace Tool',
        route_base: '/apps/workspace-tool',
        icon_key: 'wrench',
        enabled: true,
      },
      {
        app_id: 'diagrams',
        title: '데이터 시각화',
        route_base: '/apps/diagrams',
        icon_key: 'bar-chart-3',
        enabled: true,
      },
    ],
  },
];

describe('app-bar model', () => {
  it('projects visible workspace apps for active title and fixed rail items', () => {
    const visibleItems = buildVisibleAppBarItems(
      [
        app({ app_id: 'home', title: 'Home' }),
        app({ app_id: 'workspace-tool', title: 'Workspace Tool' }),
        app({ app_id: 'chatbot', title: 'Chatbot', enabled: false }),
        app({
          app_id: 'unknown-app',
          title: 'Unknown',
        } as Partial<WorkspaceBootstrapApp>),
      ],
      APP_BAR_CATEGORIES,
      translate,
      APP_BAR_ITEMS,
      LAUNCHER_POLICY,
    );

    expect(visibleItems.map((item) => item.id)).toEqual([
      'home',
      'chatbot',
      'web-search',
      'pms',
      'docs',
      'mail',
      'whiteboard',
      'diagrams',
    ]);

    const projection = buildAppBarItemsProjection({
      activeAppId: 'diagrams',
      appBarItems: APP_BAR_ITEMS,
      draftPinnedAppIds: ['diagrams', 'pms'],
      launcherPolicy: LAUNCHER_POLICY,
      pinnedAppIds: ['home', 'pms'],
      translate,
      visibleItems,
    });

    expect(projection.fixedItems.map((item) => item.id)).toEqual(['home']);
    expect(projection.pinnedItems.map((item) => item.id)).toEqual(['pms']);
    expect(projection.activeAppTitle).toBe('데이터 시각화');
  });

  it('uses app entries without carrying workspace context across apps', () => {
    const user = {
      id: 'user-1',
      workspaces: [workspace({ slug: 'hq' })],
    } as AuthUser;

    expect(buildAppLink('docs', user, 'hq', LAUNCHER_GLOBAL_PATHS)).toBe(
      '/apps/docs',
    );
    expect(buildAppLink('community', user, 'hq', LAUNCHER_GLOBAL_PATHS)).toBe(
      '/apps/community',
    );
    expect(buildAppLink('community', user, 'hq', new Map())).toBe(
      '/apps/community',
    );
    expect(buildAppLink('docs', user, null, new Map())).toBe('/apps/docs');
  });

  it('builds notification issue links from the injected owner app', () => {
    const user = {
      id: 'user-1',
      workspaces: [workspace({ slug: 'hq' })],
    } as AuthUser;

    expect(
      buildNotificationIssueHref({
        appId: 'pms',
        currentUser: user,
        launcherGlobalPaths: new Map(),
        shellWorkspaceSlug: 'hq',
        taskId: 'task / 1',
      }),
    ).toBe('/apps/pms?task=task%20%2F%201');
    expect(
      buildNotificationIssueHref({
        appId: null,
        currentUser: user,
        launcherGlobalPaths: new Map(),
        shellWorkspaceSlug: 'hq',
        taskId: 'task-1',
      }),
    ).toBeNull();
  });

  it('does not project fixed apps that are not visible in workspace bootstrap', () => {
    const visibleItems = buildVisibleAppBarItems(
      [
        app({ app_id: 'home', title: 'Home', enabled: false }),
        app({ app_id: 'pms', title: 'PMS' }),
      ],
      [],
      translate,
      APP_BAR_ITEMS,
      LAUNCHER_POLICY,
    );

    const projection = buildAppBarItemsProjection({
      activeAppId: 'pms',
      appBarItems: APP_BAR_ITEMS,
      draftPinnedAppIds: ['pms'],
      launcherPolicy: LAUNCHER_POLICY,
      pinnedAppIds: ['pms'],
      translate,
      visibleItems,
    });

    expect(projection.fixedItems).toEqual([]);
    expect(projection.pinnedItems).toEqual([]);
  });

  it('does not project unregistered fixed apps from bootstrap metadata', () => {
    const visibleItems = buildVisibleAppBarItems(
      [app({ app_id: 'feature-fixed', title: 'Fixed feature' })],
      [],
      translate,
      APP_BAR_ITEMS,
      {
        fixedAppIds: new Set(['feature-fixed']),
        pinnedByDefaultAppIds: [],
      },
    );

    expect(visibleItems).toEqual([]);
  });

  it('normalizes pinned app preferences', () => {
    const visibleItems = buildVisibleAppBarItems(
      [
        app({ app_id: 'home', title: 'Home' }),
        app({ app_id: 'chatbot', title: 'Chatbot' }),
        app({ app_id: 'pms', title: 'PMS' }),
        app({ app_id: 'diagrams', title: 'Diagrams' }),
      ],
      APP_BAR_CATEGORIES,
      translate,
      APP_BAR_ITEMS,
      LAUNCHER_POLICY,
    );

    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['home', 'diagrams', 'home', 'docs'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual(['diagrams', 'docs']);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['diagrams', 'docs', 'pms'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual(['diagrams', 'docs', 'pms']);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: [
            'chatbot',
            'docs',
            'web-search',
            'pms',
            'docs',
            'mail',
            'whiteboard',
            'workspace-tool',
            'diagrams',
          ],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual([
      'chatbot',
      'docs',
      'web-search',
      'pms',
      'mail',
      'whiteboard',
      'diagrams',
    ]);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['unknown-app', 'docs'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual(['docs']);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['ai', 'business'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual([]);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['ai', 'collaboration', 'business'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual([]);
    expect(
      resolvePinnedAppIds(
        { pinned_app_ids: [] },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual([]);
  });

  it('keeps personal tools visible but removes them from pinned preferences', () => {
    const personalToolsCategory: WorkspaceBootstrapAppBarCategory = {
      id: 'personal-tools',
      key: 'personal-tools',
      title: 'Personal tools',
      icon_key: 'user',
      position: -1,
      pinnable: false,
      items: [
        {
          app_id: 'mail',
          title: 'Mail',
          route_base: '/apps/mail',
          icon_key: 'mail',
          enabled: true,
        },
      ],
    };
    const visibleItems = buildVisibleAppBarItems(
      [app({ app_id: 'mail', title: 'Mail' })],
      [personalToolsCategory],
      translate,
      APP_BAR_ITEMS,
      LAUNCHER_POLICY,
    );

    expect(visibleItems).toMatchObject([{ id: 'mail', pinnable: false }]);
    expect(
      resolvePinnedAppIds(
        { pinned_app_ids: ['mail'] },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual([]);
  });

  it('opens the favorites launcher independently', () => {
    const opened = appBarReducer(INITIAL_APP_BAR_STATE, {
      type: 'toggleFavorites',
    });

    expect(opened.favoritesOpen).toBe(true);
    expect(opened.categoryMenuId).toBeNull();
    expect(opened.appBarEditorOpen).toBe(false);
    expect(
      appBarReducer(opened, {
        type: 'toggleFavorites',
      }).favoritesOpen,
    ).toBe(false);
  });

  it('opens one app bar category menu at a time', () => {
    const opened = appBarReducer(
      {
        ...INITIAL_APP_BAR_STATE,
        favoritesOpen: true,
      },
      { type: 'toggleCategoryMenu', categoryId: 'category-operations' },
    );

    expect(opened.categoryMenuId).toBe('category-operations');
    expect(opened.favoritesOpen).toBe(false);
    expect(
      appBarReducer(opened, {
        type: 'toggleCategoryMenu',
        categoryId: 'category-operations',
      }).categoryMenuId,
    ).toBeNull();
  });

  it('builds workspace search hrefs', () => {
    expect(buildWorkspaceSearchHref('project docs')).toBe(
      '/apps/retrieval-search/workspaces/project%20docs',
    );
    expect(buildWorkspaceSearchHref(null)).toBe('/apps/retrieval-search');
  });
});
