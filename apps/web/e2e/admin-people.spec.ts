import { expect, test, type Page } from '@playwright/test';
import {
  FAKE_COMPANY_USER,
  FAKE_PLATFORM_ADMIN_USER,
  stubAppDataBackend,
  stubShellBackend,
} from './helpers';

async function prepare(page: Page) {
  const person = {
    ...FAKE_COMPANY_USER,
    id: 'member',
    full_name: '김민수',
    display_name: '김민수',
    login_id: 'minsu',
    email: 'minsu@example.test',
    employee_code: 'E-100',
    job_title: '개발자',
    login_blocked: false,
    primary_organization_unit: null,
  };
  const users = [person];
  const groups = [
    {
      id: 'review',
      name: '리뷰 그룹',
      source: 'local',
      membership_mode: 'manual',
      description: '',
      active: true,
      source_reference: null,
      slug: null,
      unit_type: null,
      parent_id: null,
      head_user_id: null,
    },
  ];
  const memberships = new Set<string>();
  const writes: {
    method: string;
    path: string;
    payload: Record<string, unknown>;
  }[] = [];
  await stubAppDataBackend(page);
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/admin/groups**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'PUT') {
      const payload = request.postDataJSON();
      writes.push({ method: 'PUT', path: url.pathname, payload });
      if (payload.assigned) memberships.add('review');
      else memberships.delete('review');
      await route.fulfill({
        json: {
          group_id: 'review',
          user_ids: payload.assigned ? [person.id] : [],
          items: [],
        },
      });
    } else {
      const items = groups.filter(
        (group) =>
          (!url.searchParams.has('member_user_id') ||
            memberships.has(group.id)) &&
          (!url.searchParams.has('source') ||
            group.source === url.searchParams.get('source')),
      );
      await route.fulfill({
        json: { items, total: items.length, page: 1, page_size: 20 },
      });
    }
  });
  await page.route('**/api/v1/admin/users**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (method === 'GET') {
      await route.fulfill({
        json: { items: users, total: users.length, page: 1, page_size: 12 },
      });
      return;
    }
    const payload = request.postData() ? request.postDataJSON() : {};
    writes.push({ method, path: url.pathname, payload });
    if (method === 'POST' && url.pathname.endsWith('/users')) {
      const created = {
        ...person,
        ...payload,
        id: 'new',
        login_id: payload.login_id || 'newuser',
        display_name: payload.display_name || payload.full_name,
      };
      users.push(created);
      await route.fulfill({
        status: 201,
        json: { user: created, temporary_password: 'synthetic-temp-password' },
      });
    } else if (method === 'PATCH') {
      Object.assign(person, payload);
      await route.fulfill({ json: person });
    } else if (url.pathname.endsWith('/reset-password')) {
      await route.fulfill({
        json: { temporary_password: 'synthetic-reset-password' },
      });
    } else if (method === 'DELETE') {
      users.splice(
        users.findIndex((user) => url.pathname.endsWith(`/${user.id}`)),
        1,
      );
      await route.fulfill({ status: 204 });
    }
  });
  await page.goto('/admin/people');
  await expect(
    page.getByRole('button', { name: '김민수', exact: true }),
  ).toBeVisible();
  return { writes, memberships };
}

test('creates accounts, edits profiles, manages groups and confirms account operations', async ({
  page,
}) => {
  const { writes, memberships } = await prepare(page);
  await page.getByRole('button', { name: '사용자 생성', exact: true }).click();
  let dialog = page.getByRole('dialog', { name: '사용자 생성' });
  await dialog.getByLabel('이메일', { exact: true }).fill('new@example.test');
  await dialog.getByLabel('전체 이름', { exact: true }).fill('새 사용자');
  await dialog.getByRole('button', { name: '생성', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '로그인 정보 확인' });
  await expect(dialog.getByLabel('임시 비밀번호')).toHaveValue(
    'synthetic-temp-password',
  );
  await dialog
    .getByRole('button', { name: '닫기', exact: true })
    .last()
    .click();
  await expect(
    page.getByRole('button', { name: '새 사용자', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '김민수', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '사용자 편집' });
  await dialog.getByLabel('직책', { exact: true }).fill('팀장');
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect.poll(() => writes.at(-1)?.payload.job_title).toBe('팀장');
  const row = page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: '김민수', exact: true }) });
  await row.getByRole('button', { name: '그룹 관리' }).click();
  dialog = page.getByRole('dialog', { name: '김민수 · 그룹 관리' });
  await dialog.getByRole('button', { name: '추가', exact: true }).click();
  await expect.poll(() => memberships.has('review')).toBe(true);
  await dialog.getByRole('button', { name: '제거', exact: true }).click();
  let confirmation = page.getByRole('dialog', { name: '그룹 접근 권한 변경' });
  await confirmation.getByRole('button', { name: '취소', exact: true }).click();
  expect(memberships.has('review')).toBe(true);
  await dialog.getByRole('button', { name: '제거', exact: true }).click();
  await confirmation.getByRole('button', { name: '제거', exact: true }).click();
  await expect.poll(() => memberships.has('review')).toBe(false);
  await dialog.getByRole('button', { name: '닫기', exact: true }).click();
  await row.getByRole('button', { name: 'minsu@example.test 작업' }).click();
  await page.getByRole('menuitem', { name: '비밀번호 재발급' }).click();
  confirmation = page.getByRole('dialog', {
    name: '비밀번호 재발급',
    exact: true,
  });
  await confirmation.getByRole('button', { name: '취소', exact: true }).click();
  expect(writes.some((write) => write.path.endsWith('/reset-password'))).toBe(
    false,
  );
  await row.getByRole('button', { name: 'minsu@example.test 작업' }).click();
  await page.getByRole('menuitem', { name: '사용자 삭제' }).click();
  confirmation = page.getByRole('dialog', { name: '사용자 삭제', exact: true });
  await confirmation
    .getByRole('button', { name: '사용자 삭제', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: '김민수', exact: true }),
  ).toHaveCount(0);
});

test('keeps editing reachable at desktop and mobile widths', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await prepare(page);
  const edit = page.getByRole('button', { name: '사용자 편집', exact: true });
  await expect(edit).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('people-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(edit).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await edit.click();
  const dialog = page.getByRole('dialog', { name: '사용자 편집' });
  await dialog.getByLabel('전체 이름', { exact: true }).focus();
  await expect(dialog.getByLabel('전체 이름', { exact: true })).toBeFocused();
  await page.screenshot({
    path: testInfo.outputPath('people-mobile-editor.png'),
  });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(edit).toBeFocused();
});
