import type React from 'react';
import { type ReactNode, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, X } from 'lucide-react';

import {
  Button,
  Dialog,
  DropdownMenu,
  SearchField,
  Select,
  Tooltip,
} from '@open-alm/ui';

import {
  createAdminUser,
  deleteAdminUser,
  impersonateAdminUser,
  listAdminUsers,
  listWorkspaceBindings,
  replaceWorkspaceBindings,
  resetUserPassword,
  UNASSIGNED_ORG_UNIT_ID,
  updateAdminUser,
  type WorkspaceItem,
} from './admin-api';
import {
  ADMIN_PEOPLE_PAGE_SIZE_OPTIONS,
  BodyCell,
  EmptyRow,
  FORM_FIELD_CLASS as fieldClassName,
  HeadCell,
  SectionMessage,
  formatDateLabel,
  formatStatusLabel,
  getErrorMessage,
  getWorkspaceRoleLabel,
} from './admin-shared';
import {
  buildAdminPeopleExportRows,
  buildAdminPeopleRows,
  collectAdminPeopleExportUsers,
  encodeAdminPeopleCsv,
  nextAdminPeoplePageAfterDelete,
  type AdminPeopleExportHeader,
  type AdminPeopleFormatter,
  type AdminPeopleRoleFilter,
} from './admin-people-rows-model';
import {
  activeWorkspaces,
  addWorkspaceMembershipIds,
  removeWorkspaceMembershipId,
  selectedWorkspaceMemberships,
  workspaceMembershipAddCandidates,
} from './admin-user-access-model';
import {
  loadAdminUserAccessWorkflow,
  saveAdminUserAccessWorkflow,
  type AdminUserAccessWorkflowPorts,
} from './admin-user-access-workflow';
import { OrgTreePanel } from './admin-org-tree-panel';
import { useAdminPeopleDirectoryController } from './useAdminPeopleDirectoryController';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';

function ToolbarField({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`min-w-0 ${className}`.trim()}>{children}</div>;
}

function WorkspaceMembershipPicker({
  availableWorkspaces,
  disabled = false,
  loading = false,
  noAvailableWorkspacesLabel,
  onChange,
  selectedWorkspaceIds,
}: {
  availableWorkspaces: readonly WorkspaceItem[];
  disabled?: boolean;
  loading?: boolean;
  noAvailableWorkspacesLabel: string;
  onChange: (workspaceIds: string[]) => void;
  selectedWorkspaceIds: readonly string[];
}) {
  const { t } = useTranslation('apps');
  const [addOpen, setAddOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [draftAddIds, setDraftAddIds] = useState<string[]>([]);
  const selectedWorkspaces = useMemo(
    () =>
      selectedWorkspaceMemberships(availableWorkspaces, selectedWorkspaceIds),
    [availableWorkspaces, selectedWorkspaceIds],
  );
  const allAddCandidates = useMemo(
    () =>
      workspaceMembershipAddCandidates(
        availableWorkspaces,
        selectedWorkspaceIds,
        '',
      ),
    [availableWorkspaces, selectedWorkspaceIds],
  );
  const addCandidates = useMemo(
    () =>
      workspaceMembershipAddCandidates(
        availableWorkspaces,
        selectedWorkspaceIds,
        query,
      ),
    [availableWorkspaces, query, selectedWorkspaceIds],
  );
  const draftAddIdSet = useMemo(() => new Set(draftAddIds), [draftAddIds]);
  const canAdd = !disabled && !loading && allAddCandidates.length > 0;

  const openAddDialog = () => {
    if (!canAdd) {
      return;
    }
    setQuery('');
    setDraftAddIds([]);
    setAddOpen(true);
  };
  const closeAddDialog = () => {
    setAddOpen(false);
    setQuery('');
    setDraftAddIds([]);
  };
  const toggleDraftWorkspace = (workspaceId: string) => {
    setDraftAddIds((current) =>
      current.includes(workspaceId)
        ? current.filter((currentId) => currentId !== workspaceId)
        : [...current, workspaceId],
    );
  };
  const addDraftWorkspaces = () => {
    const orderedDraftIds = allAddCandidates
      .filter((workspace) => draftAddIdSet.has(workspace.id))
      .map((workspace) => workspace.id);
    if (orderedDraftIds.length === 0) {
      return;
    }
    onChange(addWorkspaceMembershipIds(selectedWorkspaceIds, orderedDraftIds));
    closeAddDialog();
  };

  return (
    <section className="grid gap-2">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="app-text-caption text-app-ink/55">
          {t('admin.console.people.workspaceMemberships')}
        </div>
        <Button
          disabled={!canAdd}
          onClick={openAddDialog}
          size="dense"
          type="button"
          variant="secondary"
        >
          <Plus size={14} />
          {t('common:actions.add')}
        </Button>
      </div>

      {loading ? (
        <div className="app-text-caption rounded-md border border-dashed border-app-border p-3 text-app-ink/55">
          {t('admin.console.people.checkingWorkspaceAccess')}
        </div>
      ) : availableWorkspaces.length === 0 ? (
        <div className="app-text-caption rounded-md border border-dashed border-app-border p-3 text-app-ink/55">
          {noAvailableWorkspacesLabel}
        </div>
      ) : selectedWorkspaces.length === 0 ? (
        <div className="app-text-caption rounded-md border border-dashed border-app-border p-3 text-app-ink/55">
          {t('admin.console.people.noWorkspaceMemberships')}
        </div>
      ) : (
        <ul className="grid gap-2">
          {selectedWorkspaces.map((workspace) => (
            <li
              className="app-text-control flex min-h-10 items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
              key={workspace.id}
            >
              <div className="min-w-0">
                <div className="truncate">{workspace.name}</div>
                <div className="app-text-caption truncate text-app-ink/55">
                  {workspace.key}
                </div>
              </div>
              <Button
                aria-label={t(
                  'admin.console.people.removeWorkspaceMembership',
                  {
                    workspace: workspace.name,
                  },
                )}
                disabled={disabled}
                onClick={() =>
                  onChange(
                    removeWorkspaceMembershipId(
                      selectedWorkspaceIds,
                      workspace.id,
                    ),
                  )
                }
                size="icon"
                type="button"
                variant="ghost"
              >
                <X size={13} />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        actions={
          <div className="flex w-full items-center gap-2">
            <span className="app-text-caption mr-auto text-app-ink/55">
              {t('admin.console.people.workspacePickerSelectedCount', {
                count: draftAddIds.length,
              })}
            </span>
            <Button onClick={closeAddDialog} type="button" variant="secondary">
              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={draftAddIds.length === 0}
              onClick={addDraftWorkspaces}
              type="button"
              variant="primary"
            >
              {t('common:actions.add')}
            </Button>
          </div>
        }
        closeLabel={t('common:actions.close')}
        layer="elevated"
        maxWidth="max-w-xl"
        onOpenChange={(open) => {
          if (!open) {
            closeAddDialog();
          }
        }}
        open={addOpen}
        title={t('admin.console.people.addWorkspaces')}
      >
        <div className="grid gap-3">
          <SearchField
            aria-label={t('admin.console.people.workspaceSearch')}
            endAdornment={<Search size={14} className="text-app-ink/50" />}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('admin.console.people.workspaceSearchPlaceholder')}
            value={query}
          />
          <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
            {addCandidates.length === 0 ? (
              <div className="app-text-caption px-4 py-6 text-center text-app-ink/55">
                {query.trim()
                  ? t('common:empty.noResults')
                  : t('admin.console.people.noWorkspaceAddCandidates')}
              </div>
            ) : (
              <ul className="divide-y divide-app-border">
                {addCandidates.map((workspace) => (
                  <li key={workspace.id}>
                    <label className="app-text-control flex cursor-pointer items-center gap-3 px-4 py-3 text-app-ink transition-colors hover:bg-app-surface-hover">
                      <input
                        checked={draftAddIdSet.has(workspace.id)}
                        onChange={() => toggleDraftWorkspace(workspace.id)}
                        type="checkbox"
                      />
                      <span className="min-w-0">
                        <span className="block truncate">{workspace.name}</span>
                        <span className="app-text-caption block truncate text-app-ink/55">
                          {workspace.key}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Dialog>
    </section>
  );
}

export function PeopleSection({ token }: { token: string }) {
  return <>{usePeopleSectionElement({ token })}</>;
}

function orgUnitPayloadValue(value: string): string | null | undefined {
  if (value === UNASSIGNED_ORG_UNIT_ID) {
    return null;
  }
  return value || undefined;
}

function UserSourceBadge({ user }: { user: AuthUser }) {
  const { t } = useTranslation('apps');
  const isGroupware = user.auth_provider === 'groupware';
  return (
    <span className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-app-ink/55">
      {isGroupware
        ? t('admin.console.people.source.groupware')
        : t('admin.console.people.source.manual')}
    </span>
  );
}

function UserWorkspaceBadges({ user }: { user: Pick<AuthUser, 'workspaces'> }) {
  const { t } = useTranslation('apps');
  if (user.workspaces.length === 0) {
    return <span className="text-app-ink/40">-</span>;
  }

  const workspaceItems = user.workspaces.map((workspace) => ({
    id: workspace.id,
    name: workspace.name,
    roleLabel: getWorkspaceRoleLabel(workspace.role, t),
  }));
  const tooltipLabel = workspaceItems
    .map((workspace) => `${workspace.name} · ${workspace.roleLabel}`)
    .join('\n');
  const tooltipContent = (
    <div className="min-w-40 max-w-64 space-y-1 py-0.5 text-left">
      {workspaceItems.map((workspace) => (
        <div
          className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3"
          key={workspace.id}
        >
          <span className="truncate">{workspace.name}</span>
          <span className="text-white/60">{workspace.roleLabel}</span>
        </div>
      ))}
    </div>
  );

  if (workspaceItems.length === 1) {
    return (
      <Tooltip content={tooltipContent}>
        <span
          aria-label={tooltipLabel}
          className="app-text-caption inline-flex max-w-[128px] items-center rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink/70 outline-none transition-colors hover:border-app-ink/25 focus-visible:ring-2 focus-visible:ring-app-accent/35"
          tabIndex={0}
        >
          <span className="truncate">{workspaceItems[0].name}</span>
        </span>
      </Tooltip>
    );
  }

  const hiddenWorkspaceCount = workspaceItems.length - 1;

  return (
    <Tooltip content={tooltipContent}>
      <span
        aria-label={tooltipLabel}
        className="app-text-caption inline-flex max-w-[144px] items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink/70 outline-none transition-colors hover:border-app-ink/25 focus-visible:ring-2 focus-visible:ring-app-accent/35"
        tabIndex={0}
      >
        <span className="min-w-0 truncate">{workspaceItems[0].name}</span>
        <span className="app-text-micro shrink-0 rounded border border-app-border bg-app-bg px-1.5 py-0.5 text-app-ink/55">
          {t('admin.console.people.workspaceMembershipMore', {
            count: hiddenWorkspaceCount,
          })}
        </span>
      </span>
    </Tooltip>
  );
}

function isGroupwareUser(user: AuthUser): boolean {
  return user.auth_provider === 'groupware';
}

function usePeopleSectionElement({ token }: { token: string }): ReactNode {
  const { t, i18n } = useTranslation('apps');
  const auth = useAuth();
  const navigate = useNavigate();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(auth.user?.time_zone);
  const directory = useAdminPeopleDirectoryController({
    token,
    messages: {
      directoryLoadFailed: t('admin.console.people.directoryLoadFailed'),
      userListLoadFailed: t('admin.console.people.userListLoadFailed'),
    },
  });
  const {
    error: directoryError,
    isLoadingUsers,
    orgUnits,
    page,
    pageSize,
    search,
    includeDescendants,
    includeInactiveOrgUnits,
    selectedOrgUnitId,
    totalUsers,
    users,
    workspaces,
  } = directory.state;
  const [inviteOpen, setInviteOpen] = useState(false);
  const [loginId, setLoginId] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [employeeCode, setEmployeeCode] = useState('');
  const [createOrgUnitId, setCreateOrgUnitId] = useState('');
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>(
    [],
  );
  const [selectedPlatformAdmin, setSelectedPlatformAdmin] = useState(false);
  const roleFilter: AdminPeopleRoleFilter = 'all';
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isCreatingUser, setIsCreatingUser] = useState(false);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editFullName, setEditFullName] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editEmployeeCode, setEditEmployeeCode] = useState('');
  const [editStatus, setEditStatus] = useState<
    'active' | 'invited' | 'suspended'
  >('active');
  const [editLoginBlocked, setEditLoginBlocked] = useState(false);
  const [editOrgUnitId, setEditOrgUnitId] = useState('');
  const [editPlatformAdmin, setEditPlatformAdmin] = useState(false);
  const [editWorkspaceIds, setEditWorkspaceIds] = useState<string[]>([]);
  const [isLoadingEditAccessContext, setIsLoadingEditAccessContext] =
    useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState<string | null>(null);
  const [impersonatingUserId, setImpersonatingUserId] = useState<string | null>(
    null,
  );
  const canImpersonateUsers = auth.hasPermission('user.impersonate');
  const availableWorkspaces = useMemo(
    () => activeWorkspaces(workspaces),
    [workspaces],
  );
  const peopleFormatter = useMemo<AdminPeopleFormatter>(
    () => ({
      role: {
        admin: t('admin.shared.roles.admin.label'),
        member: t('admin.shared.roles.member.label'),
      },
      status: (status) => formatStatusLabel(status, t),
      date: (value) => formatDateLabel(value, locale, timeZone),
      unassignedOrg: t('admin.console.people.unassignedOrg'),
    }),
    [locale, t, timeZone],
  );
  const orgUnitSelectOptions = useMemo(
    () => [
      {
        value: UNASSIGNED_ORG_UNIT_ID,
        label: t('admin.console.people.unassignedOrg'),
      },
      ...orgUnits
        .filter((item) => item.active)
        .map((item) => ({
          value: item.id,
          label: item.name,
        })),
    ],
    [orgUnits, t],
  );
  const peopleModel = useMemo(
    () =>
      buildAdminPeopleRows({
        users,
        total: totalUsers,
        page,
        pageSize,
        roleFilter,
        format: peopleFormatter,
      }),
    [page, pageSize, peopleFormatter, roleFilter, totalUsers, users],
  );
  const userAccessWorkflowPorts = useMemo<AdminUserAccessWorkflowPorts>(
    () => ({
      listWorkspaceBindings: (workspaceId) =>
        listWorkspaceBindings(token, workspaceId),
      replaceWorkspaceBindings: (workspaceId, payload) =>
        replaceWorkspaceBindings(token, workspaceId, payload),
    }),
    [token],
  );

  const editingUser = useMemo(
    () => users.find((user) => user.id === editingUserId) ?? null,
    [editingUserId, users],
  );

  async function loadEditAccessContext(user: AuthUser) {
    setIsLoadingEditAccessContext(true);
    try {
      const accessState = await loadAdminUserAccessWorkflow({
        userId: user.id,
        workspaces: availableWorkspaces,
        ports: userAccessWorkflowPorts,
      });
      setEditWorkspaceIds(accessState.directWorkspaceIds);
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.people.accessLoadFailed'),
        ),
      );
    } finally {
      setIsLoadingEditAccessContext(false);
    }
  }

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
    setCreateOrgUnitId(
      selectedOrgUnitId === UNASSIGNED_ORG_UNIT_ID
        ? UNASSIGNED_ORG_UNIT_ID
        : selectedOrgUnitId || orgUnits[0]?.id || UNASSIGNED_ORG_UNIT_ID,
    );
    setSelectedWorkspaceIds([]);
    setSelectedPlatformAdmin(false);
    setInviteOpen(true);
    requestAnimationFrame(() => {
      document.getElementById('admin-user-email')?.focus();
    });
  }

  function closeCreateUserDialog() {
    if (!isCreatingUser) {
      setInviteOpen(false);
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

    try {
      const response = await createAdminUser(token, {
        login_id: loginId.trim() || undefined,
        email: email.trim(),
        full_name: fullName.trim(),
        display_name: displayName.trim() || undefined,
        employee_code: employeeCode.trim() || undefined,
        primary_org_unit_id: orgUnitPayloadValue(createOrgUnitId),
        system_roles: selectedPlatformAdmin ? ['platform_admin'] : [],
      });
      await saveAdminUserAccessWorkflow({
        userId: response.user.id,
        workspaces: availableWorkspaces,
        directWorkspaceIds: selectedWorkspaceIds,
        ports: userAccessWorkflowPorts,
      });
      setLoginId('');
      setEmail('');
      setFullName('');
      setDisplayName('');
      setEmployeeCode('');
      setCreateOrgUnitId('');
      setSelectedWorkspaceIds([]);
      setSelectedPlatformAdmin(false);
      setInviteOpen(false);
      setMessage(
        t('admin.console.people.userCreated', {
          password: response.temporary_password,
        }),
      );
      await directory.actions.reloadDirectoryOptions();
      await reloadUsers(1);
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.people.userCreateFailed'),
        ),
      );
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

  async function handleImpersonateUser(user: AuthUser) {
    if (impersonatingUserId) {
      return;
    }

    setMessage(null);
    setError(null);
    setImpersonatingUserId(user.id);

    try {
      const session = await impersonateAdminUser(token, user.id);
      auth.switchSession(session);
      navigate('/', { replace: true });
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.people.impersonateFailed'),
        ),
      );
      setImpersonatingUserId(null);
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
    setInviteOpen(false);
    setEditingUserId(user.id);
    setEditFullName(user.full_name);
    setEditDisplayName(user.display_name);
    setEditEmployeeCode(user.employee_code ?? '');
    setEditStatus(
      user.status === 'invited' || user.status === 'suspended'
        ? user.status
        : 'active',
    );
    setEditLoginBlocked(Boolean(user.login_blocked));
    setEditOrgUnitId(user.primary_org_unit?.id ?? UNASSIGNED_ORG_UNIT_ID);
    setEditPlatformAdmin(user.system_roles.includes('platform_admin'));
    setEditWorkspaceIds([]);
    void loadEditAccessContext(user);
    requestAnimationFrame(() => {
      document.getElementById('admin-user-edit-full-name')?.focus();
    });
  }

  async function handleUpdateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingUserId || isLoadingEditAccessContext) {
      return;
    }

    setMessage(null);
    setError(null);
    setIsSavingUser(true);

    try {
      await Promise.all([
        updateAdminUser(token, editingUserId, {
          full_name: editFullName.trim(),
          display_name: editDisplayName.trim() || editFullName.trim(),
          employee_code: editEmployeeCode.trim() || null,
          primary_org_unit_id: orgUnitPayloadValue(editOrgUnitId),
          system_roles: editPlatformAdmin ? ['platform_admin'] : [],
          status: editStatus,
          login_blocked: editLoginBlocked,
        }),
        saveAdminUserAccessWorkflow({
          userId: editingUserId,
          workspaces: availableWorkspaces,
          directWorkspaceIds: editWorkspaceIds,
          ports: userAccessWorkflowPorts,
        }),
      ]);
      setEditingUserId(null);
      setMessage(t('admin.console.people.userSaved'));
      await reloadUsers(page);
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.people.userSaveFailed')),
      );
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
      const nextPage = nextAdminPeoplePageAfterDelete({
        currentPage: page,
        totalBeforeDelete: totalUsers,
        pageSize,
      });
      await reloadUsers(nextPage);
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
        loadPage: async ({ page: exportPage, pageSize }) => {
          const userResponse = await listAdminUsers(token, {
            page: exportPage,
            page_size: pageSize,
            q: search,
            org_unit_id: selectedOrgUnitId || undefined,
            include_descendants: includeDescendants,
          });
          return {
            items: userResponse.items,
            total: userResponse.total,
          };
        },
      });
      const rows = buildAdminPeopleExportRows({
        users: exportUsers,
        roleFilter,
        format: peopleFormatter,
      });
      const header: AdminPeopleExportHeader = [
        t('admin.console.people.columns.name'),
        t('admin.console.people.columns.email'),
        t('admin.console.people.columns.employeeCode'),
        t('admin.console.people.columns.org'),
        t('admin.console.people.columns.workspaces'),
        t('admin.console.people.columns.role'),
        t('admin.console.people.columns.status'),
        t('admin.console.people.columns.lastActive'),
        t('admin.console.people.columns.created'),
        t('admin.console.people.columns.enabledApps'),
      ];
      downloadBlobAsFile(
        new Blob([encodeAdminPeopleCsv({ header, rows })], {
          type: 'text/csv;charset=utf-8',
        }),
        'open-alm-people.csv',
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
    <div className="space-y-6">
      <SectionMessage error={error ?? directoryError} message={message} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-4">
        <ToolbarField className="min-w-[280px] max-w-md flex-1">
          <label className="relative block">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/55"
              size={16}
            />
            <input
              className="app-text-body w-full rounded-md border border-transparent bg-transparent py-1.5 pl-9 text-app-ink outline-none transition-colors hover:border-app-border focus:border-app-accent focus:bg-app-bg"
              onChange={(event) => {
                directory.actions.searchChanged(event.target.value);
              }}
              placeholder={t('admin.console.people.searchPlaceholder')}
              value={search}
            />
          </label>
        </ToolbarField>
        <div className="flex items-center gap-2">
          <button
            className="app-text-control rounded-md border border-transparent px-3 py-1.5 text-app-ink/55 transition-colors hover:border-app-border hover:bg-app-surface-hover hover:text-app-ink"
            disabled={isExporting || totalUsers === 0}
            onClick={() => {
              void handleExport();
            }}
            type="button"
          >
            {isExporting
              ? t('admin.console.people.exporting')
              : t('admin.console.people.export')}
          </button>
          <button
            className="app-text-control inline-flex items-center gap-1.5 rounded-md bg-app-ink px-3 py-1.5 text-app-bg transition-opacity hover:opacity-90 dark:bg-white dark:text-black"
            onClick={openCreateUserDialog}
            type="button"
          >
            <span>+</span>
            <span>{t('admin.console.people.createUser')}</span>
          </button>
        </div>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <OrgTreePanel
          includeDescendants={includeDescendants}
          includeInactiveOrgUnits={includeInactiveOrgUnits}
          onIncludeDescendantsChange={directory.actions.setIncludeDescendants}
          onIncludeInactiveOrgUnitsChange={
            directory.actions.setIncludeInactiveOrgUnits
          }
          onSelectOrgUnit={directory.actions.setSelectedOrgUnitId}
          orgUnits={orgUnits}
          selectedOrgUnitId={selectedOrgUnitId}
          totalUsers={totalUsers}
        />

        <div className="flex h-[calc(100vh-210px)] min-h-[520px] min-w-0 flex-col overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="app-text-control inline-flex items-center gap-1.5 rounded p-1 text-app-ink">
              <span>
                {t('admin.console.people.allUsers', { count: totalUsers })}
              </span>
              {isLoadingUsers ? (
                <span className="app-text-body text-app-ink/55">
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
                    {t('admin.console.people.pageSizeOption', {
                      count: option,
                    })}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="min-h-0 flex-1 overflow-auto border-t border-app-border">
            <table className="app-text-body-sm min-w-[1060px] w-full border-collapse">
              <thead>
                <tr className="sticky top-0 z-10 bg-app-surface-sidebar">
                  <HeadCell className="w-[250px]" dense>
                    {t('admin.console.people.columns.user')}
                  </HeadCell>
                  <HeadCell className="w-[130px]" dense>
                    {t('admin.console.people.columns.org')}
                  </HeadCell>
                  <HeadCell className="w-[95px]" dense>
                    {t('admin.console.people.columns.workspaces')}
                  </HeadCell>
                  <HeadCell className="w-[70px]" dense>
                    {t('admin.console.people.columns.role')}
                  </HeadCell>
                  <HeadCell className="w-[100px]" dense>
                    {t('admin.console.people.columns.status')}
                  </HeadCell>
                  <HeadCell className="w-[150px]" dense>
                    {t('admin.console.people.columns.enabledApps')}
                  </HeadCell>
                  <HeadCell className="w-[90px]" dense>
                    {t('admin.console.people.columns.lastActive')}
                  </HeadCell>
                  <HeadCell className="w-[90px]" dense>
                    {t('admin.console.people.columns.created')}
                  </HeadCell>
                  <HeadCell className="w-[72px] text-right" dense>
                    {t('admin.console.people.columns.actions')}
                  </HeadCell>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td
                    className="app-text-body-sm border-b border-app-border px-3 py-2 text-app-ink/55"
                    colSpan={9}
                  >
                    <button
                      className="transition-colors hover:text-app-ink"
                      onClick={openCreateUserDialog}
                      type="button"
                    >
                      {t('admin.console.people.createUserPrefix')}
                    </button>
                  </td>
                </tr>
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
                  peopleModel.rows.map((row) => (
                    <tr
                      className="transition-colors hover:bg-app-surface-hover/40"
                      key={row.id}
                    >
                      <BodyCell className="max-w-[250px]" dense>
                        <div className="min-w-0">
                          <div className="flex min-w-0 items-center gap-1.5">
                            <span className="truncate font-medium text-app-ink">
                              {row.name}
                            </span>
                            <UserSourceBadge user={row.user} />
                          </div>
                          <div className="app-text-caption mt-0.5 flex min-w-0 items-center gap-1.5 text-app-ink/55">
                            <span className="truncate">{row.loginId}</span>
                            <span className="text-app-ink/30">·</span>
                            <span className="truncate">{row.email}</span>
                          </div>
                          {row.employeeCode ? (
                            <div className="app-text-caption mt-0.5 flex min-w-0 items-center gap-1.5 text-app-ink/55">
                              <span className="shrink-0">
                                {t('admin.console.people.employeeCodeShort')}
                              </span>
                              <span className="truncate">
                                {row.employeeCode}
                              </span>
                            </div>
                          ) : null}
                        </div>
                      </BodyCell>
                      <BodyCell
                        className="max-w-[130px] truncate text-app-ink/55"
                        dense
                      >
                        {row.orgName}
                      </BodyCell>
                      <BodyCell className="whitespace-nowrap" dense>
                        <UserWorkspaceBadges user={row.user} />
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
                            <span className="app-text-caption rounded border border-app-warning-border px-1.5 py-0.5 text-app-warning-text dark:border-app-warning-border dark:text-app-warning-text">
                              {t('admin.console.people.loginBlockedBadge')}
                            </span>
                          ) : null}
                        </div>
                      </BodyCell>
                      <BodyCell
                        className="max-w-[150px] truncate text-app-ink/55"
                        dense
                      >
                        {row.appsLabel}
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
                              onSelect: () => {
                                void handleSetLoginBlocked(
                                  row.user,
                                  !row.user.login_blocked,
                                );
                              },
                            },
                            ...(canImpersonateUsers &&
                            row.user.id !== auth.user?.id
                              ? [
                                  {
                                    id: 'impersonate',
                                    label:
                                      impersonatingUserId === row.id
                                        ? t(
                                            'admin.console.people.impersonatingUser',
                                          )
                                        : t(
                                            'admin.console.people.impersonateUser',
                                          ),
                                    disabled:
                                      Boolean(impersonatingUserId) ||
                                      row.user.status !== 'active' ||
                                      row.user.login_blocked,
                                    separatorBefore: true,
                                    onSelect: () => {
                                      void handleImpersonateUser(row.user);
                                    },
                                  },
                                ]
                              : []),
                            ...(!isGroupwareUser(row.user)
                              ? [
                                  {
                                    id: 'reset',
                                    label: t(
                                      'admin.console.people.resetPassword',
                                    ),
                                    onSelect: () => {
                                      void handleResetPassword(row.id);
                                    },
                                  },
                                  {
                                    id: 'delete',
                                    label:
                                      deletingUserId === row.id
                                        ? t('admin.console.people.deletingUser')
                                        : t('admin.console.people.deleteUser'),
                                    disabled: deletingUserId === row.id,
                                    separatorBefore: true,
                                    tone: 'danger' as const,
                                    onSelect: () => {
                                      void handleDeleteUser(row.user);
                                    },
                                  },
                                ]
                              : []),
                          ]}
                          trigger={
                            <button
                              aria-label={t(
                                'admin.console.people.userActions',
                                {
                                  email: row.email,
                                },
                              )}
                              className="app-text-control-sm rounded-md border border-app-border px-2 py-0.5 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                              type="button"
                            >
                              {t('admin.console.people.more')}
                            </button>
                          }
                        />
                      </BodyCell>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 border-t border-app-border pt-3 sm:flex-row sm:items-center sm:justify-between sm:pr-20">
            <div className="app-text-body text-app-ink/55">
              {t('admin.console.people.range', {
                from: peopleModel.pagination.from,
                to: peopleModel.pagination.to,
                total: peopleModel.pagination.total,
              })}
            </div>
            <div className="flex items-center gap-2">
              <button
                className="app-text-control rounded-md border border-app-border px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!peopleModel.pagination.canPrevious || isLoadingUsers}
                onClick={() =>
                  directory.actions.setPage((current) =>
                    Math.max(1, current - 1),
                  )
                }
                type="button"
              >
                {t('admin.shared.pagination.previous')}
              </button>
              <span className="app-text-body min-w-20 text-center text-app-ink/55">
                {page} / {peopleModel.pagination.totalPages}
              </span>
              <button
                className="app-text-control rounded-md border border-app-border px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!peopleModel.pagination.canNext || isLoadingUsers}
                onClick={() =>
                  directory.actions.setPage((current) =>
                    Math.min(peopleModel.pagination.totalPages, current + 1),
                  )
                }
                type="button"
              >
                {t('admin.shared.pagination.next')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <Dialog
        closeLabel={t('common:actions.close')}
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
        description={t('admin.console.people.createDescription')}
        dismissOnInteractOutside={false}
        maxWidth="max-w-2xl"
        onOpenChange={(open) => {
          if (!open) closeCreateUserDialog();
        }}
        open={inviteOpen}
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
                  placeholder={t('admin.console.people.fullName')}
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
                  placeholder={t('admin.console.people.displayName')}
                  value={displayName}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.employeeCode')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={40}
                  onChange={(event) => setEmployeeCode(event.target.value)}
                  placeholder={t(
                    'admin.console.people.employeeCodePlaceholder',
                  )}
                  value={employeeCode}
                />
              </label>
              <div className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.orgUnit')}
                </span>
                <Select
                  onValueChange={setCreateOrgUnitId}
                  options={orgUnitSelectOptions}
                  value={createOrgUnitId}
                />
              </div>
            </div>
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
          <section className="border-t border-app-border pt-4">
            <WorkspaceMembershipPicker
              availableWorkspaces={availableWorkspaces}
              noAvailableWorkspacesLabel={t(
                'admin.console.people.noCreatableWorkspaces',
              )}
              onChange={setSelectedWorkspaceIds}
              selectedWorkspaceIds={selectedWorkspaceIds}
            />
          </section>
        </form>
      </Dialog>

      <Dialog
        closeLabel={t('common:actions.close')}
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
              disabled={isSavingUser || isLoadingEditAccessContext}
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
                  placeholder={t('admin.console.people.fullName')}
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
                  placeholder={t('admin.console.people.displayName')}
                  value={editDisplayName}
                />
              </label>
              <label className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.employeeCode')}
                </span>
                <input
                  className={fieldClassName}
                  maxLength={40}
                  onChange={(event) => setEditEmployeeCode(event.target.value)}
                  placeholder={t(
                    'admin.console.people.employeeCodePlaceholder',
                  )}
                  value={editEmployeeCode}
                />
              </label>
              <div className="grid gap-1">
                <span className="app-text-caption text-app-ink/55">
                  {t('admin.console.people.orgUnit')}
                </span>
                <Select
                  onValueChange={setEditOrgUnitId}
                  options={orgUnitSelectOptions}
                  value={editOrgUnitId}
                />
              </div>
            </div>
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
                disabled={isLoadingEditAccessContext}
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
          <section className="border-t border-app-border pt-4">
            <WorkspaceMembershipPicker
              availableWorkspaces={availableWorkspaces}
              disabled={isLoadingEditAccessContext}
              loading={isLoadingEditAccessContext}
              noAvailableWorkspacesLabel={t(
                'admin.console.people.noWorkspaces',
              )}
              onChange={setEditWorkspaceIds}
              selectedWorkspaceIds={editWorkspaceIds}
            />
          </section>
        </form>
      </Dialog>
    </div>
  );
}
