import type { Page, Route } from '@playwright/test';

const FAKE_TOKEN = 'e2e-test-token';
const AUTH_TOKEN_STORAGE_KEY = 'aidoo.auth.token';

// Fake user payload matching AuthUser. Returned by the /auth/me mock so the
// provider treats the seeded token as a live session.
const FAKE_USER = {
  id: 'user-e2e',
  email: 'e2e@aidoo.local',
  full_name: 'E2E Tester',
  display_name: 'E2E Tester',
  status: 'active',
  theme_preference: 'system',
  primary_org_unit: null,
  workspaces: [
    { id: 'workspace-hq', slug: 'hq', name: 'Aidoo HQ', role: 'admin' },
  ],
  workspace_roles: [],
  system_roles: [],
  group_ids: [],
  group_slugs: [],
  must_change_password: false,
};

const BOOTSTRAP_STATUS = {
  requires_setup: false,
  dev_admin_login_available: false,
  dev_login_accounts: [],
};

// Full WorkspaceBootstrapResponse payload (mirrors the production schema in
// workspaces-api.ts). Ships all AI nav items the slash menu cares about, plus
// apps[] with ai/pms/docs/etc. enabled so the AppBar and route gates render
// with real contract fields instead of a trimmed-down subset.
const NAV_ITEMS_AI = [
  {
    id: 'search',
    app_id: 'ai',
    title: '아이두 통합검색',
    category: 'Core Tools',
    icon_key: 'search',
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
  },
  {
    id: 'drafting',
    app_id: 'ai',
    title: '기안작성 도우미',
    category: 'Core Tools',
    icon_key: 'file-text',
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
  },
  {
    id: 'translate',
    app_id: 'ai',
    title: '문서 번역/요약',
    category: 'Core Tools',
    icon_key: 'languages',
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
  },
  {
    id: 'spec-compare',
    app_id: 'ai',
    title: '규격서 비교',
    category: 'Core Tools',
    icon_key: 'file-search',
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
  },
  {
    id: 'fmea-compare',
    app_id: 'ai',
    title: 'FMEA 비교',
    category: 'Core Tools',
    icon_key: 'alert-triangle',
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
  },
  {
    id: 'meeting-minutes',
    app_id: 'ai',
    title: '회의록',
    category: 'Assistants',
    icon_key: 'mic',
    link_app_id: 'meeting',
    path_suffix: '?tab=recordings',
    absolute_path: null,
  },
];

function buildApp(app_id: string, title: string, icon_key: string) {
  return {
    app_id,
    title,
    route_base: app_id,
    icon_key,
    enabled: true,
    nav_items: app_id === 'ai' ? NAV_ITEMS_AI : [],
  };
}

const WORKSPACE_BOOTSTRAP = {
  workspace: {
    id: 'workspace-hq',
    slug: 'hq',
    name: 'Aidoo HQ',
    role: 'admin',
  },
  apps: [
    buildApp('home', '홈', 'home'),
    buildApp('ai', 'AI', 'brain'),
    buildApp('pms', 'PMS', 'briefcase'),
    buildApp('docs', 'Docs', 'files'),
    buildApp('planner', 'Planner', 'calendar'),
    buildApp('meeting', 'Meeting', 'users'),
  ],
  nav: NAV_ITEMS_AI,
};

const LLM_HEALTH = {
  ready: true,
  local: {
    pool: 'local',
    provider: 'mlx-lm',
    base_url: 'http://127.0.0.1:8000',
    model: 'mlx-community/qwen3.6-35b-a3b-4bit',
    canonical_model: 'qwen3.6-35b-a3b',
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
export async function stubShellBackend(page: Page): Promise<void> {
  // Auth bootstrap: hit on every mount to check setup status.
  await page.route('**/api/v1/auth/bootstrap-status', (route: Route) =>
    route.fulfill({ json: BOOTSTRAP_STATUS }),
  );
  // /auth/me is the "is this token still valid" probe for a stored token.
  await page.route('**/api/v1/auth/me', (route: Route) =>
    route.fulfill({ json: FAKE_USER }),
  );

  // Workspace bootstrap: gates routes + feeds the slash command palette.
  await page.route('**/api/v1/workspaces/*/bootstrap', (route: Route) =>
    route.fulfill({ json: WORKSPACE_BOOTSTRAP }),
  );

  // AI health: drives the ChatTopBar model pill and shield icon. The frontend
  // rewrites /api/v1/ai/* to /api/v1/workspaces/:slug/ai/* via
  // rewriteWorkspaceApiPath, so match both shapes.
  await page.route('**/ai/health', (route: Route) =>
    route.fulfill({ json: LLM_HEALTH }),
  );

  // AppBar renders the unread-notifications badge on mount and fetches this
  // endpoint every time. Stub to keep the suite hermetic — without this,
  // tests silently rely on a real API on 127.0.0.1:8000.
  await page.route('**/pms/notifications/unread-count', (route: Route) =>
    route.fulfill({ json: { count: 0 } }),
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

/**
 * Serve a canned SSE response for /api/v1/ai/chat/stream so the empty →
 * active transition test can exercise the streaming code path without a real
 * LLM. The response is short (a couple of content deltas + a done frame) so
 * tests finish quickly.
 */
export async function stubAiChatStream(
  page: Page,
  { assistantText = '안녕하세요! 무엇을 도와드릴까요?' } = {},
): Promise<void> {
  const frames = [
    frame('content_delta', 0, { text: assistantText }),
    frame('done', 1, {
      finish_reason: 'stop',
      audit_id: null,
      meta: {
        policy: 'local_only',
        chosen_pool: 'local',
        decision_reason: 'policy_local_only',
        forced_local: false,
        pii_hits: [],
        model: 'mlx-community/qwen3.6-35b-a3b-4bit',
        canonical_model: 'qwen3.6-35b-a3b',
        provider: 'mlx-lm',
      },
    }),
  ].join('');

  await page.route('**/ai/chat/stream', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: frames,
    }),
  );
}

function frame(type: string, seq: number, data: unknown): string {
  const payload = JSON.stringify({ seq, timestamp_ms: 0, type, data });
  return `event: ${type}\r\ndata: ${payload}\r\n\r\n`;
}
