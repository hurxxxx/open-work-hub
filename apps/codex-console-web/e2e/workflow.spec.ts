import { expect, test } from '@playwright/test';

test('native plan, implementation, diff and refresh recovery', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill('인사말 기능 개발');
  await page.getByRole('button', { name: '작업 만들기' }).click();
  await expect(page.getByLabel('실행 모드')).toHaveValue('plan');
  await expect(
    page
      .getByRole('navigation', { name: '결과물' })
      .getByRole('button', { name: '요구사항', exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel('요청 내용 입력')
    .fill('Inspect the project and make a plan.');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await page
    .getByRole('navigation', { name: '결과물' })
    .getByRole('button', { name: '계획', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: '이 계획으로 실행', exact: true }),
  ).toBeEnabled();
  await page
    .getByRole('button', { name: '이 계획으로 실행', exact: true })
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '취소' }).click();
  await expect(
    page.getByText('Implemented the greeting.', { exact: false }),
  ).toHaveCount(0);
  await page
    .getByRole('button', { name: '이 계획으로 실행', exact: true })
    .click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '이 계획으로 실행' })
    .click();
  await expect(
    page.getByText('Implemented the greeting.', { exact: false }),
  ).toBeVisible();
  await page.getByRole('button', { name: '브랜치', exact: true }).click();
  await expect(
    page.getByRole('button', { name: /greeting.txt/ }),
  ).toBeVisible();
  const url = page.url();
  await page.reload();
  await expect(
    page.getByRole('heading', { name: '인사말 기능 개발' }),
  ).toBeVisible();
  expect(page.url()).toBe(url);
  await page.getByRole('button', { name: '실행 결과', exact: true }).click();
  await expect(
    page.getByLabel('결과물').getByText('종료 코드 0'),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '결과물', exact: true }).click();
  await expect(
    page.getByRole('button', { name: '실행 결과', exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test('sign out removes access to the private task list', async ({ page }) => {
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.getByRole('button', { name: '로그아웃' }).click();
  await expect(page.getByLabel('본인 전용 비밀번호')).toBeVisible();
  expect((await page.request.get('api/tasks')).status()).toBe(401);
});

test('server work survives closing the browser tab and restores progress and execution settings', async ({
  page,
  context,
}) => {
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill('백그라운드 작업 확인');
  await page.getByRole('button', { name: '작업 만들기' }).click();
  await page.getByRole('button', { name: '설정 변경' }).click();
  await expect(page.getByLabel('모델')).toContainText('another-model');
  await page.getByLabel('모델').selectOption('another-model');
  await page.getByLabel('추론 강도').selectOption('high');
  await page.getByLabel('실행 모드').selectOption('plan');
  await page
    .getByLabel('요청 내용 입력')
    .fill('Inspect the project and make a plan.');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(page.getByLabel('현재 실행 상태')).toContainText('진행 중');
  const taskUrl = page.url();
  await page.goto('about:blank');
  await page.close();
  const returned = await context.newPage();
  await returned.goto(taskUrl);
  await expect(
    returned.getByRole('heading', { name: '백그라운드 작업 확인' }),
  ).toBeVisible();
  await expect(returned.getByLabel('현재 실행 상태')).toContainText(
    'another-model · high',
  );
  await expect(returned.getByLabel('현재 실행 상태')).toContainText('준비됨');
  await returned
    .getByRole('navigation', { name: '결과물' })
    .getByRole('button', { name: '계획', exact: true })
    .click();
  await expect(
    returned.getByRole('button', { name: '이 계획으로 실행', exact: true }),
  ).toBeEnabled();
  await returned.getByLabel('실행 모드').selectOption('implement');
  await returned.getByLabel('실행 권한').selectOption('yolo');
  await returned.getByLabel('요청 내용 입력').fill('Implement the plan.');
  await returned.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(returned.getByLabel('현재 실행 상태')).toContainText('YOLO');
  await expect(
    returned.getByText('Implemented the greeting.', { exact: false }),
  ).toBeVisible();
  await returned.setViewportSize({ width: 390, height: 844 });
  expect(
    await returned.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test('late status, guidance, and recovery surfaces do not reflow the workspace', async ({
  page,
}) => {
  const box = async (selector: string) => {
    const value = await page.locator(selector).boundingBox();
    expect(value).not.toBeNull();
    return value!;
  };
  const layout = async () => ({
    conversation: await box('.conversation'),
    status: await box('.execution-status'),
    messages: await box('.messages'),
    composer: await box('.composer'),
    results: await box('.results'),
  });
  const expectStable = (
    before: Awaited<ReturnType<typeof layout>>,
    after: Awaited<ReturnType<typeof layout>>,
  ) => {
    for (const key of Object.keys(before) as (keyof typeof before)[]) {
      expect(Math.abs(after[key].y - before[key].y)).toBeLessThan(1);
      expect(Math.abs(after[key].height - before[key].height)).toBeLessThan(1);
    }
  };

  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill('레이아웃 안정성 확인');
  await page.getByRole('button', { name: '작업 만들기' }).click();
  // Measure the loaded workspace, after the initial Git summary occupies its row.
  await expect(page.locator('.task-header .git-summary')).toBeVisible();

  const closedSettings = await layout();
  const promptBefore = await box('.composer textarea');
  const toolbarBefore = await box('.composer-toolbar');
  await page.getByRole('button', { name: '설정 변경' }).click();
  await expect(page.locator('.execution-settings-popover')).toBeVisible();
  expectStable(closedSettings, await layout());
  const promptAfter = await box('.composer textarea');
  const toolbarAfter = await box('.composer-toolbar');
  expect(Math.abs(promptAfter.y - promptBefore.y)).toBeLessThan(1);
  expect(Math.abs(promptAfter.height - promptBefore.height)).toBeLessThan(1);
  expect(Math.abs(toolbarAfter.y - toolbarBefore.y)).toBeLessThan(1);
  expect(Math.abs(toolbarAfter.height - toolbarBefore.height)).toBeLessThan(1);
  expect(
    await page
      .locator('.composer')
      .evaluate((element) => getComputedStyle(element).overflowY),
  ).toBe('visible');
  await page.keyboard.press('Escape');
  await expect(page.locator('.execution-settings-popover')).toBeHidden();

  const idle = await layout();
  await page.getByLabel('요청 내용 입력').fill('Explain the workspace.');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(page.locator('.execution-progress')).toBeVisible();
  const running = await layout();
  expectStable(idle, running);

  await page.locator('.execution-progress summary').click();
  await expect(page.locator('.execution-progress')).toHaveAttribute('open', '');
  expectStable(running, await layout());

  await expect(page.getByLabel('현재 실행 상태')).toContainText('준비됨');
  const footerBefore = await box('.document-footer');
  await page.getByRole('button', { name: '문서 편집' }).click();
  await page.getByLabel('문서 편집').fill('Unsaved document draft');
  await expect(page.locator('.document-footer-status')).toBeVisible();
  const footerAfter = await box('.document-footer');
  expect(Math.abs(footerAfter.y - footerBefore.y)).toBeLessThan(1);
  expect(Math.abs(footerAfter.height - footerBefore.height)).toBeLessThan(1);
  await page
    .getByRole('button', { name: '편집 내용 버리고 최신 버전 불러오기' })
    .click();

  const beforeNotice = await layout();
  const taskId = new URL(page.url()).searchParams.get('task');
  expect(taskId).not.toBeNull();
  const detail = await (await page.request.get(`api/tasks/${taskId}`)).json();
  await page.route(`**/api/tasks/${taskId}`, (route) =>
    route.fulfill({
      json: {
        ...detail,
        status: 'uncertain',
        error_code: 'codex_request_uncertain',
        failed_request_text: 'Explain the workspace.',
      },
    }),
  );
  await page.reload();
  await expect(page.locator('.runtime-notice')).toBeVisible();
  expectStable(beforeNotice, await layout());
});

test('execution controls stay separated on a narrow desktop workspace', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 844 });
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill('좁은 화면 컨트롤 확인');
  await page.getByRole('button', { name: '작업 만들기' }).click();

  const expectSeparated = async () => {
    const composer = await page.locator('.composer').boundingBox();
    const controls = await page.locator('.composer-controls').boundingBox();
    const actions = await page
      .locator('.composer-toolbar > .actions')
      .boundingBox();
    const model = await page
      .getByRole('button', { name: '설정 변경' })
      .boundingBox();
    const permissions = await page.getByLabel('실행 권한').boundingBox();
    for (const box of [composer, controls, actions, model, permissions])
      expect(box).not.toBeNull();
    expect(model!.x + model!.width).toBeLessThanOrEqual(
      permissions!.x + 1,
    );
    expect(controls!.y + controls!.height).toBeLessThanOrEqual(actions!.y + 1);
    expect(actions!.x + actions!.width).toBeLessThanOrEqual(
      composer!.x + composer!.width + 1,
    );
    expect(actions!.y + actions!.height).toBeLessThanOrEqual(
      composer!.y + composer!.height + 1,
    );
  };

  await expectSeparated();
  await page.getByLabel('요청 내용 입력').fill('좁은 화면 실행 상태 확인');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(page.getByRole('button', { name: '중단' })).toBeVisible();
  await expectSeparated();
  await expect(page.getByLabel('현재 실행 상태')).toContainText('준비됨');
});

test('planning answers ordinary questions without creating documents and shows a read-only branch tab', async ({
  page,
}) => {
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill('일반 대화와 브랜치 표시 확인');
  await page.getByRole('button', { name: '작업 만들기' }).click();
  await expect(page.getByLabel('실행 모드')).toHaveValue('plan');
  await expect(page.locator('.git-summary')).toContainText('dev');
  await page
    .getByLabel('요청 내용 입력')
    .fill('Explain the current workspace.');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(
    page.getByText('This is a general answer; saved plan is unchanged.'),
  ).toBeVisible();
  await expect(page.getByLabel('현재 실행 상태')).toContainText('준비됨');
  const taskId = new URL(page.url()).searchParams.get('task');
  const detail = await (await page.request.get(`api/tasks/${taskId}`)).json();
  expect(detail.revisions).toEqual([]);
  expect(
    await page.getByRole('button', { name: '병합 요청', exact: true }).count(),
  ).toBe(0);
  await page.getByRole('button', { name: '브랜치', exact: true }).click();
  await expect(page.locator('.workspace-path')).toBeVisible();
  expect(await page.getByLabel('대상 브랜치').count()).toBe(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 390, height: 667 },
]) {
  test(`branch workspace scrolls through 18 files and the full diff at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.clock.install();
    await page.setViewportSize(viewport);
    let diffReads = 0;
    const files = Array.from({ length: 18 }, (_, index) => ({
      path: `src/changed-file-${String(index + 1).padStart(2, '0')}.txt`,
      status: 'M',
      old_path: null,
    }));
    await page.route('**/api/tasks/*/changes', (route) =>
      route.fulfill({ json: files }),
    );
    await page.route('**/api/tasks/*/diff?*', (route) => {
      diffReads++;
      return route.fulfill({
        json: {
          path: new URL(route.request().url()).searchParams.get('path'),
          binary: false,
          old: 'original\n',
          new:
            Array.from(
              { length: 150 },
              (_, index) => `changed line ${index + 1}`,
            ).join('\n') + '\nEND-OF-SELECTED-DIFF\n',
        },
      });
    });
    await page.goto('./');
    await page
      .getByLabel('본인 전용 비밀번호')
      .fill('console-tests-only-password');
    await page.getByRole('button', { name: '로그인', exact: true }).click();
    await page
      .getByRole('button', { name: '새 작업', exact: true })
      .first()
      .click();
    await page
      .getByLabel('작업 제목')
      .fill(`Branch scrolling ${viewport.width}`);
    await page.getByRole('button', { name: '작업 만들기' }).click();
    if (viewport.width < 960)
      await page.getByRole('button', { name: '결과물', exact: true }).click();
    await page.getByRole('button', { name: '브랜치', exact: true }).click();
    const panel = page.locator('.git-workspace');
    await expect(panel.locator('.file-list button')).toHaveCount(18);
    const panelBox = await panel.boundingBox();
    expect(panelBox!.height).toBeGreaterThan(100);
    expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(
      viewport.height + 1,
    );
    const lastFile = panel.getByRole('button', { name: /changed-file-18.txt/ });
    await lastFile.scrollIntoViewIfNeeded();
    await expect(lastFile).toBeInViewport();
    await lastFile.click();
    const diff = panel.locator('.diff-content');
    await expect(diff).toHaveAttribute('aria-label', files[17].path);
    const end = diff.getByText('END-OF-SELECTED-DIFF', { exact: true });
    await expect(end).toBeAttached();
    await panel.hover({ position: { x: 12, y: 12 } });
    await page.mouse.wheel(0, 10000);
    await expect(end).toBeInViewport();
    const beforePolling = diffReads;
    await page.clock.fastForward(10001);
    await expect.poll(() => diffReads).toBeGreaterThan(beforePolling);
    await expect(end).toBeInViewport();
    await expect
      .poll(() => panel.evaluate((element) => element.scrollTop))
      .toBeGreaterThan(0);
    await page.mouse.wheel(0, -10000);
    await expect(
      panel.getByRole('button', { name: 'Git 상태 새로고침' }),
    ).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test('Git refresh updates files and the selected diff without a task state change', async ({
  page,
}) => {
  await page.clock.install();
  let version = 1;
  await page.route('**/api/tasks/*/changes', (route) =>
    route.fulfill({
      json: [
        { path: 'selected.txt', status: 'M', old_path: null },
        { path: `version-${version}.txt`, status: 'M', old_path: null },
      ],
    }),
  );
  await page.route('**/api/tasks/*/diff?*', (route) =>
    route.fulfill({
      json: {
        path: new URL(route.request().url()).searchParams.get('path'),
        binary: false,
        old: 'original\n',
        new: `refreshed content ${version}\n`,
      },
    }),
  );
  await page.goto('./');
  await page
    .getByLabel('본인 전용 비밀번호')
    .fill('console-tests-only-password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page
    .getByRole('button', { name: '새 작업', exact: true })
    .first()
    .click();
  await page.getByLabel('작업 제목').fill('Refresh files and diff');
  await page.getByRole('button', { name: '작업 만들기' }).click();
  await page.getByRole('button', { name: '브랜치', exact: true }).click();
  const panel = page.locator('.git-workspace');
  const selected = panel.getByRole('button', { name: /selected.txt/ });
  await selected.click();
  await expect(
    panel.getByText('refreshed content 1', { exact: true }),
  ).toBeVisible();
  const taskId = new URL(page.url()).searchParams.get('task');
  const before = await (await page.request.get(`api/tasks/${taskId}`)).json();
  version = 2;
  await panel.getByRole('button', { name: 'Git 상태 새로고침' }).click();
  await expect(
    panel.getByRole('button', { name: /version-2.txt/ }),
  ).toBeVisible();
  await expect(
    panel.getByRole('button', { name: /version-1.txt/ }),
  ).toHaveCount(0);
  await expect(selected).toHaveAttribute('aria-pressed', 'true');
  await expect(
    panel.getByText('refreshed content 2', { exact: true }),
  ).toBeVisible();
  version = 3;
  await page.clock.fastForward(10001);
  await expect(
    panel.getByRole('button', { name: /version-3.txt/ }),
  ).toBeVisible();
  await expect(selected).toHaveAttribute('aria-pressed', 'true');
  await expect(
    panel.getByText('refreshed content 3', { exact: true }),
  ).toBeVisible();
  const after = await (await page.request.get(`api/tasks/${taskId}`)).json();
  expect({ id: after.id, status: after.status }).toEqual({
    id: before.id,
    status: before.status,
  });
});
