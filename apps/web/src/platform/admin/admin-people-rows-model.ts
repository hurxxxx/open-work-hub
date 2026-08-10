import type { AuthUser } from '@/src/platform/auth/auth-api';

import {
  PEOPLE_EXPORT_PAGE_SIZE,
  PEOPLE_PAGE_SIZE,
  formatUserApps,
  formatUserWorkspaces,
  isAdminUser,
} from './admin-shared-model';

export type AdminPeopleRoleFilter = 'all' | 'admin' | 'member';
export type AdminPeopleRole = 'admin' | 'member';

export interface AdminPeopleFormatter {
  role: Record<AdminPeopleRole, string>;
  status: (status: string) => string;
  date: (value?: string | null) => string;
  unassignedOrg: string;
}

export interface AdminPeopleRow {
  user: AuthUser;
  id: string;
  name: string;
  loginId: string;
  email: string;
  employeeCode: string;
  orgName: string;
  workspaceNames: string;
  role: AdminPeopleRole;
  roleLabel: string;
  statusLabel: string;
  appsLabel: string;
  lastActiveLabel: string;
  createdLabel: string;
}

export interface AdminPeoplePagination {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  from: number;
  to: number;
  canPrevious: boolean;
  canNext: boolean;
}

export interface AdminPeopleRowsModel {
  rows: AdminPeopleRow[];
  pagination: AdminPeoplePagination;
}

export type AdminPeopleExportHeader = readonly [
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
];

export type AdminPeopleExportRow = AdminPeopleExportHeader;

export interface AdminPeopleExportPage {
  items: AuthUser[];
  total: number;
}

export type AdminPeopleExportPageLoader = (query: {
  page: number;
  pageSize: number;
}) => Promise<AdminPeopleExportPage>;

function adminPeopleRole(user: Pick<AuthUser, 'system_roles'>): AdminPeopleRole {
  return isAdminUser(user) ? 'admin' : 'member';
}

function matchesRoleFilter(
  user: Pick<AuthUser, 'system_roles'>,
  roleFilter: AdminPeopleRoleFilter,
): boolean {
  const role = adminPeopleRole(user);
  return roleFilter === 'all' || role === roleFilter;
}

function buildAdminPeopleRow(
  user: AuthUser,
  format: AdminPeopleFormatter,
): AdminPeopleRow {
  const role = adminPeopleRole(user);
  return {
    user,
    id: user.id,
    name: user.display_name || user.full_name,
    loginId: user.login_id,
    email: user.email,
    employeeCode: user.employee_code?.trim() ?? '',
    orgName: user.primary_org_unit?.name ?? format.unassignedOrg,
    workspaceNames: formatUserWorkspaces(user),
    role,
    roleLabel: format.role[role],
    statusLabel: format.status(user.status),
    appsLabel: formatUserApps(user),
    lastActiveLabel: format.date(user.last_login_at),
    createdLabel: format.date(user.created_at),
  };
}

function buildAdminPeoplePagination({
  page,
  pageSize,
  total,
  visibleCount,
}: {
  page: number;
  pageSize: number;
  total: number;
  visibleCount: number;
}): AdminPeoplePagination {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return {
    page,
    pageSize,
    total,
    totalPages,
    from: total === 0 ? 0 : (page - 1) * pageSize + 1,
    to: Math.min(total, (page - 1) * pageSize + visibleCount),
    canPrevious: page > 1,
    canNext: page < totalPages,
  };
}

export function buildAdminPeopleRows({
  users,
  total,
  page,
  pageSize = PEOPLE_PAGE_SIZE,
  roleFilter = 'all',
  format,
}: {
  users: readonly AuthUser[];
  total: number;
  page: number;
  pageSize?: number;
  roleFilter?: AdminPeopleRoleFilter;
  format: AdminPeopleFormatter;
}): AdminPeopleRowsModel {
  return {
    rows: users
      .filter((user) => matchesRoleFilter(user, roleFilter))
      .map((user) => buildAdminPeopleRow(user, format)),
    pagination: buildAdminPeoplePagination({
      page,
      pageSize,
      total,
      visibleCount: users.length,
    }),
  };
}

export function nextAdminPeoplePageAfterDelete({
  currentPage,
  totalBeforeDelete,
  pageSize = PEOPLE_PAGE_SIZE,
}: {
  currentPage: number;
  totalBeforeDelete: number;
  pageSize?: number;
}): number {
  const nextTotal = Math.max(0, totalBeforeDelete - 1);
  return Math.min(
    currentPage,
    Math.max(1, Math.ceil(nextTotal / pageSize)),
  );
}

export function buildAdminPeopleExportRows({
  users,
  roleFilter = 'all',
  format,
}: {
  users: readonly AuthUser[];
  roleFilter?: AdminPeopleRoleFilter;
  format: AdminPeopleFormatter;
}): AdminPeopleExportRow[] {
  return users
    .filter((user) => matchesRoleFilter(user, roleFilter))
    .map((user) => {
      const row = buildAdminPeopleRow(user, format);
      return [
        row.name,
        row.email,
        row.employeeCode,
        row.orgName,
        row.workspaceNames,
        row.roleLabel,
        row.statusLabel,
        row.lastActiveLabel,
        row.createdLabel,
        row.appsLabel,
      ] as const;
    });
}

export function encodeAdminPeopleCsv({
  header,
  rows,
}: {
  header: AdminPeopleExportHeader;
  rows: readonly AdminPeopleExportRow[];
}): string {
  return [header, ...rows]
    .map((row) =>
      row
        .map((item) => `"${String(item).replaceAll('"', '""')}"`)
        .join(','),
    )
    .join('\n');
}

export async function collectAdminPeopleExportUsers({
  loadPage,
  pageSize = PEOPLE_EXPORT_PAGE_SIZE,
}: {
  loadPage: AdminPeopleExportPageLoader;
  pageSize?: number;
}): Promise<AuthUser[]> {
  const users: AuthUser[] = [];
  let page = 1;
  let total = 0;
  let received = 0;

  do {
    const response = await loadPage({ page, pageSize });
    users.push(...response.items);
    total = response.total;
    received = response.items.length;
    page += 1;
  } while (received > 0 && users.length < total);

  return users;
}
