import type { Page, Route } from '@playwright/test';

const FAKE_TOKEN = 'e2e-test-token';
const AUTH_TOKEN_STORAGE_KEY = 'aidoo.auth.token';

type E2EUser = {
  id: string;
  email: string;
  full_name: string;
  display_name: string;
  status: string;
  theme_preference: string;
  primary_org_unit: null;
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

// Fake user payload matching AuthUser. Returned by the /auth/me mock so the
// provider treats the seeded token as a live session.
export const FAKE_WORKSPACE_USER: E2EUser = {
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

export const FAKE_PLATFORM_ADMIN_USER: E2EUser = {
  ...FAKE_WORKSPACE_USER,
  email: 'platform-admin@aidoo.local',
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
  item: Omit<WorkspaceBootstrapNavFixture, 'link_app_id' | 'path_suffix' | 'absolute_path'> &
    Partial<Pick<WorkspaceBootstrapNavFixture, 'link_app_id' | 'path_suffix' | 'absolute_path'>>,
): WorkspaceBootstrapNavFixture {
  return {
    link_app_id: null,
    path_suffix: null,
    absolute_path: null,
    ...item,
  };
}

// Full WorkspaceBootstrapResponse nav payload. It mirrors the app manifests
// closely enough for shell/AppBar/SubSidebar E2E smoke tests to stay hermetic.
const NAV_ITEMS_BY_APP: Record<string, WorkspaceBootstrapNavFixture[]> = {
  ai: [
    navItem({
      id: 'chatbot',
      app_id: 'ai',
      title: 'AI 챗봇',
      category: 'Core Tools',
      icon_key: 'message-square',
    }),
    navItem({
      id: 'search',
      app_id: 'ai',
      title: '아이두 통합검색',
      category: 'Core Tools',
      icon_key: 'search',
    }),
    navItem({
      id: 'drafting',
      app_id: 'ai',
      title: '기안작성 도우미',
      category: 'Core Tools',
      icon_key: 'file-text',
    }),
    navItem({
      id: 'translate',
      app_id: 'ai',
      title: '문서 번역/요약',
      category: 'Core Tools',
      icon_key: 'languages',
    }),
    navItem({
      id: 'spec-compare',
      app_id: 'ai',
      title: '규격서 비교',
      category: 'Core Tools',
      icon_key: 'file-search',
    }),
    navItem({
      id: 'fmea-compare',
      app_id: 'ai',
      title: 'FMEA 비교',
      category: 'Core Tools',
      icon_key: 'alert-triangle',
    }),
    navItem({
      id: 'meeting-minutes',
      app_id: 'ai',
      title: '회의록',
      category: 'Assistants',
      icon_key: 'mic',
      link_app_id: 'meeting',
      path_suffix: '?tab=recordings',
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
    navItem({
      id: 'pms-tasks-personal',
      app_id: 'pms',
      title: 'Personal List',
      category: 'Personal',
      icon_key: 'list',
      path_suffix: '/personal',
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
  learning: [
    navItem({
      id: 'learning-home',
      app_id: 'learning',
      title: '전체 학습 홈',
      category: 'Courses',
      icon_key: 'graduation-cap',
    }),
  ],
};

const APP_FIXTURES = [
  { app_id: 'home', title: 'HOME', icon_key: 'home' },
  { app_id: 'ai', title: 'AI', icon_key: 'brain' },
  { app_id: 'pms', title: 'PMS', icon_key: 'briefcase' },
  { app_id: 'docs', title: 'DOCS', icon_key: 'files' },
  { app_id: 'planner', title: 'Planner', icon_key: 'calendar' },
  { app_id: 'meeting', title: 'MEETING', icon_key: 'users' },
  { app_id: 'learning', title: '학습', icon_key: 'graduation-cap' },
];

const DEFAULT_ENABLED_APP_IDS = APP_FIXTURES.map((app) => app.app_id);

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
    nav_items: enabled ? NAV_ITEMS_BY_APP[app_id] ?? [] : [],
  };
}

function buildWorkspaceBootstrap(
  enabledAppIds: readonly string[] = DEFAULT_ENABLED_APP_IDS,
) {
  const apps = APP_FIXTURES.map((app) =>
    buildApp(app.app_id, app.title, app.icon_key, enabledAppIds),
  );
  return {
    workspace: {
      id: 'workspace-hq',
      slug: 'hq',
      name: 'Aidoo HQ',
      role: 'admin',
    },
    apps,
    nav: apps.flatMap((app) => app.nav_items),
  };
}

const WORKSPACE_FIXTURE = {
  id: 'workspace-hq',
  key: 'hq',
  name: 'Aidoo HQ',
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
  active_issue_count: 0,
  overdue_issue_count: 0,
  my_issue_count: 0,
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

  await page.route('**/api/v1/workspaces/*/meeting/users**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/meeting/availability**', (route: Route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/workspaces/*/meeting/meetings**', (route: Route) => {
    if (route.request().url().includes('/recordings/staging')) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: { items: [], total: 0 } });
  });

  await page.route('**/api/v1/workspaces/*/pms/notifications**', (route: Route) =>
    route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route('**/api/v1/workspaces/*/pms/notifications/unread-count', (route: Route) =>
    route.fulfill({ json: { count: 0 } }),
  );
  await page.route('**/api/v1/workspaces/*/pms/spaces**', (route: Route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/pms/lists**', (route: Route) =>
    route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route('**/api/v1/workspaces/*/pms/issues/assigned**', (route: Route) =>
    route.fulfill({ json: EMPTY_PAGE }),
  );
  await page.route('**/api/v1/workspaces/*/pms/dashboard/summary**', (route: Route) =>
    route.fulfill({ json: EMPTY_PMS_DASHBOARD }),
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
  await page.route('**/api/v1/workspaces/*/docs/recent-pages**', (route: Route) =>
    route.fulfill({ json: [] }),
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
  await page.route('**/api/v1/workspaces/*/docs/shareable-users**', (route: Route) =>
    route.fulfill({ json: [] }),
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
  const user = options.user ?? FAKE_USER;
  const workspaceBootstrap = buildWorkspaceBootstrap(options.enabledAppIds);

  // Auth bootstrap: hit on every mount to check setup status.
  await page.route('**/api/v1/auth/bootstrap-status', (route: Route) =>
    route.fulfill({ json: BOOTSTRAP_STATUS }),
  );
  // /auth/me is the "is this token still valid" probe for a stored token.
  await page.route('**/api/v1/auth/me', (route: Route) =>
    route.fulfill({ json: user }),
  );

  // Workspace bootstrap: gates routes + feeds the slash command palette.
  await page.route('**/api/v1/workspaces/*/bootstrap', (route: Route) =>
    route.fulfill({ json: workspaceBootstrap }),
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
  const createResponse =
    stubs.createResponse ?? {
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

export async function stubMeetingDetail(
  page: Page,
  meeting: Record<string, unknown>,
): Promise<void> {
  await page.route('**/meeting/meetings/**', async (route: Route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    const url = route.request().url();
    if (url.includes('/recordings/staging')) {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ json: meeting });
  });
}

export async function stubMeetingInsights(
  page: Page,
  options: {
    actions?: Record<string, unknown>;
    decisions?: Record<string, unknown>;
    followup?: Record<string, unknown>;
  } = {},
): Promise<void> {
  const actions = options.actions ?? { items: [] };
  const decisions = options.decisions ?? { items: [] };
  const followup =
    options.followup ?? { items: [], attendee_user_ids: [], availability: null };

  await page.route(/\/ai\/tools\/[^/]+\/invoke$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/ai\/tools\/([^/]+)\/invoke$/);
    const toolName = decodeURIComponent(match?.[1] ?? '');
    let result: Record<string, unknown>;
    switch (toolName) {
      case 'meeting.extract_actions':
        result = actions;
        break;
      case 'meeting.extract_decisions':
        result = decisions;
        break;
      case 'meeting.draft_followup_schedule':
        result = followup;
        break;
      default:
        await route.fallback();
        return;
    }
    await route.fulfill({
      json: {
        tool: toolName,
        owner_domain: 'meeting',
        approval_required: false,
        result,
      },
    });
  });
}

export async function stubApprovalApi(
  page: Page,
  options: {
    approvalStatus?: Record<string, unknown>;
    resolveResponse?: Record<string, unknown>;
    abandonResponse?: Record<string, unknown>;
    resumeFrames?: string[];
  } = {},
): Promise<void> {
  const approvalStatus =
    options.approvalStatus ?? {
      id: 'approval-1',
      workspace_id: 'workspace-hq',
      conversation_id: 'conversation-approval',
      agent_run_id: 'agent-run-1',
      tool_call_id: 'call-approval-1',
      tool_name: 'docs.create_page',
      arguments_json: '{"title":"승인 테스트"}',
      resource_preview: '승인 테스트 문서',
      status: 'pending',
      requested_by_user_id: 'user-e2e',
      resolved_by_user_id: null,
      reject_reason: null,
      resolved_at: null,
      expires_at: '2026-04-22T12:00:00Z',
      execution_result_json: null,
      error_message: null,
      created_at: '2026-04-22T11:00:00Z',
      snapshot_status: 'awaiting_approval',
    };
  const resolveResponse =
    options.resolveResponse ?? {
      ...approvalStatus,
      status: 'approved',
      resolved_by_user_id: 'user-e2e',
      resolved_at: '2026-04-22T11:05:00Z',
      snapshot_status: 'resumed',
    };
  const abandonResponse =
    options.abandonResponse ?? {
      ...approvalStatus,
      status: 'cancelled',
      resolved_by_user_id: 'user-e2e',
      resolved_at: '2026-04-22T11:05:00Z',
      snapshot_status: 'abandoned',
    };
  const resumeFrames =
    options.resumeFrames ??
    [
      frame('approval_resolved', 0, {
        approval_id: 'approval-1',
        call_id: 'call-approval-1',
        decision: 'approved',
        reason: null,
      }),
      frame('content_delta', 1, { text: '승인 후 재개 완료' }),
      frame('done', 2, {
        finish_reason: 'stop',
        audit_id: null,
        meta: null,
      }),
    ];

  await page.route('**/ai/approvals/**', async (route: Route) => {
    const method = route.request().method();
    const url = route.request().url();
    if (method === 'GET' && !url.endsWith('/resolve') && !url.endsWith('/abandon')) {
      await route.fulfill({ json: approvalStatus });
      return;
    }
    if (method === 'POST' && url.endsWith('/resolve')) {
      await route.fulfill({ json: resolveResponse });
      return;
    }
    if (method === 'POST' && url.endsWith('/abandon')) {
      await route.fulfill({ json: abandonResponse });
      return;
    }
    await route.fallback();
  });

  await page.route('**/ai/chat/resume', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: resumeFrames.join(''),
    });
  });
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
        model: 'local/current-moe-test-model',
        canonical_model: 'local/current-moe-test-profile',
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
