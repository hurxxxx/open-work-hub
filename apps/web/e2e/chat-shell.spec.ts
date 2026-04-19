import { expect, test } from '@playwright/test';

import { stubAiChatStream, stubShellBackend } from './helpers';

test.describe('AI chat shell', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
  });

  test('empty state renders greeting + composer + suggestion cards', async ({
    page,
  }) => {
    await page.goto('/w/hq/ai');

    await expect(
      page.getByText('안녕하세요, 업무를 도와드릴게요.'),
    ).toBeVisible();
    await expect(
      page.getByPlaceholder('메시지를 입력하세요'),
    ).toBeVisible();

    // Four suggestion cards, each linking to /tool/:id.
    const cards = page.locator('a[href^="/tool/"]');
    await expect(cards).toHaveCount(4);
  });

  test('clicking a suggestion card navigates to /tool/:id', async ({ page }) => {
    await page.goto('/w/hq/ai');

    // Scope to the EmptyState suggestion grid — the SubSidebar also renders
    // a link for every AI tool, which would make `getByRole('link')` ambiguous.
    const suggestionCard = page
      .locator('a[href^="/tool/"]')
      .filter({ hasText: '아이두 통합검색' })
      .first();
    await suggestionCard.click();
    await expect(page).toHaveURL(/\/tool\/search$/);
  });

  test('slash command palette opens for "/" and routes on Enter', async ({
    page,
  }) => {
    await page.goto('/w/hq/ai');

    const composer = page.getByPlaceholder('메시지를 입력하세요');
    await composer.fill('/fmea');

    // Palette is a listbox above the textarea.
    const listbox = page.getByRole('listbox');
    await expect(listbox).toBeVisible();
    await expect(listbox.getByText('FMEA 비교')).toBeVisible();

    await composer.press('Enter');
    await expect(page).toHaveURL(/\/tool\/fmea-compare$/);
  });

  test('slash menu hides for literal slash-prefixed prompts like /tmp', async ({
    page,
  }) => {
    await page.goto('/w/hq/ai');

    const composer = page.getByPlaceholder('메시지를 입력하세요');
    await composer.fill('/tmp');

    await expect(page.getByRole('listbox')).toHaveCount(0);
    // Send button should be enabled so the user can actually submit the prompt.
    const sendButton = page.getByRole('button', { name: /전송/ });
    await expect(sendButton).toBeEnabled();
  });

  test('sending a message transitions from empty hero to active thread', async ({
    page,
  }) => {
    await stubAiChatStream(page, { assistantText: '테스트 응답입니다.' });
    await page.goto('/w/hq/ai');

    const composer = page.getByPlaceholder('메시지를 입력하세요');
    await composer.fill('안녕');
    await composer.press('Enter');

    // Empty-state greeting should disappear once the user turn is added.
    await expect(
      page.getByText('안녕하세요, 업무를 도와드릴게요.'),
    ).toHaveCount(0);
    // User turn + assistant response both land in the thread.
    await expect(page.getByText('안녕').first()).toBeVisible();
    await expect(page.getByText('테스트 응답입니다.')).toBeVisible();
  });

  test('ModelPill popover exposes the routing mode toggle', async ({
    page,
  }) => {
    await page.goto('/w/hq/ai');

    // Pill label carries the canonical model when health is local-ready.
    await page.getByRole('button', { name: /자동 라우팅/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('라우팅 모드')).toBeVisible();
    await expect(dialog.getByText('Local pool')).toBeVisible();
  });
});
