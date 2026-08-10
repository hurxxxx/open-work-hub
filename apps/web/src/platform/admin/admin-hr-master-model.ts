import type { AdminHrEmployeeItem, AdminHrGroupSource } from './admin-api';

export const ADMIN_HR_PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
export type AdminHrPageSize = (typeof ADMIN_HR_PAGE_SIZE_OPTIONS)[number];

export interface AdminHrPagination {
  from: number;
  to: number;
  totalPages: number;
  previousDisabled: boolean;
  nextDisabled: boolean;
}

export function buildAdminHrPagination({
  loading,
  page,
  pageSize,
  total,
}: {
  loading: boolean;
  page: number;
  pageSize: number;
  total: number;
}): AdminHrPagination {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return {
    from: total === 0 ? 0 : (page - 1) * pageSize + 1,
    to: Math.min(page * pageSize, total),
    totalPages,
    previousDisabled: loading || page <= 1,
    nextDisabled: loading || page >= totalPages,
  };
}

export function getAdminHrSourcePresence(
  item: Pick<AdminHrEmployeeItem, 'has_erp' | 'has_groupware'>,
): AdminHrGroupSource[] {
  const sources: AdminHrGroupSource[] = [];
  if (item.has_erp) {
    sources.push('erp');
  }
  if (item.has_groupware) {
    sources.push('groupware');
  }
  return sources;
}

export function getAdminHrRoleValues(
  item: Pick<AdminHrEmployeeItem, 'position' | 'occupation'>,
): string[] {
  return [item.position, item.occupation].filter((value): value is string =>
    Boolean(value?.trim()),
  );
}
