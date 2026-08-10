import { describe, expect, it } from 'vitest';

import {
  buildAdminHrPagination,
  getAdminHrRoleValues,
  getAdminHrSourcePresence,
} from './admin-hr-master-model';

describe('admin HR master model', () => {
  it('builds external pagination boundaries', () => {
    expect(
      buildAdminHrPagination({
        loading: false,
        page: 2,
        pageSize: 20,
        total: 45,
      }),
    ).toEqual({
      from: 21,
      to: 40,
      totalPages: 3,
      previousDisabled: false,
      nextDisabled: false,
    });

    expect(
      buildAdminHrPagination({
        loading: false,
        page: 1,
        pageSize: 20,
        total: 0,
      }),
    ).toMatchObject({
      from: 0,
      to: 0,
      previousDisabled: true,
      nextDisabled: true,
    });
  });

  it('projects source presence and non-empty role values', () => {
    expect(
      getAdminHrSourcePresence({ has_erp: true, has_groupware: false }),
    ).toEqual(['erp']);
    expect(
      getAdminHrSourcePresence({ has_erp: true, has_groupware: true }),
    ).toEqual(['erp', 'groupware']);
    expect(
      getAdminHrRoleValues({ position: 'Manager', occupation: '  ' }),
    ).toEqual(['Manager']);
  });
});
