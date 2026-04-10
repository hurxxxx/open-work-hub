import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';

import { Button, Dialog, DropdownMenu, InlineNotice, Select } from '@aidoo/ui';

import {
  createAdminUser,
  createGroup,
  createWorkspace,
  deleteAdminUser,
  listAdminUsers,
  listAuditLogs,
  listFeaturePolicies,
  listGroups,
  listOrgUnits,
  listTeams,
  listWorkspaceBindings,
  listWorkspaces,
  replaceWorkspaceBindings,
  resetUserPassword,
  updateAdminUser,
  updateFeaturePolicies,
  type AccessGroupItem,
  type AuditLogItem,
  type FeaturePolicyItem,
  type OrgUnitItem,
  type WorkspaceBindingItem,
  type WorkspaceItem,
} from './admin-api';
import {
  hasAnyAdminReadPermission,
  type AdminSection,
} from './admin-permissions';
import type { AuthUser } from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';

const NONE_OPTION_VALUE = '__none__';
const PEOPLE_PAGE_SIZE = 20;
const PEOPLE_EXPORT_PAGE_SIZE = 100;
const APP_WORKSPACE_LABELS: Record<string, string> = {
  ai: 'AI',
  docs: 'Docs',
  pms: 'PMS',
  planner: 'Planner',
  meeting: 'Meeting',
};
const fieldClassName =
  'app-text-body w-full rounded-lg border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none transition-colors focus:border-app-accent';

const sectionMeta: Record<
  AdminSection,
  { title: string; description: string; learnMoreLabel?: string }
> = {
  general: {
    title: 'General settings',
    description: '공통 사용자, 공간, 워크스페이스, 권한 정책의 현재 상태를 한곳에서 확인합니다.',
  },
  people: {
    title: 'Manage people',
    description: '',
    learnMoreLabel: 'Learn more',
  },
  workspaces: {
    title: 'Manage workspaces',
    description: '업무 영역과 접근 바인딩을 관리합니다.',
  },
  security: {
    title: 'Security & permissions',
    description: '권한 그룹과 기능 노출 정책을 운영합니다.',
  },
  audit: {
    title: 'Audit logs',
    description: '관리 작업과 인증 이벤트를 시간순으로 추적합니다.',
  },
};

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

function getInitials(label: string): string {
  const value = label
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return value || 'TM';
}

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return '-';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return '-';
  }

  return parsed.toLocaleDateString('en-US', {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
  });
}

function isAdminUser(user: Pick<AuthUser, 'system_roles'>): boolean {
  return user.system_roles.length > 0;
}

function formatUserApps(user: Pick<AuthUser, 'app_access'>): string {
  return user.app_access
    .map((item) => APP_WORKSPACE_LABELS[item.app] ?? item.workspace_name ?? item.app)
    .join(', ') || '-';
}

function formatUserGroups(user: Pick<AuthUser, 'group_slugs'>): string {
  return user.group_slugs.join(', ') || '-';
}

function formatStatusLabel(status: string): string {
  if (status === 'active') return 'Active';
  if (status === 'invited') return 'Invited';
  if (status === 'suspended') return 'Suspended';
  return status || '-';
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

function SurfaceCard({
  title,
  description,
  children,
  actions,
  className = '',
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`space-y-4 ${className}`.trim()}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="app-text-title-md text-app-ink">{title}</h2>
          {description ? <p className="app-text-body mt-1 text-gray-500">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      <div>{children}</div>
    </section>
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

function Badge({
  children,
  tone = 'default',
}: {
  children: React.ReactNode;
  tone?: 'default' | 'purple' | 'green' | 'amber';
}) {
  const toneClassName =
    tone === 'purple'
      ? 'border-app-accent/20 bg-app-accent/10 text-app-accent'
      : tone === 'green'
        ? 'border-green-500/20 bg-green-500/10 text-green-600 dark:text-green-400'
        : tone === 'amber'
          ? 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-300'
          : 'border-app-border bg-app-surface-sidebar text-gray-500';

  return (
    <span className={`app-text-label inline-flex items-center rounded-full border px-2.5 py-1 ${toneClassName}`.trim()}>
      {children}
    </span>
  );
}

function SectionMessage({
  message,
  error,
}: {
  message: string | null;
  error: string | null;
}) {
  if (!message && !error) {
    return null;
  }

  return (
    <div className="space-y-3">
      {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
    </div>
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
    policyCount: null as number | null,
    enabledPolicyCount: null as number | null,
    auditCount: null as number | null,
  });
  const [error, setError] = useState<string | null>(null);
  const canReadUsers = auth.hasPermission('user.read');
  const canReadGroups = auth.hasPermission('group.read');
  const canReadWorkspaces = auth.hasPermission('workspace.read');
  const canReadTeams = auth.hasPermission('team.read');
  const canReadPolicies = auth.hasPermission('feature_policy.read');
  const canReadAudit = auth.hasPermission('audit.read');

  function formatCount(value: number | null) {
    return value ?? 'Restricted';
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [users, groups, workspaces, teams, policies, audits] = await Promise.all([
          canReadUsers ? listAdminUsers(token, { page_size: 100 }) : Promise.resolve(null),
          canReadGroups ? listGroups(token) : Promise.resolve(null),
          canReadWorkspaces ? listWorkspaces(token) : Promise.resolve(null),
          canReadTeams ? listTeams(token) : Promise.resolve(null),
          canReadPolicies ? listFeaturePolicies(token) : Promise.resolve(null),
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
          policyCount: policies?.length ?? null,
          enabledPolicyCount: policies?.filter((item) => item.enabled).length ?? null,
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
    canReadPolicies,
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
                <div>기능 정책 {formatCount(summary.policyCount)}{summary.policyCount !== null ? '개' : ''}</div>
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
              사용자, PMS 공간, 워크스페이스, 권한 정책은 좌측 서브사이드바를 기준으로 분리합니다.
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
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [selectedAppWorkspaceIds, setSelectedAppWorkspaceIds] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter] = useState<'all' | 'admin' | 'member'>('all');
  const [selectedOrgUnitId, setSelectedOrgUnitId] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState(NONE_OPTION_VALUE);
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
  const [editGroupId, setEditGroupId] = useState(NONE_OPTION_VALUE);
  const [editAppWorkspaceIds, setEditAppWorkspaceIds] = useState<string[]>([]);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState<string | null>(null);
  const appWorkspaces = useMemo(
    () => workspaces.filter((workspace) => workspace.active && workspace.key in APP_WORKSPACE_LABELS),
    [workspaces],
  );
  const totalPages = Math.max(1, Math.ceil(totalUsers / PEOPLE_PAGE_SIZE));
  const firstVisibleUser = totalUsers === 0 ? 0 : (page - 1) * PEOPLE_PAGE_SIZE + 1;
  const lastVisibleUser = Math.min(totalUsers, (page - 1) * PEOPLE_PAGE_SIZE + users.length);

  async function loadDirectoryOptions() {
    try {
      const [groupItems, orgUnitItems, workspaceItems] = await Promise.all([
        listGroups(token),
        listOrgUnits(token),
        listWorkspaces(token),
      ]);
      setGroups(groupItems);
      setOrgUnits(orgUnitItems);
      setWorkspaces(workspaceItems);
      setSelectedOrgUnitId((current) => current || orgUnitItems[0]?.id || '');
      setSelectedGroupId((current) => {
        if (current !== NONE_OPTION_VALUE && groupItems.some((item) => item.id === current)) {
          return current;
        }
        return groupItems[0]?.id ?? NONE_OPTION_VALUE;
      });
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '사용자 정보를 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [groupItems, orgUnitItems, workspaceItems] = await Promise.all([
          listGroups(token),
          listOrgUnits(token),
          listWorkspaces(token),
        ]);
        if (cancelled) {
          return;
        }
        setGroups(groupItems);
        setOrgUnits(orgUnitItems);
        setWorkspaces(workspaceItems);
        setSelectedOrgUnitId((current) => current || orgUnitItems[0]?.id || '');
        setSelectedGroupId((current) => {
          if (current !== NONE_OPTION_VALUE && groupItems.some((item) => item.id === current)) {
            return current;
          }
          return groupItems[0]?.id ?? NONE_OPTION_VALUE;
        });
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

  function resolveUserAppWorkspaceIds(user: AuthUser) {
    const workspaceIds = new Set<string>();
    const appWorkspaceByKey = new Map(appWorkspaces.map((workspace) => [workspace.key, workspace]));
    for (const role of user.workspace_roles) {
      if (appWorkspaces.some((workspace) => workspace.id === role.workspace_id)) {
        workspaceIds.add(role.workspace_id);
      }
    }
    for (const access of user.app_access) {
      const workspace = access.workspace_key ? appWorkspaceByKey.get(access.workspace_key) : null;
      if (workspace) {
        workspaceIds.add(workspace.id);
      }
    }
    return Array.from(workspaceIds);
  }

  async function syncUserAppAccess(userId: string, selectedWorkspaceIds: string[]) {
    const selectedIds = new Set(selectedWorkspaceIds);
    for (const workspace of appWorkspaces) {
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
        group_ids: selectedGroupId !== NONE_OPTION_VALUE ? [selectedGroupId] : [],
      });
      await syncUserAppAccess(response.user.id, selectedAppWorkspaceIds);
      setEmail('');
      setFullName('');
      setDisplayName('');
      setSelectedAppWorkspaceIds([]);
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
    setEditGroupId(user.group_ids[0] ?? NONE_OPTION_VALUE);
    setEditAppWorkspaceIds(resolveUserAppWorkspaceIds(user));
    requestAnimationFrame(() => {
      document.getElementById('admin-user-edit-full-name')?.focus();
    });
  }

  async function handleUpdateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingUserId) {
      return;
    }

    setMessage(null);
    setError(null);
    setIsSavingUser(true);

    try {
      await updateAdminUser(token, editingUserId, {
        full_name: editFullName.trim(),
        display_name: editDisplayName.trim() || editFullName.trim(),
        primary_org_unit_id: editOrgUnitId || undefined,
        group_ids: editGroupId !== NONE_OPTION_VALUE ? [editGroupId] : [],
        status: editStatus,
      });
      await syncUserAppAccess(editingUserId, editAppWorkspaceIds);
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
          isAdminUser(user) ? 'Admin' : 'Member',
          formatStatusLabel(user.status),
          formatDateLabel(user.last_login_at),
          formatDateLabel(user.created_at),
          formatUserApps(user),
        ]);

      const header = ['Name', 'Email', 'Org', 'Groups', 'Role', 'Status', 'Last active', 'Created on', 'Apps'];
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
        <table className="app-text-body-sm min-w-[1180px] w-full border-collapse">
          <thead>
            <tr className="bg-app-surface-sidebar/40">
              <HeadCell className="w-[270px]" dense>User</HeadCell>
              <HeadCell className="w-[150px]" dense>Org</HeadCell>
              <HeadCell className="w-[150px]" dense>Groups</HeadCell>
              <HeadCell className="w-[90px]" dense>Role</HeadCell>
              <HeadCell className="w-[100px]" dense>Status</HeadCell>
              <HeadCell className="w-[220px]" dense>Apps</HeadCell>
              <HeadCell className="w-[110px]" dense>Last active</HeadCell>
              <HeadCell className="w-[110px]" dense>Created</HeadCell>
              <HeadCell className="w-[72px] text-right" dense>Actions</HeadCell>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="app-text-body-sm border-b border-app-border px-3 py-2 text-gray-500" colSpan={9}>
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
                colSpan={9}
                description="잠시만 기다려 주세요."
                title="사용자 목록을 불러오는 중입니다."
              />
            ) : filteredUsers.length === 0 ? (
              <EmptyRow
                colSpan={9}
                description="검색어를 바꾸거나 생성 버튼으로 사용자를 추가하세요."
                title="조건에 맞는 사용자가 없습니다."
              />
            ) : (
              filteredUsers.map((user) => (
                <tr className="transition-colors hover:bg-app-surface-hover/40" key={user.id}>
                  <BodyCell dense>
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="app-text-micro flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-app-surface-sidebar text-gray-500">
                        {getInitials(user.display_name || user.full_name)}
                      </div>
                      <div className="min-w-0">
                        <div className="truncate font-medium text-app-ink">{user.display_name || user.full_name}</div>
                        <div className="app-text-caption truncate text-gray-500">{user.email}</div>
                      </div>
                    </div>
                  </BodyCell>
                  <BodyCell className="max-w-[150px] truncate text-gray-500" dense>
                    {user.primary_org_unit?.name ?? '-'}
                  </BodyCell>
                  <BodyCell className="max-w-[150px] truncate text-gray-500" dense>
                    {formatUserGroups(user)}
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
        description="계정을 만들고 조직, 그룹, 접근 가능한 앱을 함께 배정합니다."
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
            <div className="grid gap-1 md:col-span-2">
              <span className="app-text-caption text-gray-500">Group</span>
              <Select
                onValueChange={setSelectedGroupId}
                options={[
                  { value: NONE_OPTION_VALUE, label: 'No group' },
                  ...groups.map((item) => ({ value: item.id, label: item.name })),
                ]}
                value={selectedGroupId}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <div className="app-text-caption text-gray-500">Accessible apps</div>
            {appWorkspaces.length === 0 ? (
              <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                접근 가능한 앱 워크스페이스가 없습니다.
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {appWorkspaces.map((workspace) => (
                  <label
                    className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                    key={workspace.id}
                  >
                    <input
                      checked={selectedAppWorkspaceIds.includes(workspace.id)}
                      onChange={() => toggleWorkspaceSelection(setSelectedAppWorkspaceIds, workspace.id)}
                      type="checkbox"
                    />
                    <span>{APP_WORKSPACE_LABELS[workspace.key] ?? workspace.name}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </form>
      </Dialog>

      <Dialog
        actions={
          <div className="flex w-full items-center justify-end gap-2">
            <Button disabled={isSavingUser} onClick={closeEditUserDialog} variant="secondary">
              Cancel
            </Button>
            <Button disabled={isSavingUser} form="admin-user-edit-form" type="submit" variant="primary">
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
            <div className="grid gap-1 md:col-span-2">
              <span className="app-text-caption text-gray-500">Group</span>
              <Select
                onValueChange={setEditGroupId}
                options={[
                  { value: NONE_OPTION_VALUE, label: 'No group' },
                  ...groups.map((item) => ({ value: item.id, label: item.name })),
                ]}
                value={editGroupId}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <div className="app-text-caption text-gray-500">Accessible apps</div>
            {appWorkspaces.length === 0 ? (
              <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-gray-500">
                접근 가능한 앱 워크스페이스가 없습니다.
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {appWorkspaces.map((workspace) => (
                  <label
                    className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                    key={workspace.id}
                  >
                    <input
                      checked={editAppWorkspaceIds.includes(workspace.id)}
                      onChange={() => toggleWorkspaceSelection(setEditAppWorkspaceIds, workspace.id)}
                      type="checkbox"
                    />
                    <span>{APP_WORKSPACE_LABELS[workspace.key] ?? workspace.name}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </form>
      </Dialog>
    </div>
  );
}

function WorkspacesSection({ token }: { token: string }) {
  const auth = useAuth();
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [bindings, setBindings] = useState<WorkspaceBindingItem[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [selectedUserId, setSelectedUserId] = useState(NONE_OPTION_VALUE);
  const [selectedGroupId, setSelectedGroupId] = useState(NONE_OPTION_VALUE);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canCreateWorkspaces = auth.hasPermission('workspace.write');
  const canReadUsers = auth.hasPermission('user.read');
  const canReadGroups = auth.hasPermission('group.read');
  const canManageBindings = canCreateWorkspaces;
  const selectedWorkspace = useMemo(
    () => workspaces.find((item) => item.id === selectedWorkspaceId) ?? null,
    [selectedWorkspaceId, workspaces],
  );
  const isPmsWorkspace = selectedWorkspace?.key === 'pms';

  async function load() {
    try {
      setError(null);
      const [workspaceItems, userResponse, groupItems] = await Promise.all([
        listWorkspaces(token),
        canReadUsers
          ? listAdminUsers(token, { page_size: 100 })
          : Promise.resolve({ items: [], total: 0, page: 1, page_size: 100 }),
        canReadGroups ? listGroups(token) : Promise.resolve([]),
      ]);
      setWorkspaces(workspaceItems);
      setUsers(userResponse.items);
      setGroups(groupItems);
      const workspaceId = selectedWorkspaceId || workspaceItems[0]?.id || '';
      setSelectedWorkspaceId(workspaceId);
      if (workspaceId) {
        setBindings(await listWorkspaceBindings(token, workspaceId));
      } else {
        setBindings([]);
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '워크스페이스 정보를 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    void load();
  }, [canReadGroups, canReadUsers, token]);

  async function handleCreateWorkspace(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreateWorkspaces) {
      return;
    }
    setMessage(null);
    setError(null);

    try {
      await createWorkspace(token, {
        name: name.trim(),
        description: description.trim(),
      });
      setName('');
      setDescription('');
      setMessage('워크스페이스를 생성했습니다.');
      await load();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '워크스페이스를 생성하지 못했습니다.'));
    }
  }

  async function handleAddBindings() {
    if (!selectedWorkspaceId || !canManageBindings) {
      return;
    }

    setMessage(null);
    setError(null);

    try {
      const nextUsers = [...bindings.filter((item) => item.subject_type === 'user')];
      const nextGroups = [...bindings.filter((item) => item.subject_type === 'group')];

      if (selectedUserId !== NONE_OPTION_VALUE) {
        nextUsers.push({
          subject_id: selectedUserId,
          subject_type: 'user',
          subject_label: users.find((item) => item.id === selectedUserId)?.email ?? selectedUserId,
          role: 'member',
        });
      }
      if (selectedGroupId !== NONE_OPTION_VALUE) {
        nextGroups.push({
          subject_id: selectedGroupId,
          subject_type: 'group',
          subject_label: groups.find((item) => item.id === selectedGroupId)?.name ?? selectedGroupId,
          role: isPmsWorkspace ? 'member' : 'viewer',
        });
      }

      const response = await replaceWorkspaceBindings(token, selectedWorkspaceId, {
        users: Array.from(new Map(nextUsers.map((item) => [item.subject_id, item])).values()).map((item) => ({
          subject_id: item.subject_id,
          role: item.role,
        })),
        groups: Array.from(new Map(nextGroups.map((item) => [item.subject_id, item])).values()).map((item) => ({
          subject_id: item.subject_id,
          role: item.role,
        })),
      });
      setBindings(response);
      setMessage(isPmsWorkspace ? 'PMS 앱 접근 바인딩을 저장했습니다.' : '워크스페이스 바인딩을 저장했습니다.');
      setSelectedUserId(NONE_OPTION_VALUE);
      setSelectedGroupId(NONE_OPTION_VALUE);
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          isPmsWorkspace ? 'PMS 앱 접근 바인딩을 저장하지 못했습니다.' : '워크스페이스 바인딩을 저장하지 못했습니다.',
        ),
      );
    }
  }

  return (
    <div className="space-y-6">


      <SectionMessage error={error} message={message} />

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <SurfaceCard
          description="업무 영역 이름과 설명을 정의합니다."
          title="Create workspace"
        >
          <form className="grid gap-3" onSubmit={(event) => void handleCreateWorkspace(event)}>
            <input
              className={fieldClassName}
              disabled={!canCreateWorkspaces}
              onChange={(event) => setName(event.target.value)}
              placeholder="Workspace name"
              value={name}
            />
            <input
              className={fieldClassName}
              disabled={!canCreateWorkspaces}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Description"
              value={description}
            />
            <div className="flex justify-end">
              <Button disabled={!canCreateWorkspaces} type="submit" variant="primary">Create workspace</Button>
            </div>
          </form>
        </SurfaceCard>

        <SurfaceCard
          description={
            isPmsWorkspace
              ? 'PMS는 앱 접근만 여기서 관리하고, 실제 권한은 PMS 내부 스페이스 역할에서 관리합니다.'
              : '사용자 또는 그룹을 선택한 워크스페이스에 연결합니다.'
          }
          title={isPmsWorkspace ? 'PMS app access bindings' : 'Workspace access bindings'}
        >
          <div className="grid gap-3">
            <Select
              onValueChange={async (value) => {
                setSelectedWorkspaceId(value);
                setMessage(null);
                setError(null);
                try {
                  setBindings(await listWorkspaceBindings(token, value));
                } catch (caughtError) {
                  setBindings([]);
                  setError(getErrorMessage(caughtError, '워크스페이스 바인딩을 불러오지 못했습니다.'));
                }
              }}
              options={workspaces.map((item) => ({ value: item.id, label: item.name }))}
              value={selectedWorkspaceId}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <Select
                disabled={!canReadUsers || !canManageBindings}
                onValueChange={setSelectedUserId}
                options={[
                  { value: NONE_OPTION_VALUE, label: 'No user selected' },
                  ...users.map((item) => ({ value: item.id, label: item.email })),
                ]}
                value={selectedUserId}
              />
              <Select
                disabled={!canReadGroups || !canManageBindings}
                onValueChange={setSelectedGroupId}
                options={[
                  { value: NONE_OPTION_VALUE, label: 'No group selected' },
                  ...groups.map((item) => ({ value: item.id, label: item.name })),
                ]}
                value={selectedGroupId}
              />
            </div>
            {!canReadUsers || !canReadGroups ? (
              <InlineNotice tone="warning">
                사용자 또는 그룹 디렉터리 읽기 권한이 없어 새 바인딩 대상을 선택할 수 없습니다.
              </InlineNotice>
            ) : null}
            {isPmsWorkspace ? (
              <InlineNotice tone="default">
                PMS 바인딩은 접근 on/off만 의미합니다. 스페이스 내 관리자와 멤버 역할은 PMS 앱 내부에서 설정합니다.
              </InlineNotice>
            ) : null}
            <div className="flex justify-end">
              <Button disabled={!canManageBindings} onClick={() => { void handleAddBindings(); }} variant="primary">Save bindings</Button>
            </div>
            <div className="grid gap-2">
              {bindings.length === 0 ? (
                <div className="app-text-body rounded-xl border border-dashed border-app-border bg-app-surface-sidebar px-4 py-6 text-gray-500">
                  아직 바인딩이 없습니다.
                </div>
              ) : (
                bindings.map((binding) => (
                  <div
                    key={`${binding.subject_type}-${binding.subject_id}`}
                    className="flex items-center justify-between rounded-xl border border-app-border bg-app-surface-sidebar px-4 py-3"
                  >
                    <div>
                      <div className="font-medium text-app-ink">{binding.subject_label}</div>
                      <div className="app-text-caption mt-1 text-gray-500">{binding.subject_type}</div>
                    </div>
                    <Badge tone="purple">{isPmsWorkspace ? 'access enabled' : binding.role}</Badge>
                  </div>
                ))
              )}
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard
        description="등록된 워크스페이스와 연결된 공간 수를 요약합니다."
        title="Workspace directory"
      >
        <TableShell>
          <thead>
            <tr>
              <HeadCell>Name</HeadCell>
              <HeadCell>Key</HeadCell>
              <HeadCell>Description</HeadCell>
              <HeadCell>Spaces</HeadCell>
              <HeadCell>Status</HeadCell>
            </tr>
          </thead>
          <tbody>
            {workspaces.length === 0 ? (
              <EmptyRow
                colSpan={5}
                description="새 워크스페이스를 만들어 시작하세요."
                title="등록된 워크스페이스가 없습니다."
              />
            ) : (
              workspaces.map((workspace) => (
                <tr key={workspace.id}>
                  <BodyCell>
                    <div className="font-medium text-app-ink">{workspace.name}</div>
                  </BodyCell>
                  <BodyCell>{workspace.key}</BodyCell>
                  <BodyCell>{workspace.description || '설명 없음'}</BodyCell>
                  <BodyCell>{workspace.team_count}</BodyCell>
                  <BodyCell>
                    <Badge tone={workspace.active ? 'green' : 'amber'}>
                      {workspace.active ? 'active' : 'inactive'}
                    </Badge>
                  </BodyCell>
                </tr>
              ))
            )}
          </tbody>
        </TableShell>
      </SurfaceCard>
    </div>
  );
}

function SecuritySection({
  token,
  canReadGroups,
  canWriteGroups,
  canReadPolicies,
  canWritePolicies,
}: {
  token: string;
  canReadGroups: boolean;
  canWriteGroups: boolean;
  canReadPolicies: boolean;
  canWritePolicies: boolean;
}) {
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [policies, setPolicies] = useState<FeaturePolicyItem[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemRoles, setSystemRoles] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const results = await Promise.allSettled([
        canReadGroups ? listGroups(token) : Promise.resolve<AccessGroupItem[]>([]),
        canReadPolicies ? listFeaturePolicies(token) : Promise.resolve<FeaturePolicyItem[]>([]),
      ]);
      const [groupResult, policyResult] = results;

      if (groupResult.status === 'fulfilled') {
        setGroups(groupResult.value);
      } else if (canReadGroups) {
        setError(getErrorMessage(groupResult.reason, '권한 그룹을 불러오지 못했습니다.'));
      }

      if (policyResult.status === 'fulfilled') {
        setPolicies(policyResult.value);
      } else if (canReadPolicies) {
        setError((current) => current ?? getErrorMessage(policyResult.reason, '기능 정책을 불러오지 못했습니다.'));
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '권한 설정을 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    void load();
  }, [canReadGroups, canReadPolicies, token]);

  async function handleCreateGroup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWriteGroups) return;
    setMessage(null);
    setError(null);

    try {
      await createGroup(token, {
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
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹을 생성하지 못했습니다.'));
    }
  }

  async function handleSavePolicies() {
    if (!canWritePolicies) return;
    setMessage(null);
    setError(null);

    try {
      const response = await updateFeaturePolicies(
        token,
        policies.map((policy) => ({
          id: policy.id,
          enabled: policy.enabled,
        })),
      );
      setPolicies(response);
      setMessage('기능 정책을 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '기능 정책을 저장하지 못했습니다.'));
    }
  }

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
                placeholder="org_admin"
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
                  <HeadCell>Members</HeadCell>
                </tr>
              </thead>
              <tbody>
                {groups.length === 0 ? (
                  <EmptyRow
                    colSpan={4}
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

      <SurfaceCard
        actions={canReadPolicies && canWritePolicies ? <Button onClick={() => { void handleSavePolicies(); }} variant="primary">Save policies</Button> : undefined}
        description="각 워크스페이스와 도구 노출을 개별 정책으로 토글합니다."
        title="Feature access policies"
      >
        {canReadPolicies ? (
          <div className="grid gap-3">
            {policies.map((policy) => (
              <label
                key={policy.id}
                className="flex items-start gap-4 rounded-xl border border-app-border bg-app-surface-sidebar px-4 py-4"
              >
                <input
                  checked={policy.enabled}
                  className="mt-1"
                  disabled={!canWritePolicies}
                  onChange={(event) => {
                    setPolicies((current) =>
                      current.map((item) =>
                        item.id === policy.id ? { ...item, enabled: event.target.checked } : item,
                      ),
                    );
                  }}
                  type="checkbox"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <strong className="app-text-body text-app-ink">{policy.name}</strong>
                    <Badge tone={policy.enabled ? 'green' : 'default'}>
                      {policy.enabled ? 'enabled' : 'disabled'}
                    </Badge>
                  </div>
                  <div className="app-text-body mt-1 text-gray-500">{policy.description}</div>
                  <div className="app-text-caption mt-3 flex flex-wrap gap-2">
                    <Badge>{policy.code}</Badge>
                    {policy.allowed_workspace_keys.map((workspaceKey) => (
                      <Badge key={`${policy.id}-${workspaceKey}`}>{workspaceKey}</Badge>
                    ))}
                  </div>
                  {!canWritePolicies ? (
                    <div className="app-text-caption mt-3 text-gray-500">읽기 전용 정책입니다.</div>
                  ) : null}
                </div>
              </label>
            ))}
          </div>
        ) : (
          <InlineNotice tone="warning">
            기능 정책 조회 권한이 없어 정책 목록을 볼 수 없습니다.
          </InlineNotice>
        )}
      </SurfaceCard>
    </div>
  );
}

function AuditSection({ token }: { token: string }) {
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
                    {new Date(item.created_at).toLocaleString()}
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
          canReadGroups={auth.hasPermission('group.read')}
          canReadPolicies={auth.hasPermission('feature_policy.read')}
          canWriteGroups={auth.hasPermission('group.write')}
          canWritePolicies={auth.hasPermission('feature_policy.write')}
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
