import { expect, test, type Page } from '@playwright/test';

import {
  FAKE_WORKSPACE_USER,
  stubConversationsApi,
  stubShellBackend,
  stubWorkspaceAppDataBackend,
} from './helpers';

const LOCALE_STORAGE_KEY = 'open-work-hub:locale';

async function stubFullShell(
  page: Page,
  onLocalePatch: (locale: string) => void,
) {
  await stubWorkspaceAppDataBackend(page);
  await stubShellBackend(page, {
    onUpdatePreferences: (payload) => {
      if (typeof payload.locale === 'string') {
        onLocalePatch(payload.locale);
      }
    },
  });
  await stubConversationsApi(page);
}

async function stubEnglishWorkspaceShell(page: Page) {
  await stubWorkspaceAppDataBackend(page);
  await stubShellBackend(page, {
    user: {
      ...FAKE_WORKSPACE_USER,
      locale: 'en-US',
    },
  });
  await stubConversationsApi(page);
}

test.describe('i18n locale smoke', () => {
  test('persists language changes through settings, localStorage, and session reloads', async ({
    page,
  }) => {
    const patchedLocales: string[] = [];
    await stubFullShell(page, (locale) => patchedLocales.push(locale));

    await page.goto('/apps/home/workspaces/hq');
    await expect(page.getByRole('button', { name: '내 설정' })).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.lang))
      .toBe('ko-KR');

    await page.getByRole('button', { name: '내 설정' }).click();
    await expect(page.getByRole('heading', { name: '내 설정' })).toBeVisible();
    await page.getByRole('button', { name: '화면 설정' }).click();
    await expect(
      page.getByRole('heading', { name: '화면 설정' }),
    ).toBeVisible();

    await page.getByRole('combobox').first().selectOption('en-US');
    await expect(
      page.getByRole('heading', { name: 'My Settings' }),
    ).toBeVisible();
    await expect(
      page.getByText('Used for app messages, dates, and relative times.'),
    ).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.lang))
      .toBe('en-US');
    await expect
      .poll(() =>
        page.evaluate(
          (key) => window.localStorage.getItem(key),
          LOCALE_STORAGE_KEY,
        ),
      )
      .toBe('en-US');
    expect(patchedLocales).toContain('en-US');

    await page.reload();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.lang))
      .toBe('en-US');
    await expect(
      page.getByRole('button', { name: 'My Settings' }),
    ).toBeVisible();

    await page.getByRole('button', { name: 'My Settings' }).click();
    await page.getByRole('button', { name: 'Appearance' }).click();
    await page.getByRole('combobox').first().selectOption('ko-KR');
    await expect(page.getByRole('heading', { name: '내 설정' })).toBeVisible();
    await expect(
      page.getByText('앱 화면 메시지와 날짜/상대시간 표시에 사용됩니다.'),
    ).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.lang))
      .toBe('ko-KR');
    await expect
      .poll(() =>
        page.evaluate(
          (key) => window.localStorage.getItem(key),
          LOCALE_STORAGE_KEY,
        ),
      )
      .toBe('ko-KR');
    expect(patchedLocales).toContain('ko-KR');
  });

  test('renders representative English copy across workspace apps', async ({
    page,
  }) => {
    await stubEnglishWorkspaceShell(page);

    const routes: Array<{
      path: string;
      assert: (current: Page) => Promise<void>;
    }> = [
      {
        path: '/apps/home/workspaces/hq',
        assert: async (current) => {
          await expect(
            current.getByRole('link', { name: 'New Meeting' }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/chatbot/workspaces/hq',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { name: 'AI Assistant Chatbot' }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/pms/workspaces/hq',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { name: 'No Spaces Yet' }),
          ).toBeVisible();
          await expect(
            current
              .getByRole('button', { name: 'Create Space' })
              .filter({ hasText: 'Create Space' }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/docs/workspaces/hq',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { name: 'No Docs found' }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/planner',
        assert: async (current) => {
          await expect(
            current.getByRole('button', { name: 'Month' }),
          ).toBeVisible();
          await expect(
            current.getByRole('button', { name: 'Today', exact: true }),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/meeting/workspaces/hq',
        assert: async (current) => {
          await expect(
            current.getByText('No upcoming meetings.'),
          ).toBeVisible();
        },
      },
      {
        path: '/admin/workspaces/hq/settings',
        assert: async (current) => {
          await expect(
            current.getByText('Workspace Settings', { exact: true }).first(),
          ).toBeVisible();
        },
      },
      {
        path: '/apps/retrieval-search/workspaces/hq',
        assert: async (current) => {
          await expect(
            current.getByRole('heading', { name: 'Open Work Hub Search' }),
          ).toBeVisible();
          await expect(
            current.getByPlaceholder(
              'Search docs, meetings, tasks, and schedules',
            ),
          ).toBeVisible();
        },
      },
    ];

    for (const route of routes) {
      await page.goto(route.path);
      await expect
        .poll(() => page.evaluate(() => document.documentElement.lang))
        .toBe('en-US');
      await route.assert(page);
    }
  });
});
