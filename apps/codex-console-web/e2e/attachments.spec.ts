import { expect, test, type Page } from '@playwright/test';

async function newTask(page: Page, title: string) {
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill(title);
  await page.getByRole('button', { name: '작업 만들기' }).click();
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
});

test('library files are selected per message, retained on failure, and cleared after sending', async ({
  page,
}) => {
  await newTask(page, '선택 첨부 확인');
  await page.getByRole('button', { name: '파일', exact: true }).click();
  await page.locator('.attachment-library input[type=file]').setInputFiles([
    {
      name: '설계-A.unknown',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('Design A'),
    },
    {
      name: '설계-B.bin',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from([0, 1, 2, 255]),
    },
  ]);
  const first = page.getByRole('checkbox', { name: /설계-A/ });
  const second = page.getByRole('checkbox', { name: /설계-B/ });
  await expect(second).toBeEnabled();
  await expect(first).not.toBeChecked();
  await expect(page.locator('.composer .attachment-badge')).toHaveCount(0);
  await first.check();
  await page.getByLabel('요청 내용 입력').fill('첨부 자료를 참고해줘');
  await page.route(
    '**/api/tasks/*/messages',
    (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'codex_unavailable' }),
      }),
    { times: 1 },
  );
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(page.getByLabel('요청 내용 입력')).toHaveValue(
    '첨부 자료를 참고해줘',
  );
  await expect(page.locator('.composer .attachment-badge')).toContainText(
    '설계-A',
  );
  const sent = page.waitForRequest((request) =>
    request.url().endsWith('/messages'),
  );
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  expect((await sent).postDataJSON().attachment_ids).toHaveLength(1);
  await expect(page.locator('.composer .attachment-badge')).toHaveCount(0);
  await expect(page.locator('.user-message .attachment-badge')).toContainText(
    '설계-A',
  );
  await expect(first).not.toBeChecked();
  await expect(second).not.toBeChecked();
  await expect(
    page.getByRole('button', { name: '보내기', exact: true }),
  ).toBeVisible();
  await page.getByLabel('요청 내용 입력').fill('다음 요청');
  const next = page.waitForRequest((request) =>
    request.url().endsWith('/messages'),
  );
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  expect((await next).postDataJSON().attachment_ids).toEqual([]);
  await expect(page.locator('.user-message')).toHaveCount(2);
  await page.reload();
  await expect(page.locator('.user-message .attachment-badge')).toContainText(
    '설계-A',
  );
  await page.getByRole('button', { name: '파일', exact: true }).click();
  await expect(first).not.toBeChecked();
  await expect(second).not.toBeChecked();
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: /다운로드: 설계-B/ }).click();
  expect((await download).suggestedFilename()).toBe('설계-B.bin');
  await page.getByRole('button', { name: /파일 삭제: 설계-A/ }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '파일 삭제', exact: true })
    .click();
  await expect(first).toHaveCount(0);
  await expect(page.locator('.user-message .attachment-badge')).toContainText(
    '삭제됨',
  );
});

test('composer uploads select files, attachment-only messages work, and tasks do not share selections', async ({
  page,
}) => {
  await newTask(page, '첨부만 전송');
  await page.getByRole('button', { name: '파일 첨부', exact: true }).click();
  await page
    .getByRole('dialog')
    .locator('input[type=file]')
    .setInputFiles({
      name: '원본',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('File without an extension'),
    });
  await expect(
    page.getByRole('dialog').getByRole('checkbox', { name: /원본/ }),
  ).toBeChecked();
  await page.getByRole('button', { name: '선택 완료' }).click();
  await expect(page.getByLabel('요청 내용 입력')).toHaveValue('');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(page.locator('.user-message .attachment-badge')).toContainText(
    '원본',
  );
  await page.getByRole('button', { name: '파일', exact: true }).click();
  await page.getByRole('checkbox', { name: /원본/ }).check();
  const previousUrl = page.url();
  await newTask(page, '다른 작업');
  await expect(page.locator('.composer .attachment-badge')).toHaveCount(0);
  await page.getByRole('button', { name: '파일', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: /원본/ })).toHaveCount(0);
  await page.goto(previousUrl);
  await page.getByRole('button', { name: '파일', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: /원본/ })).not.toBeChecked();
  const transfer = await page.evaluateHandle(() => {
    const value = new DataTransfer();
    value.items.add(new File(['dragged reference'], '끌어놓기.xyz'));
    return value;
  });
  await page
    .locator('.composer')
    .dispatchEvent('drop', { dataTransfer: transfer });
  await expect(page.locator('.composer .attachment-badge')).toContainText(
    '끌어놓기.xyz',
  );
  await expect(page.getByLabel('현재 실행 상태')).toContainText('준비됨');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test('many selected files scroll inside the composer without hiding its controls', async ({
  page,
}) => {
  await newTask(page, '다중 첨부 레이아웃');
  await page.getByRole('button', { name: '파일 첨부', exact: true }).click();
  await page
    .getByRole('dialog')
    .locator('input[type=file]')
    .setInputFiles(
      Array.from({ length: 20 }, (_, index) => ({
        name: `참고-${String(index + 1).padStart(2, '0')}.txt`,
        mimeType: 'text/plain',
        buffer: Buffer.from(`Reference ${index + 1}`),
      })),
    );
  await expect(
    page.getByRole('dialog').getByRole('checkbox'),
  ).toHaveCount(20);
  await page.getByRole('button', { name: '선택 완료' }).click();

  const badges = page.locator('.composer > .attachment-badges');
  const toolbar = page.locator('.composer-toolbar');
  await expect(badges.locator('.attachment-badge')).toHaveCount(20);
  await expect(toolbar).toBeVisible();
  expect(
    await badges.evaluate((element) => ({
      scrollable: element.scrollHeight > element.clientHeight,
      overflowY: getComputedStyle(element).overflowY,
    })),
  ).toEqual({ scrollable: true, overflowY: 'auto' });
  const composerBox = await page.locator('.composer').boundingBox();
  const toolbarBox = await toolbar.boundingBox();
  expect(composerBox).not.toBeNull();
  expect(toolbarBox).not.toBeNull();
  expect(toolbarBox!.y + toolbarBox!.height).toBeLessThanOrEqual(
    composerBox!.y + composerBox!.height + 1,
  );
});
