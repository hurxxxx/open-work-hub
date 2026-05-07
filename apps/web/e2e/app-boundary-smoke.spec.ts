import { expect, test, type Page } from '@playwright/test';

import {
  FAKE_PLATFORM_ADMIN_USER,
  stubConversationsApi,
  stubShellBackend,
  stubWorkspaceAppDataBackend,
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
  await stubWorkspaceAppDataBackend(page);
  await stubShellBackend(page);
  await stubConversationsApi(page);
}

test.describe('AI-friendly app boundary smoke', () => {
  test('renders workspace apps and tool wrappers through the shell registry', async ({ page }) => {
    await stubFullShell(page);
    const errors = collectBrowserErrors(page);

    const routes: Array<{
      path: string;
      assert: (page: Page) => Promise<void>;
    }> = [
      {
        path: '/w/hq/home',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: /Good/ })).toBeVisible();
        },
      },
      {
        path: '/w/hq/ai',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: 'AI' })).toBeVisible();
          await expect(current.getByText('안녕하세요, 업무를 도와드릴게요.')).toBeVisible();
        },
      },
      {
        path: '/w/hq/pms',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: 'PMS', exact: true })).toBeVisible();
          await expect(current.getByRole('link', { name: 'Assigned to me' })).toBeVisible();
        },
      },
      {
        path: '/w/hq/docs',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: 'DOCS', exact: true })).toBeVisible();
          await expect(current.getByRole('link', { name: 'All Docs' })).toBeVisible();
        },
      },
      {
        path: '/w/hq/planner',
        assert: async (current) => {
          await expect(current.getByRole('heading', { level: 1, name: 'Planner' })).toBeVisible();
          await expect(current.getByRole('link', { name: '캘린더' })).toBeVisible();
        },
      },
      {
        path: '/w/hq/meeting',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: 'MEETING', exact: true })).toBeVisible();
          await expect(current.getByRole('button', { name: 'New Meeting' }).first()).toBeVisible();
        },
      },
      {
        path: '/w/hq/learning',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: '학습' })).toBeVisible();
          await expect(current.getByRole('region', { name: '코스 목록' })).toBeVisible();
        },
      },
      {
        path: '/w/hq/settings',
        assert: async (current) => {
          await expect(current.getByText('Workspace Settings')).toBeVisible();
          await expect(current.getByRole('heading', { level: 1, name: 'AI-DO HQ' })).toBeVisible();
        },
      },
      {
        path: '/tool/search?workspace=hq',
        assert: async (current) => {
          await expect(current.getByRole('heading', { name: 'AI-DO 통합검색' })).toBeVisible();
        },
      },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect(page).toHaveURL(new RegExp(`${route.path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`));
      await route.assert(page);
    }

    errors.expectClean();
  });

  test('keeps disabled workspace apps blocked by WorkspaceGate', async ({ page }) => {
    await stubWorkspaceAppDataBackend(page);
    await stubShellBackend(page, {
      enabledAppIds: ['home', 'ai', 'pms', 'docs', 'planner', 'learning'],
    });
    await stubConversationsApi(page);
    const errors = collectBrowserErrors(page);

    await page.goto('/w/hq/meeting');

    await expect(page.getByRole('heading', { name: '접근 권한 없음' })).toBeVisible();
    await expect(
      page.getByText('현재 workspace에서는 이 앱이 활성화되어 있지 않습니다.'),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'MEETING' })).toHaveCount(0);
    errors.expectClean();
  });

  test('keeps legacy top-level app paths on NotFoundView', async ({ page }) => {
    await stubFullShell(page);
    const errors = collectBrowserErrors(page);

    for (const path of ['/meeting', '/docs', '/pms', '/planner', '/ai']) {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(
        page.getByRole('heading', { name: '페이지를 찾을 수 없습니다' }),
      ).toBeVisible();
    }

    errors.expectClean();
  });

  test('renders admin sections for platform admin through settings boundaries', async ({ page }) => {
    await stubWorkspaceAppDataBackend(page);
    await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
    const errors = collectBrowserErrors(page);

    await page.goto('/admin/general');
    await expect(page.getByRole('heading', { name: 'General settings' })).toBeVisible();

    await page.goto('/admin/workspaces');
    await expect(page.getByRole('heading', { name: 'Workspaces', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /AI-DO HQ/ })).toBeVisible();

    errors.expectClean();
  });
});
