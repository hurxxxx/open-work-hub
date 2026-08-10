import type { Page, Route } from '@playwright/test';

const FAKE_TOKEN = 'e2e-test-token';
const AUTH_TOKEN_STORAGE_KEY = 'open-work-hub.auth.token';

type E2EUser = {
  id: string;
  email: string;
  full_name: string;
  display_name: string;
  status: string;
  theme_preference: string;
  locale: 'ko-KR' | 'en-US';
  time_zone: string;
  workspaces: Array<{
    id: string;
    slug: string;
    name: string;
    role: string;
  }>;
  workspace_roles: string[];
  system_roles: string[];
  group_ids: string[];
  group_slugs: string[];
  must_change_password: boolean;
};

type WorkspaceBootstrapNavFixture = {
  id: string;
  app_id: string;
  title: string;
  category: string;
  icon_key: string;
  link_app_id: string | null;
  path_suffix: string | null;
  absolute_path: string | null;
  coming_soon?: boolean | null;
};

type WorkspaceBootstrapAppBarCategoryItemFixture = {
  app_id: string;
  title: string;
  route_base: string;
  icon_key: string;
  enabled: boolean;
  coming_soon?: boolean | null;
};

type WorkspaceBootstrapAppBarCategoryFixture = {
  id: string;
  key: string;
  title: string;
  icon_key: string;
  position: number;
  items: WorkspaceBootstrapAppBarCategoryItemFixture[];
};

type WorkspaceBootstrapKeywordSearchEntityTypeFixture = {
  value: string;
  label: string;
  label_key: string;
};

// Fake user payload matching AuthUser. Returned by the /auth/me mock so the
// provider treats the seeded token as a live session.
export const FAKE_WORKSPACE_USER: E2EUser = {
  id: 'user-e2e',
  email: 'e2e@open-work-hub.local',
  full_name: 'E2E Tester',
  display_name: 'E2E Tester',
  status: 'active',
  theme_preference: 'system',
  locale: 'ko-KR',
  time_zone: 'Asia/Seoul',
  workspaces: [
    { id: 'workspace-hq', slug: 'hq', name: 'Open Work Hub HQ', role: 'admin' },
  ],
  workspace_roles: [],
  system_roles: [],
  group_ids: [],
  group_slugs: [],
  must_change_password: false,
};

export const FAKE_PLATFORM_ADMIN_USER: E2EUser = {
  ...FAKE_WORKSPACE_USER,
  email: 'platform-admin@open-work-hub.local',
  full_name: 'Platform Admin',
  display_name: 'Platform Admin',
  system_roles: ['platform_admin'],
};

const BOOTSTRAP_STATUS = {
  requires_setup: false,
  dev_admin_login_available: false,
  dev_login_accounts: [],
};

function navItem(
  item: Omit<
    WorkspaceBootstrapNavFixture,
    'link_app_id' | 'path_suffix' | 'absolute_path'
  > &
    Partial<
      Pick<
        WorkspaceBootstrapNavFixture,
        'link_app_id' | 'path_suffix' | 'absolute_path'
      >
    >,
): WorkspaceBootstrapNavFixture {
  return {
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
    ...item,
  };
}

function categoryItem(
  item: Omit<WorkspaceBootstrapAppBarCategoryItemFixture, 'enabled'>,
): WorkspaceBootstrapAppBarCategoryItemFixture {
  return {
    enabled: true,
    ...item,
  };
}

// Full WorkspaceBootstrapResponse nav payload. It mirrors the app manifests
// closely enough for shell/AppBar/SubSidebar E2E smoke tests to stay hermetic.
const NAV_ITEMS_BY_APP: Record<string, WorkspaceBootstrapNavFixture[]> = {
  chatbot: [
    navItem({
      id: 'chatbot',
      app_id: 'chatbot',
      title: 'AI 챗봇',
      category: 'AI 앱',
      icon_key: 'message-square',
    }),
  ],
  docs: [
    navItem({
      id: 'docs',
      app_id: 'docs',
      title: '문서 AI',
      category: 'AI 앱',
      icon_key: 'message-circle-question',
      absolute_path: '/docs',
    }),
  ],
  'web-search': [
    navItem({
      id: 'web-search',
      app_id: 'web-search',
      title: '웹 검색 봇',
      category: 'AI 앱',
      icon_key: 'globe-2',
    }),
  ],
  learning: [
    navItem({
      id: 'learning-home',
      app_id: 'learning',
      title: '전체 학습 홈',
      category: '업무 앱',
      icon_key: 'graduation-cap',
    }),
  ],
  drafting: [
    navItem({
      id: 'drafting',
      app_id: 'drafting',
      title: '기안작성 도우미',
      category: 'Business AI',
      icon_key: 'file-text',
    }),
  ],
  'document-translate': [
    navItem({
      id: 'translate',
      app_id: 'document-translate',
      title: '문서 번역/요약',
      category: 'Business AI',
      icon_key: 'languages',
    }),
  ],
  'spec-compare': [
    navItem({
      id: 'spec-compare',
      app_id: 'spec-compare',
      title: '규격서 비교',
      category: 'Business AI',
      icon_key: 'file-search',
    }),
  ],
  pms: [
    navItem({
      id: 'pms-inbox',
      app_id: 'pms',
      title: 'Inbox',
      category: 'Personal',
      icon_key: 'inbox',
    }),
    navItem({
      id: 'pms-tasks',
      app_id: 'pms',
      title: 'My Tasks',
      category: 'Personal',
      icon_key: 'check-circle',
      path_suffix: '/assigned',
    }),
    navItem({
      id: 'pms-tasks-assigned',
      app_id: 'pms',
      title: 'Assigned to me',
      category: 'Personal',
      icon_key: 'user',
      path_suffix: '/assigned',
    }),
    navItem({
      id: 'pms-tasks-today',
      app_id: 'pms',
      title: 'Today & Overdue',
      category: 'Personal',
      icon_key: 'calendar',
      path_suffix: '/today',
    }),
  ],
  docs: [
    navItem({
      id: 'docs-all',
      app_id: 'docs',
      title: 'All Docs',
      category: 'Library',
      icon_key: 'files',
    }),
    navItem({
      id: 'docs-my',
      app_id: 'docs',
      title: 'My Docs',
      category: 'Library',
      icon_key: 'user',
    }),
    navItem({
      id: 'docs-shared',
      app_id: 'docs',
      title: 'Shared with me',
      category: 'Library',
      icon_key: 'share',
    }),
    navItem({
      id: 'docs-private',
      app_id: 'docs',
      title: 'Private',
      category: 'Library',
      icon_key: 'lock',
    }),
    navItem({
      id: 'docs-notes',
      app_id: 'docs',
      title: 'Meeting Notes',
      category: 'Library',
      icon_key: 'mic',
    }),
    navItem({
      id: 'docs-recent',
      app_id: 'docs',
      title: 'Recent Pages',
      category: 'Library',
      icon_key: 'history',
    }),
    navItem({
      id: 'docs-archived',
      app_id: 'docs',
      title: 'Archived',
      category: 'Library',
      icon_key: 'history',
    }),
  ],
  planner: [
    navItem({
      id: 'planner-calendar',
      app_id: 'planner',
      title: '캘린더',
      category: 'Schedule',
      icon_key: 'calendar',
    }),
    navItem({
      id: 'planner-timeline',
      app_id: 'planner',
      title: '타임라인',
      category: 'Schedule',
      icon_key: 'activity',
      path_suffix: '?view=timeline',
    }),
  ],
  meeting: [
    navItem({
      id: 'meeting-upcoming',
      app_id: 'meeting',
      title: 'Upcoming',
      category: 'Meetings',
      icon_key: 'calendar',
    }),
    navItem({
      id: 'meeting-mine',
      app_id: 'meeting',
      title: 'My Meetings',
      category: 'Meetings',
      icon_key: 'user',
      path_suffix: '?scope=mine',
    }),
    navItem({
      id: 'meeting-recordings',
      app_id: 'meeting',
      title: 'Recordings',
      category: 'Meetings',
      icon_key: 'video',
      path_suffix: '?tab=recordings',
    }),
  ],
};

const APP_BAR_CATEGORIES: WorkspaceBootstrapAppBarCategoryFixture[] = [
  {
    id: 'category-ai-tools',
    key: 'ai-tools',
    title: 'AI',
    icon_key: 'sparkles',
    position: 0,
    items: [
      categoryItem({
        app_id: 'chatbot',
        title: 'AI 어시스턴트 챗봇',
        route_base: '/chatbot',
        icon_key: 'message-square',
      }),
      categoryItem({
        app_id: 'docs',
        title: '문서 AI',
        route_base: '/docs',
        icon_key: 'message-circle-question',
      }),
      categoryItem({
        app_id: 'web-search',
        title: '웹 검색 봇',
        route_base: '/web-search',
        icon_key: 'globe-2',
      }),
    ],
  },
  {
    id: 'category-business-tools',
    key: 'business-tools',
    title: '업무',
    icon_key: 'briefcase',
    position: 1,
    items: [
      categoryItem({
        app_id: 'learning',
        title: '학습',
        route_base: '/learning',
        icon_key: 'graduation-cap',
      }),
      categoryItem({
        app_id: 'drafting',
        title: '기안작성 도우미',
        route_base: '/drafting',
        icon_key: 'file-text',
      }),
      categoryItem({
        app_id: 'document-translate',
        title: '문서 번역/요약',
        route_base: '/document-translate',
        icon_key: 'languages',
      }),
      categoryItem({
        app_id: 'spec-compare',
        title: '규격서 비교',
        route_base: '/spec-compare',
        icon_key: 'file-search',
      }),
    ],
  },
  {
    id: 'category-collaboration-tools',
    key: 'collaboration-tools',
    title: '협업',
    icon_key: 'users',
    position: 2,
    items: [
      categoryItem({
        app_id: 'pms',
        title: 'PMS',
        route_base: '/pms',
        icon_key: 'folder-kanban',
      }),
      categoryItem({
        app_id: 'docs',
        title: 'DOCS',
        route_base: '/docs',
        icon_key: 'files',
      }),
      categoryItem({
        app_id: 'meeting',
        title: 'MEETING',
        route_base: '/meeting',
        icon_key: 'users',
      }),
      categoryItem({
        app_id: 'planner',
        title: 'Planner',
        route_base: '/planner',
        icon_key: 'calendar',
      }),
    ],
  },
];

const APP_FIXTURES = [
  { app_id: 'home', title: 'HOME', icon_key: 'home' },
  ...APP_BAR_CATEGORIES.flatMap((category) => category.items).map((item) => ({
    app_id: item.app_id,
    title: item.title,
    icon_key: item.icon_key,
  })),
];

const DEFAULT_ENABLED_APP_IDS = APP_FIXTURES.map((app) => app.app_id);

const KEYWORD_SEARCH_ENTITY_TYPES_BY_APP: Record<
  string,
  WorkspaceBootstrapKeywordSearchEntityTypeFixture
> = {
  docs: {
    value: 'doc',
    label: '문서',
    label_key: 'ai.search.entityDoc',
  },
  meeting: {
    value: 'meeting',
    label: '회의',
    label_key: 'ai.search.entityMeeting',
  },
  pms: {
    value: 'pms_task',
    label: 'PMS',
    label_key: 'ai.search.entityPms',
  },
};

const GLOBAL_APPS_BOOTSTRAP = {
  apps: [
    {
      app_id: 'mail',
      title: 'Mail',
      route_base: '/mail',
      icon_key: 'mail',
      availability_scope: 'platform',
      enabled: true,
      coming_soon: false,
    },
    {
      app_id: 'planner',
      title: 'Planner',
      route_base: '/planner',
      icon_key: 'calendar',
      availability_scope: 'platform',
      enabled: true,
      coming_soon: false,
    },
  ],
  app_bar_categories: [],
  personal_tools: [
    {
      app_id: 'mail',
      title: 'Mail',
      route_base: '/mail',
      icon_key: 'mail',
      availability_scope: 'platform',
      enabled: true,
      coming_soon: false,
    },
    {
      app_id: 'planner',
      title: 'Planner',
      route_base: '/planner',
      icon_key: 'calendar',
      availability_scope: 'platform',
      enabled: true,
      coming_soon: false,
    },
  ],
  platform_enabled_app_ids: ['mail', 'planner'],
  principal: {
    kind: 'user',
    scope: 'personal',
    workspace_id: null,
    source: 'e2e.apps_bootstrap',
    user_id: 'user-e2e',
    session_id: null,
  },
};

function buildApp(
  app_id: string,
  title: string,
  icon_key: string,
  enabledAppIds: readonly string[],
) {
  const enabled = enabledAppIds.includes(app_id);
  return {
    app_id,
    title,
    route_base: app_id,
    icon_key,
    enabled,
    coming_soon: false,
    nav_items: enabled ? (NAV_ITEMS_BY_APP[app_id] ?? []) : [],
  };
}

function buildWorkspaceBootstrap(
  enabledAppIds: readonly string[] = DEFAULT_ENABLED_APP_IDS,
) {
  const apps = APP_FIXTURES.map((app) =>
    buildApp(app.app_id, app.title, app.icon_key, enabledAppIds),
  );
  const enabledAppIdSet = new Set(enabledAppIds);
  const app_bar_categories = APP_BAR_CATEGORIES.map((category) => ({
    ...category,
    items: category.items
      .filter((item) => enabledAppIdSet.has(item.app_id))
      .map((item) => ({ ...item, enabled: true })),
  })).filter((category) => category.items.length > 0);
  return {
    workspace: {
      id: 'workspace-hq',
      slug: 'hq',
      name: 'Open Work Hub HQ',
      role: 'admin',
    },
    apps,
    app_bar_categories,
    nav: apps.flatMap((app) => app.nav_items),
    keyword_search: {
      entity_types: enabledAppIds.flatMap((appId) => {
        const descriptor = KEYWORD_SEARCH_ENTITY_TYPES_BY_APP[appId];
        return descriptor ? [descriptor] : [];
      }),
    },
  };
}

const WORKSPACE_FIXTURE = {
  id: 'workspace-hq',
  key: 'hq',
  name: 'Open Work Hub HQ',
  description: 'E2E workspace',
  active: true,
  team_count: 0,
  member_count: 1,
  meeting_count: 0,
  doc_count: 0,
  created_at: '2026-04-30T00:00:00Z',
  updated_at: '2026-04-30T00:00:00Z',
};

const EMPTY_PAGE = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
};

const EMPTY_PMS_DASHBOARD = {
  list_count: 0,
  active_task_count: 0,
  overdue_task_count: 0,
  my_task_count: 0,
  milestone_due_soon_count: 0,
  status_counts: [],
  priority_counts: [],
  lists: [],
  recent_activity: [],
};

const EMPTY_KEYWORD_SEARCH_RESPONSE = {
  query: '',
  hits: [],
  facets: {
    entity_types: [],
    status: [],
    containers: [],
  },
  total: 0,
  has_more: false,
  next_offset: null,
  trace_id: 'trace-e2e-empty-search',
};

const EMPTY_RAG_QUERY_RESPONSE = {
  query: '',
  answer_mode: 'grounded-answer',
  hits: [],
  grounded_answer: null,
  sources_used: [],
  query_profile: {},
  trace_id: 'trace-e2e-empty-rag',
  latency_ms: 0,
};

const EMPTY_PERSONAL_MEMO = {
  id: null,
  body: '',
  createdAt: null,
  updatedAt: null,
};

/**
 * Stub app-specific list endpoints used by the shell smoke suite. The goal is
 * not feature coverage; it prevents route smoke tests from relying on a live
 * API while keeping each app's empty state renderable.
 */
export async function stubWorkspaceAppDataBackend(page: Page): Promise<void> {
  await page.route('**/api/v1/workspaces/*/calendar/events**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/calendar/events**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );

  await page.route('**/api/v1/workspaces/*/planner/events**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/planner/events**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route(
    '**/api/v1/personal-widgets/pms/tasks/assigned**',
    (route: Route) => route.fulfill({ json: EMPTY_PAGE }),
  );

  await page.route('**/api/v1/workspaces/*/meeting/users**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(
    '**/api/v1/workspaces/*/meeting/availability**',
    (route: Route) => route.fulfill({ json: { items: [] } }),
  );
  await page.route(
    '**/api/v1/workspaces/*/meeting/meetings**',
    (route: Route) => {
      if (route.request().url().includes('/recordings/staging')) {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({ json: { items: [], total: 0 } });
    },
  );

  await page.route(
    '**/api/v1/workspaces/*/pms/notifications**',
    (route: Route) => route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route(
    '**/api/v1/workspaces/*/pms/notifications/unread-count',
    (route: Route) => route.fulfill({ json: { count: 0 } }),
  );
  await page.route('**/api/v1/workspaces/*/pms/spaces**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/pms/lists**', (route: Route) =>
    route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route(
    '**/api/v1/workspaces/*/pms/tasks/assigned**',
    (route: Route) => route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route(
    '**/api/v1/workspaces/*/pms/dashboard/summary**',
    (route: Route) => route.fulfill({ json: EMPTY_PMS_DASHBOARD }),
  );
  await page.route('**/api/v1/workspaces/*/pms/folders**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/workspaces/*/pms/users**', (route: Route) =>
    route.fulfill({ json: [] }),
  );

  await page.route('**/api/v1/workspaces/*/docs/hub**', (route: Route) =>
    route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route(
    '**/api/v1/workspaces/*/docs/recent-pages**',
    (route: Route) => route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/docs/recent-pages**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/docs/favorites**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/docs/favorites**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(
    '**/api/v1/workspaces/*/docs/shareable-users**',
    (route: Route) => route.fulfill({ json: [] }),
  );

  await page.route('**/api/v1/workspaces/*/search/query**', (route: Route) =>
    route.fulfill({ json: EMPTY_KEYWORD_SEARCH_RESPONSE }),
  );
  await page.route('**/api/v1/workspaces/*/rag/sources**', (route: Route) =>
    route.fulfill({ json: { sources: [] } }),
  );
  await page.route('**/api/v1/workspaces/*/rag/query**', (route: Route) =>
    route.fulfill({ json: EMPTY_RAG_QUERY_RESPONSE }),
  );

  await page.route(
    '**/api/v1/workspaces/*/images/generations**',
    (route: Route) => route.fulfill({ json: { items: [], next_cursor: null } }),
  );

  await page.route('**/api/v1/admin/workspaces**', (route: Route) =>
    route.fulfill({ json: [WORKSPACE_FIXTURE] }),
  );
  await page.route('**/api/v1/admin/groups**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/admin/teams**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/admin/audit-logs**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/admin/users**', (route: Route) =>
    route.fulfill({ json: { ...EMPTY_PAGE, page_size: 20 } }),
  );
  await page.route('**/api/v1/admin/workspaces/*/members**', (route: Route) =>
    route.fulfill({
      json: {
        ...EMPTY_PAGE,
        page_size: 20,
        role_counts: { admin: 0, member: 0 },
        user_count: 0,
        group_count: 0,
        pending_count: 0,
      },
    }),
  );
}

interface ShellBackendOptions {
  enabledAppIds?: readonly string[];
  user?: E2EUser;
  onUpdatePreferences?: (
    payload: Record<string, unknown>,
    user: E2EUser,
  ) => void;
}

// Legacy constant retained for compatibility with older helper consumers.
const FAKE_USER = FAKE_WORKSPACE_USER;

const LLM_HEALTH = {
  ready: true,
  local: {
    pool: 'local',
    provider: 'mlx-lm',
    base_url: 'http://127.0.0.1:8000',
    model: 'local/current-moe-test-model',
    canonical_model: 'local/current-moe-test-profile',
    status: 'ready',
    ready: true,
    detail: null,
  },
  external: null,
};

/**
 * Wire up the minimum set of backend stubs so the chat shell renders offline.
 * Call inside `test.beforeEach` (or at the top of a single test) before the
 * first page.goto().
 */
export async function stubShellBackend(
  page: Page,
  options: ShellBackendOptions = {},
): Promise<void> {
  let user: E2EUser = {
    ...(options.user ?? FAKE_USER),
    workspaces: [...(options.user ?? FAKE_USER).workspaces],
    workspace_roles: [...(options.user ?? FAKE_USER).workspace_roles],
    system_roles: [...(options.user ?? FAKE_USER).system_roles],
    group_ids: [...(options.user ?? FAKE_USER).group_ids],
    group_slugs: [...(options.user ?? FAKE_USER).group_slugs],
  };
  const workspaceBootstrap = buildWorkspaceBootstrap(options.enabledAppIds);

  // Auth bootstrap: hit on every mount to check setup status.
  await page.route('**/api/v1/auth/bootstrap-status', (route: Route) =>
    route.fulfill({ json: BOOTSTRAP_STATUS }),
  );
  // /auth/me is the "is this token still valid" probe for a stored token.
  await page.route('**/api/v1/auth/me', (route: Route) =>
    route.fulfill({ json: user }),
  );
  await page.route('**/api/v1/auth/preferences', async (route: Route) => {
    if (route.request().method() !== 'PATCH') {
      await route.fallback();
      return;
    }
    const payload = route.request().postDataJSON() as Partial<E2EUser>;
    user = { ...user, ...payload };
    options.onUpdatePreferences?.(payload, user);
    await route.fulfill({ json: user });
  });

  // Workspace bootstrap: gates routes + feeds the slash command palette.
  await page.route('**/api/v1/workspaces/*/bootstrap', (route: Route) =>
    route.fulfill({ json: workspaceBootstrap }),
  );
  await page.route('**/api/v1/apps/bootstrap', (route: Route) =>
    route.fulfill({ json: GLOBAL_APPS_BOOTSTRAP }),
  );

  // Chatbot health: drives the ChatTopBar model pill and shield icon. The frontend
  // rewrites /api/v1/chatbot/* to /api/v1/workspaces/:slug/chatbot/* via
  // rewriteWorkspaceApiPath, so match both shapes.
  await page.route('**/chatbot/health', (route: Route) =>
    route.fulfill({ json: LLM_HEALTH }),
  );

  // AppBar renders the unread-notifications badge on mount and fetches this
  // endpoint every time. Stub to keep the suite hermetic — without this,
  // tests silently rely on a real API on 127.0.0.1:8000.
  await page.route('**/pms/notifications/unread-count', (route: Route) =>
    route.fulfill({ json: { count: 0 } }),
  );
  await page.route('**/api/v1/notifications/unread-count', (route: Route) =>
    route.fulfill({ json: { count: 0 } }),
  );
  await page.route(
    (url) => url.pathname === '/api/v1/notifications',
    (route: Route) => route.fulfill({ json: { ...EMPTY_PAGE, page_size: 20 } }),
  );
  await page.route(
    (url) => url.pathname.endsWith('/announcements'),
    (route: Route) => route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/release-notes/current', (route: Route) =>
    route.fulfill({ json: { item: null } }),
  );
  await page.route('**/api/v1/usage/events', (route: Route) =>
    route.fulfill({ json: { ok: true } }),
  );

  // Personal widgets and DM are mounted by the shell itself, so every shell
  // route smoke test needs these stubs even when it does not exercise them.
  await page.route('**/api/v1/personal-widgets/todos**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/personal-widgets/memo', (route: Route) =>
    route.fulfill({ json: EMPTY_PERSONAL_MEMO }),
  );
  await page.route('**/api/v1/dm/conversations**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );

  // Seed the auth token so AuthProvider hydrates without a login redirect.
  await page.addInitScript(
    ({ token, key }) => {
      try {
        window.localStorage.setItem(key, token);
      } catch {
        // Private browsing or quota issues — test will surface the failure.
      }
    },
    { token: FAKE_TOKEN, key: AUTH_TOKEN_STORAGE_KEY },
  );
}

export interface ConversationStubs {
  list?: Array<{
    id: string;
    title: string;
    createdAt: string;
    updatedAt: string;
  }>;
  createResponse?: {
    id: string;
    title: string;
    createdAt: string;
    updatedAt: string;
    scopeRef?: 'meeting' | null;
    scopeResourceId?: string | null;
    livePendingApproval?: {
      approvalId: string;
      agentRunId: string;
      callId: string;
      tool: string;
      resourcePreview?: string | null;
      expiresAtMs: number;
      status: 'pending' | 'approved' | 'rejected';
      reason?: string | null;
    } | null;
    turns: Array<{
      id: string;
      seq: number;
      role: string;
      content: string;
      createdAt: string;
      artifacts?: unknown[];
    }>;
  };
  detail?: Record<
    string,
    {
      id: string;
      title: string;
      createdAt: string;
      updatedAt: string;
      scopeRef?: 'meeting' | null;
      scopeResourceId?: string | null;
      livePendingApproval?: {
        approvalId: string;
        agentRunId: string;
        callId: string;
        tool: string;
        resourcePreview?: string | null;
        expiresAtMs: number;
        status: 'pending' | 'approved' | 'rejected';
        reason?: string | null;
      } | null;
      turns: Array<{
        id: string;
        seq: number;
        role: string;
        content: string;
        createdAt: string;
        artifacts?: unknown[];
      }>;
    }
  >;
}

/**
 * Stub the conversations CRUD endpoints so the sidebar list and detail
 * hydration render from a fixture instead of a live API. Accepts optional
 * list + detail maps; unknown ids return 404 and DELETE always succeeds.
 */
export async function stubConversationsApi(
  page: Page,
  stubs: ConversationStubs = {},
): Promise<void> {
  const list = stubs.list ?? [];
  const detail = stubs.detail ?? {};
  const createResponse = stubs.createResponse ?? {
    id: 'new-conversation',
    title: '',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    scopeRef: null,
    scopeResourceId: null,
    livePendingApproval: null,
    turns: [],
  };

  // Regex matches both the list/create (`/conversations` with optional query)
  // and the detail/patch/delete (`/conversations/<id>`) endpoints in one
  // handler. Playwright's glob patterns had trouble matching query strings
  // reliably in cross-browser runs, so a regex is cheaper to reason about.
  await page.route(/\/conversations(?:\/[^?]*)?(?:\?.*)?$/, (route: Route) => {
    const url = new URL(route.request().url());
    const segmentsAfter = url.pathname.split('/conversations');
    const tail = segmentsAfter[segmentsAfter.length - 1] ?? '';
    const method = route.request().method();
    if (tail === '' || tail === '/') {
      if (method === 'POST') {
        return route.fulfill({
          json: createResponse,
        });
      }
      return route.fulfill({ json: { items: list, nextCursor: null } });
    }
    const id = tail.replace(/^\//, '');
    if (method === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    const row = detail[id];
    if (!row) {
      return route.fulfill({ status: 404, json: { detail: 'not found' } });
    }
    return route.fulfill({ json: row });
  });
}
