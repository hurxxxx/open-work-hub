import { expect, test, type Page } from '@playwright/test';
import { APP_CONTRACTS } from '@open-work-hub/contracts/app-contracts';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import {
  FAKE_PLATFORM_ADMIN_USER,
  stubConversationsApi,
  stubShellBackend,
  stubAppDataBackend,
} from './helpers';

function collectBrowserErrors(page: Page) {
  const consoleErrors: string[] = [];
  const failedApiResponses: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });
  page.on('response', (response) => {
    const status = response.status();
    if (status >= 400 && response.url().includes('/api/')) {
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

async function stubFullShell(page: Page) {
  await stubAppDataBackend(page);
  await stubShellBackend(page);
  await stubConversationsApi(page);
}

test.describe('AI-friendly app boundary smoke', () => {
  test('opens admitted apps directly from the company launcher', async ({
    page,
  }) => {
    await stubFullShell(page);
    const errors = collectBrowserErrors(page);

    await page.goto('/');
    await expect(
      page.getByRole('heading', { level: 1, name: /앱 런처|App launcher/ }),
    ).toBeVisible();
    await page.locator('a[href="/apps/docs"]').click();
    await expect(page).toHaveURL(/\/apps\/docs$/);
    await expect(page.getByText(/^(실행 범위|Execution scope)$/)).toHaveCount(
      0,
    );
    await page.goto('/apps/planner');
    await expect(page).toHaveURL(/\/apps\/planner$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /Planner|플래너/ }),
    ).toBeVisible();
    errors.expectClean();
  });

  test('does not fetch app data when admission is denied', async ({ page }) => {
    const deniedRequests: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).pathname.startsWith('/api/v1/meeting/'))
        deniedRequests.push(request.url());
    });
    await stubShellBackend(page, { enabledAppIds: ['home'] });
    await page.goto('/apps/meeting');
    await expect(
      page.getByRole('heading', { name: /접근 권한 없음|No access/ }),
    ).toBeVisible();
    expect(deniedRequests).toEqual([]);
  });

  test('renders company apps and tool wrappers through the shell registry', async ({
    page,
  }) => {
    await stubFullShell(page);
    const errors = collectBrowserErrors(page);

    const routes: Array<{
      path: string;
      assert: (page: Page) => Promise<void>;
    }> = [
      {
        path: '/apps/home',
        assert: async (current) => {
          await expect(current.getByText(/Good/)).toBeVisible();
        },
      },
      {
        path: '/apps/chatbot',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', {
              name: /AI 어시스턴트 챗봇|AI Assistant Chatbot/,
            }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/pms',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { name: 'PMS', exact: true }).or(
              current.getByRole('heading', {
                name: /^(No Spaces Yet|아직 스페이스가 없습니다)$/,
              }),
            ),
          ).toBeVisible();
          await expect(
            current
              .getByRole('link', { name: /Assigned to me|내게 배정됨/ })
              .or(
                current.getByRole('button', {
                  name: /Create Space|스페이스 만들기/,
                }),
              )
              .first(),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/docs',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', {
              level: 1,
              name: /All Docs|전체 문서/,
            }),
          ).toBeVisible();
          await expect(
            current.getByRole('button', { name: /New Doc|새 Doc/ }).first(),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/planner',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { level: 1, name: /Planner|플래너/ }),
          ).toBeVisible();
          await expect(
            current.getByRole('button', { name: /Calendar|캘린더/ }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/meeting',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { level: 1, name: /Meetings|회의/ }),
          ).toBeVisible();
          await expect(
            current
              .getByRole('button', { name: /New Meeting|새 회의/ })
              .first(),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/retrieval-search',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', {
              level: 1,
              name: /Retrieval 진단 검색|Retrieval diagnostics search/,
            }),
          ).toBeVisible();
        },
      },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect(page).toHaveURL(
        new RegExp(`${route.path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
      );
      await route.assert(page);
    }

    errors.expectClean();
  });

  test('mounts every executable app entry without falling through to NotFoundView', async ({
    context,
  }) => {
    test.setTimeout(120_000);
    for (const app of APP_CONTRACTS) {
      await test.step(app.app_id, async () => {
        const appPage = await context.newPage();
        try {
          await stubAppDataBackend(appPage);
          await stubShellBackend(appPage, {
            enabledAppIds: APP_CONTRACTS.map((contract) => contract.app_id),
          });
          await stubConversationsApi(appPage);

          const href = buildAppHref({
            routeId: app.entry_route_id,
          });
          await appPage.goto(href, { waitUntil: 'domcontentloaded' });
          await expect(appPage).toHaveURL(
            new RegExp(`${href.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
          );
          await expect(
            appPage.getByRole('navigation', {
              name: /주요 앱 탐색|Primary app navigation/,
            }),
          ).toBeVisible();
          await expect(
            appPage.getByRole('heading', {
              name: /페이지를 찾을 수 없습니다|Page not found/,
            }),
            app.app_id,
          ).toHaveCount(0);
        } finally {
          await appPage.close();
        }
      });
    }
  });

  test('opens a newly created Bento presentation on its canonical detail route', async ({
    page,
  }) => {
    await stubFullShell(page);
    const document = {
      id: 'presentation-1',
      title: 'Untitled Presentation',
      visibility: 'personal',
      version: 1,
      created_by_id: 'user-e2e',
      created_by_name: 'E2E Tester',
      created_at: '2026-08-31T00:00:00Z',
      updated_at: '2026-08-31T00:00:00Z',
      archived_at: null,
      can_edit: true,
      can_manage: true,
      document_json: '{}',
    };
    await page.route('**/api/v1/bento/**', (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (pathname.endsWith('/bento/hub')) {
        return route.fulfill({
          json: { items: [], view: 'all', page: 1, page_size: 200, total: 0 },
        });
      }
      if (pathname.endsWith('/bento/ai-jobs')) {
        return route.fulfill({ json: [] });
      }
      if (pathname.endsWith('/bento/items') && request.method() === 'POST') {
        return route.fulfill({ json: document });
      }
      if (pathname.endsWith('/bento/items/presentation-1')) {
        return route.fulfill({ json: document });
      }
      return route.fulfill({ status: 404, json: { detail: 'not stubbed' } });
    });

    await page.goto('/apps/bento');
    await page
      .getByRole('button', { name: /새 프레젠테이션|New presentation/ })
      .first()
      .click();

    await expect(page).toHaveURL(
      /\/apps\/bento\/presentations\/presentation-1$/,
    );
    await expect(
      page.getByRole('heading', {
        name: /페이지를 찾을 수 없습니다|Page not found/,
      }),
    ).toHaveCount(0);
  });

  test('keeps denied apps blocked before their data loads', async ({
    page,
  }) => {
    await stubAppDataBackend(page);
    await stubShellBackend(page, {
      enabledAppIds: ['home', 'chatbot', 'docs', 'planner', 'pms'],
    });
    await stubConversationsApi(page);
    const errors = collectBrowserErrors(page);

    await page.goto('/apps/meeting');

    await expect(
      page.getByRole('heading', { name: '접근 권한 없음' }),
    ).toBeVisible();
    await expect(
      page.getByText('현재 계정은 이 앱을 사용할 수 없습니다.'),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'MEETING' })).toHaveCount(0);
    errors.expectClean();
  });

  test('keeps legacy top-level app paths on NotFoundView', async ({ page }) => {
    await stubFullShell(page);
    const errors = collectBrowserErrors(page);

    for (const path of ['/meeting', '/docs', '/pms', '/chatbot']) {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(
        page.getByRole('heading', { name: '페이지를 찾을 수 없습니다' }),
      ).toBeVisible();
    }

    errors.expectClean();
  });

  test('renders admin sections for platform admin through settings boundaries', async ({
    page,
  }) => {
    await stubAppDataBackend(page);
    await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
    const errors = collectBrowserErrors(page);

    await page.goto('/admin/general');
    await expect(
      page.locator('main').getByRole('heading', { level: 1 }),
    ).toBeVisible();

    await page.goto('/admin/groups');
    await expect(
      page.locator('main').getByRole('heading', { level: 1 }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', {
        name: /수동 그룹 생성|Create manual group/,
      }),
    ).toBeVisible();

    errors.expectClean();
  });
});
