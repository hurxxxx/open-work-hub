import { expect, test, type Page, type Route } from '@playwright/test';

import { stubShellBackend } from './helpers';

type KeywordSearchPayload = {
  query?: string;
  hits?: unknown[];
  facets?: {
    entity_types?: unknown[];
    status?: unknown[];
    containers?: unknown[];
  };
  total?: number;
  has_more?: boolean;
  next_offset?: number | null;
};

const KEYWORD_SEARCH_ROUTE = '**/api/v1/workspaces/*/search/query**';

const baseHit = {
  entity_type: 'pms_issue',
  entity_id: 'issue-1',
  workspace_id: 'workspace-hq',
  title: 'Budget blocker',
  summary: 'Supplier repricing increased the budget risk.',
  snippet: {
    text: 'Supplier repricing increased the budget risk.',
    highlights: [{ start: 40, end: 44 }],
  },
  score: 7.4,
  status: 'in_progress',
  status_label: 'In Progress',
  visibility: 'workspace',
  updated_at: '2026-04-24T00:00:00Z',
  created_at: '2026-04-20T00:00:00Z',
  date_markers: {
    start_date: null,
    due_date: '2026-04-30',
    event_start_at: null,
  },
  people: [{ role: 'assignee', user_id: 'user-e2e', label: 'Kim' }],
  containers: [{ type: 'list', id: 'list-1', label: 'Sprint Backlog' }],
  deep_link: '/tool/pms-list-list-1?workspace=hq&issue=issue-1',
  preview_url: null,
  metadata: {},
};

function keywordResponse(overrides: KeywordSearchPayload = {}) {
  return {
    query: 'budget risk',
    hits: [baseHit],
    facets: {
      entity_types: [
        { value: 'doc', label: '문서', count: 12 },
        { value: 'meeting', label: '회의', count: 4 },
        { value: 'pms_issue', label: 'PMS', count: 7 },
        { value: 'planner_event', label: '일정', count: 2 },
      ],
      status: [
        { entity_type: 'pms_issue', value: 'in_progress', label: 'In Progress', count: 3 },
      ],
      containers: [{ type: 'list', id: 'list-1', label: 'Sprint Backlog', count: 5 }],
    },
    total: 25,
    has_more: false,
    next_offset: null,
    trace_id: 'trace-keyword',
    ...overrides,
  };
}

async function stubKeywordSearch(page: Page, payload: KeywordSearchPayload = {}) {
  await page.route(KEYWORD_SEARCH_ROUTE, async (route: Route) => {
    const requestBody = readJsonRequest(route);
    await route.fulfill({
      json: {
        ...keywordResponse(payload),
        query: readQueryValue(requestBody, payload.query ?? 'budget risk'),
      },
    });
  });
}

async function stubKeywordSearchSequence(page: Page) {
  await page.route(KEYWORD_SEARCH_ROUTE, async (route: Route) => {
    const requestBody = readJsonRequest(route);
    if ((requestBody?.offset ?? 0) === 0) {
      await route.fulfill({
        json: keywordResponse({
          has_more: true,
          next_offset: 20,
        }),
      });
      return;
    }
    await route.fulfill({
      json: keywordResponse({
        query: readQueryValue(requestBody, 'budget risk'),
        hits: [
          {
            ...baseHit,
            entity_id: 'issue-2',
            title: 'Second blocker',
            deep_link: '/tool/pms-list-list-1?workspace=hq&issue=issue-2',
          },
        ],
        has_more: false,
        next_offset: null,
      }),
    });
  });
}

async function stubKeywordSearchError(page: Page) {
  await page.route(KEYWORD_SEARCH_ROUTE, (route: Route) =>
    route.fulfill({
      status: 503,
      json: { detail: 'keyword search is unavailable' },
    }),
  );
}

function readJsonRequest(route: Route): Record<string, unknown> {
  const body = route.request().postData();
  if (!body) {
    return {};
  }
  try {
    return JSON.parse(body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function readQueryValue(request: Record<string, unknown>, fallback: string): string {
  return typeof request.query === 'string' ? request.query : fallback;
}

async function failLegacyRagRoutes(page: Page) {
  await page.route('**/api/v1/workspaces/*/rag/**', (route: Route) =>
    route.fulfill({
      status: 500,
      json: { detail: 'legacy RAG API must not be used by /tool/search' },
    }),
  );
}

test.describe('keyword search tool', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
    await failLegacyRagRoutes(page);
  });

  test('renders keyword results with server facets, highlights, preview, and explicit open links', async ({
    page,
  }) => {
    await stubKeywordSearch(page);

    await page.goto('/tool/search?workspace=hq&q=budget%20risk&type=pms_issue');

    await expect(page.getByRole('heading', { name: '아이두 통합검색' })).toBeVisible();
    await expect(page.getByText('25건 중 1건 표시')).toBeVisible();
    await expect(page.getByRole('button', { name: /문서 12/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /회의 4/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /PMS 7/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /일정 2/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeVisible();
    await expect(page.locator('mark').first()).toHaveText('risk');
    await expect(
      page
        .getByRole('complementary', { name: '선택한 검색 결과 미리보기' })
        .getByRole('link', { name: /선택한 결과 열기: Budget blocker/ }),
    ).toHaveAttribute(
      'href',
      '/tool/pms-list-list-1?workspace=hq&issue=issue-1',
    );
    await expect(page.getByText('근거 답변')).toHaveCount(0);
  });

  test('selects a result without leaving search and opens only from explicit action', async ({
    page,
  }) => {
    await stubKeywordSearch(page);

    await page.goto('/tool/search?workspace=hq&q=budget%20risk');
    await page.getByRole('button', { name: /검색 결과 선택: Budget blocker/ }).click();

    await expect(page).toHaveURL(/\/tool\/search\?/);
    await expect(page).toHaveURL(/selected_type=pms_issue/);
    await expect(page).toHaveURL(/selected_id=issue-1/);

    await page
      .getByRole('complementary', { name: '선택한 검색 결과 미리보기' })
      .getByRole('link', { name: /선택한 결과 열기: Budget blocker/ })
      .click();

    await expect(page).toHaveURL(/\/tool\/pms-list-list-1\?workspace=hq&issue=issue-1/);
  });

  test('submits workspace-scoped keyword requests from filters and sort controls', async ({
    page,
  }) => {
    const requests: unknown[] = [];
    await page.route(KEYWORD_SEARCH_ROUTE, async (route: Route) => {
      requests.push(readJsonRequest(route));
      await route.fulfill({ json: keywordResponse() });
    });

    await page.goto('/tool/search?workspace=hq&q=budget%20risk');
    await expect(page.getByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeVisible();

    await page.getByRole('button', { name: /문서/ }).click();
    await expect
      .poll(() => requests.some((request) => hasRequestShape(request, ['doc'], 'relevance')))
      .toBe(true);

    await page.getByRole('button', { name: '최신순' }).first().click();
    await expect
      .poll(() => requests.some((request) => hasRequestShape(request, ['doc'], 'updated_at')))
      .toBe(true);
  });

  test('opens from AI quick action and global AppBar search with workspace scope', async ({
    page,
  }) => {
    await stubKeywordSearch(page, { total: 0, hits: [] });

    await page.goto('/w/hq/ai');
    await page.getByRole('link', { name: '아이두 통합검색', exact: true }).click();
    await expect(page).toHaveURL(/\/tool\/search\?workspace=hq/);

    await page.goto('/w/hq/docs');
    await page.getByRole('button', { name: '통합검색' }).click();
    await expect(page).toHaveURL(/\/tool\/search\?workspace=hq/);
  });

  test('shows compact mobile filters without answer-mode controls', async ({ page }) => {
    await stubKeywordSearch(page, { total: 0, hits: [] });
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/tool/search?workspace=hq');

    await expect(page.getByLabel('통합검색어')).toBeVisible();
    await expect(page.getByRole('button', { name: /전체/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /문서/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /회의/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /PMS/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /일정/ })).toBeVisible();
    await expect(page.getByText('답변 포함')).toHaveCount(0);
  });

  test('shows inline preview on mobile after selecting a result', async ({ page }) => {
    await stubKeywordSearch(page);
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/tool/search?workspace=hq&q=budget%20risk');
    await page.getByRole('button', { name: /검색 결과 선택: Budget blocker/ }).click();

    await expect(page.getByRole('region', { name: /Budget blocker 미리보기/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /선택한 결과 열기: Budget blocker/ })).toBeVisible();
  });

  test('uses pagination metadata for loading more results', async ({ page }) => {
    await stubKeywordSearchSequence(page);

    await page.goto('/tool/search?workspace=hq&q=budget%20risk');
    await expect(page.getByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeVisible();

    await page.getByRole('button', { name: '더 보기' }).click();

    await expect(page.getByRole('button', { name: /검색 결과 선택: Second blocker/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeVisible();
  });

  test('renders an empty state and keyword API error state', async ({ page }) => {
    await stubKeywordSearch(page, { total: 0, hits: [] });

    await page.goto('/tool/search?workspace=hq&q=missing');

    await expect(page.getByText('검색 결과가 없습니다.')).toBeVisible();

    await page.unroute(KEYWORD_SEARCH_ROUTE);
    await stubKeywordSearchError(page);
    await page.getByLabel('통합검색어').fill('budget risk');
    await page.getByRole('button', { name: '검색', exact: true }).click();

    await expect(page.getByText('keyword search is unavailable')).toBeVisible();
  });
});

function hasRequestShape(
  request: unknown,
  entityTypes: string[],
  sortField: 'relevance' | 'updated_at',
) {
  if (!request || typeof request !== 'object') {
    return false;
  }
  const payload = request as {
    workspace_id?: string | null;
    entity_types?: string[];
    sort?: { field?: string; direction?: string };
  };
  return payload.workspace_id === 'workspace-hq'
    && JSON.stringify(payload.entity_types ?? []) === JSON.stringify(entityTypes)
    && payload.sort?.field === sortField
    && payload.sort?.direction === 'desc';
}
