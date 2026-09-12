import { expect, test, type Page } from '@playwright/test';
import type { ApiSchema } from '../src/platform/api/types';
import {
  FAKE_PLATFORM_ADMIN_USER,
  stubAppDataBackend,
  stubShellBackend,
} from './helpers';

type Group = ApiSchema<'GroupResponse'>;
function group(id: string, name: string, source: Group['source']): Group {
  return {
    id,
    name,
    source,
    membership_mode: source === 'hr' ? 'hr_assignment' : 'manual',
    description: '',
    active: true,
    source_reference: null,
    slug: source === 'hr' ? id : null,
    unit_type: source === 'hr' ? 'department' : null,
    parent_id: null,
    head_user_id: null,
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  };
}
async function prepare(page: Page) {
  const groups = [
    group('engineering', '개발팀', 'hr'),
    group('task-force', '서비스 TF', 'local'),
  ];
  const writes: { method: string; payload: Record<string, unknown> }[] = [];
  const people = [
    {
      id: 'member',
      display_name: '테스트 사용자',
      login_id: 'tester',
      status: 'active',
      login_blocked: false,
    },
  ];
  const members = new Map<string, string[]>();
  await stubAppDataBackend(page);
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/directory/people**', (route) => {
    const ids = new URL(route.request().url()).searchParams.getAll('ids');
    const items = people.filter(
      (person) => ids.length === 0 || ids.includes(person.id),
    );
    return route.fulfill({
      json: {
        items,
        total: items.length,
        page: 1,
        page_size: 50,
      },
    });
  });
  await page.route('**/api/v1/admin/groups**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (method === 'PUT') {
      const payload = request.postDataJSON();
      writes.push({ method, payload });
      const id = url.pathname.split('/').at(-2)!;
      members.set(id, payload.user_ids);
      await route.fulfill({
        json: {
          group_id: id,
          user_ids: payload.user_ids,
          items: people.filter((person) =>
            payload.user_ids.includes(person.id),
          ),
        },
      });
    } else if (method === 'POST') {
      const payload = request.postDataJSON();
      writes.push({ method, payload });
      const created = {
        ...group(`new-${groups.length}`, payload.name, payload.source),
        ...payload,
      };
      groups.push(created);
      await route.fulfill({ status: 201, json: created });
    } else if (method === 'PATCH') {
      const payload = request.postDataJSON();
      writes.push({ method, payload });
      const selected = groups.find((item) =>
        url.pathname.endsWith(`/${item.id}`),
      );
      Object.assign(selected!, payload);
      await route.fulfill({ json: selected });
    } else if (url.pathname.endsWith('/members')) {
      const id = url.pathname.split('/').at(-2)!;
      const ids = members.get(id) ?? [];
      await route.fulfill({
        json: {
          group_id: id,
          user_ids: ids,
          items: people.filter((person) => ids.includes(person.id)),
        },
      });
    } else {
      const source = url.searchParams.get('source');
      const items = groups.filter((item) => !source || item.source === source);
      await route.fulfill({
        json: {
          items,
          total: items.length,
          page: 1,
          page_size: Number(url.searchParams.get('page_size') ?? 50),
        },
      });
    }
  });
  await page.goto('/admin/groups');
  await expect(
    page.getByRole('button', { name: '개발팀', exact: true }),
  ).toBeVisible();
  return { groups, writes };
}

test('manages HR and locally created groups through one surface', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const { writes } = await prepare(page);
  await expect(page.locator('a[href="/admin/organization"]')).toHaveCount(0);
  await page
    .getByRole('combobox', { name: '생성 출처', exact: true })
    .selectOption('hr');
  await expect(
    page.getByRole('button', { name: '서비스 TF', exact: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: '개발팀', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await expect(
    dialog.getByRole('button', { name: '구성원 저장', exact: true }),
  ).toHaveCount(0);
  await expect(
    dialog.getByRole('link', { name: '사용자 인사배치 관리' }),
  ).toHaveAttribute('href', '/admin/people');
  await dialog.getByLabel('그룹 이름', { exact: true }).fill('플랫폼 개발팀');
  await dialog.getByLabel('원본 식별자', { exact: true }).fill('HR-100');
  await dialog.getByRole('button', { name: '그룹 정보 저장' }).click();
  await expect
    .poll(() => writes.at(-1)?.payload)
    .toMatchObject({ name: '플랫폼 개발팀', source_reference: 'HR-100' });
  expect(writes.at(-1)?.payload).not.toHaveProperty('source');
  await expect(
    dialog.getByRole('button', { name: '그룹 정보 저장' }),
  ).toBeEnabled();
  // The shared toast is the top dismissable layer after a successful save.
  const savedToast = page
    .locator('li[data-state="open"]')
    .filter({ hasText: '그룹 변경사항을 저장했습니다.' });
  await expect(savedToast).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(savedToast).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.getByRole('button', { name: '그룹 생성', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('그룹 이름', { exact: true }).fill('품질 TF');
  await dialog.getByRole('button', { name: '그룹 생성', exact: true }).click();
  await expect
    .poll(() => writes.at(-1)?.payload)
    .toEqual({ name: '품질 TF', source: 'local', description: '' });
  await expect(
    page
      .getByRole('dialog')
      .getByRole('button', { name: '구성원 저장', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '닫기', exact: true })
    .click();
  await page.getByRole('button', { name: '그룹 생성', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog
    .getByRole('combobox', { name: '생성 출처', exact: true })
    .selectOption('hr');
  await dialog.getByLabel('그룹 이름', { exact: true }).fill('인사팀');
  await dialog
    .getByRole('combobox', { name: '상위 그룹', exact: true })
    .selectOption('engineering');
  await dialog.getByRole('button', { name: '그룹 생성', exact: true }).click();
  await expect
    .poll(() => writes.at(-1)?.payload)
    .toMatchObject({ name: '인사팀', source: 'hr', parent_id: 'engineering' });
  expect(errors).toEqual([]);
});

test('adds and removes group members and confirms group deactivation', async ({
  page,
}) => {
  const { writes } = await prepare(page);
  await page.getByRole('button', { name: '서비스 TF', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '서비스 TF', exact: true });
  await dialog
    .getByRole('button', { name: '구성원 추가', exact: true })
    .click();
  await dialog
    .getByPlaceholder('사용자 이름 검색', { exact: true })
    .fill('테스트');
  await dialog.getByRole('button', { name: /테스트 사용자/ }).click();
  await dialog
    .getByRole('button', { name: '추가 창 닫기', exact: true })
    .click();
  await expect(
    dialog.getByRole('button', {
      name: '테스트 사용자 구성원 제거',
      exact: true,
    }),
  ).toBeVisible();
  await dialog
    .getByRole('button', { name: '구성원 저장', exact: true })
    .click();
  await expect
    .poll(() => writes.at(-1)?.payload)
    .toEqual({ user_ids: ['member'] });
  await dialog
    .getByRole('button', { name: '테스트 사용자 구성원 제거', exact: true })
    .click();
  await dialog
    .getByRole('button', { name: '구성원 저장', exact: true })
    .click();
  let confirmation = page.getByRole('dialog', {
    name: '그룹 접근 권한 변경',
    exact: true,
  });
  await confirmation
    .getByRole('button', { name: '접근 권한 변경', exact: true })
    .click();
  await expect.poll(() => writes.at(-1)?.payload).toEqual({ user_ids: [] });
  await dialog.getByRole('checkbox', { name: '활성', exact: true }).uncheck();
  await dialog
    .getByRole('button', { name: '그룹 정보 저장', exact: true })
    .click();
  confirmation = page.getByRole('dialog', {
    name: '그룹 접근 권한 변경',
    exact: true,
  });
  await confirmation
    .getByRole('button', { name: '접근 권한 변경', exact: true })
    .click();
  await expect.poll(() => writes.at(-1)?.payload.active).toBe(false);
  await expect(
    dialog.getByRole('button', { name: '구성원 추가', exact: true }),
  ).toBeDisabled();
});

test('keeps group forms usable on a narrow viewport', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepare(page);
  await page.screenshot({
    path: testInfo.outputPath('groups-mobile.png'),
    fullPage: true,
  });
  await page.getByRole('button', { name: '개발팀', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(
    dialog.getByRole('button', { name: '그룹 정보 저장' }),
  ).toBeVisible();
  await dialog.getByLabel('그룹 이름', { exact: true }).focus();
  await expect(dialog.getByLabel('그룹 이름', { exact: true })).toBeFocused();
  await page.screenshot({
    path: testInfo.outputPath('group-mobile-editor.png'),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
});
