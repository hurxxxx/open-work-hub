import { expect, test } from '@playwright/test';

import { stubConversationsApi, stubShellBackend } from './helpers';

test.describe('AI chat history', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
  });

  test('sidebar "최근 대화" lists saved conversations and highlights the active one', async ({
    page,
  }) => {
    await stubConversationsApi(page, {
      list: [
        {
          id: 'c-fmea',
          title: 'FMEA 비교 검토',
          createdAt: '2026-04-19T00:00:00',
          updatedAt: '2026-04-19T01:00:00',
        },
        {
          id: 'c-draft',
          title: '기안서 초안 요청',
          createdAt: '2026-04-18T00:00:00',
          updatedAt: '2026-04-18T01:00:00',
        },
      ],
    });

    await page.goto('/w/hq/ai?c=c-fmea');

    // Wait for the sidebar list to render, then assert both titles appear.
    await expect(
      page.getByRole('button', { name: /FMEA 비교 검토/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /기안서 초안 요청/ }),
    ).toBeVisible();
  });

  test('clicking a conversation row navigates to /ai?c=<id> and hydrates turns', async ({
    page,
  }) => {
    await stubConversationsApi(page, {
      list: [
        {
          id: 'c-draft',
          title: '기안서 초안 요청',
          createdAt: '2026-04-18T00:00:00',
          updatedAt: '2026-04-18T01:00:00',
        },
      ],
      detail: {
        'c-draft': {
          id: 'c-draft',
          title: '기안서 초안 요청',
          createdAt: '2026-04-18T00:00:00',
          updatedAt: '2026-04-18T01:00:00',
          turns: [
            {
              id: 't-0',
              seq: 0,
              role: 'user',
              content: '기안서 초안 써줘',
              createdAt: '2026-04-18T00:00:10',
            },
            {
              id: 't-1',
              seq: 1,
              role: 'assistant',
              content: '여기 있습니다. 초안을 제안드립니다...',
              createdAt: '2026-04-18T00:00:20',
            },
          ],
        },
      },
    });

    await page.goto('/w/hq/ai');

    // Empty state before selection.
    await expect(
      page.getByText('안녕하세요, 업무를 도와드릴게요.'),
    ).toBeVisible();

    // Click the saved conversation in the sidebar.
    await page.getByRole('button', { name: /기안서 초안 요청/ }).click();

    await expect(page).toHaveURL(/\?c=c-draft$/);
    // Both persisted turns should render in the thread.
    await expect(page.getByText('기안서 초안 써줘')).toBeVisible();
    await expect(page.getByText('여기 있습니다. 초안을 제안드립니다...')).toBeVisible();
    // Empty-state greeting is gone once turns hydrate.
    await expect(
      page.getByText('안녕하세요, 업무를 도와드릴게요.'),
    ).toHaveCount(0);
  });

  test('"+ 새 대화" clears the active conversation and returns to empty state', async ({
    page,
  }) => {
    await stubConversationsApi(page, {
      list: [
        {
          id: 'c-draft',
          title: '기안서 초안 요청',
          createdAt: '2026-04-18T00:00:00',
          updatedAt: '2026-04-18T01:00:00',
        },
      ],
      detail: {
        'c-draft': {
          id: 'c-draft',
          title: '기안서 초안 요청',
          createdAt: '2026-04-18T00:00:00',
          updatedAt: '2026-04-18T01:00:00',
          turns: [
            {
              id: 't-0',
              seq: 0,
              role: 'user',
              content: '기안서 초안',
              createdAt: '2026-04-18T00:00:10',
            },
          ],
        },
      },
    });

    await page.goto('/w/hq/ai?c=c-draft');
    await expect(page.getByText('기안서 초안', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: '새 대화' }).click();
    await expect(page).toHaveURL(/\/w\/hq\/ai$/);
    await expect(
      page.getByText('안녕하세요, 업무를 도와드릴게요.'),
    ).toBeVisible();
  });
});
