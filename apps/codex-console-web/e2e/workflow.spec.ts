import { expect, test } from '@playwright/test';

test('requirements, saved plan, implementation, diff and refresh recovery', async ({
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
  await page
    .getByLabel('요청 내용 입력')
    .fill('프로젝트에 인사말 기능을 추가하고 검증하고 싶습니다.');
  await page.getByRole('button', { name: '보내기', exact: true }).click();
  await expect(
    page.getByRole('button', { name: '구현 계획 작성' }),
  ).toBeEnabled();
  await page.getByRole('button', { name: '구현 계획 작성' }).click();
  await expect(
    page.getByRole('button', { name: '이 계획으로 구현', exact: true }),
  ).toBeEnabled();
  await page
    .getByRole('button', { name: '이 계획으로 구현', exact: true })
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '취소' }).click();
  await expect(
    page.getByText('Implemented the greeting.', { exact: false }),
  ).toHaveCount(0);
  await page
    .getByRole('button', { name: '이 계획으로 구현', exact: true })
    .click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '이 계획으로 구현' })
    .click();
  await expect(
    page.getByText('Implemented the greeting.', { exact: false }),
  ).toBeVisible();
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
    .getByRole('button', { name: '구현 계획', exact: true })
    .click();
  await expect(
    returned.getByRole('button', { name: '이 계획으로 구현', exact: true }),
  ).toBeEnabled();
  await returned.getByLabel('실행 모드').selectOption('implement');
  await returned.getByLabel('실행 권한').selectOption('yolo');
  await returned.getByLabel('요청 내용 입력').fill('Implement the plan.');
  await returned.getByRole('button', { name: '보내기', exact: true }).click();
  await returned
    .getByRole('dialog')
    .getByRole('button', { name: '이 계획으로 구현' })
    .click();
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
