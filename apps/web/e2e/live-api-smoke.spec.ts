import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const AUTH_TOKEN_STORAGE_KEY = 'aidoo.auth.token';
const API_BASE_URL = 'http://127.0.0.1:8000';

type LoginSession = {
  token: string;
};

function collectBrowserErrors(page: Page) {
  const consoleErrors: string[] = [];
  const failedApiResponses: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (message) => {
    const text = message.text();
    const optionalLocalSearchResourceError =
      text.includes('Failed to load resource') &&
      text.includes('503 (Service Unavailable)');
    if (message.type() === 'error' && !optionalLocalSearchResourceError) {
      consoleErrors.push(text);
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });
  page.on('response', (response) => {
    const status = response.status();
    const url = response.url();
    // Local dev smoke can run without a warmed OpenSearch index; the route
    // should still render its empty/error state without breaking the shell.
    const optionalLocalSearchUnavailable =
      status === 503 && url.includes('/api/v1/workspaces/hq/search/query');
    if (
      status >= 400 &&
      url.includes('/api/') &&
      !optionalLocalSearchUnavailable
    ) {
      failedApiResponses.push(`${status} ${response.url()}`);
    }
  });

  return {
    expectClean() {
      expect(pageErrors, 'page errors').toEqual([]);
      expect(failedApiResponses, 'failed API responses').toEqual([]);
      expect(consoleErrors, 'console errors').toEqual([]);
    },
  };
}

async function loginWithDevAccount(
  request: APIRequestContext,
  page: Page,
  accountKey: string,
) {
  const response = await request.post(`${API_BASE_URL}/api/v1/auth/dev-login`, {
    data: { account_key: accountKey },
  });
  expect(response.ok(), await response.text()).toBe(true);
  const session = await response.json() as LoginSession;
  await page.addInitScript(
    ([key, token]) => window.localStorage.setItem(key, token),
    [AUTH_TOKEN_STORAGE_KEY, session.token],
  );
}

test.describe('live API shell smoke', () => {
  test('opens workspace apps and tool routes against the local API', async ({ page, request }) => {
    await loginWithDevAccount(request, page, 'hq-admin');
    const errors = collectBrowserErrors(page);

    const routes: Array<{
      path: string;
      heading: string | RegExp;
    }> = [
      { path: '/w/hq/home', heading: /Good/ },
      { path: '/w/hq/ai', heading: 'AI' },
      { path: '/w/hq/pms', heading: 'PMS' },
      { path: '/w/hq/docs', heading: 'DOCS' },
      { path: '/w/hq/planner', heading: 'Planner' },
      { path: '/w/hq/meeting', heading: 'MEETING' },
      { path: '/w/hq/learning', heading: '학습' },
      { path: '/w/hq/settings', heading: 'Aidoo HQ' },
      { path: '/tool/search?workspace=hq', heading: '아이두 통합검색' },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect(page).toHaveURL(new RegExp(`${route.path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
      await expect(page.getByRole('heading', { name: route.heading }).first()).toBeVisible();
    }

    errors.expectClean();
  });

  test('opens admin workspace management against the local API', async ({ page, request }) => {
    await loginWithDevAccount(request, page, 'platform-admin');
    const errors = collectBrowserErrors(page);

    await page.goto('/admin/workspaces');
    await expect(page.getByRole('heading', { name: 'Workspaces', exact: true })).toBeVisible();

    errors.expectClean();
  });

  test('keeps legacy top-level app routes on NotFoundView', async ({ page, request }) => {
    await loginWithDevAccount(request, page, 'hq-admin');
    const errors = collectBrowserErrors(page);

    for (const path of ['/meeting', '/docs', '/pms', '/planner', '/ai']) {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(page.getByRole('heading', { name: '페이지를 찾을 수 없습니다' })).toBeVisible();
    }

    errors.expectClean();
  });
});
