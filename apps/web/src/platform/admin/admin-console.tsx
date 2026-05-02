import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Search } from 'lucide-react';

import {
  Button,
  Dialog,
  DropdownMenu,
  InlineNotice,
  Select,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@aidoo/ui';

import {
  createAdminUser,
  createGroup,
  createWorkspace,
  deleteAdminUser,
  listAdminUsers,
  listAuditLogs,
  listGroups,
  listOrgUnits,
  listUserTeamMemberships,
  listTeams,
  listWorkspaceBindings,
  listWorkspaces,
  replaceGroupMembers,
  replaceGroupWorkspaceBindings,
  replaceWorkspaceBindings,
  resetUserPassword,
  updateGroup,
  updateAdminUser,
  type AccessGroupItem,
  type AuditLogItem,
  type OrgUnitItem,
  type TeamItem,
  type WorkspaceItem,
} from './admin-api';
import {
  Badge,
  FORM_FIELD_CLASS as fieldClassName,
  PEOPLE_EXPORT_PAGE_SIZE,
  PEOPLE_PAGE_SIZE,
  SectionMessage,
  SurfaceCard,
  UserWorkspaceChips,
  formatDateLabel,
  formatStatusLabel,
  formatUserApps,
  formatUserGroups,
  formatUserWorkspaces,
  getErrorMessage,
  isAdminUser,
} from './admin-shared';
import { WorkspaceDetailPanel } from './workspace-detail-panel';
import {
  hasAnyAdminReadPermission,
  type AdminSection,
} from './admin-permissions';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import { addSpaceMember, removeSpaceMember, updateSpaceMemberRole } from '@/src/app-modules/pms/public-api';
import { formatDateTime, normalizeTimeZone } from '@/src/platform/time/time-utils';

const NONE_OPTION_VALUE = '__none__';

const sectionMeta: Record<
  AdminSection,
  { titleKey: string; descriptionKey?: string; learnMoreLabelKey?: string }
> = {
  general: {
    titleKey: 'admin.console.sections.general.title',
    descriptionKey: 'admin.console.sections.general.description',
  },
  people: {
    titleKey: 'admin.console.sections.people.title',
    learnMoreLabelKey: 'admin.console.sections.people.learnMore',
  },
  workspaces: {
    titleKey: 'admin.console.sections.workspaces.title',
    descriptionKey: 'admin.console.sections.workspaces.description',
  },
  security: {
    titleKey: 'admin.console.sections.security.title',
    descriptionKey: 'admin.console.sections.security.description',
  },
  audit: {
    titleKey: 'admin.console.sections.audit.title',
    descriptionKey: 'admin.console.sections.audit.description',
  },
};

function formatGroupWorkspaceBindings(group: Pick<AccessGroupItem, 'workspace_bindings'>): string {
  return group.workspace_bindings.map((binding) => binding.workspace_name).join(', ') || '-';
}

function SettingsShell({
  section,
  children,
  actions,
}: {
  section: AdminSection;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const { t } = useTranslation('apps');
  const meta = sectionMeta[section];
  const description = meta.descriptionKey ? t(meta.descriptionKey) : '';

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 border-b border-app-border pb-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="app-text-title-lg text-app-ink">{t(meta.titleKey)}</h1>
              {meta.learnMoreLabelKey ? (
                <button className="app-text-control-sm text-app-accent hover:underline" type="button">
                  {t(meta.learnMoreLabelKey)}
                </button>
              ) : null}
            </div>
            {description ? <p className="app-text-body max-w-3xl text-gray-500">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-3">{actions}</div> : null}
        </header>
        {children}
      </div>
    </div>
  );
}

function ToolbarField({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`min-w-0 ${className}`.trim()}>{children}</div>;
}

function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto w-full">
      <table className="app-text-body min-w-full border-collapse">{children}</table>
    </div>
  );
}

function HeadCell({
  children,
  className = '',
  dense = false,
}: {
  children: React.ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <th
      className={`app-text-overline border-b border-app-border text-left text-gray-500 ${
        dense ? 'px-3 py-2' : 'px-4 py-3'
      } ${className}`.trim()}
    >
      {children}
    </th>
  );
}

function BodyCell({
  children,
  className = '',
  dense = false,
}: {
  children: React.ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <td
      className={`border-b border-app-border text-app-ink ${
        dense ? 'app-text-body-sm px-3 py-2 align-middle' : 'app-text-body px-4 py-3 align-top'
      } ${className}`.trim()}
    >
      {children}
    </td>
  );
}

function EmptyRow({
  colSpan,
  title,
  description,
}: {
  colSpan: number;
  title: string;
  description: string;
}) {
  return (
    <tr>
      <td className="px-3 py-10 text-center" colSpan={colSpan}>
        <div className="space-y-1">
          <div className="app-text-body font-medium text-app-ink">{title}</div>
          <div className="app-text-body text-gray-500">{description}</div>
        </div>
      </td>
    </tr>
  );
}

function GeneralSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const auth = useAuth();
  const [summary, setSummary] = useState({
    userCount: null as number | null,
    adminCount: null as number | null,
    groupCount: null as number | null,
    workspaceCount: null as number | null,
    teamCount: null as number | null,
    auditCount: null as number | null,
  });
  const [error, setError] = useState<string | null>(null);
  const canReadUsers = auth.hasPermission('user.read');
  const canReadGroups = auth.hasPermission('group.read');
  const canReadWorkspaces = auth.hasPermission('workspace.read');
  const canReadTeams = auth.hasPermission('team.read');
  const canReadAudit = auth.hasPermission('audit.read');

  function formatCount(value: number | null) {
    return value ?? t('admin.console.general.restricted');
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [users, groups, workspaces, teams, audits] = await Promise.all([
          canReadUsers ? listAdminUsers(token, { page_size: 100 }) : Promise.resolve(null),
          canReadGroups ? listGroups(token) : Promise.resolve(null),
          canReadWorkspaces ? listWorkspaces(token) : Promise.resolve(null),
          canReadTeams ? listTeams(token) : Promise.resolve(null),
          canReadAudit ? listAuditLogs(token) : Promise.resolve(null),
        ]);
        if (cancelled) {
          return;
        }
        setSummary({
          userCount: users?.total ?? null,
          adminCount: users?.items.filter((item) => isAdminUser(item)).length ?? null,
          groupCount: groups?.length ?? null,
          workspaceCount: workspaces?.length ?? null,
          teamCount: teams?.length ?? null,
          auditCount: audits?.length ?? null,
        });
      } catch (caughtError) {
        if (!cancelled) {
          setError(getErrorMessage(caughtError, t('admin.console.general.summaryLoadFailed')));
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [
    canReadAudit,
    canReadGroups,
    canReadTeams,
    canReadUsers,
    canReadWorkspaces,
    token,
  ]);

  return (
    <div className="space-y-6">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}



      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SurfaceCard
	          title={t('admin.console.general.operatingModelTitle')}
	          description={t('admin.console.general.operatingModelDescription')}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
	              <div className="app-text-title-md text-app-ink">{t('admin.console.general.identityTitle')}</div>
	                <div className="app-text-body mt-3 space-y-2 text-gray-500">
	                <div>{t('admin.console.general.userCount', { count: formatCount(summary.userCount), suffix: summary.userCount !== null ? t('admin.console.units.count') : '' })}</div>
	                <div>{t('admin.console.general.adminCount', { count: formatCount(summary.adminCount), suffix: summary.adminCount !== null ? t('admin.console.units.people') : '' })}</div>
	                <div>{t('admin.console.general.groupCount', { count: formatCount(summary.groupCount), suffix: summary.groupCount !== null ? t('admin.console.units.count') : '' })}</div>
	              </div>
	            </div>
	            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
	              <div className="app-text-title-md text-app-ink">{t('admin.console.general.workModelTitle')}</div>
	              <div className="app-text-body mt-3 space-y-2 text-gray-500">
	                <div>{t('admin.console.general.workspaceCount', { count: formatCount(summary.workspaceCount), suffix: summary.workspaceCount !== null ? t('admin.console.units.count') : '' })}</div>
	                <div>{t('admin.console.general.teamCount', { count: formatCount(summary.teamCount), suffix: summary.teamCount !== null ? t('admin.console.units.count') : '' })}</div>
	              </div>
	            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard
	          title={t('admin.console.general.notesTitle')}
	          description={t('admin.console.general.notesDescription')}
        >
          <div className="app-text-body space-y-3 text-gray-500">
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
	              {t('admin.console.general.noteProfile')}
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
	              {t('admin.console.general.noteNavigation')}
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
	              {t('admin.console.general.noteAudit')}
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  );
}

function PeopleSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [page, setPage] = useState(1);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [orgUnits, setOrgUnits] = useState<OrgUnitItem[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [allSpaces, setAllSpaces] = useState<TeamItem[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter] = useState<'all' | 'admin' | 'member'>('all');
  const [selectedOrgUnitId, setSelectedOrgUnitId] = useState('');
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isCreatingUser, setIsCreatingUser] = useState(false);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editFullName, setEditFullName] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editStatus, setEditStatus] = useState<'active' | 'invited' | 'suspended'>('active');
  const [editOrgUnitId, setEditOrgUnitId] = useState('');
  const [editGroupIds, setEditGroupIds] = useState<string[]>([]);
  const [editWorkspaceIds, setEditWorkspaceIds] = useState<string[]>([]);
  const [editPmsSpaces, setEditPmsSpaces] = useState<
    Array<{
      id: string;
      workspace_id: string;
      workspace_key: string;
      workspace_name: string;
      name: string;
      role: string;
      description: string;
    }>
  >([]);
  const [initialEditPmsSpaces, setInitialEditPmsSpaces] = useState<
    Array<{
      id: string;
      workspace_id: string;
      workspace_key: string;
      workspace_name: string;
      name: string;
      role: string;
      description: string;
    }>
  >([]);
  const [selectedPmsSpaceId, setSelectedPmsSpaceId] = useState('');
  const [selectedPmsSpaceRole, setSelectedPmsSpaceRole] = useState('member');
  const [isLoadingEditAccessContext, setIsLoadingEditAccessContext] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState<string | null>(null);
  const availableWorkspaces = useMemo(
    () => workspaces.filter((workspace) => workspace.active),
    [workspaces],
  );
  const workspaceById = useMemo(
    () => new Map(workspaces.map((workspace) => [workspace.id, workspace])),
    [workspaces],
  );
  const availablePmsSpaces = useMemo(
    () =>
      allSpaces
        .filter((space) => !editPmsSpaces.some((item) => item.id === space.id))
        .sort((left, right) => {
          const leftWorkspaceName = workspaceById.get(left.workspace_id)?.name ?? left.workspace_key;
          const rightWorkspaceName = workspaceById.get(right.workspace_id)?.name ?? right.workspace_key;
          if (leftWorkspaceName !== rightWorkspaceName) {
            return leftWorkspaceName.localeCompare(rightWorkspaceName, locale);
          }
          return left.name.localeCompare(right.name, locale);
        }),
    [allSpaces, editPmsSpaces, workspaceById, locale],
  );
  const totalPages = Math.max(1, Math.ceil(totalUsers / PEOPLE_PAGE_SIZE));
  const firstVisibleUser = totalUsers === 0 ? 0 : (page - 1) * PEOPLE_PAGE_SIZE + 1;
  const lastVisibleUser = Math.min(totalUsers, (page - 1) * PEOPLE_PAGE_SIZE + users.length);
  const selectedGroupWorkspaceIds = useMemo(
    () => Array.from(
      new Set(
        groups
          .filter((group) => selectedGroupIds.includes(group.id))
          .flatMap((group) => group.workspace_bindings.map((binding) => binding.workspace_id)),
      ),
    ),
    [groups, selectedGroupIds],
  );
  const effectiveCreateWorkspaceIds = useMemo(
    () => Array.from(new Set([...selectedWorkspaceIds, ...selectedGroupWorkspaceIds])),
    [selectedGroupWorkspaceIds, selectedWorkspaceIds],
  );
  const selectedWorkspaceAppSummary = useMemo(
    () =>
      availableWorkspaces
        .filter((workspace) => effectiveCreateWorkspaceIds.includes(workspace.id))
        .map((workspace) => workspace.name)
        .join(', ') || '-',
    [availableWorkspaces, effectiveCreateWorkspaceIds],
  );
  const editInheritedWorkspaceIds = useMemo(
    () => Array.from(
      new Set(
        groups
          .filter((group) => editGroupIds.includes(group.id))
          .flatMap((group) => group.workspace_bindings.map((binding) => binding.workspace_id))
          .filter((workspaceId) => !editWorkspaceIds.includes(workspaceId)),
      ),
    ),
    [editGroupIds, editWorkspaceIds, groups],
  );
  const effectiveEditWorkspaceIds = useMemo(
    () => Array.from(new Set([...editWorkspaceIds, ...editInheritedWorkspaceIds])),
    [editInheritedWorkspaceIds, editWorkspaceIds],
  );
  const editWorkspaceAppSummary = useMemo(
    () =>
      availableWorkspaces
        .filter((workspace) => effectiveEditWorkspaceIds.includes(workspace.id))
        .map((workspace) => workspace.name)
        .join(', ') || '-',
    [availableWorkspaces, effectiveEditWorkspaceIds],
  );
  const selectedPmsSpace = useMemo(
    () => allSpaces.find((space) => space.id === selectedPmsSpaceId) ?? null,
    [allSpaces, selectedPmsSpaceId],
  );

  async function loadDirectoryOptions() {
    try {
      const [groupItems, orgUnitItems, workspaceItems, spaceItems] = await Promise.all([
        listGroups(token),
        listOrgUnits(token),
        listWorkspaces(token),
        listTeams(token),
      ]);
      setGroups(groupItems);
      setOrgUnits(orgUnitItems);
      setWorkspaces(workspaceItems);
      setAllSpaces(spaceItems);
      setSelectedOrgUnitId((current) => current || orgUnitItems[0]?.id || '');
      setSelectedGroupIds((current) => current.filter((groupId) => groupItems.some((item) => item.id === groupId)));
      setEditGroupIds((current) => current.filter((groupId) => groupItems.some((item) => item.id === groupId)));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.directoryLoadFailed')));
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [groupItems, orgUnitItems, workspaceItems, spaceItems] = await Promise.all([
          listGroups(token),
          listOrgUnits(token),
          listWorkspaces(token),
          listTeams(token),
        ]);
        if (cancelled) {
          return;
        }
        setGroups(groupItems);
        setOrgUnits(orgUnitItems);
        setWorkspaces(workspaceItems);
        setAllSpaces(spaceItems);
        setSelectedOrgUnitId((current) => current || orgUnitItems[0]?.id || '');
        setSelectedGroupIds((current) => current.filter((groupId) => groupItems.some((item) => item.id === groupId)));
        setEditGroupIds((current) => current.filter((groupId) => groupItems.some((item) => item.id === groupId)));
      } catch (caughtError) {
        if (!cancelled) {
          setError(getErrorMessage(caughtError, t('admin.console.people.directoryLoadFailed')));
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [token, t]);

  useEffect(() => {
    let cancelled = false;
    const handle = window.setTimeout(() => {
      async function load() {
        setIsLoadingUsers(true);
        try {
          const userResponse = await listAdminUsers(token, {
            page,
            page_size: PEOPLE_PAGE_SIZE,
            q: search,
          });
          if (cancelled) {
            return;
          }
          setUsers(userResponse.items);
          setTotalUsers(userResponse.total);
        } catch (caughtError) {
          if (!cancelled) {
            setError(getErrorMessage(caughtError, t('admin.console.people.userListLoadFailed')));
          }
        } finally {
          if (!cancelled) {
            setIsLoadingUsers(false);
          }
        }
      }

      void load();
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [page, search, token, t]);

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const matchesRole =
        roleFilter === 'all' ||
        (roleFilter === 'admin' ? isAdminUser(user) : !isAdminUser(user));

      return matchesRole;
    });
  }, [roleFilter, users]);
  const editingUser = useMemo(
    () => users.find((user) => user.id === editingUserId) ?? null,
    [editingUserId, users],
  );

  function toggleWorkspaceSelection(
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    workspaceId: string,
  ) {
    setter((current) =>
      current.includes(workspaceId)
        ? current.filter((item) => item !== workspaceId)
        : [...current, workspaceId],
    );
  }

  async function syncUserWorkspaceMemberships(userId: string, selectedWorkspaceIds: string[]) {
    const selectedIds = new Set(selectedWorkspaceIds);
    for (const workspace of availableWorkspaces) {
      const bindings = await listWorkspaceBindings(token, workspace.id);
      const existingUserBinding = bindings.find(
        (binding) => binding.subject_type === 'user' && binding.subject_id === userId,
      );
      const nextUsers = bindings
        .filter((binding) => binding.subject_type === 'user' && binding.subject_id !== userId)
        .map((binding) => ({ subject_id: binding.subject_id, role: binding.role }));

      if (selectedIds.has(workspace.id)) {
        nextUsers.push({
          subject_id: userId,
          role: existingUserBinding?.role ?? 'member',
        });
      }

      const nextGroups = bindings
        .filter((binding) => binding.subject_type === 'group')
        .map((binding) => ({ subject_id: binding.subject_id, role: binding.role }));

      await replaceWorkspaceBindings(token, workspace.id, {
        users: nextUsers,
        groups: nextGroups,
      });
    }
  }

  function sortPmsSpaces(
    spaces: Array<{
      id: string;
      workspace_id: string;
      workspace_key: string;
      workspace_name: string;
      name: string;
      role: string;
      description: string;
    }>,
  ) {
    return [...spaces].sort((left, right) => {
      if (left.workspace_name !== right.workspace_name) {
        return left.workspace_name.localeCompare(right.workspace_name, locale);
      }
      return left.name.localeCompare(right.name, locale);
    });
  }

  function stageAddPmsSpace() {
    if (!selectedPmsSpace) {
      return;
    }

    setEditPmsSpaces((current) =>
      sortPmsSpaces([
        ...current,
        {
          id: selectedPmsSpace.id,
          workspace_id: selectedPmsSpace.workspace_id,
          workspace_key: selectedPmsSpace.workspace_key,
          workspace_name: workspaceById.get(selectedPmsSpace.workspace_id)?.name ?? selectedPmsSpace.workspace_key,
          name: selectedPmsSpace.name,
          role: selectedPmsSpaceRole,
          description: selectedPmsSpace.description,
        },
      ]),
    );
    if (!effectiveEditWorkspaceIds.includes(selectedPmsSpace.workspace_id)) {
      setEditWorkspaceIds((current) => Array.from(new Set([...current, selectedPmsSpace.workspace_id])));
    }
    setSelectedPmsSpaceId('');
    setSelectedPmsSpaceRole('member');
  }

  function stageUpdatePmsSpaceRole(spaceId: string, role: string) {
    setEditPmsSpaces((current) =>
      current.map((space) => (space.id === spaceId ? { ...space, role } : space)),
    );
  }

  function stageRemovePmsSpace(spaceId: string) {
    setEditPmsSpaces((current) => current.filter((space) => space.id !== spaceId));
  }

  async function syncUserPmsSpaces(userId: string) {
    const initialById = new Map(initialEditPmsSpaces.map((space) => [space.id, space]));
    const nextById = new Map(editPmsSpaces.map((space) => [space.id, space]));

    for (const [spaceId, initialSpace] of initialById) {
      if (!nextById.has(spaceId)) {
        await removeSpaceMember(token, spaceId, userId, initialSpace.workspace_key);
      }
    }

    for (const [spaceId, nextSpace] of nextById) {
      const initialSpace = initialById.get(spaceId);
      if (!initialSpace) {
        await addSpaceMember(
          token,
          spaceId,
          {
            user_id: userId,
            role: nextSpace.role,
          },
          nextSpace.workspace_key,
        );
        continue;
      }
      if (initialSpace.role !== nextSpace.role) {
        await updateSpaceMemberRole(token, spaceId, userId, nextSpace.role, nextSpace.workspace_key);
      }
    }
  }

  async function loadEditAccessContext(user: AuthUser) {
    setIsLoadingEditAccessContext(true);
    try {
      const bindingResults = await Promise.all(
        availableWorkspaces.map(async (workspace) => ({
          workspace,
          bindings: await listWorkspaceBindings(token, workspace.id),
        })),
      );
      const directWorkspaceIds: string[] = [];

      for (const { workspace, bindings } of bindingResults) {
        const hasDirectBinding = bindings.some(
          (binding) => binding.subject_type === 'user' && binding.subject_id === user.id,
        );
        if (hasDirectBinding) {
          directWorkspaceIds.push(workspace.id);
        }
      }

      setEditWorkspaceIds(directWorkspaceIds);

      const pmsSpaces = await listUserTeamMemberships(token, user.id);
      const nextPmsSpaces = sortPmsSpaces(
        pmsSpaces.map((space) => ({
          id: space.id,
          workspace_id: space.workspace_id,
          workspace_key: space.workspace_key,
          workspace_name: space.workspace_name,
          name: space.name,
          role: space.role,
          description: space.description,
        })),
      );
      setEditPmsSpaces(nextPmsSpaces);
      setInitialEditPmsSpaces(nextPmsSpaces);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.accessLoadFailed')));
    } finally {
      setIsLoadingEditAccessContext(false);
    }
  }

  async function reloadUsers(nextPage: number) {
    setIsLoadingUsers(true);
    try {
      const userResponse = await listAdminUsers(token, {
        page: nextPage,
        page_size: PEOPLE_PAGE_SIZE,
        q: search,
      });
      setUsers(userResponse.items);
      setTotalUsers(userResponse.total);
      setPage(userResponse.page);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.userListLoadFailed')));
    } finally {
      setIsLoadingUsers(false);
    }
  }

  function openCreateUserDialog() {
    setMessage(null);
    setError(null);
    setEditingUserId(null);
    setEmail('');
    setFullName('');
    setDisplayName('');
    setSelectedWorkspaceIds([]);
    setSelectedGroupIds([]);
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
        email: email.trim(),
        full_name: fullName.trim(),
        display_name: displayName.trim() || undefined,
        primary_org_unit_id: selectedOrgUnitId || undefined,
        group_ids: selectedGroupIds,
      });
      await syncUserWorkspaceMemberships(response.user.id, selectedWorkspaceIds);
      setEmail('');
      setFullName('');
      setDisplayName('');
      setSelectedWorkspaceIds([]);
      setSelectedGroupIds([]);
      setInviteOpen(false);
      setMessage(t('admin.console.people.userCreated', { password: response.temporary_password }));
      await loadDirectoryOptions();
      await reloadUsers(1);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.userCreateFailed')));
    } finally {
      setIsCreatingUser(false);
    }
  }

  async function handleResetPassword(userId: string) {
    setMessage(null);
    setError(null);

    try {
      const response = await resetUserPassword(token, userId);
      setMessage(t('admin.console.people.passwordReset', { password: response.temporary_password }));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.passwordResetFailed')));
    }
  }

  function startEditUser(user: AuthUser) {
    setMessage(null);
    setError(null);
    setInviteOpen(false);
    setEditingUserId(user.id);
    setEditFullName(user.full_name);
    setEditDisplayName(user.display_name);
    setEditStatus(
      user.status === 'invited' || user.status === 'suspended' ? user.status : 'active',
    );
    setEditOrgUnitId(user.primary_org_unit?.id ?? orgUnits[0]?.id ?? '');
    setEditGroupIds(user.group_ids);
    setEditWorkspaceIds([]);
    setEditPmsSpaces([]);
    setInitialEditPmsSpaces([]);
    setSelectedPmsSpaceId('');
    setSelectedPmsSpaceRole('member');
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
      const requiredDirectWorkspaceIds = Array.from(
        new Set(
          editPmsSpaces
            .map((space) => space.workspace_id)
            .filter((workspaceId) => !editInheritedWorkspaceIds.includes(workspaceId)),
        ),
      );
      const nextDirectWorkspaceIds = Array.from(
        new Set([...editWorkspaceIds, ...requiredDirectWorkspaceIds]),
      );
      await updateAdminUser(token, editingUserId, {
        full_name: editFullName.trim(),
        display_name: editDisplayName.trim() || editFullName.trim(),
        primary_org_unit_id: editOrgUnitId || undefined,
        group_ids: editGroupIds,
        status: editStatus,
      });
      await syncUserWorkspaceMemberships(editingUserId, nextDirectWorkspaceIds);
      await syncUserPmsSpaces(editingUserId);
      setEditingUserId(null);
      setMessage(t('admin.console.people.userSaved'));
      await reloadUsers(page);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.userSaveFailed')));
    } finally {
      setIsSavingUser(false);
    }
  }

  async function handleDeleteUser(user: AuthUser) {
    if (!window.confirm(t('admin.console.people.deleteConfirm', { email: user.email }))) {
      return;
    }

    setMessage(null);
    setError(null);
    setDeletingUserId(user.id);

    try {
      await deleteAdminUser(token, user.id);
      setEditingUserId((current) => (current === user.id ? null : current));
      setMessage(t('admin.console.people.userDeleted', { email: user.email }));
      const nextTotal = Math.max(0, totalUsers - 1);
      const nextPage = Math.min(page, Math.max(1, Math.ceil(nextTotal / PEOPLE_PAGE_SIZE)));
      await reloadUsers(nextPage);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.userDeleteFailed')));
    } finally {
      setDeletingUserId(null);
    }
  }

  async function handleExport() {
    setIsExporting(true);
    setError(null);
    try {
      const exportUsers: AuthUser[] = [];
      let nextPage = 1;
      let total = 0;
      let received = 0;

      do {
        const userResponse = await listAdminUsers(token, {
          page: nextPage,
          page_size: PEOPLE_EXPORT_PAGE_SIZE,
          q: search,
        });
        exportUsers.push(...userResponse.items);
        total = userResponse.total;
        received = userResponse.items.length;
        nextPage += 1;
      } while (received > 0 && exportUsers.length < total);

      const rows = exportUsers
        .filter((user) => {
          return roleFilter === 'all' || (roleFilter === 'admin' ? isAdminUser(user) : !isAdminUser(user));
        })
        .map((user) => [
          user.display_name || user.full_name,
          user.email,
          user.primary_org_unit?.name ?? '-',
          formatUserGroups(user),
          formatUserWorkspaces(user),
          isAdminUser(user) ? t('admin.shared.roles.admin.label') : t('admin.shared.roles.member.label'),
          formatStatusLabel(user.status, t),
          formatDateLabel(user.last_login_at, locale),
          formatDateLabel(user.created_at, locale),
          formatUserApps(user),
        ]);

      const header = [
        t('admin.console.people.columns.name'),
        t('admin.console.people.columns.email'),
        t('admin.console.people.columns.org'),
        t('admin.console.people.columns.groups'),
        t('admin.console.people.columns.workspaces'),
        t('admin.console.people.columns.role'),
        t('admin.console.people.columns.status'),
        t('admin.console.people.columns.lastActive'),
        t('admin.console.people.columns.created'),
        t('admin.console.people.columns.enabledApps'),
      ];
      const csv = [header, ...rows]
        .map((row) =>
          row
            .map((item) => `"${String(item).replaceAll('"', '""')}"`)
            .join(','),
        )
        .join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'aidoo-people.csv';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.people.exportFailed')));
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionMessage error={error} message={message} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-4">
        <ToolbarField className="min-w-[280px] max-w-md flex-1">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
            <input
              className="app-text-body w-full rounded-md border border-transparent bg-transparent py-1.5 pl-9 text-app-ink outline-none transition-colors hover:border-app-border focus:border-app-accent focus:bg-app-bg"
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder={t('admin.console.people.searchPlaceholder')}
              value={search}
            />
          </label>
        </ToolbarField>
        <div className="flex items-center gap-2">
          <button
            className="app-text-control rounded-md border border-transparent px-3 py-1.5 text-gray-500 transition-colors hover:border-app-border hover:bg-app-surface-hover hover:text-app-ink"
            disabled={isExporting || totalUsers === 0}
            onClick={() => {
              void handleExport();
            }}
            type="button"
          >
            {isExporting ? t('admin.console.people.exporting') : t('admin.console.people.export')}
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

      <div className="flex items-center gap-2 py-2">
        <button
          className="app-text-control inline-flex items-center gap-1.5 rounded p-1 text-app-ink hover:bg-app-surface-hover"
          type="button"
        >
          <span>{t('admin.console.people.allUsers', { count: totalUsers })}</span>
          <span className="app-text-micro text-gray-500">▾</span>
        </button>
        {isLoadingUsers ? <span className="app-text-body text-gray-500">{t('common:feedback.loading')}</span> : null}
      </div>

      <div className="w-full overflow-x-auto">
        <table className="app-text-body-sm min-w-[1380px] w-full border-collapse">
          <thead>
            <tr className="bg-app-surface-sidebar/40">
              <HeadCell className="w-[270px]" dense>{t('admin.console.people.columns.user')}</HeadCell>
              <HeadCell className="w-[150px]" dense>{t('admin.console.people.columns.org')}</HeadCell>
              <HeadCell className="w-[150px]" dense>{t('admin.console.people.columns.groups')}</HeadCell>
              <HeadCell className="w-[220px]" dense>{t('admin.console.people.columns.workspaces')}</HeadCell>
              <HeadCell className="w-[90px]" dense>{t('admin.console.people.columns.role')}</HeadCell>
              <HeadCell className="w-[100px]" dense>{t('admin.console.people.columns.status')}</HeadCell>
              <HeadCell className="w-[220px]" dense>{t('admin.console.people.columns.enabledApps')}</HeadCell>
              <HeadCell className="w-[110px]" dense>{t('admin.console.people.columns.lastActive')}</HeadCell>
              <HeadCell className="w-[110px]" dense>{t('admin.console.people.columns.created')}</HeadCell>
              <HeadCell className="w-[72px] text-right" dense>{t('admin.console.people.columns.actions')}</HeadCell>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="app-text-body-sm border-b border-app-border px-3 py-2 text-gray-500" colSpan={10}>
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
                colSpan={10}
	                description={t('admin.console.people.loadingDescription')}
	                title={t('admin.console.people.loadingTitle')}
              />
            ) : filteredUsers.length === 0 ? (
              <EmptyRow
                colSpan={10}
	                description={t('admin.console.people.emptyDescription')}
	                title={t('admin.console.people.emptyTitle')}
              />
            ) : (
              filteredUsers.map((user) => (
                <tr className="transition-colors hover:bg-app-surface-hover/40" key={user.id}>
                  <BodyCell dense>
                    <div className="min-w-0">
                      <span className="font-medium text-app-ink">
                        {user.display_name || user.full_name}
                      </span>
                      <span className="ml-2 text-gray-500">{user.email}</span>
                    </div>
                  </BodyCell>
                  <BodyCell className="max-w-[150px] truncate text-gray-500" dense>
                    {user.primary_org_unit?.name ?? '-'}
                  </BodyCell>
                  <BodyCell className="max-w-[150px] truncate text-gray-500" dense>
                    {formatUserGroups(user)}
                  </BodyCell>
                  <BodyCell className="max-w-[260px]" dense>
                    <UserWorkspaceChips user={user} />
                  </BodyCell>
	                  <BodyCell dense>{isAdminUser(user) ? t('admin.shared.roles.admin.label') : t('admin.shared.roles.member.label')}</BodyCell>
                  <BodyCell dense>
                    <span className="rounded border border-app-border px-1.5 py-0.5 text-gray-500">
	                      {formatStatusLabel(user.status, t)}
                    </span>
                  </BodyCell>
                  <BodyCell className="max-w-[220px] truncate text-gray-500" dense>
                    {formatUserApps(user)}
                  </BodyCell>
	                  <BodyCell className="text-gray-500" dense>{formatDateLabel(user.last_login_at, locale)}</BodyCell>
	                  <BodyCell className="text-gray-500" dense>{formatDateLabel(user.created_at, locale)}</BodyCell>
                  <BodyCell className="text-right" dense>
                    <DropdownMenu
                      items={[
                        {
                          id: 'edit',
	                          label: t('admin.console.people.editUser'),
                          onSelect: () => startEditUser(user),
                        },
                        {
                          id: 'reset',
	                          label: t('admin.console.people.resetPassword'),
                          onSelect: () => {
                            void handleResetPassword(user.id);
                          },
                        },
                        {
                          id: 'delete',
	                          label: deletingUserId === user.id ? t('admin.console.people.deletingUser') : t('admin.console.people.deleteUser'),
                          disabled: deletingUserId === user.id,
                          separatorBefore: true,
                          tone: 'danger',
                          onSelect: () => {
                            void handleDeleteUser(user);
                          },
                        },
                      ]}
                      trigger={
                        <button
	                          aria-label={t('admin.console.people.userActions', { email: user.email })}
                          className="app-text-control rounded-md border border-app-border px-2 py-1 text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
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

      <div className="flex flex-col gap-3 border-t border-app-border pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="app-text-body text-gray-500">
	          {t('admin.console.people.range', { from: firstVisibleUser, to: lastVisibleUser, total: totalUsers })}
        </div>
        <div className="flex items-center gap-2">
          <button
            className="app-text-control rounded-md border border-app-border px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
            disabled={page <= 1 || isLoadingUsers}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            type="button"
          >
	            {t('admin.shared.pagination.previous')}
          </button>
          <span className="app-text-body min-w-20 text-center text-gray-500">
            {page} / {totalPages}
          </span>
          <button
            className="app-text-control rounded-md border border-app-border px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
            disabled={page >= totalPages || isLoadingUsers}
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            type="button"
          >
	            {t('admin.shared.pagination.next')}
          </button>
        </div>
      </div>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button disabled={isCreatingUser} onClick={closeCreateUserDialog} variant="secondary">
	              {t('common:actions.cancel')}
            </Button>
            <Button disabled={isCreatingUser} form="admin-user-create-form" type="submit" variant="primary">
	              {isCreatingUser ? t('admin.console.people.creating') : t('common:actions.create')}
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
        <form className="grid gap-4" id="admin-user-create-form" onSubmit={(event) => void handleCreateUser(event)}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.email')}</span>
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
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.fullName')}</span>
              <input
                className={fieldClassName}
                onChange={(event) => setFullName(event.target.value)}
	                placeholder={t('admin.console.people.fullName')}
                required
                value={fullName}
              />
            </label>
            <label className="grid gap-1">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.displayName')}</span>
              <input
                className={fieldClassName}
                onChange={(event) => setDisplayName(event.target.value)}
	                placeholder={t('admin.console.people.displayName')}
                value={displayName}
              />
            </label>
            <div className="grid gap-1">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.orgUnit')}</span>
              <Select
                onValueChange={setSelectedOrgUnitId}
                options={orgUnits.map((item) => ({ value: item.id, label: item.name }))}
                value={selectedOrgUnitId}
              />
            </div>
            <div className="grid gap-2 md:col-span-2">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.columns.groups')}</span>
              {groups.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                  {t('admin.console.people.noGroups')}
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {groups.map((group) => (
                    <label
                      className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                      key={group.id}
                    >
                      <input
                        checked={selectedGroupIds.includes(group.id)}
                        onChange={() => toggleWorkspaceSelection(setSelectedGroupIds, group.id)}
                        type="checkbox"
                      />
                      <span>{group.name}</span>
                      <span className="app-text-caption text-gray-500">
                        {formatGroupWorkspaceBindings(group)}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="grid gap-2">
	            <div className="app-text-caption text-gray-500">{t('admin.console.people.directWorkspaces')}</div>
            {availableWorkspaces.length === 0 ? (
              <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                {t('admin.console.people.noCreatableWorkspaces')}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {availableWorkspaces.map((workspace) => (
                  <label
                    className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                    key={workspace.id}
                  >
                    <input
                      checked={selectedWorkspaceIds.includes(workspace.id)}
                      onChange={() => toggleWorkspaceSelection(setSelectedWorkspaceIds, workspace.id)}
                      type="checkbox"
                    />
                    <span>{workspace.name}</span>
                    <span className="app-text-caption text-gray-500">
                      · {workspace.key}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
	              {t('admin.console.people.selectedWorkspaces', { workspaces: selectedWorkspaceAppSummary })}
	              <br />
	              {t('admin.console.people.groupInheritanceHint')}
            </div>
          </div>
        </form>
      </Dialog>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button disabled={isSavingUser} onClick={closeEditUserDialog} variant="secondary">
	              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={isSavingUser || isLoadingEditAccessContext}
              form="admin-user-edit-form"
              type="submit"
              variant="primary"
            >
	              {isSavingUser ? t('common:actions.saving') : t('common:actions.save')}
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
        <form className="grid gap-4" id="admin-user-edit-form" onSubmit={(event) => void handleUpdateUser(event)}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.fullName')}</span>
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
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.displayName')}</span>
              <input
                className={fieldClassName}
                onChange={(event) => setEditDisplayName(event.target.value)}
	                placeholder={t('admin.console.people.displayName')}
                value={editDisplayName}
              />
            </label>
            <label className="grid gap-1">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.columns.status')}</span>
              <select
                className={fieldClassName}
                onChange={(event) => setEditStatus(event.target.value as typeof editStatus)}
                value={editStatus}
              >
	                <option value="active">{t('admin.shared.status.active')}</option>
	                <option value="invited">{t('admin.shared.status.invited')}</option>
	                <option value="suspended">{t('admin.shared.status.suspended')}</option>
              </select>
            </label>
            <div className="grid gap-1">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.orgUnit')}</span>
              <Select
                onValueChange={setEditOrgUnitId}
                options={orgUnits.map((item) => ({ value: item.id, label: item.name }))}
                value={editOrgUnitId}
              />
            </div>
            <div className="grid gap-2 md:col-span-2">
	              <span className="app-text-caption text-gray-500">{t('admin.console.people.columns.groups')}</span>
              {groups.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                  {t('admin.console.people.noGroups')}
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {groups.map((group) => (
                    <label
                      className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                      key={group.id}
                    >
                      <input
                        checked={editGroupIds.includes(group.id)}
                        disabled={isLoadingEditAccessContext}
                        onChange={() => toggleWorkspaceSelection(setEditGroupIds, group.id)}
                        type="checkbox"
                      />
                      <span>{group.name}</span>
                      <span className="app-text-caption text-gray-500">
                        {formatGroupWorkspaceBindings(group)}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="grid gap-2">
	            <div className="app-text-caption text-gray-500">{t('admin.console.people.directWorkspaces')}</div>
            {availableWorkspaces.length === 0 ? (
              <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                {t('admin.console.people.noWorkspaces')}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {availableWorkspaces.map((workspace) => (
                  <label
                    className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                    key={workspace.id}
                  >
                    <input
                      checked={editWorkspaceIds.includes(workspace.id)}
                      disabled={isLoadingEditAccessContext}
                      onChange={() => toggleWorkspaceSelection(setEditWorkspaceIds, workspace.id)}
                      type="checkbox"
                    />
                    <span>{workspace.name}</span>
                    <span className="app-text-caption text-gray-500">
                      · {workspace.key}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
	              {t('admin.console.people.effectiveWorkspaces', { workspaces: editWorkspaceAppSummary })}
            </div>
            <div className="grid gap-2">
	              <div className="app-text-caption text-gray-500">{t('admin.console.people.inheritedWorkspaceAccess')}</div>
              {isLoadingEditAccessContext ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                  {t('admin.console.people.checkingWorkspaceAccess')}
                </div>
              ) : editInheritedWorkspaceIds.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                  {t('admin.console.people.noInheritedWorkspaceAccess')}
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {editInheritedWorkspaceIds.map((workspaceId) => (
                    <div
                      className="app-text-control rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                      key={workspaceId}
                    >
                      {workspaceById.get(workspaceId)?.name ?? workspaceId}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="grid gap-2">
	              <div className="app-text-caption text-gray-500">{t('admin.console.people.pmsSpaces')}</div>
              {isLoadingEditAccessContext ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                  {t('admin.console.people.loadingPmsSpaces')}
                </div>
              ) : (
                <div className="grid gap-3">
                  <div className="grid gap-3 md:grid-cols-[1.25fr_0.7fr_auto]">
                    <select
                      className={fieldClassName}
                      disabled={isSavingUser || availablePmsSpaces.length === 0}
                      onChange={(event) => setSelectedPmsSpaceId(event.target.value)}
                      value={selectedPmsSpaceId}
                    >
	                      <option value="">{t('admin.console.people.selectPmsSpace')}</option>
                      {availablePmsSpaces.map((space) => (
                        <option key={space.id} value={space.id}>
                          {(workspaceById.get(space.workspace_id)?.name ?? space.workspace_key)} / {space.name}
                        </option>
                      ))}
                    </select>
                    <select
                      className={fieldClassName}
                      disabled={isSavingUser || !selectedPmsSpaceId}
                      onChange={(event) => setSelectedPmsSpaceRole(event.target.value)}
                      value={selectedPmsSpaceRole}
                    >
	                      <option value="member">{t('admin.shared.roles.member.label')}</option>
	                      <option value="admin">{t('admin.shared.roles.admin.label')}</option>
                    </select>
                    <Button
                      disabled={isSavingUser || !selectedPmsSpaceId}
                      onClick={() => stageAddPmsSpace()}
                      variant="secondary"
                    >
	                      {t('admin.console.people.addSpace')}
                    </Button>
                  </div>
                  <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
	                    {t('admin.console.people.pmsSpaceHint')}
                  </div>
                  {editPmsSpaces.length === 0 ? (
                    <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                      {t('admin.console.people.noPmsSpaces')}
                    </div>
                  ) : (
                    <div className="grid gap-2">
                      {editPmsSpaces.map((space) => (
                        <div
                          className="grid gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 md:grid-cols-[1fr_180px_auto]"
                          key={space.id}
                        >
                          <div>
                            <div className="app-text-control text-app-ink">{space.name}</div>
                            <div className="app-text-caption text-gray-500">
                              {space.workspace_name}
                              {space.description ? ` · ${space.description}` : ''}
                            </div>
                          </div>
                          <select
                            className={fieldClassName}
                            disabled={isSavingUser}
                            onChange={(event) => stageUpdatePmsSpaceRole(space.id, event.target.value)}
                            value={space.role}
                          >
	                            <option value="viewer">{t('pms.settings.role.viewer')}</option>
	                            <option value="member">{t('pms.settings.role.member')}</option>
	                            <option value="admin">{t('pms.settings.role.admin')}</option>
	                            <option value="owner">{t('pms.settings.role.owner')}</option>
                          </select>
                          <div className="flex justify-end">
                            <Button
                              disabled={isSavingUser}
                              onClick={() => stageRemovePmsSpace(space.id)}
                              variant="secondary"
                            >
	                              {t('common:actions.delete')}
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

type WorkspaceFilter = 'active' | 'archived' | 'all';

function CreateWorkspaceModal({
  open,
  onOpenChange,
  onCreate,
  busy,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (payload: { name: string; description: string }) => Promise<void>;
  busy: boolean;
  error: string | null;
}) {
  const { t } = useTranslation('apps');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
    }
  }, [open]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    await onCreate({ name: trimmed, description: description.trim() });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('admin.console.workspaces.createTitle')}
      description={t('admin.console.workspaces.createDescription')}
      dismissOnInteractOutside={false}
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {t('common:actions.cancel')}
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="create-workspace-form"
            disabled={busy || !name.trim()}
          >
            {busy ? t('admin.console.workspaces.creating') : t('admin.console.workspaces.createAction')}
          </Button>
        </>
      }
    >
      <form id="create-workspace-form" className="grid gap-4" onSubmit={(e) => void handleSubmit(e)}>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">{t('admin.workspace.nameLabel')}</span>
          <input
            autoFocus
            className={fieldClassName}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('admin.console.workspaces.namePlaceholder')}
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">{t('admin.console.workspaces.descriptionOptional')}</span>
          <textarea
            className={`${fieldClassName} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={t('admin.console.workspaces.descriptionPlaceholder')}
            maxLength={1000}
          />
        </label>
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <p className="app-text-caption text-app-ink/60">
          {t('admin.console.workspaces.appToggleHint')}
        </p>
      </form>
    </Dialog>
  );
}

function WorkspacesSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const auth = useAuth();
  const currentUserId = auth.user?.id ?? '';
  const canCreateWorkspaces = auth.hasPermission('workspace.write');
  const canReadGroups = auth.hasPermission('group.read');
  const canManage = canCreateWorkspaces;

  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [filter, setFilter] = useState<WorkspaceFilter>('active');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const flashSuccess = useCallback((text: string) => {
    setError(null);
    setMessage(text);
    window.setTimeout(() => setMessage(null), 3500);
  }, []);

  const flashError = useCallback((text: string) => {
    setMessage(null);
    setError(text);
  }, []);

  const reloadWorkspaces = useCallback(
    async (preserveSelection?: string | null) => {
      try {
        const items = await listWorkspaces(token, { includeArchived: true });
        setWorkspaces(items);
        if (preserveSelection && items.some((item) => item.id === preserveSelection)) {
          setSelectedWorkspaceId(preserveSelection);
        } else {
          setSelectedWorkspaceId((current) => {
            if (current && items.some((item) => item.id === current)) {
              return current;
            }
            const fallback = items.find((item) => item.active) ?? items[0] ?? null;
            return fallback?.id ?? null;
          });
        }
      } catch (caughtError) {
        flashError(getErrorMessage(caughtError, t('admin.console.workspaces.listLoadFailed')));
      }
    },
    [token, flashError, t],
  );

  useEffect(() => {
    void (async () => {
      try {
        const [workspaceItems, groupItems] = await Promise.all([
          listWorkspaces(token, { includeArchived: true }),
          canReadGroups ? listGroups(token) : Promise.resolve([]),
        ]);
        setWorkspaces(workspaceItems);
        setGroups(groupItems);
        const fallback = workspaceItems.find((item) => item.active) ?? workspaceItems[0] ?? null;
        setSelectedWorkspaceId(fallback?.id ?? null);
      } catch (caughtError) {
        flashError(getErrorMessage(caughtError, t('admin.console.workspaces.infoLoadFailed')));
      }
    })();
  }, [token, canReadGroups, flashError, t]);

  const selectedWorkspace = useMemo(
    () => workspaces.find((item) => item.id === selectedWorkspaceId) ?? null,
    [selectedWorkspaceId, workspaces],
  );

  const filteredWorkspaces = useMemo(() => {
    const trimmed = searchQuery.trim().toLowerCase();
    return workspaces
      .filter((workspace) => {
        if (filter === 'active') return workspace.active;
        if (filter === 'archived') return !workspace.active;
        return true;
      })
      .filter((workspace) => {
        if (!trimmed) return true;
        return (
          workspace.name.toLowerCase().includes(trimmed) ||
          workspace.key.toLowerCase().includes(trimmed) ||
          workspace.description.toLowerCase().includes(trimmed)
        );
      })
      .sort((a, b) => {
        if (a.active !== b.active) return a.active ? -1 : 1;
	        return a.name.localeCompare(b.name, locale);
	      });
	  }, [workspaces, filter, searchQuery, locale]);

  async function handleCreateWorkspace(payload: { name: string; description: string }) {
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createWorkspace(token, payload);
      setCreateOpen(false);
      await reloadWorkspaces(created.id);
      flashSuccess(t('admin.console.workspaces.created', { name: created.name }));
    } catch (caughtError) {
      setCreateError(getErrorMessage(caughtError, t('admin.console.workspaces.createFailed')));
    } finally {
      setCreateBusy(false);
    }
  }

  const handleWorkspaceChanged = useCallback((next: WorkspaceItem) => {
    setWorkspaces((current) => current.map((item) => (item.id === next.id ? next : item)));
  }, []);

  const handleWorkspaceDeleted = useCallback(
    (workspaceId: string) => {
      setWorkspaces((current) => {
        const remaining = current.filter((item) => item.id !== workspaceId);
        const fallback = remaining.find((item) => item.active) ?? remaining[0] ?? null;
        setSelectedWorkspaceId(fallback?.id ?? null);
        return remaining;
      });
    },
    [],
  );

  return (
    <div className="space-y-3">
      <SectionMessage error={error} message={message} />

      <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
        <aside className="overflow-hidden rounded-md border border-app-border bg-app-bg">
          <div className="flex items-center justify-between gap-2 border-b border-app-border px-3 py-2">
            <h2 className="app-text-overline uppercase tracking-wide text-app-ink/60">
	              {t('admin.console.sections.workspaces.title')} · {workspaces.length}
            </h2>
            {canCreateWorkspaces ? (
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
	                aria-label={t('admin.console.workspaces.createTitle')}
              >
                <Plus size={14} />
              </button>
            ) : null}
          </div>
          <div className="space-y-1.5 px-3 py-2">
            <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
              <Search size={12} className="text-app-ink/50" />
              <input
                className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
	                placeholder={t('admin.console.workspaces.searchPlaceholder')}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <Tabs value={filter} onValueChange={(value) => setFilter(value as WorkspaceFilter)}>
              <TabsList className="w-full">
                <TabsTrigger className="flex-1" value="active">
	                  {t('admin.console.workspaces.filterActive')}
                </TabsTrigger>
                <TabsTrigger className="flex-1" value="archived">
	                  {t('admin.console.workspaces.filterArchived')}
                </TabsTrigger>
                <TabsTrigger className="flex-1" value="all">
	                  {t('admin.console.workspaces.filterAll')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <div className="max-h-[640px] overflow-y-auto pb-1">
            {filteredWorkspaces.length === 0 ? (
              <div className="px-3 py-8 text-center text-app-ink/60">
	                <p className="app-text-body-sm">{t('admin.console.workspaces.empty')}</p>
              </div>
            ) : (
              filteredWorkspaces.map((workspace) => {
                const isSelected = workspace.id === selectedWorkspaceId;
                return (
                  <button
                    key={workspace.id}
                    type="button"
                    onClick={() => setSelectedWorkspaceId(workspace.id)}
                    className={`relative flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors ${
                      isSelected
                        ? 'bg-app-accent/10 text-app-ink'
                        : 'text-app-ink/85 hover:bg-app-surface-sidebar'
                    }`}
                  >
                    {isSelected ? (
                      <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-app-accent" />
                    ) : null}
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        workspace.active ? 'bg-emerald-500' : 'bg-app-ink/30'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="app-text-body-sm truncate font-medium text-app-ink">
                        {workspace.name}
                      </div>
                      <div className="app-text-caption truncate text-app-ink/50">
	                        {t('admin.console.workspaces.itemMeta', { key: workspace.key, count: workspace.member_count })}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <section className="flex min-h-[560px] flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
          <WorkspaceDetailPanel
            workspace={selectedWorkspace}
            token={token}
            currentUserId={currentUserId}
            groups={groups}
            canReadGroups={canReadGroups}
            capabilities={{
              canEditProfile: canManage,
              canManageMembers: canManage,
              canArchive: canManage,
              canDelete: canManage,
              canBrowseDirectory: auth.hasPermission('user.read'),
            }}
            onWorkspaceChanged={handleWorkspaceChanged}
            onWorkspaceDeleted={handleWorkspaceDeleted}
            flashSuccess={flashSuccess}
            flashError={flashError}
          />
        </section>
      </div>

      <CreateWorkspaceModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={handleCreateWorkspace}
        busy={createBusy}
        error={createError}
      />
    </div>
  );
}


function SecuritySection({
  token,
  canReadUsers,
  canReadGroups,
  canWriteGroups,
}: {
  token: string;
  canReadUsers: boolean;
  canReadGroups: boolean;
  canWriteGroups: boolean;
}) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemRoles, setSystemRoles] = useState('');
  const [selectedTemplateGroupId, setSelectedTemplateGroupId] = useState('');
  const [selectedGroupMemberIds, setSelectedGroupMemberIds] = useState<string[]>([]);
  const [selectedMemberCandidateId, setSelectedMemberCandidateId] = useState(NONE_OPTION_VALUE);
  const [groupName, setGroupName] = useState('');
  const [groupDescription, setGroupDescription] = useState('');
  const [groupSystemRoles, setGroupSystemRoles] = useState('');
  const [groupActive, setGroupActive] = useState(true);
  const [isSavingGroupDetails, setIsSavingGroupDetails] = useState(false);
  const [templateBindings, setTemplateBindings] = useState<Array<{ workspace_id: string; role: string }>>([]);
  const [isSavingGroupTemplates, setIsSavingGroupTemplates] = useState(false);
  const [isSavingGroupMembers, setIsSavingGroupMembers] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadAllUsers() {
    const allUsers: AuthUser[] = [];
    let nextPage = 1;

    while (true) {
      const response = await listAdminUsers(token, {
        page: nextPage,
        page_size: 100,
      });
      allUsers.push(...response.items);
      if (allUsers.length >= response.total || response.items.length === 0) {
        break;
      }
      nextPage += 1;
    }

    return allUsers;
  }

  async function load() {
    setError(null);
    try {
      const results = await Promise.allSettled([
        canReadUsers ? loadAllUsers() : Promise.resolve<AuthUser[]>([]),
        canReadGroups ? listGroups(token) : Promise.resolve<AccessGroupItem[]>([]),
        canReadGroups ? listWorkspaces(token) : Promise.resolve<WorkspaceItem[]>([]),
      ]);
      const [userResult, groupResult, workspaceResult] = results;

      if (userResult.status === 'fulfilled') {
        setUsers(userResult.value);
      } else if (canReadUsers) {
        setError(getErrorMessage(userResult.reason, t('admin.console.security.usersLoadFailed')));
      }

      if (groupResult.status === 'fulfilled') {
        setGroups(groupResult.value);
      } else if (canReadGroups) {
        setError(getErrorMessage(groupResult.reason, t('admin.console.security.groupsLoadFailed')));
      }

      if (workspaceResult.status === 'fulfilled') {
        setWorkspaces(workspaceResult.value.filter((workspace) => workspace.active));
      } else if (canReadGroups) {
        setError((current) => current ?? getErrorMessage(workspaceResult.reason, t('admin.console.security.workspacesLoadFailed')));
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.security.settingsLoadFailed')));
    }
  }

  useEffect(() => {
    void load();
    // `load` intentionally stays local so it reads the latest permission gates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canReadGroups, canReadUsers, token]);

  useEffect(() => {
    setSelectedTemplateGroupId((current) => {
      if (current && groups.some((group) => group.id === current)) {
        return current;
      }
      return groups[0]?.id ?? '';
    });
  }, [groups]);

  useEffect(() => {
    const selectedGroup = groups.find((group) => group.id === selectedTemplateGroupId) ?? null;
    setTemplateBindings(
      selectedGroup
        ? selectedGroup.workspace_bindings.map((binding) => ({
            workspace_id: binding.workspace_id,
            role: binding.role,
          }))
        : [],
    );
  }, [groups, selectedTemplateGroupId]);

  useEffect(() => {
    const selectedGroup = groups.find((group) => group.id === selectedTemplateGroupId) ?? null;
    setGroupName(selectedGroup?.name ?? '');
    setGroupDescription(selectedGroup?.description ?? '');
    setGroupSystemRoles(selectedGroup?.system_roles.join(', ') ?? '');
    setGroupActive(selectedGroup?.active ?? true);
  }, [groups, selectedTemplateGroupId]);

  useEffect(() => {
    if (!selectedTemplateGroupId) {
      setSelectedGroupMemberIds([]);
      return;
    }
    setSelectedGroupMemberIds(
      users
        .filter((user) => user.group_ids.includes(selectedTemplateGroupId))
        .map((user) => user.id),
    );
    setSelectedMemberCandidateId(NONE_OPTION_VALUE);
  }, [selectedTemplateGroupId, users]);

  async function handleCreateGroup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWriteGroups) return;
    setMessage(null);
    setError(null);

    try {
      const created = await createGroup(token, {
        name: name.trim(),
        description: description.trim(),
        system_roles: systemRoles
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      });
      setName('');
      setDescription('');
      setSystemRoles('');
      setMessage(t('admin.console.security.groupCreated'));
      await load();
      setSelectedTemplateGroupId(created.id);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.security.groupCreateFailed')));
    }
  }

  async function handleSaveGroupTemplates() {
    if (!canWriteGroups || !selectedTemplateGroupId) return;
    setMessage(null);
    setError(null);
    setIsSavingGroupTemplates(true);

    try {
      const response = await replaceGroupWorkspaceBindings(token, selectedTemplateGroupId, templateBindings);
      setGroups((current) =>
        current.map((group) => (group.id === response.id ? response : group)),
      );
      setMessage(t('admin.console.security.templatesSaved'));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.security.templatesSaveFailed')));
    } finally {
      setIsSavingGroupTemplates(false);
    }
  }

  async function handleSaveGroupDetails() {
    if (!canWriteGroups || !selectedTemplateGroup) return;
    setMessage(null);
    setError(null);
    setIsSavingGroupDetails(true);

    try {
      const response = await updateGroup(token, selectedTemplateGroup.id, {
        name: groupName.trim(),
        description: groupDescription.trim(),
        system_roles: groupSystemRoles
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        slug: selectedTemplateGroup.slug,
        group_kind: selectedTemplateGroup.group_kind,
        active: groupActive,
      });
      setGroups((current) =>
        current.map((group) => (group.id === response.id ? response : group)),
      );
      setMessage(t('admin.console.security.groupSaved'));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.security.groupSaveFailed')));
    } finally {
      setIsSavingGroupDetails(false);
    }
  }

  async function handleSaveGroupMembers() {
    if (!canWriteGroups || !selectedTemplateGroupId) return;
    setMessage(null);
    setError(null);
    setIsSavingGroupMembers(true);

    try {
      const response = await replaceGroupMembers(token, selectedTemplateGroupId, selectedGroupMemberIds);
      setGroups((current) =>
        current.map((group) => (group.id === response.id ? response : group)),
      );
      await load();
      setMessage(t('admin.console.security.membersSaved'));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, t('admin.console.security.membersSaveFailed')));
    } finally {
      setIsSavingGroupMembers(false);
    }
  }

  const selectedTemplateGroup = groups.find((group) => group.id === selectedTemplateGroupId) ?? null;
  const selectedGroupMembers = users
    .filter((user) => selectedGroupMemberIds.includes(user.id))
    .sort((left, right) => {
      const leftName = left.display_name || left.full_name;
      const rightName = right.display_name || right.full_name;
      return leftName.localeCompare(rightName, locale);
    });
  const groupMemberCandidates = users
    .filter((user) => !selectedGroupMemberIds.includes(user.id))
    .sort((left, right) => {
      const leftName = left.display_name || left.full_name;
      const rightName = right.display_name || right.full_name;
      return leftName.localeCompare(rightName, locale);
    });

  return (
    <div className="space-y-6">


      <SectionMessage error={error} message={message} />

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard
	          description={t('admin.console.security.createDescription')}
	          title={t('admin.console.security.createTitle')}
        >
          {canWriteGroups ? (
            <form className="grid gap-3" onSubmit={(event) => void handleCreateGroup(event)}>
              <input
                className={fieldClassName}
                onChange={(event) => setName(event.target.value)}
	                placeholder={t('admin.console.security.groupName')}
                value={name}
              />
              <input
                className={fieldClassName}
                onChange={(event) => setDescription(event.target.value)}
	                placeholder={t('admin.workspace.descriptionLabel')}
                value={description}
              />
              <input
                className={fieldClassName}
                onChange={(event) => setSystemRoles(event.target.value)}
	                placeholder={t('admin.console.security.systemRolePlaceholder')}
                value={systemRoles}
              />
              <div className="flex justify-end">
	                <Button type="submit" variant="primary">{t('admin.console.security.createGroup')}</Button>
              </div>
            </form>
          ) : (
            <InlineNotice tone="warning">
	              {t('admin.console.security.createReadOnly')}
            </InlineNotice>
          )}
        </SurfaceCard>

        <SurfaceCard
	          description={t('admin.console.security.groupsDescription')}
	          title={t('admin.console.security.groupsTitle')}
        >
          {canReadGroups ? (
            <TableShell>
              <thead>
                <tr>
	                  <HeadCell>{t('admin.console.security.columns.name')}</HeadCell>
	                  <HeadCell>{t('admin.console.security.columns.slug')}</HeadCell>
	                  <HeadCell>{t('admin.console.security.columns.systemRoles')}</HeadCell>
	                  <HeadCell>{t('admin.console.security.columns.workspaceTemplates')}</HeadCell>
	                  <HeadCell>{t('admin.console.security.columns.members')}</HeadCell>
                </tr>
              </thead>
              <tbody>
                {groups.length === 0 ? (
                  <EmptyRow
                    colSpan={5}
	                    description={t('admin.console.security.emptyGroupsDescription')}
	                    title={t('admin.console.security.emptyGroupsTitle')}
                  />
                ) : (
                  groups.map((group) => (
                    <tr key={group.id}>
                      <BodyCell>
                        <div className="font-medium text-app-ink">{group.name}</div>
	                        <div className="app-text-caption mt-1 text-gray-500">{group.description || t('common:empty.none')}</div>
                      </BodyCell>
                      <BodyCell>{group.slug}</BodyCell>
                      <BodyCell>{group.system_roles.join(', ') || 'None'}</BodyCell>
                      <BodyCell>{formatGroupWorkspaceBindings(group)}</BodyCell>
                      <BodyCell>{group.member_count}</BodyCell>
                    </tr>
                  ))
                )}
              </tbody>
            </TableShell>
          ) : (
            <InlineNotice tone="warning">
	              {t('admin.console.security.groupsReadDenied')}
            </InlineNotice>
          )}
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard
	          actions={canReadGroups && canWriteGroups ? <Button disabled={isSavingGroupDetails || !selectedTemplateGroup} onClick={() => { void handleSaveGroupDetails(); }} variant="primary">{isSavingGroupDetails ? t('admin.console.security.savingGroup') : t('admin.console.security.saveGroup')}</Button> : undefined}
	          description={t('admin.console.security.detailsDescription')}
	          title={t('admin.console.security.detailsTitle')}
        >
          {!canReadGroups ? (
            <InlineNotice tone="warning">
	              {t('admin.console.security.detailsReadDenied')}
            </InlineNotice>
          ) : groups.length === 0 ? (
            <InlineNotice tone="info">
	              {t('admin.console.security.detailsCreateFirst')}
            </InlineNotice>
          ) : (
            <div className="grid gap-3">
              <div className="grid gap-1">
	                <span className="app-text-caption text-gray-500">{t('admin.shared.directory.group')}</span>
                <Select
                  disabled={!canWriteGroups}
                  onValueChange={setSelectedTemplateGroupId}
                  options={groups.map((group) => ({ value: group.id, label: group.name }))}
                  value={selectedTemplateGroupId}
                />
              </div>
              <div className="grid gap-1">
	                <span className="app-text-caption text-gray-500">{t('admin.console.security.columns.slug')}</span>
                <div className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
                  {selectedTemplateGroup?.slug ?? '-'}
                </div>
              </div>
              <input
                className={fieldClassName}
                disabled={!canWriteGroups || !selectedTemplateGroup}
                onChange={(event) => setGroupName(event.target.value)}
	                placeholder={t('admin.console.security.groupName')}
                value={groupName}
              />
              <input
                className={fieldClassName}
                disabled={!canWriteGroups || !selectedTemplateGroup}
                onChange={(event) => setGroupDescription(event.target.value)}
	                placeholder={t('admin.workspace.descriptionLabel')}
                value={groupDescription}
              />
              <input
                className={fieldClassName}
                disabled={!canWriteGroups || !selectedTemplateGroup}
                onChange={(event) => setGroupSystemRoles(event.target.value)}
	                placeholder={t('admin.console.security.systemRolePlaceholder')}
                value={groupSystemRoles}
              />
              <label className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
                <input
                  checked={groupActive}
                  disabled={!canWriteGroups || !selectedTemplateGroup}
                  onChange={(event) => setGroupActive(event.target.checked)}
                  type="checkbox"
                />
	                <span>{t('admin.console.security.groupIsActive')}</span>
              </label>
            </div>
          )}
        </SurfaceCard>

        <SurfaceCard
	          actions={canReadGroups && canReadUsers && canWriteGroups ? <Button disabled={isSavingGroupMembers || !selectedTemplateGroupId} onClick={() => { void handleSaveGroupMembers(); }} variant="primary">{isSavingGroupMembers ? t('admin.console.security.savingMembers') : t('admin.console.security.saveMembers')}</Button> : undefined}
	          description={t('admin.console.security.membersDescription')}
	          title={t('admin.console.security.membersTitle')}
        >
          {!canReadGroups || !canReadUsers ? (
            <InlineNotice tone="warning">
	              {t('admin.console.security.membersReadDenied')}
            </InlineNotice>
          ) : groups.length === 0 ? (
            <InlineNotice tone="info">
	              {t('admin.console.security.membersCreateFirst')}
            </InlineNotice>
          ) : (
            <div className="grid gap-4">
              <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                <Select
                  disabled={!canWriteGroups || groupMemberCandidates.length === 0}
                  onValueChange={setSelectedMemberCandidateId}
                  options={[
	                    { value: NONE_OPTION_VALUE, label: t('admin.console.security.addMember') },
                    ...groupMemberCandidates.map((user) => ({
                      value: user.id,
                      label: `${user.display_name || user.full_name} (${user.email})`,
                    })),
                  ]}
                  value={selectedMemberCandidateId}
                />
                <Button
                  disabled={!canWriteGroups || selectedMemberCandidateId === NONE_OPTION_VALUE}
                  onClick={() => {
                    if (selectedMemberCandidateId === NONE_OPTION_VALUE) return;
                    setSelectedGroupMemberIds((current) => Array.from(new Set([...current, selectedMemberCandidateId])));
                    setSelectedMemberCandidateId(NONE_OPTION_VALUE);
                  }}
                  variant="secondary"
                >
	                  {t('admin.console.security.addMember')}
                </Button>
              </div>
              {selectedGroupMembers.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
	                  {t('admin.console.security.noGroupMembers')}
                </div>
              ) : (
                <div className="grid gap-2">
                  {selectedGroupMembers.map((user) => (
                    <div
                      className="flex items-center justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3"
                      key={user.id}
                    >
                      <div className="min-w-0">
                        <div className="app-text-control truncate text-app-ink">
                          {user.display_name || user.full_name}
                        </div>
                        <div className="app-text-caption truncate text-gray-500">
                          {user.email}
                        </div>
                      </div>
                      <Button
                        disabled={!canWriteGroups}
                        onClick={() => {
                          setSelectedGroupMemberIds((current) => current.filter((item) => item !== user.id));
                        }}
                        variant="secondary"
                      >
	                        {t('common:actions.delete')}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </SurfaceCard>
      </div>

      <SurfaceCard
	        actions={canReadGroups && canWriteGroups ? <Button disabled={isSavingGroupTemplates || !selectedTemplateGroupId} onClick={() => { void handleSaveGroupTemplates(); }} variant="primary">{isSavingGroupTemplates ? t('admin.console.security.savingTemplates') : t('admin.console.security.saveTemplates')}</Button> : undefined}
	        description={t('admin.console.security.templatesDescription')}
	        title={t('admin.console.security.templatesTitle')}
      >
        {!canReadGroups ? (
          <InlineNotice tone="warning">
	            {t('admin.console.security.templatesReadDenied')}
          </InlineNotice>
        ) : groups.length === 0 ? (
          <InlineNotice tone="info">
	            {t('admin.console.security.templatesCreateFirst')}
          </InlineNotice>
        ) : workspaces.length === 0 ? (
          <InlineNotice tone="info">
	            {t('admin.console.security.noActiveWorkspaces')}
          </InlineNotice>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-1 md:max-w-sm">
	              <span className="app-text-caption text-gray-500">{t('admin.shared.directory.group')}</span>
              <Select
                disabled={!canWriteGroups}
                onValueChange={setSelectedTemplateGroupId}
                options={groups.map((group) => ({ value: group.id, label: group.name }))}
                value={selectedTemplateGroupId}
              />
            </div>
            {selectedTemplateGroup ? (
              <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
	                {t('admin.console.security.selectedGroup', { name: selectedTemplateGroup.name })}
	                <br />
	                {t('admin.console.security.templateInheritanceHint')}
              </div>
            ) : null}
            <div className="grid gap-3">
              {workspaces.map((workspace) => {
                const binding = templateBindings.find((item) => item.workspace_id === workspace.id) ?? null;
                return (
                  <div
                    className="grid gap-3 rounded-xl border border-app-border bg-app-surface-sidebar px-4 py-3 md:grid-cols-[1fr_180px]"
                    key={workspace.id}
                  >
                    <label className="flex items-start gap-3">
                      <input
                        checked={binding !== null}
                        disabled={!canWriteGroups}
                        onChange={() => {
                          setTemplateBindings((current) => (
                            current.some((item) => item.workspace_id === workspace.id)
                              ? current.filter((item) => item.workspace_id !== workspace.id)
                              : [...current, { workspace_id: workspace.id, role: 'member' }]
                          ));
                        }}
                        type="checkbox"
                      />
                      <div>
                        <div className="font-medium text-app-ink">{workspace.name}</div>
                        <div className="app-text-caption mt-1 text-gray-500">
	                          {workspace.description || t('common:empty.none')}
                        </div>
                      </div>
                    </label>
                    <select
                      className={fieldClassName}
                      disabled={!canWriteGroups || binding === null}
                      onChange={(event) => {
                        setTemplateBindings((current) =>
                          current.map((item) => (
                            item.workspace_id === workspace.id
                              ? { ...item, role: event.target.value }
                              : item
                          )),
                        );
                      }}
                      value={binding?.role ?? 'member'}
                    >
	                      <option value="member">{t('admin.shared.roles.member.label')}</option>
	                      <option value="admin">{t('admin.shared.roles.admin.label')}</option>
                    </select>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </SurfaceCard>

    </div>
  );
}

function AuditSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const { user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listAuditLogs(token)
      .then(setItems)
      .catch((caughtError) => {
        setError(getErrorMessage(caughtError, t('admin.console.audit.loadFailed')));
      });
  }, [token, t]);

  return (
    <div className="space-y-6">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}



      <SurfaceCard
	        description={t('admin.console.audit.description')}
	        title={t('admin.console.audit.title')}
      >
        <div className="space-y-3">
          {items.length === 0 ? (
            <div className="app-text-body rounded-xl border border-dashed border-app-border bg-app-surface-sidebar px-4 py-8 text-center text-gray-500">
	              {t('admin.console.audit.empty')}
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-app-border bg-app-surface-sidebar px-5 py-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-app-ink">{item.summary}</div>
                      <Badge tone="purple">{item.action}</Badge>
                    </div>
                    <div className="app-text-body text-gray-500">
	                      {item.entity_kind} / {item.entity_id ?? t('common:empty.none')} / {item.actor_name ?? t('admin.console.audit.systemActor')}
                    </div>
                  </div>
                  <div className="app-text-body text-gray-500">
                    {formatDateTime(item.created_at, {
                      dateStyle: 'medium',
	                      locale,
                      timeStyle: 'short',
                      timeZone,
                    })}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </SurfaceCard>
    </div>
  );
}

export function AdminConsoleView({ section }: { section: AdminSection }) {
  const { t } = useTranslation('apps');
  const auth = useAuth();
  const token = auth.token;
  const hasAdminReadPermission = useMemo(
    () => hasAnyAdminReadPermission(auth.user?.system_roles ?? []),
    [auth.user],
  );

  if (!token) {
    return null;
  }

  if (!hasAdminReadPermission) {
    return <AccessDeniedView description={t('admin.console.accessDenied')} />;
  }

  let content: React.ReactNode;
  let actions: React.ReactNode;

  switch (section) {
    case 'general':
      content = <GeneralSection token={token} />;
      break;
    case 'people':
      content = <PeopleSection token={token} />;
      actions = <Badge tone="purple">{t('admin.console.badges.adminOnly')}</Badge>;
      break;
    case 'workspaces':
      content = <WorkspacesSection token={token} />;
      break;
    case 'security':
      content = (
        <SecuritySection
          canReadUsers={auth.hasPermission('user.read')}
          canReadGroups={auth.hasPermission('group.read')}
          canWriteGroups={auth.hasPermission('group.write')}
          token={token}
        />
      );
      actions = <Badge tone="purple">{t('admin.console.badges.restricted')}</Badge>;
      break;
    case 'audit':
      content = <AuditSection token={token} />;
      break;
    default:
      content = null;
  }

  return (
    <SettingsShell actions={actions} section={section}>
      {content}
    </SettingsShell>
  );
}
