import { createAuthUser } from '../../../tests/fixtures/company';
import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';

import {
  buildAdminPeopleExportRows,
  buildAdminPeopleRows,
  collectAdminPeopleExportUsers,
  encodeAdminPeopleCsv,
  nextAdminPeoplePageAfterDelete,
  type AdminPeopleFormatter,
} from './admin-people-rows-model';

const formatter: AdminPeopleFormatter = {
  role: {
    admin: 'Admin',
    member: 'Member',
  },
  status: (status) => ['status', status || '-'].join(':'),
  date: (value) => value ?? '-',
};

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return createAuthUser({
    id: 'user-1',
    login_id: 'ada',
    email: 'ada@example.test',
    full_name: 'Ada Lovelace',
    display_name: '',
    status: 'active',
    login_blocked: false,
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    system_roles: [],
    group_ids: [],
    managed_organization_unit_ids: [],
    must_change_password: false,
    last_login_at: null,
    created_at: undefined,
    ...overrides,
  });
}

describe('admin people rows model', () => {
  it('derives table rows with labels and effective group count', () => {
    const model = buildAdminPeopleRows({
      users: [
        user({
          display_name: 'Ada',
          system_roles: ['platform_admin'],
          group_ids: ['group-1'],
          last_login_at: '2026-05-29T00:00:00Z',
          created_at: '2026-01-01T00:00:00Z',
        }),
      ],
      total: 1,
      page: 1,
      format: formatter,
    });

    expect(model.rows[0]).toMatchObject({
      id: 'user-1',
      name: 'Ada',
      loginId: 'ada',
      email: 'ada@example.test',
      groupCount: '1',
      role: 'admin',
      roleLabel: 'Admin',
      statusLabel: 'status:active',
      lastActiveLabel: '2026-05-29T00:00:00Z',
      createdLabel: '2026-01-01T00:00:00Z',
    });
  });

  it('handles empty and partial pagination ranges', () => {
    expect(
      buildAdminPeopleRows({
        users: [],
        total: 0,
        page: 1,
        pageSize: 20,
        format: formatter,
      }).pagination,
    ).toMatchObject({
      from: 0,
      to: 0,
      totalPages: 1,
      canPrevious: false,
      canNext: false,
    });

    expect(
      buildAdminPeopleRows({
        users: [user({ id: 'last' })],
        total: 21,
        page: 2,
        pageSize: 20,
        format: formatter,
      }).pagination,
    ).toMatchObject({ from: 21, to: 21, totalPages: 2 });
  });

  it('chooses the previous page after deleting the final row', () => {
    expect(
      nextAdminPeoplePageAfterDelete({
        currentPage: 2,
        totalBeforeDelete: 21,
        pageSize: 20,
      }),
    ).toBe(1);
    expect(
      nextAdminPeoplePageAfterDelete({
        currentPage: 1,
        totalBeforeDelete: 1,
        pageSize: 20,
      }),
    ).toBe(1);
  });

  it('builds and escapes CSV rows in the declared column order', () => {
    const rows = buildAdminPeopleExportRows({
      users: [
        user({
          display_name: 'Ada "Countess"',
          employee_code: 'E-1001',
          job_title: 'Researcher',
          primary_organization_unit: {
            id: 'organization-1',
            name: 'Research',
            slug: 'research',
            unit_type: 'department',
            active: true,
          },
          group_ids: ['group-1'],
          created_at: '2026-01-01T00:00:00Z',
        }),
      ],
      format: formatter,
    });

    expect(rows[0]).toEqual([
      'Ada "Countess"',
      'ada',
      'ada@example.test',
      'E-1001',
      'Researcher',
      'Research',
      '1',
      'Member',
      'status:active',
      '-',
      '2026-01-01T00:00:00Z',
    ]);
    expect(
      encodeAdminPeopleCsv({
        header: [
          'Name',
          'ID',
          'Email',
          'Employee code',
          'Job title',
          'Organization',
          'Groups',
          'Role',
          'Status',
          'Last Active',
          'Created',
        ],
        rows,
      }),
    ).toContain('"Ada ""Countess"""');
  });

  it('collects export users until the server total is reached', async () => {
    const calls: Array<{ page: number; pageSize: number }> = [];
    const users = await collectAdminPeopleExportUsers({
      pageSize: 2,
      loadPage: async (query) => {
        calls.push(query);
        if (query.page === 1) {
          return { total: 3, items: [user({ id: 'a' }), user({ id: 'b' })] };
        }
        return { total: 3, items: [user({ id: 'c' })] };
      },
    });

    expect(users.map((item) => item.id)).toEqual(['a', 'b', 'c']);
    expect(calls).toEqual([
      { page: 1, pageSize: 2 },
      { page: 2, pageSize: 2 },
    ]);
  });
});
