import { expect, test } from '@playwright/test';

import { stubShellBackend } from './helpers';

test.describe('AI chat meeting-insight deep link (Step E.4)', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
  });

  test('pre-fills the composer from ?draft= and clears the URL params', async ({
    page,
  }) => {
    const draft = '회의 `Weekly Sync`의 액션 아이템 `로그인 플로우 정리`을(를) PMS 이슈로 만들고 싶어.';
    const params = new URLSearchParams({
      draft,
      context: 'meeting',
      context_id: 'm-1',
      insight_id: 'i-1',
      insight_kind: 'action',
    });

    await page.goto(`/w/hq/ai?${params.toString()}`);

    const composer = page.getByPlaceholder('메시지를 입력하세요');
    await expect(composer).toHaveValue(draft);
    await expect(
      page.getByText('회의 AI 제안에서 시작됨'),
    ).toBeVisible();

    // The consume effect clears draft + companion params in the same
    // tick (D7 + D11). A reload with the cleaned URL should leave the
    // composer empty, which confirms the URL no longer carries the
    // seeding state.
    await expect
      .poll(() => new URL(page.url()).search, { timeout: 5_000 })
      .toBe('');
  });

  test('ignores the draft when the URL already names an existing conversation', async ({
    page,
  }) => {
    // When `?c=` is present, AIView hydrates that conversation; the
    // deep-link draft must not leak into the composer. We do not need
    // a real conversation payload — letting the hydration 404 is fine
    // because this test only asserts the composer state.
    const params = new URLSearchParams({
      c: 'c-existing',
      draft: '버려질 초안',
    });

    await page.goto(`/w/hq/ai?${params.toString()}`);

    const composer = page.getByPlaceholder(/대화|이 대화|메시지/);
    await expect(composer).toHaveValue('');
    await expect(
      page.getByText('회의 AI 제안에서 시작됨'),
    ).toHaveCount(0);
  });

  test('re-consumes a second deep link while still on the fresh chat', async ({
    page,
  }) => {
    // First draft — landed via initial navigation.
    await page.goto(
      '/w/hq/ai?draft=' + encodeURIComponent('첫 초안'),
    );

    const composer = page.getByPlaceholder('메시지를 입력하세요');
    await expect(composer).toHaveValue('첫 초안');

    // Simulate a second "챗에서 진행" click — we can't reach the
    // MeetingDetail view without the meeting API backend, so we
    // navigate directly to the deep-link URL to exercise the same
    // code path the helper would produce.
    await page.goto(
      '/w/hq/ai?draft=' + encodeURIComponent('두번째 초안'),
    );
    await expect(composer).toHaveValue('두번째 초안');
  });
});
