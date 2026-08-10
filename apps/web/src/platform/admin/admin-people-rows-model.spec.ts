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
  status: (status) => `status:${status || '-'}`,
  date: (value) => value ?? '-',
  unassignedOrg: 'Unassigned',
};

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    login_id: 'ada',
    email: 'ada@example.test',
    employee_code: null,
    full_name: 'Ada Lovelace',
    display_name: '',
    auth_provider: 'local',
    status: 'active',
    login_blocked: false,
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    primary_org_unit: null,
    system_roles: [],
    workspaces: [],
    workspace_roles: [],
    must_change_password: false,
    last_login_at: null,
    created_at: undefined,
    ...overrides,
  } as AuthUser;
}

describe('admin people rows model', () => {
  it('derives table rows with labels and fallbacks', () => {
    const model = buildAdminPeopleRows({
      users: [
        user({
          display_name: 'Ada',
          employee_code: 'E100',
          primary_org_unit: {
            id: 'org-1',
            name: 'Research',
            path: 'Research',
          },
          system_roles: ['platform_admin'],
          workspaces: [
            {
              id: 'workspace-1',
              slug: 'hq',
              name: 'HQ',
              role: 'admin',
            },
          ],
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
      employeeCode: 'E100',
      orgName: 'Research',
      workspaceNames: 'HQ',
      role: 'admin',
      roleLabel: 'Admin',
      statusLabel: 'status:active',
      appsLabel: 'Admin',
      lastActiveLabel: '2026-05-29T00:00:00Z',
      createdLabel: '2026-01-01T00:00:00Z',
    });
  });

  it('labels users without a primary org unit as unassigned', () => {
    const model = buildAdminPeopleRows({
      users: [user()],
      total: 1,
      page: 1,
      format: formatter,
    });

    expect(model.rows[0]?.orgName).toBe('Unassigned');
    expect(
      buildAdminPeopleExportRows({
        users: [user()],
        format: formatter,
      })[0]?.[2],
    ).toBe('');
    expect(
      buildAdminPeopleExportRows({
        users: [user()],
        format: formatter,
      })[0]?.[3],
    ).toBe('Unassigned');
  });

  it('filters rows by role while preserving pagination from the loaded page', () => {
    const admin = user({
      id: 'admin',
      system_roles: ['platform_admin'],
    });
    const member = user({ id: 'member' });

    expect(
      buildAdminPeopleRows({
        users: [admin, member],
        total: 25,
        page: 2,
        pageSize: 20,
        roleFilter: 'member',
        format: formatter,
      }),
    ).toMatchObject({
      rows: [{ id: 'member' }],
      pagination: {
        from: 21,
        to: 22,
        totalPages: 2,
        canPrevious: true,
        canNext: false,
      },
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

  it('chooses the next page after deleting a user', () => {
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

  it('builds export rows in CSV column order', () => {
    expect(
      buildAdminPeopleExportRows({
        users: [
          user({
            display_name: 'Ada',
            employee_code: 'E100',
            primary_org_unit: { id: 'org-1', name: 'Research', path: 'Research' },
            workspaces: [
              {
                id: 'workspace-1',
                slug: 'hq',
                name: 'HQ',
                role: 'member',
              },
            ],
            created_at: '2026-01-01T00:00:00Z',
          }),
        ],
        format: formatter,
      }),
    ).toEqual([
      [
        'Ada',
        'ada@example.test',
        'E100',
        'Research',
        'HQ',
        'Member',
        'status:active',
        '-',
        '2026-01-01T00:00:00Z',
        '-',
      ],
    ]);
  });

  it('encodes CSV with quoted and escaped cells', () => {
    expect(
      encodeAdminPeopleCsv({
        header: [
          'Name',
          'Email',
          'Employee no.',
          'Org',
          'Workspaces',
          'Role',
          'Status',
          'Last Active',
          'Created',
          'Apps',
        ],
        rows: [
          [
            'Ada "Countess"',
            'ada@example.test',
            'E100',
            '-',
            'HQ',
            'Member',
            'status:active',
            '-',
            '-',
            '-',
          ],
        ],
      }),
    ).toBe(
      '"Name","Email","Employee no.","Org","Workspaces","Role","Status","Last Active","Created","Apps"\n' +
        '"Ada ""Countess""","ada@example.test","E100","-","HQ","Member","status:active","-","-","-"',
    );
  });

  it('collects export users until total is reached or an empty page is returned', async () => {
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

    await expect(
      collectAdminPeopleExportUsers({
        loadPage: async () => ({ total: 10, items: [] }),
      }),
    ).resolves.toEqual([]);
  });
});
