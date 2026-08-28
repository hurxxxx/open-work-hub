import { expect, test } from '@playwright/test';

import { stubShellBackend, stubWorkspaceAppDataBackend } from './helpers';

const LONG_RELEASE_NOTE = {
  id: 'release-note-layout-repro',
  release_key: 'release-note-layout-repro',
  title: '긴 릴리즈 노트 레이아웃 재현',
  summary:
    '업데이트 내용을 조금 길게 작성했을 때에도 사용자가 본문을 읽고 하단의 나중에, 업데이트 내역 보기, 다시 보지 않기 버튼을 항상 사용할 수 있어야 합니다. 요약이 두세 줄로 늘어나는 실제 상황을 재현합니다. 여러 업무 영역의 개선 내용을 함께 안내하면 요약은 자연스럽게 조금 더 길어집니다. 이 경우에도 중요한 동작 버튼이 화면 밖으로 밀려서는 안 됩니다.',
  body: Array.from(
    { length: 12 },
    (_, index) => `- ${index + 1}번째 변경 사항을 안내합니다.`,
  ).join('\n'),
  published_at: '2026-07-25T12:00:00Z',
  dismissed_at: null,
};

test('keeps release-note actions inside the announcement modal', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 600 });
  await stubWorkspaceAppDataBackend(page);
  await stubShellBackend(page);
  await page.unroute('**/api/v1/release-notes/current');
  await page.route('**/api/v1/release-notes/current', (route) =>
    route.fulfill({ json: { item: LONG_RELEASE_NOTE } }),
  );

  await page.goto('/apps/home/workspaces/hq');

  const dismissButton = page.getByRole('button', {
    name: /다시 보지 않기|Do not show again/,
  });
  await expect(dismissButton).toBeVisible();

  const metrics = await dismissButton.evaluate((button) => {
    const modal = button.closest('section');
    if (!modal) {
      throw new Error('Release-note announcement modal was not found.');
    }
    const scrollRegion = Array.from(modal.children).find(
      (element) => getComputedStyle(element).overflowY === 'auto',
    );
    if (!scrollRegion) {
      throw new Error('Release-note scroll region was not found.');
    }
    const buttonRect = button.getBoundingClientRect();
    const modalRect = modal.getBoundingClientRect();
    return {
      buttonBottom: buttonRect.bottom,
      modalBottom: modalRect.bottom,
      scrollClientHeight: scrollRegion.clientHeight,
      scrollHeight: scrollRegion.scrollHeight,
      viewportHeight: window.innerHeight,
    };
  });

  expect(metrics.scrollHeight).toBeGreaterThan(metrics.scrollClientHeight);
  expect(metrics.buttonBottom).toBeLessThanOrEqual(metrics.modalBottom + 1);
  expect(metrics.buttonBottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
});
