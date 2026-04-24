import { expect, test, type Page, type Route } from '@playwright/test';

import { stubShellBackend } from './helpers';

async function stubRagSources(page: Page) {
  await page.route('**/api/v1/workspaces/*/rag/sources', (route: Route) =>
    route.fulfill({
      json: {
        sources: [
          {
            source_kind: 'manual',
            resource_type: 'docs_native_doc',
            label: 'Docs / Manual',
            app_id: 'docs',
          },
          {
            source_kind: 'meeting',
            resource_type: 'meeting',
            label: 'Meetings',
            app_id: 'meeting',
          },
          {
            source_kind: 'pms_issue',
            resource_type: 'pms_issue',
            label: 'PMS Issues',
            app_id: 'pms',
          },
        ],
      },
    }),
  );
}

async function stubRagQuery(page: Page, payload: unknown) {
  await page.route('**/api/v1/workspaces/*/rag/query', (route: Route) =>
    route.fulfill({ json: payload }),
  );
}

async function stubRagQueryError(page: Page) {
  await page.route('**/api/v1/workspaces/*/rag/query', (route: Route) =>
    route.fulfill({
      status: 503,
      json: { detail: 'RAG query is unavailable: The read operation timed out' },
    }),
  );
}

test.describe('RAG search tool', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
    await stubRagSources(page);
  });

  test('renders grounded answers with citation cards for docs hits', async ({ page }) => {
    await stubRagQuery(page, {
      query: 'budget risk',
      answer_mode: 'grounded-answer',
      hits: [
        {
          source_kind: 'manual',
          resource_type: 'docs_native_doc',
          resource_id: 'doc-1',
          workspace_id: 'hq',
          title: 'Budget Review',
          summary: 'Supplier repricing increased the budget risk.',
          score: 0.91,
          citation: 'doc-1:0',
          owner_label: 'Kim',
          acl_summary: [],
          origin_ref: 'docs:doc-1',
          metadata: {},
        },
      ],
      grounded_answer: {
        text: 'Budget risk is elevated because supplier repricing changed the cost baseline.',
        citations: [
          {
            resource_id: 'doc-1',
            source_kind: 'manual',
            quote: 'Supplier repricing increased the budget risk.',
            locator: 'doc-1:0',
          },
        ],
        unsupported_claims: [],
        sources_used: ['manual'],
      },
      sources_used: ['manual'],
      query_profile: {},
      trace_id: 'trace-docs',
      latency_ms: 142,
    });

    await page.goto('/tool/search?workspace=hq&q=budget%20risk&source=manual');

    await expect(page.getByText('근거 답변')).toBeVisible();
    await expect(
      page.getByText(
        'Budget risk is elevated because supplier repricing changed the cost baseline.',
      ),
    ).toBeVisible();
    await expect(page.getByText('“Supplier repricing increased the budget risk.”')).toBeVisible();
    await expect(page.getByRole('link', { name: '근거 문서 열기' })).toHaveAttribute('href', '/w/hq/docs/doc-1');
  });

  test('opens search from AI quick action and global AppBar search', async ({ page }) => {
    await page.goto('/w/hq/ai');

    await page.getByRole('link', { name: '아이두 통합검색', exact: true }).click();
    await expect(page).toHaveURL(/\/tool\/search\?workspace=hq/);

    await page.goto('/w/hq/docs');
    await page.getByRole('button', { name: '통합검색' }).click();
    await expect(page).toHaveURL(/\/tool\/search\?workspace=hq/);
  });

  test('shows pre-search recommendations and keeps source filters near the input on mobile', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/tool/search?workspace=hq');

    await expect(page.getByText('추천 질문')).toBeVisible();
    await expect(page.getByRole('button', { name: '문서', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '상세 검색 대상 전체 검색 대상' })).toBeVisible();
  });

  test('shows the empty state when no accessible hits remain after filtering', async ({ page }) => {
    await stubRagQuery(page, {
      query: 'budget risk',
      answer_mode: 'grounded-answer',
      hits: [],
      grounded_answer: null,
      sources_used: [],
      query_profile: {},
      trace_id: 'trace-empty',
      latency_ms: 87,
    });

    await page.goto('/tool/search?workspace=hq&q=budget%20risk&source=manual');

    await expect(page.getByText('현재 조건에서 접근 가능한 결과를 찾지 못했습니다.')).toBeVisible();
  });

  test('renders meeting transcript hits with workspace-scoped links', async ({ page }) => {
    await stubRagQuery(page, {
      query: 'launch follow up',
      answer_mode: 'search-only',
      hits: [
        {
          source_kind: 'meeting',
          resource_type: 'meeting',
          resource_id: 'meeting-1',
          workspace_id: 'hq',
          title: 'Launch Follow-up',
          summary: 'Transcript highlights the unresolved launch blocker.',
          score: 0.84,
          citation: 'meeting-1:0',
          owner_label: null,
          acl_summary: [],
          origin_ref: null,
          metadata: {},
        },
      ],
      grounded_answer: null,
      sources_used: ['meeting'],
      query_profile: {},
      trace_id: 'trace-meeting',
      latency_ms: 96,
    });

    await page.goto('/tool/search?workspace=hq&q=launch%20follow%20up&mode=search-only&source=meeting');

    await expect(page.getByText('Launch Follow-up')).toBeVisible();
    await expect(page.getByRole('link', { name: '원문 열기' })).toHaveAttribute('href', '/w/hq/meeting/meeting-1');
  });

  test('renders PMS issue hits with workspace-scoped tool links', async ({ page }) => {
    await stubRagQuery(page, {
      query: 'private blocker',
      answer_mode: 'search-only',
      hits: [
        {
          source_kind: 'pms_issue',
          resource_type: 'pms_issue',
          resource_id: 'issue-1',
          workspace_id: 'hq',
          title: 'Blocked task',
          summary: 'Private issue visible only to the current workspace members.',
          score: 0.8,
          citation: 'issue-1:0',
          owner_label: null,
          acl_summary: ['team access'],
          origin_ref: null,
          metadata: { list_id: 'list-1' },
        },
      ],
      grounded_answer: null,
      sources_used: ['pms_issue'],
      query_profile: {},
      trace_id: 'trace-pms',
      latency_ms: 91,
    });

    await page.goto('/tool/search?workspace=hq&q=private%20blocker&mode=search-only&source=pms_issue');

    await expect(page.getByText('Blocked task')).toBeVisible();
    await expect(page.getByRole('link', { name: '원문 열기' })).toHaveAttribute(
      'href',
      '/tool/pms-list-list-1?workspace=hq&issue=issue-1',
    );
  });

  test('shows a degraded banner when grounded-answer synthesis falls back to search-only', async ({
    page,
  }) => {
    await stubRagQuery(page, {
      query: 'budget risk',
      answer_mode: 'grounded-answer',
      hits: [
        {
          source_kind: 'manual',
          resource_type: 'docs_native_doc',
          resource_id: 'doc-1',
          workspace_id: 'hq',
          title: 'Budget Review',
          summary: 'Supplier repricing increased the budget risk.',
          score: 0.91,
          citation: 'doc-1:0',
          owner_label: 'Kim',
          acl_summary: [],
          origin_ref: 'docs:doc-1',
          metadata: {},
        },
      ],
      grounded_answer: null,
      sources_used: ['manual'],
      query_profile: { grounded_answer_degraded: true },
      trace_id: 'trace-degraded',
      latency_ms: 118,
    });

    await page.goto('/tool/search?workspace=hq&q=budget%20risk&source=manual');

    await expect(
      page.getByText('근거 답변 생성에 실패해 검색 결과만 표시합니다. 인용과 원문 링크를 확인해주세요.'),
    ).toBeVisible();
    await expect(page.getByText('원본 docs:doc-1')).toBeVisible();
  });

  test('shows recovery actions when RAG query times out', async ({ page }) => {
    await stubRagQueryError(page);

    await page.goto('/tool/search?workspace=hq');
    await page.getByLabel('질문 또는 검색어').fill('budget risk');
    await page.getByRole('button', { name: '검색', exact: true }).click();

    await expect(page.getByText('검색 서비스 응답 지연')).toBeVisible();
    await expect(page.getByRole('button', { name: '다시 시도' })).toBeVisible();
    await expect(page.getByRole('button', { name: '검색 결과만 보기' })).toBeVisible();
  });
});
