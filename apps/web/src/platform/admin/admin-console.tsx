import { useCallback, useEffect, useMemo, useState } from 'react';
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
  { title: string; description: string; learnMoreLabel?: string }
> = {
  general: {
    title: 'General settings',
    description: '공통 사용자, 공간, 워크스페이스 운영 현황을 한곳에서 확인합니다.',
  },
  people: {
    title: 'Manage people',
    description: '',
    learnMoreLabel: 'Learn more',
  },
  workspaces: {
    title: 'Workspaces',
    description: '협업 공간을 만들고 멤버 구성을 관리합니다.',
  },
  security: {
    title: 'Security & permissions',
    description: '권한 그룹과 관리자 역할을 운영합니다.',
  },
  audit: {
    title: 'Audit logs',
    description: '관리 작업과 인증 이벤트를 시간순으로 추적합니다.',
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
  const meta = sectionMeta[section];

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 border-b border-app-border pb-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="app-text-title-lg text-app-ink">{meta.title}</h1>
              {meta.learnMoreLabel ? (
                <button className="app-text-control-sm text-app-accent hover:underline" type="button">
                  {meta.learnMoreLabel}
                </button>
              ) : null}
            </div>
            {meta.description ? <p className="app-text-body max-w-3xl text-gray-500">{meta.description}</p> : null}
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
    return value ?? 'Restricted';
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
          setError(getErrorMessage(caughtError, '관리자 요약 정보를 불러오지 못했습니다.'));
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
          title="Current operating model"
          description="현재 공통 계정 체계와 작업 영역 운영 방식을 한 번에 확인할 수 있는 요약입니다."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              <div className="app-text-title-md text-app-ink">Identity</div>
                <div className="app-text-body mt-3 space-y-2 text-gray-500">
                <div>사용자 계정 {formatCount(summary.userCount)}{summary.userCount !== null ? '개' : ''}</div>
                <div>관리자 {formatCount(summary.adminCount)}{summary.adminCount !== null ? '명' : ''}</div>
                <div>권한 그룹 {formatCount(summary.groupCount)}{summary.groupCount !== null ? '개' : ''}</div>
              </div>
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              <div className="app-text-title-md text-app-ink">Work model</div>
              <div className="app-text-body mt-3 space-y-2 text-gray-500">
                <div>워크스페이스 {formatCount(summary.workspaceCount)}{summary.workspaceCount !== null ? '개' : ''}</div>
                <div>PMS 공간 {formatCount(summary.teamCount)}{summary.teamCount !== null ? '개' : ''}</div>
              </div>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard
          title="Admin notes"
          description="설정 앱과 마이페이지의 역할을 분리한 현재 UX 원칙입니다."
        >
          <div className="app-text-body space-y-3 text-gray-500">
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              프로필 아바타는 개인 설정으로만 이동하고, 조직 운영 기능은 모두 Settings 앱 안에서 다룹니다.
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              사용자, PMS 공간, 워크스페이스, 관리자 보안 설정은 좌측 서브사이드바를 기준으로 분리합니다.
            </div>
            <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-4">
              관리자 이벤트와 인증 이벤트는 Audit 섹션에서 시간순으로 확인합니다.
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  );
}

function PeopleSection({ token }: { token: string }) {
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
            return leftWorkspaceName.localeCompare(rightWorkspaceName, 'ko');
          }
          return left.name.localeCompare(right.name, 'ko');
        }),
    [allSpaces, editPmsSpaces, workspaceById],
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
      setError(getErrorMessage(caughtError, '사용자 정보를 불러오지 못했습니다.'));
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
          setError(getErrorMessage(caughtError, '사용자 정보를 불러오지 못했습니다.'));
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [token]);

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
            setError(getErrorMessage(caughtError, '사용자 목록을 불러오지 못했습니다.'));
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
  }, [page, search, token]);

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
        return left.workspace_name.localeCompare(right.workspace_name, 'ko');
      }
      return left.name.localeCompare(right.name, 'ko');
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
      setError(getErrorMessage(caughtError, '사용자 접근 정보를 불러오지 못했습니다.'));
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
      setError(getErrorMessage(caughtError, '사용자 목록을 불러오지 못했습니다.'));
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
      setMessage(`사용자를 생성했습니다. 임시 비밀번호: ${response.temporary_password}`);
      await loadDirectoryOptions();
      await reloadUsers(1);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '사용자를 생성하지 못했습니다.'));
    } finally {
      setIsCreatingUser(false);
    }
  }

  async function handleResetPassword(userId: string) {
    setMessage(null);
    setError(null);

    try {
      const response = await resetUserPassword(token, userId);
      setMessage(`임시 비밀번호를 재발급했습니다. 새 비밀번호: ${response.temporary_password}`);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '비밀번호를 재발급하지 못했습니다.'));
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
      setMessage('사용자 정보를 저장했습니다.');
      await reloadUsers(page);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '사용자 정보를 저장하지 못했습니다.'));
    } finally {
      setIsSavingUser(false);
    }
  }

  async function handleDeleteUser(user: AuthUser) {
    if (!window.confirm(`${user.email} 사용자를 삭제할까요?`)) {
      return;
    }

    setMessage(null);
    setError(null);
    setDeletingUserId(user.id);

    try {
      await deleteAdminUser(token, user.id);
      setEditingUserId((current) => (current === user.id ? null : current));
      setMessage(`${user.email} 사용자를 삭제했습니다.`);
      const nextTotal = Math.max(0, totalUsers - 1);
      const nextPage = Math.min(page, Math.max(1, Math.ceil(nextTotal / PEOPLE_PAGE_SIZE)));
      await reloadUsers(nextPage);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '사용자를 삭제하지 못했습니다.'));
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
          isAdminUser(user) ? 'Admin' : 'Member',
          formatStatusLabel(user.status),
          formatDateLabel(user.last_login_at),
          formatDateLabel(user.created_at),
          formatUserApps(user),
        ]);

      const header = ['Name', 'Email', 'Org', 'Groups', 'Workspaces', 'Role', 'Status', 'Last active', 'Created on', 'Enabled apps'];
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
      setError(getErrorMessage(caughtError, '사용자 목록을 내보내지 못했습니다.'));
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
              placeholder="Search by name or email"
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
            {isExporting ? 'Exporting' : 'Export'}
          </button>
          <button
            className="app-text-control inline-flex items-center gap-1.5 rounded-md bg-app-ink px-3 py-1.5 text-app-bg transition-opacity hover:opacity-90 dark:bg-white dark:text-black"
            onClick={openCreateUserDialog}
            type="button"
          >
            <span>+</span>
            <span>Create user</span>
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 py-2">
        <button
          className="app-text-control inline-flex items-center gap-1.5 rounded p-1 text-app-ink hover:bg-app-surface-hover"
          type="button"
        >
          <span>All Users ({totalUsers})</span>
          <span className="app-text-micro text-gray-500">▾</span>
        </button>
        {isLoadingUsers ? <span className="app-text-body text-gray-500">Loading</span> : null}
      </div>

      <div className="w-full overflow-x-auto">
        <table className="app-text-body-sm min-w-[1380px] w-full border-collapse">
          <thead>
            <tr className="bg-app-surface-sidebar/40">
              <HeadCell className="w-[270px]" dense>User</HeadCell>
              <HeadCell className="w-[150px]" dense>Org</HeadCell>
              <HeadCell className="w-[150px]" dense>Groups</HeadCell>
              <HeadCell className="w-[220px]" dense>Workspaces</HeadCell>
              <HeadCell className="w-[90px]" dense>Role</HeadCell>
              <HeadCell className="w-[100px]" dense>Status</HeadCell>
              <HeadCell className="w-[220px]" dense>Enabled apps</HeadCell>
              <HeadCell className="w-[110px]" dense>Last active</HeadCell>
              <HeadCell className="w-[110px]" dense>Created</HeadCell>
              <HeadCell className="w-[72px] text-right" dense>Actions</HeadCell>
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
                  + Create user
                </button>
              </td>
            </tr>
            {isLoadingUsers && users.length === 0 ? (
              <EmptyRow
                colSpan={10}
                description="잠시만 기다려 주세요."
                title="사용자 목록을 불러오는 중입니다."
              />
            ) : filteredUsers.length === 0 ? (
              <EmptyRow
                colSpan={10}
                description="검색어를 바꾸거나 생성 버튼으로 사용자를 추가하세요."
                title="조건에 맞는 사용자가 없습니다."
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
                  <BodyCell dense>{isAdminUser(user) ? 'Admin' : 'Member'}</BodyCell>
                  <BodyCell dense>
                    <span className="rounded border border-app-border px-1.5 py-0.5 text-gray-500">
                      {formatStatusLabel(user.status)}
                    </span>
                  </BodyCell>
                  <BodyCell className="max-w-[220px] truncate text-gray-500" dense>
                    {formatUserApps(user)}
                  </BodyCell>
                  <BodyCell className="text-gray-500" dense>{formatDateLabel(user.last_login_at)}</BodyCell>
                  <BodyCell className="text-gray-500" dense>{formatDateLabel(user.created_at)}</BodyCell>
                  <BodyCell className="text-right" dense>
                    <DropdownMenu
                      items={[
                        {
                          id: 'edit',
                          label: 'Edit user',
                          onSelect: () => startEditUser(user),
                        },
                        {
                          id: 'reset',
                          label: 'Reset password',
                          onSelect: () => {
                            void handleResetPassword(user.id);
                          },
                        },
                        {
                          id: 'delete',
                          label: deletingUserId === user.id ? 'Deleting user' : 'Delete user',
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
                          aria-label={`${user.email} actions`}
                          className="app-text-control rounded-md border border-app-border px-2 py-1 text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                          type="button"
                        >
                          More
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
          {firstVisibleUser}-{lastVisibleUser} of {totalUsers}
        </div>
        <div className="flex items-center gap-2">
          <button
            className="app-text-control rounded-md border border-app-border px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
            disabled={page <= 1 || isLoadingUsers}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            type="button"
          >
            Previous
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
            Next
          </button>
        </div>
      </div>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button disabled={isCreatingUser} onClick={closeCreateUserDialog} variant="secondary">
              Cancel
            </Button>
            <Button disabled={isCreatingUser} form="admin-user-create-form" type="submit" variant="primary">
              {isCreatingUser ? 'Creating' : 'Create'}
            </Button>
          </div>
        }
        description="계정을 만들고 조직, 그룹, workspace memberships 를 함께 배정합니다."
        dismissOnInteractOutside={false}
        maxWidth="max-w-2xl"
        onOpenChange={(open) => {
          if (!open) closeCreateUserDialog();
        }}
        open={inviteOpen}
        title="Create user"
      >
        <form className="grid gap-4" id="admin-user-create-form" onSubmit={(event) => void handleCreateUser(event)}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1">
              <span className="app-text-caption text-gray-500">Email</span>
              <input
                className={fieldClassName}
                id="admin-user-email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                required
                type="email"
                value={email}
              />
            </label>
            <label className="grid gap-1">
              <span className="app-text-caption text-gray-500">Full name</span>
              <input
                className={fieldClassName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Full name"
                required
                value={fullName}
              />
            </label>
            <label className="grid gap-1">
              <span className="app-text-caption text-gray-500">Display name</span>
              <input
                className={fieldClassName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Display name"
                value={displayName}
              />
            </label>
            <div className="grid gap-1">
              <span className="app-text-caption text-gray-500">Org unit</span>
              <Select
                onValueChange={setSelectedOrgUnitId}
                options={orgUnits.map((item) => ({ value: item.id, label: item.name }))}
                value={selectedOrgUnitId}
              />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <span className="app-text-caption text-gray-500">Groups</span>
              {groups.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                  선택 가능한 그룹이 없습니다.
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
            <div className="app-text-caption text-gray-500">Direct workspace memberships</div>
            {availableWorkspaces.length === 0 ? (
              <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                생성 가능한 workspace 가 없습니다.
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
              Selected workspaces: {selectedWorkspaceAppSummary}
              <br />
              그룹으로 상속되는 workspace memberships 도 함께 반영됩니다.
            </div>
          </div>
        </form>
      </Dialog>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button disabled={isSavingUser} onClick={closeEditUserDialog} variant="secondary">
              Cancel
            </Button>
            <Button
              disabled={isSavingUser || isLoadingEditAccessContext}
              form="admin-user-edit-form"
              type="submit"
              variant="primary"
            >
              {isSavingUser ? 'Saving' : 'Save'}
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
        title="Edit user"
      >
        <form className="grid gap-4" id="admin-user-edit-form" onSubmit={(event) => void handleUpdateUser(event)}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1">
              <span className="app-text-caption text-gray-500">Full name</span>
              <input
                className={fieldClassName}
                id="admin-user-edit-full-name"
                onChange={(event) => setEditFullName(event.target.value)}
                placeholder="Full name"
                required
                value={editFullName}
              />
            </label>
            <label className="grid gap-1">
              <span className="app-text-caption text-gray-500">Display name</span>
              <input
                className={fieldClassName}
                onChange={(event) => setEditDisplayName(event.target.value)}
                placeholder="Display name"
                value={editDisplayName}
              />
            </label>
            <label className="grid gap-1">
              <span className="app-text-caption text-gray-500">Status</span>
              <select
                className={fieldClassName}
                onChange={(event) => setEditStatus(event.target.value as typeof editStatus)}
                value={editStatus}
              >
                <option value="active">Active</option>
                <option value="invited">Invited</option>
                <option value="suspended">Suspended</option>
              </select>
            </label>
            <div className="grid gap-1">
              <span className="app-text-caption text-gray-500">Org unit</span>
              <Select
                onValueChange={setEditOrgUnitId}
                options={orgUnits.map((item) => ({ value: item.id, label: item.name }))}
                value={editOrgUnitId}
              />
            </div>
            <div className="grid gap-2 md:col-span-2">
              <span className="app-text-caption text-gray-500">Groups</span>
              {groups.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                  선택 가능한 그룹이 없습니다.
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
            <div className="app-text-caption text-gray-500">Direct workspace memberships</div>
            {availableWorkspaces.length === 0 ? (
              <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                생성된 workspace 가 없습니다.
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
              Effective workspaces: {editWorkspaceAppSummary}
            </div>
            <div className="grid gap-2">
              <div className="app-text-caption text-gray-500">Inherited workspace access</div>
              {isLoadingEditAccessContext ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                  사용자의 workspace access 를 확인하는 중입니다.
                </div>
              ) : editInheritedWorkspaceIds.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                  그룹을 통해 상속된 workspace access 가 없습니다.
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
              <div className="app-text-caption text-gray-500">PMS spaces</div>
              {isLoadingEditAccessContext ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                  PMS space membership 을 불러오는 중입니다.
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
                      <option value="">추가할 PMS space 를 선택하세요</option>
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
                      <option value="member">Member</option>
                      <option value="admin">Admin</option>
                    </select>
                    <Button
                      disabled={isSavingUser || !selectedPmsSpaceId}
                      onClick={() => stageAddPmsSpace()}
                      variant="secondary"
                    >
                      Add space
                    </Button>
                  </div>
                  <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
                    새 space 를 추가할 때 필요한 workspace membership 이 없으면 direct membership 에 자동으로 포함됩니다.
                  </div>
                  {editPmsSpaces.length === 0 ? (
                    <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                      소속된 PMS space 가 없습니다.
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
                            <option value="viewer">Viewer</option>
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                            <option value="owner">Owner</option>
                          </select>
                          <div className="flex justify-end">
                            <Button
                              disabled={isSavingUser}
                              onClick={() => stageRemovePmsSpace(space.id)}
                              variant="secondary"
                            >
                              Remove
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
      title="새 워크스페이스 만들기"
      description="협업 공간을 생성합니다. 생성 직후 본인이 자동으로 admin 으로 등록되고 기본 Team Space 가 함께 만들어집니다."
      dismissOnInteractOutside={false}
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            취소
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="create-workspace-form"
            disabled={busy || !name.trim()}
          >
            {busy ? '만드는 중...' : '워크스페이스 만들기'}
          </Button>
        </>
      }
    >
      <form id="create-workspace-form" className="grid gap-4" onSubmit={(e) => void handleSubmit(e)}>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">이름</span>
          <input
            autoFocus
            className={fieldClassName}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="예: Delivery Hub"
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">설명 (선택)</span>
          <textarea
            className={`${fieldClassName} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="이 워크스페이스에서 어떤 일을 하나요?"
            maxLength={1000}
          />
        </label>
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <p className="app-text-caption text-app-ink/60">
          앱(AI/Docs/PMS/Planner/Meeting)은 생성 후 워크스페이스 detail 의 Apps 탭에서 토글할 수 있습니다.
        </p>
      </form>
    </Dialog>
  );
}

function WorkspacesSection({ token }: { token: string }) {
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
        flashError(getErrorMessage(caughtError, '워크스페이스 목록을 불러오지 못했습니다.'));
      }
    },
    [token, flashError],
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
        flashError(getErrorMessage(caughtError, '워크스페이스 정보를 불러오지 못했습니다.'));
      }
    })();
  }, [token, canReadGroups, flashError]);

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
        return a.name.localeCompare(b.name);
      });
  }, [workspaces, filter, searchQuery]);

  async function handleCreateWorkspace(payload: { name: string; description: string }) {
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createWorkspace(token, payload);
      setCreateOpen(false);
      await reloadWorkspaces(created.id);
      flashSuccess(`워크스페이스 "${created.name}" 를 만들었습니다.`);
    } catch (caughtError) {
      setCreateError(getErrorMessage(caughtError, '워크스페이스를 만들지 못했습니다.'));
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
              Workspaces · {workspaces.length}
            </h2>
            {canCreateWorkspaces ? (
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                aria-label="새 워크스페이스 만들기"
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
                placeholder="이름, key 검색"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <Tabs value={filter} onValueChange={(value) => setFilter(value as WorkspaceFilter)}>
              <TabsList className="w-full">
                <TabsTrigger className="flex-1" value="active">
                  활성
                </TabsTrigger>
                <TabsTrigger className="flex-1" value="archived">
                  보관
                </TabsTrigger>
                <TabsTrigger className="flex-1" value="all">
                  전체
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <div className="max-h-[640px] overflow-y-auto pb-1">
            {filteredWorkspaces.length === 0 ? (
              <div className="px-3 py-8 text-center text-app-ink/60">
                <p className="app-text-body-sm">표시할 워크스페이스가 없습니다.</p>
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
                        {workspace.key} · {workspace.member_count}명
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
        setError(getErrorMessage(userResult.reason, '사용자 디렉터리를 불러오지 못했습니다.'));
      }

      if (groupResult.status === 'fulfilled') {
        setGroups(groupResult.value);
      } else if (canReadGroups) {
        setError(getErrorMessage(groupResult.reason, '권한 그룹을 불러오지 못했습니다.'));
      }

      if (workspaceResult.status === 'fulfilled') {
        setWorkspaces(workspaceResult.value.filter((workspace) => workspace.active));
      } else if (canReadGroups) {
        setError((current) => current ?? getErrorMessage(workspaceResult.reason, '워크스페이스를 불러오지 못했습니다.'));
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '권한 설정을 불러오지 못했습니다.'));
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
      setMessage('그룹을 생성했습니다.');
      await load();
      setSelectedTemplateGroupId(created.id);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹을 생성하지 못했습니다.'));
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
      setMessage('그룹 workspace templates 를 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹 workspace templates 를 저장하지 못했습니다.'));
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
      setMessage('그룹 정보를 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹 정보를 저장하지 못했습니다.'));
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
      setMessage('그룹 멤버를 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹 멤버를 저장하지 못했습니다.'));
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
      return leftName.localeCompare(rightName, 'ko');
    });
  const groupMemberCandidates = users
    .filter((user) => !selectedGroupMemberIds.includes(user.id))
    .sort((left, right) => {
      const leftName = left.display_name || left.full_name;
      const rightName = right.display_name || right.full_name;
      return leftName.localeCompare(rightName, 'ko');
    });

  return (
    <div className="space-y-6">


      <SectionMessage error={error} message={message} />

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard
          description="그룹은 사용자 묶음이며, 필요하면 시스템 역할을 함께 연결할 수 있습니다."
          title="Create principal group"
        >
          {canWriteGroups ? (
            <form className="grid gap-3" onSubmit={(event) => void handleCreateGroup(event)}>
              <input
                className={fieldClassName}
                onChange={(event) => setName(event.target.value)}
                placeholder="Group name"
                value={name}
              />
              <input
                className={fieldClassName}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Description"
                value={description}
              />
              <input
                className={fieldClassName}
                onChange={(event) => setSystemRoles(event.target.value)}
                placeholder="platform_admin"
                value={systemRoles}
              />
              <div className="flex justify-end">
                <Button type="submit" variant="primary">Create group</Button>
              </div>
            </form>
          ) : (
            <InlineNotice tone="warning">
              그룹 생성 권한이 없어 이 섹션은 읽기 전용입니다.
            </InlineNotice>
          )}
        </SurfaceCard>

        <SurfaceCard
          description="그룹에 연결된 시스템 역할과 현재 멤버 수를 확인합니다."
          title="Principal groups"
        >
          {canReadGroups ? (
            <TableShell>
              <thead>
                <tr>
                  <HeadCell>Name</HeadCell>
                  <HeadCell>Slug</HeadCell>
                  <HeadCell>System roles</HeadCell>
                  <HeadCell>Workspace templates</HeadCell>
                  <HeadCell>Members</HeadCell>
                </tr>
              </thead>
              <tbody>
                {groups.length === 0 ? (
                  <EmptyRow
                    colSpan={5}
                    description="새 권한 그룹을 만들어 시작하세요."
                    title="등록된 권한 그룹이 없습니다."
                  />
                ) : (
                  groups.map((group) => (
                    <tr key={group.id}>
                      <BodyCell>
                        <div className="font-medium text-app-ink">{group.name}</div>
                        <div className="app-text-caption mt-1 text-gray-500">{group.description || '설명 없음'}</div>
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
              그룹 조회 권한이 없어 권한 그룹 목록을 볼 수 없습니다.
            </InlineNotice>
          )}
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard
          actions={canReadGroups && canWriteGroups ? <Button disabled={isSavingGroupDetails || !selectedTemplateGroup} onClick={() => { void handleSaveGroupDetails(); }} variant="primary">{isSavingGroupDetails ? 'Saving group' : 'Save group'}</Button> : undefined}
          description="선택한 그룹의 기본 정보와 시스템 역할을 수정합니다."
          title="Group details"
        >
          {!canReadGroups ? (
            <InlineNotice tone="warning">
              그룹 조회 권한이 없어 상세 정보를 편집할 수 없습니다.
            </InlineNotice>
          ) : groups.length === 0 ? (
            <InlineNotice tone="info">
              먼저 그룹을 만들어야 상세 정보를 편집할 수 있습니다.
            </InlineNotice>
          ) : (
            <div className="grid gap-3">
              <div className="grid gap-1">
                <span className="app-text-caption text-gray-500">Group</span>
                <Select
                  disabled={!canWriteGroups}
                  onValueChange={setSelectedTemplateGroupId}
                  options={groups.map((group) => ({ value: group.id, label: group.name }))}
                  value={selectedTemplateGroupId}
                />
              </div>
              <div className="grid gap-1">
                <span className="app-text-caption text-gray-500">Slug</span>
                <div className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
                  {selectedTemplateGroup?.slug ?? '-'}
                </div>
              </div>
              <input
                className={fieldClassName}
                disabled={!canWriteGroups || !selectedTemplateGroup}
                onChange={(event) => setGroupName(event.target.value)}
                placeholder="Group name"
                value={groupName}
              />
              <input
                className={fieldClassName}
                disabled={!canWriteGroups || !selectedTemplateGroup}
                onChange={(event) => setGroupDescription(event.target.value)}
                placeholder="Description"
                value={groupDescription}
              />
              <input
                className={fieldClassName}
                disabled={!canWriteGroups || !selectedTemplateGroup}
                onChange={(event) => setGroupSystemRoles(event.target.value)}
                placeholder="platform_admin"
                value={groupSystemRoles}
              />
              <label className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
                <input
                  checked={groupActive}
                  disabled={!canWriteGroups || !selectedTemplateGroup}
                  onChange={(event) => setGroupActive(event.target.checked)}
                  type="checkbox"
                />
                <span>Group is active</span>
              </label>
            </div>
          )}
        </SurfaceCard>

        <SurfaceCard
          actions={canReadGroups && canReadUsers && canWriteGroups ? <Button disabled={isSavingGroupMembers || !selectedTemplateGroupId} onClick={() => { void handleSaveGroupMembers(); }} variant="primary">{isSavingGroupMembers ? 'Saving members' : 'Save members'}</Button> : undefined}
          description="선택한 그룹의 현재 멤버를 관리합니다."
          title="Group members"
        >
          {!canReadGroups || !canReadUsers ? (
            <InlineNotice tone="warning">
              그룹 또는 사용자 디렉터리 조회 권한이 없어 멤버를 편집할 수 없습니다.
            </InlineNotice>
          ) : groups.length === 0 ? (
            <InlineNotice tone="info">
              먼저 그룹을 만들어야 멤버를 연결할 수 있습니다.
            </InlineNotice>
          ) : (
            <div className="grid gap-4">
              <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                <Select
                  disabled={!canWriteGroups || groupMemberCandidates.length === 0}
                  onValueChange={setSelectedMemberCandidateId}
                  options={[
                    { value: NONE_OPTION_VALUE, label: 'Add a member' },
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
                  Add member
                </Button>
              </div>
              {selectedGroupMembers.length === 0 ? (
                <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                  아직 이 그룹의 멤버가 없습니다.
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
                        Remove
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
        actions={canReadGroups && canWriteGroups ? <Button disabled={isSavingGroupTemplates || !selectedTemplateGroupId} onClick={() => { void handleSaveGroupTemplates(); }} variant="primary">{isSavingGroupTemplates ? 'Saving templates' : 'Save templates'}</Button> : undefined}
        description="그룹에 사용자를 넣었을 때 상속되는 workspace memberships 를 정의합니다."
        title="Group workspace templates"
      >
        {!canReadGroups ? (
          <InlineNotice tone="warning">
            그룹 조회 권한이 없어 workspace template 을 편집할 수 없습니다.
          </InlineNotice>
        ) : groups.length === 0 ? (
          <InlineNotice tone="info">
            먼저 그룹을 만들어야 workspace template 을 연결할 수 있습니다.
          </InlineNotice>
        ) : workspaces.length === 0 ? (
          <InlineNotice tone="info">
            연결 가능한 active workspace 가 없습니다.
          </InlineNotice>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-1 md:max-w-sm">
              <span className="app-text-caption text-gray-500">Group</span>
              <Select
                disabled={!canWriteGroups}
                onValueChange={setSelectedTemplateGroupId}
                options={groups.map((group) => ({ value: group.id, label: group.name }))}
                value={selectedTemplateGroupId}
              />
            </div>
            {selectedTemplateGroup ? (
              <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
                선택한 그룹: {selectedTemplateGroup.name}
                <br />
                이 그룹에 사용자를 넣으면 아래 workspace memberships 가 상속됩니다.
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
                          {workspace.description || '설명 없음'}
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
                      <option value="member">Member</option>
                      <option value="admin">Admin</option>
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
  const { user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listAuditLogs(token)
      .then(setItems)
      .catch((caughtError) => {
        setError(getErrorMessage(caughtError, '감사로그를 불러오지 못했습니다.'));
      });
  }, [token]);

  return (
    <div className="space-y-6">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}



      <SurfaceCard
        description="최신 순으로 정렬된 운영 로그입니다."
        title="Recent activity"
      >
        <div className="space-y-3">
          {items.length === 0 ? (
            <div className="app-text-body rounded-xl border border-dashed border-app-border bg-app-surface-sidebar px-4 py-8 text-center text-gray-500">
              표시할 감사 이벤트가 없습니다.
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
                      {item.entity_kind} / {item.entity_id ?? 'n/a'} / {item.actor_name ?? 'system'}
                    </div>
                  </div>
                  <div className="app-text-body text-gray-500">
                    {formatDateTime(item.created_at, {
                      dateStyle: 'medium',
                      locale: 'ko-KR',
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
    return <AccessDeniedView description="관리 콘솔 접근 권한이 없습니다." />;
  }

  let content: React.ReactNode;
  let actions: React.ReactNode;

  switch (section) {
    case 'general':
      content = <GeneralSection token={token} />;
      break;
    case 'people':
      content = <PeopleSection token={token} />;
      actions = <Badge tone="purple">Admin only</Badge>;
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
      actions = <Badge tone="purple">Restricted</Badge>;
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
