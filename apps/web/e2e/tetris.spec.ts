import { expect, test } from '@playwright/test';
import {
  FAKE_COMPANY_USER,
  stubAppDataBackend,
  stubConversationsApi,
  stubShellBackend,
} from './helpers';

test('plays through the launcher and resets after reload and navigation', async ({
  page,
}) => {
  await stubAppDataBackend(page);
  await stubShellBackend(page);
  await stubConversationsApi(page);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page.locator('a[href="/apps/tetris"]').first().click();
  await expect(page).toHaveURL(/\/apps\/tetris$/);
  const board = page.getByRole('region', { name: /게임 보드|Game board/ });
  const start = page.getByRole('button', { name: /게임 시작|Start game/ });
  const resume = page.getByRole('button', { name: /게임 재개|Resume game/ });
  await start.click();
  await expect(board).toBeFocused();
  await board.press('ArrowDown');
  await expect(page.getByTestId('tetris-score')).toHaveText('1');
  const beforeScroll = await page.evaluate(() => window.scrollY);
  await board.press('Space');
  await expect(page.getByTestId('tetris-score')).not.toHaveText('1');
  expect(await page.evaluate(() => window.scrollY)).toBe(beforeScroll);
  await board.press('KeyP');
  await expect(resume).toBeVisible();
  const paused = await board.innerHTML();
  await page.waitForTimeout(1100);
  expect(await board.innerHTML()).toBe(paused);
  await resume.click();
  await expect(board).toBeFocused();
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await expect(resume).toBeVisible();
  await page.reload();
  await expect(start).toBeVisible();
  await expect(page.getByTestId('tetris-score')).toHaveText('0');
  await start.click();
  await board.press('Space');
  await page.goto('/');
  await page.locator('a[href="/apps/tetris"]').first().click();
  await expect(start).toBeVisible();
  await expect(page.getByTestId('tetris-score')).toHaveText('0');
  expect(errors).toEqual([]);
});

test('denies direct entry when the server bootstrap does not admit the app', async ({
  page,
}) => {
  await stubShellBackend(page, { enabledAppIds: ['home'] });
  await page.goto('/apps/tetris');
  await expect(
    page.getByRole('heading', { name: /접근 권한 없음|No access/ }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: /게임 시작|Start game/ }),
  ).toHaveCount(0);
});

test('ends a stacked game and restarts from an empty board', async ({
  page,
}) => {
  await stubAppDataBackend(page);
  await stubShellBackend(page);
  await stubConversationsApi(page);
  await page.goto('/apps/tetris');
  await page.getByRole('button', { name: /게임 시작|Start game/ }).click();
  const drop = page.getByRole('button', { name: /즉시 낙하|Drop instantly/ });
  for (let i = 0; i < 25 && (await drop.isEnabled()); i++) await drop.click();
  await expect(page.getByRole('status')).toHaveText(/게임 오버|Game over/);
  await expect(drop).toBeDisabled();
  await page.getByRole('button', { name: /다시 시작|Restart game/ }).click();
  await expect(page.getByTestId('tetris-score')).toHaveText('0');
  await expect(drop).toBeEnabled();
  const board = page.getByRole('region', { name: /게임 보드|Game board/ });
  await expect(board.locator('[data-cell]:not([data-cell=""])')).toHaveCount(4);
});

test.describe('narrow touch screens', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 740 } });
  for (const locale of ['ko-KR', 'en-US'] as const) {
    test(`plays using screen buttons in ${locale} and both themes`, async ({
      page,
    }) => {
      await stubAppDataBackend(page);
      await stubShellBackend(page, { user: { ...FAKE_COMPANY_USER, locale } });
      await stubConversationsApi(page);
      await page.goto('/apps/tetris');
      const board = page.getByRole('region', { name: /게임 보드|Game board/ });
      await expect(board).toBeVisible();
      await page.getByRole('button', { name: /게임 시작|Start game/ }).tap();
      await page.getByRole('button', { name: /빠른 낙하|Soft drop/ }).tap();
      await expect(page.getByTestId('tetris-score')).toHaveText('1');
      await page.getByRole('button', { name: /블록 홀드|Hold block/ }).tap();
      await expect(
        page.getByRole('button', { name: /블록 홀드|Hold block/ }),
      ).toBeDisabled();
      await page
        .getByRole('button', { name: /즉시 낙하|Drop instantly/ })
        .tap();
      await expect(
        page.getByRole('button', { name: /블록 홀드|Hold block/ }),
      ).toBeEnabled();
      await page
        .getByRole('button', { name: /일시정지|Pause game/, exact: true })
        .tap();
      for (const theme of ['light', 'dark']) {
        await page.evaluate((value) => {
          document.documentElement.classList.toggle('dark', value === 'dark');
        }, theme);
        const box = await board.boundingBox();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(360);
        const controls = page.getByRole('group', {
          name: /화면 조작|Screen controls/,
        });
        const controlsBox = await controls.boundingBox();
        expect(controlsBox!.x).toBeGreaterThanOrEqual(0);
        expect(controlsBox!.x + controlsBox!.width).toBeLessThanOrEqual(360);
        expect(controlsBox!.y + controlsBox!.height).toBeLessThanOrEqual(740);
        for (const button of await controls.getByRole('button').all()) {
          const buttonBox = await button.boundingBox();
          expect(buttonBox!.height).toBeGreaterThanOrEqual(44);
          expect(buttonBox!.x + buttonBox!.width).toBeLessThanOrEqual(360);
          expect(
            await button.evaluate(
              (element) => element.scrollWidth <= element.clientWidth,
            ),
          ).toBe(true);
        }
        await expect(page.getByTestId('tetris-score')).toBeInViewport();
        await expect(
          page.getByRole('img', { name: /다음 블록|Next block/ }),
        ).toBeInViewport();
        await page.screenshot({
          path: `test-results/tetris-${locale}-${theme}-narrow.png`,
          fullPage: true,
          animations: 'disabled',
        });
      }
    });
  }
});
