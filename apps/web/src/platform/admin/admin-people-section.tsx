import { Plus, Search } from 'lucide-react';
import type React from 'react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, Dialog, DropdownMenu, SearchField } from '@open-work-hub/ui';

import {
  createAdminUser,
  deleteAdminUser,
  listAdminUsers,
  resetUserPassword,
  updateAdminUser,
} from './admin-api';
import {
  buildAdminPeopleExportRows,
  buildAdminPeopleRows,
  collectAdminPeopleExportUsers,
  encodeAdminPeopleCsv,
  nextAdminPeoplePageAfterDelete,
  type AdminPeopleExportHeader,
  type AdminPeopleFormatter,
} from './admin-people-rows-model';
import {
  ADMIN_PEOPLE_PAGE_SIZE_OPTIONS,
  BodyCell,
  EmptyRow,
  FORM_FIELD_CLASS as fieldClassName,
  formatDateLabel,
  formatStatusLabel,
  getErrorMessage,
  HeadCell,
  SectionMessage,
} from './admin-shared';
import { useAdminPeopleDirectoryController } from './useAdminPeopleDirectoryController';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';

function primaryOrganizationValue(user: AuthUser, key: 'id' | 'name'): string {
  const value = user.primary_organization_unit?.[key];
  return typeof value === 'string' ? value : '';
}

export function PeopleSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const auth = useAuth();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(auth.user?.time_zone);
  const directory = useAdminPeopleDirectoryController({
    token,
    messages: {
      organizationListLoadFailed: t(
        'admin.console.people.organizationListLoadFailed',
      ),
      userListLoadFailed: t('admin.console.people.userListLoadFailed'),
    },
  });
  const {
    error: directoryError,
    isLoadingUsers,
    includeDescendants,
    organizationUnitId,
    organizationUnits,
    page,
    pageSize,
    search,
    totalUsers,
    unassignedOnly,
    users,
  } = directory.state;
  const [createOpen, setCreateOpen] = useState(false);
  const [loginId, setLoginId] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [employeeCode, setEmployeeCode] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [primaryOrganizationUnitId, setPrimaryOrganizationUnitId] =
    useState('');
  const [selectedPlatformAdmin, setSelectedPlatformAdmin] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isCreatingUser, setIsCreatingUser] = useState(false);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editFullName, setEditFullName] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editEmployeeCode, setEditEmployeeCode] = useState('');
  const [editJobTitle, setEditJobTitle] = useState('');
  const [editPrimaryOrganizationUnitId, setEditPrimaryOrganizationUnitId] =
    useState('');
  const [editStatus, setEditStatus] = useState<
    'active' | 'invited' | 'suspended'
  >('active');
  const [editLoginBlocked, setEditLoginBlocked] = useState(false);
  const [editPlatformAdmin, setEditPlatformAdmin] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState<string | null>(null);
  const peopleFormatter = useMemo<AdminPeopleFormatter>(
    () => ({
      role: {
        admin: t('admin.console.people.platformAdmin'),
        member: t('admin.console.people.regularUser'),
      },
      status: (status) => formatStatusLabel(status, t),
      date: (value) => formatDateLabel(value, locale, timeZone),
    }),
    [locale, t, timeZone],
  );
  const peopleModel = useMemo(
    () =>
      buildAdminPeopleRows({
        users,
        total: totalUsers,
        page,
        pageSize,
        format: peopleFormatter,
      }),
    [page, pageSize, peopleFormatter, totalUsers, users],
  );
  const editingUser = useMemo(
    () => users.find((user) => user.id === editingUserId) ?? null,
    [editingUserId, users],
  );

  async function reloadUsers(nextPage: number) {
    await directory.actions.reloadUsers(nextPage);
  }

  function openCreateUserDialog() {
    setMessage(null);
    setError(null);
    setEditingUserId(null);
    setLoginId('');
    setEmail('');
    setFullName('');
    setDisplayName('');
    setEmployeeCode('');
    setJobTitle('');
    setPrimaryOrganizationUnitId('');
    setSelectedPlatformAdmin(false);
    setCreateOpen(true);
    requestAnimationFrame(() => {
      document.getElementById('admin-user-email')?.focus();
    });
  }

  function closeCreateUserDialog() {
    if (!isCreatingUser) {
      setCreateOpen(false);
    }
  }

  function closeEditUserDialog() {
    if (!isSavingUser) {
      setEditingUserId(null);
    }
  }

  async function handleCreateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setIsCreatingUser(true);
    let createdUser: Awaited<ReturnType<typeof createAdminUser>> | null = null;

    try {
      createdUser = await createAdminUser(token, {
        login_id: loginId.trim() || undefined,
        email: email.trim(),
        full_name: fullName.trim(),
        display_name: displayName.trim() || undefined,
        employee_code: employeeCode.trim() || null,
        job_title: jobTitle.trim() || null,
        primary_organization_unit_id: primaryOrganizationUnitId || null,
        system_roles: selectedPlatformAdmin ? ['platform_admin'] : [],
      });
      setCreateOpen(false);
      setMessage(
        t('admin.console.people.userCreated', {
          password: createdUser.temporary_password,
        }),
      );
      await reloadUsers(1);
    } catch (caughtError) {
      if (createdUser) {
        setCreateOpen(false);
        setError(
          t('admin.console.people.userCreatedReloadFailed', {
            password: createdUser.temporary_password,
          }),
        );
        await reloadUsers(1);
      } else {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.people.userCreateFailed'),
          ),
        );
      }
    } finally {
      setIsCreatingUser(false);
    }
  }

  async function handleResetPassword(userId: string) {
    setMessage(null);
    setError(null);
    try {
      const response = await resetUserPassword(token, userId);
      setMessage(
        t('admin.console.people.passwordReset', {
          password: response.temporary_password,
        }),
      );
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.people.passwordResetFailed'),
        ),
      );
    }
  }

  async function handleSetLoginBlocked(user: AuthUser, loginBlocked: boolean) {
    setMessage(null);
    setError(null);
    try {
      await updateAdminUser(token, user.id, {
        login_blocked: loginBlocked,
      });
      setMessage(
        loginBlocked
          ? t('admin.console.people.loginBlocked', { email: user.email })
          : t('admin.console.people.loginUnblocked', { email: user.email }),
      );
      await reloadUsers(page);
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.people.loginBlockFailed'),
        ),
      );
    }
  }

  function startEditUser(user: AuthUser) {
    setMessage(null);
    setError(null);
    setCreateOpen(false);
    setEditingUserId(user.id);
    setEditFullName(user.full_name);
    setEditDisplayName(user.display_name);
    setEditEmployeeCode(user.employee_code ?? '');
    setEditJobTitle(user.job_title ?? '');
    setEditPrimaryOrganizationUnitId(primaryOrganizationValue(user, 'id'));
    setEditStatus(
      user.status === 'invited' || user.status === 'suspended'
        ? user.status
        : 'active',
    );
    setEditLoginBlocked(Boolean(user.login_blocked));
    setEditPlatformAdmin(user.system_roles.includes('platform_admin'));
    requestAnimationFrame(() => {
      document.getElementById('admin-user-edit-full-name')?.focus();
    });
  }

  function handleUpdateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingUserId) {
      return;
    }
    void saveEditedUser();
  }

  async function saveEditedUser() {
    if (!editingUserId) {
      return;
    }
    setMessage(null);
    setError(null);
    setIsSavingUser(true);
    let profileSaved = false;

    try {
      await updateAdminUser(token, editingUserId, {
        full_name: editFullName.trim(),
        display_name: editDisplayName.trim() || editFullName.trim(),
        employee_code: editEmployeeCode.trim() || null,
        job_title: editJobTitle.trim() || null,
        ...(editPrimaryOrganizationUnitId !==
        (editingUser ? primaryOrganizationValue(editingUser, 'id') : '')
          ? {
              primary_organization_unit_id:
                editPrimaryOrganizationUnitId || null,
            }
          : {}),
        system_roles: editPlatformAdmin ? ['platform_admin'] : [],
        status: editStatus,
        login_blocked: editLoginBlocked,
      });
      profileSaved = true;
      setEditingUserId(null);
      setMessage(t('admin.console.people.userSaved'));
      await reloadUsers(page);
    } catch (caughtError) {
      if (profileSaved) {
        setEditingUserId(null);
        setError(t('admin.console.people.userSavedAccessFailed'));
        await reloadUsers(page);
      } else {
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.people.userSaveFailed'),
          ),
        );
      }
    } finally {
      setIsSavingUser(false);
    }
  }

  async function handleDeleteUser(user: AuthUser) {
    if (
      !window.confirm(
        t('admin.console.people.deleteConfirm', { email: user.email }),
      )
    ) {
      return;
    }
    setMessage(null);
    setError(null);
    setDeletingUserId(user.id);
    try {
      await deleteAdminUser(token, user.id);
      setEditingUserId((current) => (current === user.id ? null : current));
      setMessage(t('admin.console.people.userDeleted', { email: user.email }));
      await reloadUsers(
        nextAdminPeoplePageAfterDelete({
          currentPage: page,
          totalBeforeDelete: totalUsers,
          pageSize,
        }),
      );
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.people.userDeleteFailed'),
        ),
      );
    } finally {
      setDeletingUserId(null);
    }
  }

  async function handleExport() {
    setIsExporting(true);
    setError(null);
    try {
      const exportUsers = await collectAdminPeopleExportUsers({
        loadPage: async ({ page: exportPage, pageSize: exportPageSize }) => {
          const userResponse = await listAdminUsers(token, {
            page: exportPage,
            page_size: exportPageSize,
            q: search,
            ...(unassignedOnly
              ? { unassigned_only: true }
              : organizationUnitId
                ? {
                    organization_unit_id: organizationUnitId,
                    include_descendants: includeDescendants,
                  }
                : {}),
          });
          return {
            items: userResponse.items,
            total: userResponse.total,
          };
        },
      });
      const rows = buildAdminPeopleExportRows({
        users: exportUsers,
        format: peopleFormatter,
      });
      const header: AdminPeopleExportHeader = [
        t('admin.console.people.columns.name'),
        t('admin.console.people.columns.loginId'),
        t('admin.console.people.columns.email'),
        t('admin.console.people.columns.employeeCode'),
        t('admin.console.people.columns.jobTitle'),
        t('admin.console.people.columns.organization'),
        t('admin.console.people.columns.groups'),
        t('admin.console.people.columns.role'),
        t('admin.console.people.columns.status'),
        t('admin.console.people.columns.lastActive'),
        t('admin.console.people.columns.created'),
      ];
      downloadBlobAsFile(
        new Blob([encodeAdminPeopleCsv({ header, rows })], {
          type: 'text/csv;charset=utf-8',
        }),
        'open-work-hub-people.csv',
      );
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.people.exportFailed')),
      );
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <SectionMessage error={error ?? directoryError} message={message} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-4">
        <SearchField
          aria-label={t('admin.console.people.search')}
          className="min-w-[280px] max-w-md flex-1"
          endAdornment={<Search size={15} className="text-app-ink/50" />}
          onChange={(event) =>
            directory.actions.searchChanged(event.target.value)
          }
          placeholder={t('admin.console.people.searchPlaceholder')}
          value={search}
        />
        <div className="flex items-center gap-2">
          <Button
            disabled={isExporting || totalUsers === 0}
            onClick={() => void handleExport()}
            type="button"
            variant="ghost"
          >
            {isExporting
              ? t('admin.console.people.exporting')
              : t('admin.console.people.export')}
          </Button>
          <Button
            onClick={openCreateUserDialog}
            type="button"
            variant="primary"
          >
            <Plus size={14} />
            {t('admin.console.people.createUser')}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
        <label className="app-text-caption flex items-center gap-2 text-app-ink/55">
          <span>{t('admin.console.people.organizationFilter')}</span>
          <select
            className="app-field-input-sm min-w-48"
            onChange={(event) =>
              directory.actions.organizationUnitChanged(event.target.value)
            }
            value={organizationUnitId}
          >
            <option value="">
              {t('admin.console.people.allOrganizations')}
            </option>
            {organizationUnits.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
                {!item.active
                  ? ` (${t('admin.console.people.inactiveOrganization')})`
                  : ''}
              </option>
            ))}
          </select>
        </label>
        <label className="app-text-caption flex items-center gap-2 text-app-ink/65">
          <input
            checked={includeDescendants}
            disabled={!organizationUnitId}
            onChange={(event) =>
              directory.actions.setIncludeDescendants(event.target.checked)
            }
            type="checkbox"
          />
          {t('admin.console.people.includeDescendants')}
        </label>
        <label className="app-text-caption flex items-center gap-2 text-app-ink/65">
          <input
            checked={unassignedOnly}
            onChange={(event) =>
              directory.actions.setUnassignedOnly(event.target.checked)
            }
            type="checkbox"
          />
          {t('admin.console.people.unassignedOnly')}
        </label>
      </div>

      <div className="flex h-[calc(100vh-230px)] min-h-[520px] min-w-0 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <div className="app-text-control inline-flex items-center gap-2 text-app-ink">
            <span>
              {t('admin.console.people.allUsers', { count: totalUsers })}
            </span>
            {isLoadingUsers ? (
              <span className="app-text-caption text-app-ink/55">
                {t('common:feedback.loading')}
              </span>
            ) : null}
          </div>
          <label className="app-text-caption inline-flex items-center gap-2 text-app-ink/55">
            <span>{t('admin.console.people.pageSizeLabel')}</span>
            <select
              className="app-field-input-sm w-auto"
              onChange={(event) =>
                directory.actions.setPageSize(Number(event.target.value))
              }
              value={pageSize}
            >
              {ADMIN_PEOPLE_PAGE_SIZE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {t('admin.console.people.pageSizeOption', { count: option })}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-auto border-t border-app-border">
          <table className="app-text-body-sm min-w-[1080px] w-full border-collapse">
            <thead>
              <tr className="sticky top-0 z-10 bg-app-surface-sidebar">
                <HeadCell className="w-[260px]" dense>
                  {t('admin.console.people.columns.user')}
                </HeadCell>
                <HeadCell className="w-[180px]" dense>
                  {t('admin.console.people.columns.organization')}
                </HeadCell>
                <HeadCell className="w-[150px]" dense>
                  {t('admin.console.people.columns.groups')}
                </HeadCell>
                <HeadCell className="w-[80px]" dense>
                  {t('admin.console.people.columns.role')}
                </HeadCell>
                <HeadCell className="w-[120px]" dense>
                  {t('admin.console.people.columns.status')}
                </HeadCell>
                <HeadCell className="w-[110px]" dense>
                  {t('admin.console.people.columns.enabledApps')}
                </HeadCell>
                <HeadCell className="w-[95px]" dense>
                  {t('admin.console.people.columns.lastActive')}
                </HeadCell>
                <HeadCell className="w-[95px]" dense>
                  {t('admin.console.people.columns.created')}
                </HeadCell>
                <HeadCell className="w-[76px] text-right" dense>
                  {t('admin.console.people.columns.actions')}
                </HeadCell>
              </tr>
            </thead>
            <tbody>
              {isLoadingUsers && users.length === 0 ? (
                <EmptyRow
                  colSpan={9}
                  description={t('admin.console.people.loadingDescription')}
                  title={t('admin.console.people.loadingTitle')}
                />
              ) : peopleModel.rows.length === 0 ? (
                <EmptyRow
                  colSpan={9}
                  description={t('admin.console.people.emptyDescription')}
                  title={t('admin.console.people.emptyTitle')}
                />
              ) : (
                peopleModel.rows.map((row) => {
                  const isCurrentUser = row.id === auth.user?.id;
                  return (
                    <tr
                      className="transition-colors hover:bg-app-surface-hover/40"
                      key={row.id}
                    >
                      <BodyCell className="max-w-[260px]" dense>
                        <div className="min-w-0">
                          <div className="truncate font-medium text-app-ink">
                            {row.name}
                          </div>
                          <div className="app-text-caption mt-0.5 flex min-w-0 items-center gap-1.5 text-app-ink/55">
                            <span className="truncate">{row.loginId}</span>
                            <span className="text-app-ink/30">·</span>
                            <span className="truncate">{row.email}</span>
                          </div>
                        </div>
                      </BodyCell>
                      <BodyCell className="max-w-[180px]" dense>
                        <div className="truncate text-app-ink/65">
                          {primaryOrganizationValue(row.user, 'name') ||
                            t('admin.console.people.unassigned')}
                        </div>
                        {row.user.job_title || row.user.employee_code ? (
                          <div className="app-text-caption mt-0.5 truncate text-app-ink/45">
                            {[row.user.job_title, row.user.employee_code]
                              .filter(Boolean)
                              .join(' · ')}
                          </div>
                        ) : null}
                      </BodyCell>
                      <BodyCell
                        className="max-w-[150px] truncate text-app-ink/55"
                        dense
                      >
                        {row.groupCount}
                      </BodyCell>
                      <BodyCell
                        className="whitespace-nowrap text-app-ink/55"
                        dense
                      >
                        {row.roleLabel}
                      </BodyCell>
                      <BodyCell dense>
                        <div className="flex items-center gap-1">
                          <span className="app-text-caption rounded border border-app-border px-1.5 py-0.5 text-app-ink/55">
                            {row.statusLabel}
                          </span>
                          {row.user.login_blocked ? (
                            <span className="app-text-caption rounded border border-app-warning-border px-1.5 py-0.5 text-app-warning-text">
                              {t('admin.console.people.loginBlockedBadge')}
                            </span>
                          ) : null}
                        </div>
                      </BodyCell>
                      <BodyCell className="text-app-ink/55" dense>
                        {row.lastActiveLabel}
                      </BodyCell>
                      <BodyCell className="text-app-ink/55" dense>
                        {row.createdLabel}
                      </BodyCell>
                      <BodyCell className="text-right" dense>
                        <DropdownMenu
                          items={[
                            {
                              id: 'edit',
                              label: t('admin.console.people.editUser'),
                              onSelect: () => startEditUser(row.user),
                            },
                            {
                              id: 'login-block',
                              label: row.user.login_blocked
                                ? t('admin.console.people.unblockLogin')
                                : t('admin.console.people.blockLogin'),
                              disabled: isCurrentUser,
                              onSelect: () =>
                                void handleSetLoginBlocked(
                                  row.user,
                                  !row.user.login_blocked,
                                ),
                            },
                            {
                              id: 'reset',
                              label: t('admin.console.people.resetPassword'),
                              onSelect: () => void handleResetPassword(row.id),
                            },
                            {
                              id: 'delete',
                              label:
                                deletingUserId === row.id
                                  ? t('admin.console.people.deletingUser')
                                  : t('admin.console.people.deleteUser'),
                              disabled:
                                isCurrentUser || deletingUserId === row.id,
                              separatorBefore: true,
                              tone: 'danger' as const,
                              onSelect: () => void handleDeleteUser(row.user),
                            },
                          ]}
                          trigger={
                            <Button
                              aria-label={t(
                                'admin.console.people.userActions',
                                { email: row.email },
                              )}
                              size="dense"
                              type="button"
                              variant="secondary"
                            >
                              {t('admin.console.people.more')}
                            </Button>
                          }
                        />
                      </BodyCell>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col gap-3 border-t border-app-border pt-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="app-text-body text-app-ink/55">
            {t('admin.console.people.range', {
              from: peopleModel.pagination.from,
              to: peopleModel.pagination.to,
              total: peopleModel.pagination.total,
            })}
          </div>
          <div className="flex items-center gap-2">
            <Button
              disabled={!peopleModel.pagination.canPrevious || isLoadingUsers}
              onClick={() =>
                directory.actions.setPage((current) => Math.max(1, current - 1))
              }
              type="button"
              variant="secondary"
            >
              {t('admin.shared.pagination.previous')}
            </Button>
            <span className="app-text-body min-w-20 text-center text-app-ink/55">
              {page} / {peopleModel.pagination.totalPages}
            </span>
            <Button
              disabled={!peopleModel.pagination.canNext || isLoadingUsers}
              onClick={() =>
                directory.actions.setPage((current) =>
                  Math.min(peopleModel.pagination.totalPages, current + 1),
                )
              }
              type="button"
              variant="secondary"
            >
              {t('admin.shared.pagination.next')}
            </Button>
          </div>
        </div>
      </div>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button
              disabled={isCreatingUser}
              onClick={closeCreateUserDialog}
              variant="secondary"
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={isCreatingUser}
              form="admin-user-create-form"
              type="submit"
              variant="primary"
            >
              {isCreatingUser
                ? t('admin.console.people.creating')
                : t('common:actions.create')}
            </Button>
          </div>
        }
        closeLabel={t('common:actions.close')}
        description={t('admin.console.people.createDescription')}
        dismissOnInteractOutside={false}
        maxWidth="max-w-2xl"
        onOpenChange={(open) => {
          if (!open) closeCreateUserDialog();
        }}
        open={createOpen}
        title={t('admin.console.people.createUser')}
      >
        <form
          className="grid gap-5"
          id="admin-user-create-form"
          onSubmit={(event) => void handleCreateUser(event)}
        >
          <section className="grid gap-3">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.profileSection')}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.loginId')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={40}
                  minLength={3}
                  onChange={(event) => setLoginId(event.target.value)}
                  placeholder={t('admin.console.people.loginIdPlaceholder')}
                  value={loginId}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.email')}
                </span>
                <input
                  className={fieldClassName}
                  id="admin-user-email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder={t('admin.console.people.emailPlaceholder')}
                  required
                  type="email"
                  value={email}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.fullName')}
                </span>
                <input
                  className={fieldClassName}
                  onChange={(event) => setFullName(event.target.value)}
                  required
                  value={fullName}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.displayName')}
                </span>
                <input
                  className={fieldClassName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  value={displayName}
                />
              </label>
            </div>
          </section>
          <section className="grid gap-3 border-t border-app-border pt-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.organizationMetadataSection')}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.employeeCode')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={40}
                  onChange={(event) => setEmployeeCode(event.target.value)}
                  value={employeeCode}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.jobTitle')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={120}
                  onChange={(event) => setJobTitle(event.target.value)}
                  value={jobTitle}
                />
              </label>
              <label className="grid gap-1 md:col-span-2">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.primaryOrganization')}
                </span>
                <select
                  className="app-field-input"
                  onChange={(event) =>
                    setPrimaryOrganizationUnitId(event.target.value)
                  }
                  value={primaryOrganizationUnitId}
                >
                  <option value="">
                    {t('admin.console.people.unassigned')}
                  </option>
                  {organizationUnits
                    .filter((item) => item.active)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <p className="app-text-caption text-app-ink/55">
              {t('admin.console.people.organizationMetadataHint')}
            </p>
          </section>
          <section className="grid gap-3 border-t border-app-border pt-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.adminPrivilegesSection')}
            </h3>
            <label className="app-text-control inline-flex items-start gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
              <input
                checked={selectedPlatformAdmin}
                onChange={(event) =>
                  setSelectedPlatformAdmin(event.target.checked)
                }
                type="checkbox"
              />
              <span className="grid gap-0.5">
                <span>{t('admin.console.people.platformAdmin')}</span>
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.platformAdminDescription')}
                </span>
              </span>
            </label>
          </section>
        </form>
      </Dialog>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button
              disabled={isSavingUser}
              onClick={closeEditUserDialog}
              variant="secondary"
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={isSavingUser}
              form="admin-user-edit-form"
              type="submit"
              variant="primary"
            >
              {isSavingUser
                ? t('common:actions.saving')
                : t('common:actions.save')}
            </Button>
          </div>
        }
        closeLabel={t('common:actions.close')}
        description={editingUser ? editingUser.email : undefined}
        dismissOnInteractOutside={false}
        maxWidth="max-w-2xl"
        onOpenChange={(open) => {
          if (!open) closeEditUserDialog();
        }}
        open={editingUserId !== null}
        title={t('admin.console.people.editUser')}
      >
        <form
          className="grid gap-5"
          id="admin-user-edit-form"
          onSubmit={(event) => void handleUpdateUser(event)}
        >
          <section className="grid gap-3">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.profileSection')}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.fullName')}
                </span>
                <input
                  className={fieldClassName}
                  id="admin-user-edit-full-name"
                  onChange={(event) => setEditFullName(event.target.value)}
                  required
                  value={editFullName}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.displayName')}
                </span>
                <input
                  className={fieldClassName}
                  onChange={(event) => setEditDisplayName(event.target.value)}
                  value={editDisplayName}
                />
              </label>
            </div>
          </section>
          <section className="grid gap-3 border-t border-app-border pt-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.organizationMetadataSection')}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.employeeCode')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={40}
                  onChange={(event) => setEditEmployeeCode(event.target.value)}
                  value={editEmployeeCode}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.jobTitle')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={120}
                  onChange={(event) => setEditJobTitle(event.target.value)}
                  value={editJobTitle}
                />
              </label>
              <label className="grid gap-1 md:col-span-2">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.primaryOrganization')}
                </span>
                <select
                  className="app-field-input"
                  onChange={(event) =>
                    setEditPrimaryOrganizationUnitId(event.target.value)
                  }
                  value={editPrimaryOrganizationUnitId}
                >
                  <option value="">
                    {t('admin.console.people.unassigned')}
                  </option>
                  {organizationUnits
                    .filter(
                      (item) =>
                        item.active ||
                        item.id === editPrimaryOrganizationUnitId,
                    )
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                        {!item.active
                          ? ` (${t('admin.console.people.inactiveOrganization')})`
                          : ''}
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <p className="app-text-caption text-app-ink/55">
              {t('admin.console.people.organizationMetadataHint')}
            </p>
          </section>
          <section className="grid gap-3 border-t border-app-border pt-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.accountAccessSection')}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.columns.status')}
                </span>
                <select
                  className="app-field-input"
                  disabled={editingUser?.id === auth.user?.id}
                  onChange={(event) =>
                    setEditStatus(event.target.value as typeof editStatus)
                  }
                  value={editStatus}
                >
                  <option value="active">
                    {t('admin.shared.status.active')}
                  </option>
                  <option value="invited">
                    {t('admin.shared.status.invited')}
                  </option>
                  <option value="suspended">
                    {t('admin.shared.status.suspended')}
                  </option>
                </select>
              </label>
              <label className="app-text-control inline-flex items-start gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
                <input
                  checked={editLoginBlocked}
                  disabled={editingUser?.id === auth.user?.id}
                  onChange={(event) =>
                    setEditLoginBlocked(event.target.checked)
                  }
                  type="checkbox"
                />
                <span className="grid gap-0.5">
                  <span>{t('admin.console.people.blockLogin')}</span>
                  <span className="app-text-caption text-app-ink/55">
                    {t('admin.console.people.blockLoginDescription')}
                  </span>
                </span>
              </label>
            </div>
          </section>
          <section className="grid gap-3 border-t border-app-border pt-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('admin.console.people.adminPrivilegesSection')}
            </h3>
            <label className="app-text-control inline-flex items-start gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
              <input
                checked={editPlatformAdmin}
                disabled={editingUser?.id === auth.user?.id}
                onChange={(event) => setEditPlatformAdmin(event.target.checked)}
                type="checkbox"
              />
              <span className="grid gap-0.5">
                <span>{t('admin.console.people.platformAdmin')}</span>
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.platformAdminDescription')}
                </span>
              </span>
            </label>
          </section>
        </form>
      </Dialog>
    </div>
  );
}
