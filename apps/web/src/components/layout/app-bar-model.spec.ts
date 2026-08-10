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
  buildAppBarWorkspaceProjection,
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
    name: 'AI-DO HQ',
    role: 'owner',
    ...overrides,
  };
}

function app(overrides: Partial<WorkspaceBootstrapApp>): WorkspaceBootstrapApp {
  return {
    app_id: 'home',
    title: 'HOME',
    route_base: '/home',
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
  pinnedByDefaultAppIds: ['pms', 'docs', 'whiteboard', 'qa-assistant'],
} as const;

const LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map([
  ['community', '/community'],
  ['qa-assistant', '/qa-assistant'],
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
        title: '아이두 챗봇',
        route_base: '/chatbot',
        icon_key: 'chat',
        enabled: true,
      },
      {
        app_id: 'qa-assistant',
        title: '사내 관리 QNA',
        route_base: '/qa-assistant',
        icon_key: 'message-square',
        enabled: true,
      },
      {
        app_id: 'web-search',
        title: '웹 검색 봇',
        route_base: '/web-search',
        icon_key: 'globe-2',
        enabled: true,
      },
      {
        app_id: 'research-trends',
        title: '논문·기술동향',
        route_base: '/research-trends',
        icon_key: 'book-open',
        enabled: true,
      },
      {
        app_id: 'standards-monitor',
        title: '규격·법규 모니터링',
        route_base: '/standards-monitor',
        icon_key: 'scale',
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
        route_base: '/pms',
        icon_key: 'clipboard-list',
        enabled: true,
      },
      {
        app_id: 'docs',
        title: '문서',
        route_base: '/docs',
        icon_key: 'copy',
        enabled: true,
      },
      {
        app_id: 'mail',
        title: '메일',
        route_base: '/mail',
        icon_key: 'mail',
        enabled: true,
      },
      {
        app_id: 'whiteboard',
        title: '화이트보드',
        route_base: '/whiteboard',
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
        app_id: 'plm',
        title: 'PLM',
        route_base: '/plm',
        icon_key: 'database',
        enabled: true,
      },
      {
        app_id: 'data-viz',
        title: '데이터 시각화',
        route_base: '/data-viz',
        icon_key: 'bar-chart-3',
        enabled: true,
      },
      {
        app_id: 'legacy-issues',
        title: '과거차문제점',
        route_base: '/legacy-issues',
        icon_key: 'history',
        enabled: true,
      },
    ],
  },
];

describe('app-bar model', () => {
  it('projects workspace switcher options with query filtering and default normalization', () => {
    const workspaces = [
      workspace({ id: 'workspace-hq', slug: 'hq', name: 'AI-DO HQ' }),
      workspace({ id: 'workspace-bravo', slug: 'bravo', name: 'Bravo Team' }),
      workspace({ id: 'workspace-alpha', slug: 'alpha', name: 'Alpha Team' }),
    ];

    const projection = buildAppBarWorkspaceProjection({
      defaultWorkspaceId: 'missing',
      locale: 'en-US',
      shellWorkspaceSlug: 'hq',
      workspaceFallbackLabel: 'Workspace',
      workspaceQuery: 'team',
      workspaces,
    });

    expect(projection.currentWorkspace?.slug).toBe('hq');
    expect(projection.currentWorkspaceName).toBe('AI-DO HQ');
    expect(projection.pinnedWorkspace).toBeNull();
    expect(projection.otherWorkspaces.map((item) => item.slug)).toEqual([
      'alpha',
      'bravo',
    ]);
    expect(projection.defaultWorkspaceOptions.map((item) => item.slug)).toEqual(
      ['hq', 'alpha', 'bravo'],
    );
    expect(projection.normalizedDefaultWorkspaceId).toBeNull();
  });

  it('keeps the current workspace pinned when it matches the query', () => {
    const projection = buildAppBarWorkspaceProjection({
      defaultWorkspaceId: 'workspace-hq',
      locale: 'en-US',
      shellWorkspaceSlug: 'hq',
      workspaceFallbackLabel: 'Workspace',
      workspaceQuery: 'hq',
      workspaces: [
        workspace({ id: 'workspace-hq', slug: 'hq', name: 'AI-DO HQ' }),
        workspace({ id: 'workspace-other', slug: 'other', name: 'Other' }),
      ],
    });

    expect(projection.pinnedWorkspace?.slug).toBe('hq');
    expect(projection.normalizedDefaultWorkspaceId).toBe('workspace-hq');
  });

  it('projects visible workspace apps for active title and fixed rail items', () => {
    const visibleItems = buildVisibleAppBarItems(
      [
        app({ app_id: 'home', title: 'Home' }),
        app({ app_id: 'plm', title: 'PLM' }),
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
      'qa-assistant',
      'web-search',
      'research-trends',
      'standards-monitor',
      'pms',
      'docs',
      'mail',
      'whiteboard',
      'plm',
      'data-viz',
      'legacy-issues',
    ]);

    const projection = buildAppBarItemsProjection({
      activeAppId: 'plm',
      appBarItems: APP_BAR_ITEMS,
      draftPinnedAppIds: ['plm', 'pms'],
      launcherPolicy: LAUNCHER_POLICY,
      pinnedAppIds: ['home', 'pms'],
      translate,
      visibleItems,
    });

    expect(projection.fixedItems.map((item) => item.id)).toEqual(['home']);
    expect(projection.pinnedItems.map((item) => item.id)).toEqual(['pms']);
    expect(projection.activeAppTitle).toBe('PLM');
  });

  it('uses company-wide links for global app bar entries', () => {
    const user = {
      id: 'user-1',
      workspaces: [workspace({ slug: 'hq' })],
    } as AuthUser;

    expect(
      buildAppLink('qa-assistant', user, 'hq', LAUNCHER_GLOBAL_PATHS),
    ).toBe('/qa-assistant');
    expect(buildAppLink('community', user, 'hq', LAUNCHER_GLOBAL_PATHS)).toBe(
      '/community',
    );
    expect(buildAppLink('docs', user, 'hq', LAUNCHER_GLOBAL_PATHS)).toBe(
      '/w/hq/docs',
    );
    expect(buildAppLink('community', user, 'hq', new Map())).toBe(
      '/w/hq/community',
    );
  });

  it('builds notification issue links from the injected owner app', () => {
    const user = {
      id: 'user-1',
      workspaces: [workspace({ slug: 'hq' })],
    } as AuthUser;

    expect(
      buildNotificationIssueHref({
        appId: 'custom-issue-app',
        currentUser: user,
        launcherGlobalPaths: new Map(),
        shellWorkspaceSlug: 'hq',
        taskId: 'task / 1',
      }),
    ).toBe('/w/hq/custom-issue-app?task=task%20%2F%201');
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

  it('projects a fixed feature app from bootstrap metadata without a core app bar item', () => {
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

    expect(visibleItems).toHaveLength(1);
    expect(visibleItems[0]).toMatchObject({
      id: 'feature-fixed',
      title: 'Fixed feature',
    });
    expect(visibleItems[0]?.icon).toBeTypeOf('object');
  });

  it('normalizes pinned app preferences', () => {
    const visibleItems = buildVisibleAppBarItems(
      [
        app({ app_id: 'home', title: 'Home' }),
        app({ app_id: 'chatbot', title: 'Chatbot' }),
        app({ app_id: 'pms', title: 'PMS' }),
        app({ app_id: 'plm', title: 'PLM' }),
      ],
      APP_BAR_CATEGORIES,
      translate,
      APP_BAR_ITEMS,
      LAUNCHER_POLICY,
    );

    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['home', 'plm', 'home', 'docs'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual(['plm', 'docs']);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['data-viz', 'qa-assistant', 'pms'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual(['data-viz', 'qa-assistant', 'pms']);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: [
            'chatbot',
            'qa-assistant',
            'web-search',
            'research-trends',
            'standards-monitor',
            'pms',
            'docs',
            'mail',
            'whiteboard',
            'plm',
            'data-viz',
          ],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual([
      'chatbot',
      'qa-assistant',
      'web-search',
      'research-trends',
      'standards-monitor',
      'pms',
      'docs',
      'mail',
      'whiteboard',
      'plm',
      'data-viz',
    ]);
    expect(
      resolvePinnedAppIds(
        {
          pinned_app_ids: ['unknown-app', 'qa-assistant'],
        },
        visibleItems,
        LAUNCHER_POLICY,
      ),
    ).toEqual(['qa-assistant']);
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
          route_base: '/mail',
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

  it('opens the favorites launcher exclusively from the workspace switcher', () => {
    const opened = appBarReducer(
      {
        ...INITIAL_APP_BAR_STATE,
        businessSitesOpen: true,
        workspaceSwitcherOpen: true,
      },
      { type: 'toggleFavorites' },
    );

    expect(opened.favoritesOpen).toBe(true);
    expect(opened.categoryMenuId).toBeNull();
    expect(opened.appBarEditorOpen).toBe(false);
    expect(opened.businessSitesOpen).toBe(false);
    expect(opened.workspaceSwitcherOpen).toBe(false);
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

  it('opens the business sites menu exclusively from other desktop menus', () => {
    const opened = appBarReducer(
      {
        ...INITIAL_APP_BAR_STATE,
        appBarEditorOpen: true,
        categoryMenuId: 'category-operations',
        favoritesOpen: true,
        workspaceSwitcherOpen: true,
      },
      { type: 'toggleBusinessSites' },
    );

    expect(opened.businessSitesOpen).toBe(true);
    expect(opened.appBarEditorOpen).toBe(false);
    expect(opened.categoryMenuId).toBeNull();
    expect(opened.favoritesOpen).toBe(false);
    expect(opened.workspaceSwitcherOpen).toBe(false);
    expect(
      appBarReducer(opened, { type: 'closeBusinessSites' }).businessSitesOpen,
    ).toBe(false);
  });

  it('builds workspace search hrefs', () => {
    expect(buildWorkspaceSearchHref('ai do')).toBe(
      '/tool/search?workspace=ai%20do',
    );
    expect(buildWorkspaceSearchHref(null)).toBe('/tool/search');
  });
});
