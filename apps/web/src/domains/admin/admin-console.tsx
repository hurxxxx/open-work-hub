import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CalendarDays,
  Check,
  Copy,
  FileText,
  ListTodo,
  MoreHorizontal,
  Plus,
  Search,
  Shield,
  Users as UsersIcon,
  Video,
  type LucideIcon,
} from 'lucide-react';

import {
  Button,
  ConfirmDialog,
  Dialog,
  DropdownMenu,
  InlineNotice,
  Select,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@aidoo/ui';

import {
  addWorkspaceMember,
  bulkWorkspaceMembers,
  createAdminUser,
  createGroup,
  createWorkspace,
  deleteAdminUser,
  deleteWorkspace,
  getWorkspaceApps,
  listAdminUsers,
  listAuditLogs,
  listFeaturePolicies,
  listGroups,
  listOrgUnits,
  listUserTeamMemberships,
  listTeams,
  listWorkspaceBindings,
  listWorkspaceMemberCandidates,
  listWorkspaceMembers,
  listWorkspaces,
  removeWorkspaceMember,
  replaceGroupMembers,
  replaceGroupWorkspaceBindings,
  replaceWorkspaceBindings,
  resetUserPassword,
  updateGroup,
  updateWorkspace,
  updateWorkspaceApps,
  updateWorkspaceMemberRole,
  updateAdminUser,
  updateFeaturePolicies,
  type AccessGroupItem,
  type AuditLogItem,
  type FeaturePolicyItem,
  type OrgUnitItem,
  type TeamItem,
  type WorkspaceBindingItem,
  type WorkspaceItem,
  type WorkspaceMemberCandidate,
  type WorkspaceMemberItem,
  type WorkspaceMembersResponse,
} from './admin-api';
import {
  hasAnyAdminReadPermission,
  type AdminSection,
} from './admin-permissions';
import type { AuthUser } from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import { addSpaceMember, removeSpaceMember, updateSpaceMemberRole } from '@/src/domains/pms/pms-api';

const NONE_OPTION_VALUE = '__none__';
const PEOPLE_PAGE_SIZE = 20;
const PEOPLE_EXPORT_PAGE_SIZE = 100;
const APP_LABELS: Record<string, string> = {
  ai: 'AI',
  docs: 'Docs',
  pms: 'PMS',
  planner: 'Planner',
  meeting: 'Meeting',
  admin: 'Admin',
};
const WORKSPACE_ENABLED_APP_LABELS = {
  ai: APP_LABELS.ai,
  docs: APP_LABELS.docs,
  pms: APP_LABELS.pms,
  planner: APP_LABELS.planner,
  meeting: APP_LABELS.meeting,
} satisfies Record<string, string>;
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
    title: 'Workspaces',
    description: '협업 공간을 만들고 멤버와 앱을 관리합니다.',
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

function formatAppCodes(codes: string[]): string {
  const labels = Array.from(
    new Set(codes.map((code) => APP_LABELS[code] ?? code)),
  );
  return labels.join(', ') || '-';
}

function collectUserAppCodes(
  user: Pick<AuthUser, 'workspaces' | 'app_access' | 'system_roles'>,
): string[] {
  const codes = new Set<string>();
  for (const workspace of user.workspaces) {
    for (const appCode of workspace.enabled_apps) {
      codes.add(appCode);
    }
  }
  for (const access of user.app_access ?? []) {
    codes.add(access.app);
  }
  if (user.system_roles.length > 0) {
    codes.add('admin');
  }
  return Array.from(codes);
}

function formatUserApps(
  user: Pick<AuthUser, 'workspaces' | 'app_access' | 'system_roles'>,
): string {
  return formatAppCodes(collectUserAppCodes(user));
}

function formatUserWorkspaces(user: Pick<AuthUser, 'workspaces'>): string {
  return user.workspaces.map((workspace) => workspace.name).join(', ') || '-';
}

const WORKSPACE_ROLE_RANK_DISPLAY: Record<string, number> = {
  admin: 0,
  member: 1,
};

function UserWorkspaceChips({ user }: { user: Pick<AuthUser, 'workspaces'> }) {
  if (user.workspaces.length === 0) {
    return <span className="text-app-ink/40">-</span>;
  }
  const sorted = [...user.workspaces].sort((a, b) => {
    const rankDiff =
      (WORKSPACE_ROLE_RANK_DISPLAY[a.role] ?? 99) - (WORKSPACE_ROLE_RANK_DISPLAY[b.role] ?? 99);
    if (rankDiff !== 0) return rankDiff;
    return a.name.localeCompare(b.name);
  });
  const visible = sorted.slice(0, 3);
  const hiddenCount = sorted.length - visible.length;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {visible.map((workspace) => {
        const isElevated = workspace.role === 'admin';
        return (
          <span
            key={workspace.id}
            className={`app-text-caption inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${
              isElevated
                ? 'border-app-accent/30 bg-app-accent/10 text-app-accent'
                : 'border-app-border bg-app-surface-sidebar text-app-ink/70'
            }`}
            title={`${workspace.name} · ${workspace.role}`}
          >
            <span>{workspace.name}</span>
            {isElevated ? (
              <span className="opacity-70">🛡</span>
            ) : null}
          </span>
        );
      })}
      {hiddenCount > 0 ? (
        <span
          className="app-text-caption text-app-ink/50"
          title={sorted
            .slice(3)
            .map((workspace) => `${workspace.name} (${workspace.role})`)
            .join(', ')}
        >
          +{hiddenCount}
        </span>
      ) : null}
    </div>
  );
}

function formatUserGroups(user: Pick<AuthUser, 'group_slugs'>): string {
  return user.group_slugs.join(', ') || '-';
}

function formatGroupWorkspaceBindings(group: Pick<AccessGroupItem, 'workspace_bindings'>): string {
  return group.workspace_bindings.map((binding) => binding.workspace_name).join(', ') || '-';
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
      formatAppCodes(
        availableWorkspaces
          .filter((workspace) => effectiveCreateWorkspaceIds.includes(workspace.id))
          .flatMap((workspace) => workspace.enabled_apps),
      ),
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
      formatAppCodes(
        availableWorkspaces
          .filter((workspace) => effectiveEditWorkspaceIds.includes(workspace.id))
          .flatMap((workspace) => workspace.enabled_apps),
      ),
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
                      · {formatAppCodes(workspace.enabled_apps)}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
              Enabled apps: {selectedWorkspaceAppSummary}
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
                      · {formatAppCodes(workspace.enabled_apps)}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3 text-gray-500">
              Effective enabled apps: {editWorkspaceAppSummary}
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

const WORKSPACE_ROLE_OPTIONS: { value: string; label: string; description: string }[] = [
  { value: 'admin', label: '관리자', description: '멤버와 설정 관리' },
  { value: 'member', label: '멤버', description: '워크스페이스 앱 사용' },
];
const WORKSPACE_ROLE_LABELS: Record<string, string> = WORKSPACE_ROLE_OPTIONS.reduce(
  (acc, option) => {
    acc[option.value] = option.label;
    return acc;
  },
  {} as Record<string, string>,
);
const WORKSPACE_ROLE_RANK: Record<string, number> = {
  admin: 0,
  member: 1,
};

const APP_DESCRIPTIONS: Record<string, string> = {
  ai: 'AI 검색과 어시스턴트',
  docs: '문서 작성과 지식 베이스',
  pms: '프로젝트와 이슈 관리',
  planner: '일정과 캘린더',
  meeting: '회의록과 첨부 자료',
};


function MemberRoleBadge({ role }: { role: string }) {
  if (role === 'admin') {
    return (
      <span className="app-text-caption inline-flex items-center gap-1 text-app-ink/70">
        <Shield className="text-app-ink/50" size={12} />
        관리자
      </span>
    );
  }
  return (
    <span className="app-text-caption text-app-ink/70">
      {WORKSPACE_ROLE_LABELS[role] ?? role}
    </span>
  );
}

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

function EditWorkspaceModal({
  open,
  workspace,
  onOpenChange,
  onSave,
  busy,
  error,
}: {
  open: boolean;
  workspace: WorkspaceItem | null;
  onOpenChange: (open: boolean) => void;
  onSave: (payload: { name: string; description: string }) => Promise<void>;
  busy: boolean;
  error: string | null;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (open && workspace) {
      setName(workspace.name);
      setDescription(workspace.description);
    }
  }, [open, workspace]);

  if (!workspace) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    await onSave({ name: trimmed, description: description.trim() });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="워크스페이스 편집"
      description="이름과 설명을 수정합니다. key 는 고정 식별자라 변경할 수 없습니다."
      dismissOnInteractOutside={false}
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            취소
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="edit-workspace-form"
            disabled={busy || !name.trim()}
          >
            {busy ? '저장 중...' : '저장'}
          </Button>
        </>
      }
    >
      <form id="edit-workspace-form" className="grid gap-4" onSubmit={(e) => void handleSubmit(e)}>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">이름</span>
          <input
            className={fieldClassName}
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">설명</span>
          <textarea
            className={`${fieldClassName} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={1000}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">Key</span>
          <input
            className={`${fieldClassName} cursor-not-allowed bg-app-surface-sidebar text-app-ink/60`}
            value={workspace.key}
            readOnly
          />
        </label>
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
      </form>
    </Dialog>
  );
}

function WorkspaceMemberRow({
  binding,
  canManage,
  isCurrentUser,
  busy,
  onChangeRole,
  onRemove,
}: {
  binding: WorkspaceBindingItem;
  canManage: boolean;
  isCurrentUser: boolean;
  busy: boolean;
  onChangeRole: (role: string) => void;
  onRemove: () => void;
}) {
  const showMenu = canManage && !isCurrentUser;
  const items: Parameters<typeof DropdownMenu>[0]['items'] = [
    ...WORKSPACE_ROLE_OPTIONS.map((option) => ({
      id: `role-${option.value}`,
      label: (
        <span className="flex items-center justify-between gap-2">
          <span className="flex flex-col">
            <span className="font-medium">{option.label}</span>
            <span className="app-text-caption text-app-ink/60">{option.description}</span>
          </span>
          {binding.role === option.value ? <Check size={14} className="text-app-accent" /> : null}
        </span>
      ),
      onSelect: () => {
        if (binding.role !== option.value) {
          onChangeRole(option.value);
        }
      },
      disabled: busy,
    })),
    {
      id: 'remove',
      label: '워크스페이스에서 제거',
      onSelect: onRemove,
      disabled: busy,
      tone: 'danger' as const,
      separatorBefore: true,
    },
  ];

  return (
    <div className="flex items-center gap-2 px-3 py-1.5">
      {binding.subject_type === 'group' ? (
        <UsersIcon size={12} className="shrink-0 text-app-ink/50" aria-label="그룹" />
      ) : (
        <span
          className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-app-ink/30"
          aria-label="사용자"
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="app-text-body-sm truncate text-app-ink">
          <span className="font-medium">{binding.subject_label}</span>
          {binding.subject_secondary ? (
            <span className="ml-2 text-app-ink/50">{binding.subject_secondary}</span>
          ) : null}
          {isCurrentUser ? <span className="ml-2 text-app-ink/40">(본인)</span> : null}
        </div>
      </div>
      <MemberRoleBadge role={binding.role} />
      {showMenu ? (
        <DropdownMenu
          trigger={
            <button
              type="button"
              className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
              aria-label="멤버 작업"
            >
              <MoreHorizontal size={14} />
            </button>
          }
          items={items}
        />
      ) : (
        <span className="inline-block w-6" />
      )}
    </div>
  );
}

// Subject selection contract — shared across inline picker, modal, and future
// org-chart picker. Stores user/group ids that have been ticked but not yet
// committed.
type SubjectKind = 'user' | 'group';

interface SelectedSubject {
  id: string;
  kind: SubjectKind;
  label: string;
  secondary?: string;
}

interface SubjectSelectionState {
  users: Map<string, SelectedSubject>;
  groups: Map<string, SelectedSubject>;
}

function emptySubjectSelection(): SubjectSelectionState {
  return { users: new Map(), groups: new Map() };
}

function selectionSize(selection: SubjectSelectionState): number {
  return selection.users.size + selection.groups.size;
}

function toggleSubject(
  selection: SubjectSelectionState,
  subject: SelectedSubject,
): SubjectSelectionState {
  const target = subject.kind === 'user' ? selection.users : selection.groups;
  const next = new Map(target);
  if (next.has(subject.id)) {
    next.delete(subject.id);
  } else {
    next.set(subject.id, subject);
  }
  return subject.kind === 'user'
    ? { ...selection, users: next }
    : { ...selection, groups: next };
}

function removeSubject(
  selection: SubjectSelectionState,
  kind: SubjectKind,
  id: string,
): SubjectSelectionState {
  const target = kind === 'user' ? selection.users : selection.groups;
  if (!target.has(id)) return selection;
  const next = new Map(target);
  next.delete(id);
  return kind === 'user'
    ? { ...selection, users: next }
    : { ...selection, groups: next };
}

function PeopleDirectoryGrid({
  token,
  selection,
  onToggleSelect,
  excludeIds,
  membershipLabel = '이미 멤버',
  className,
}: {
  token: string;
  selection: SubjectSelectionState;
  onToggleSelect: (subject: SelectedSubject) => void;
  excludeIds: Set<string>;
  membershipLabel?: string;
  className?: string;
}) {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(search.trim()), 200);
    return () => window.clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const response = await listAdminUsers(token, {
          page,
          page_size: PEOPLE_PAGE_SIZE,
          q: debouncedSearch || undefined,
        });
        if (!cancelled) {
          setUsers(response.items);
          setTotal(response.total);
        }
      } catch {
        if (!cancelled) {
          setUsers([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, page, debouncedSearch]);

  const totalPages = Math.max(1, Math.ceil(total / PEOPLE_PAGE_SIZE));

  return (
    <div className={`flex h-full flex-col ${className ?? ''}`}>
      <div className="flex items-center gap-2 border-b border-app-border px-3 py-2">
        <div className="flex flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
          <Search size={12} className="text-app-ink/50" />
          <input
            className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
            placeholder="이름 또는 이메일로 검색"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            autoFocus
          />
        </div>
        <span className="app-text-caption text-app-ink/50">총 {total} 명</span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="app-text-body-sm w-full">
          <thead className="sticky top-0 bg-app-bg">
            <tr className="border-b border-app-border">
              <th className="w-8 px-2 py-1.5 text-left"></th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">사용자</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">조직</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">그룹</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">워크스페이스</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">상태</th>
              <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">최근</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && !loading ? (
              <tr>
                <td colSpan={7} className="px-2 py-8 text-center text-app-ink/60">
                  결과 없음
                </td>
              </tr>
            ) : (
              users.map((user) => {
                const isExcluded = excludeIds.has(user.id);
                const isChecked = selection.users.has(user.id);
                return (
                  <tr
                    key={user.id}
                    className={`border-b border-app-border/50 ${
                      isExcluded ? 'opacity-50' : 'hover:bg-app-surface-hover/40'
                    }`}
                  >
                    <td className="px-2 py-1">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={isExcluded}
                        onChange={() =>
                          onToggleSelect({
                            id: user.id,
                            kind: 'user',
                            label: user.display_name || user.full_name,
                            secondary: user.email,
                          })
                        }
                      />
                    </td>
                    <td className="px-2 py-1">
                      <div className="min-w-0">
                        <span className="font-medium text-app-ink">
                          {user.display_name || user.full_name}
                        </span>
                        <span className="ml-2 text-app-ink/50">{user.email}</span>
                      </div>
                    </td>
                    <td className="max-w-[140px] truncate px-2 py-1 text-app-ink/60">
                      {user.primary_org_unit?.name ?? '-'}
                    </td>
                    <td className="max-w-[140px] truncate px-2 py-1 text-app-ink/60">
                      {formatUserGroups(user)}
                    </td>
                    <td className="px-2 py-1">
                      <UserWorkspaceChips user={user} />
                    </td>
                    <td className="px-2 py-1">
                      {isExcluded ? (
                        <Badge tone="green">{membershipLabel}</Badge>
                      ) : user.status === 'invited' ? (
                        <Badge tone="amber">초대</Badge>
                      ) : user.status === 'suspended' ? (
                        <Badge tone="amber">정지</Badge>
                      ) : (
                        <span className="text-app-ink/60">활성</span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-app-ink/60">
                      {formatDateLabel(user.last_login_at)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-app-border px-3 py-1.5">
        <span className="app-text-caption text-app-ink/60">
          {total === 0
            ? '0'
            : `${(page - 1) * PEOPLE_PAGE_SIZE + 1}-${Math.min(page * PEOPLE_PAGE_SIZE, total)} / ${total}`}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            이전
          </Button>
          <span className="app-text-caption px-2 text-app-ink/60">
            {page} / {totalPages}
          </span>
          <Button
            variant="ghost"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            다음
          </Button>
        </div>
      </div>
    </div>
  );
}

function SelectedSubjectsBar({
  selection,
  onRemove,
}: {
  selection: SubjectSelectionState;
  onRemove: (kind: SubjectKind, id: string) => void;
}) {
  const all: SelectedSubject[] = [
    ...Array.from(selection.groups.values()),
    ...Array.from(selection.users.values()),
  ];
  if (all.length === 0) {
    return (
      <div className="app-text-caption text-app-ink/40">선택한 사용자가 없습니다.</div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {all.map((subject) => (
        <span
          key={`${subject.kind}-${subject.id}`}
          className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-0.5 text-app-ink"
        >
          {subject.kind === 'group' ? <UsersIcon size={11} /> : null}
          <span>{subject.label}</span>
          <button
            type="button"
            className="text-app-ink/50 hover:text-app-ink"
            onClick={() => onRemove(subject.kind, subject.id)}
            aria-label={`${subject.label} 선택 해제`}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

function SubjectPickerInline({
  workspaceId,
  token,
  groups,
  excludeIds,
  selection,
  onSelectionChange,
  canReadGroups,
  onOpenDirectory,
}: {
  workspaceId: string;
  token: string;
  groups: AccessGroupItem[];
  excludeIds: Set<string>;
  selection: SubjectSelectionState;
  onSelectionChange: (next: SubjectSelectionState) => void;
  canReadGroups: boolean;
  onOpenDirectory: () => void;
}) {
  const [tab, setTab] = useState<'user' | 'group'>('user');
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [candidates, setCandidates] = useState<WorkspaceMemberCandidate[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(query.trim()), 150);
    return () => window.clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    if (tab !== 'user') return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const items = await listWorkspaceMemberCandidates(
          token,
          workspaceId,
          debouncedQuery || undefined,
        );
        if (!cancelled) {
          setCandidates(items);
        }
      } catch {
        // silent
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, debouncedQuery, token, workspaceId]);

  const filteredGroups = useMemo(() => {
    const trimmed = debouncedQuery.toLowerCase();
    const items = groups.filter((g) => !excludeIds.has(g.id));
    if (!trimmed) return items.slice(0, 50);
    return items
      .filter(
        (g) =>
          g.name.toLowerCase().includes(trimmed) || g.slug.toLowerCase().includes(trimmed),
      )
      .slice(0, 50);
  }, [groups, debouncedQuery, excludeIds]);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className={`app-text-control rounded px-2 py-0.5 ${
            tab === 'user'
              ? 'bg-app-surface-sidebar text-app-ink'
              : 'text-app-ink/60 hover:text-app-ink'
          }`}
          onClick={() => setTab('user')}
        >
          사용자
        </button>
        <button
          type="button"
          disabled={!canReadGroups}
          className={`app-text-control rounded px-2 py-0.5 ${
            tab === 'group'
              ? 'bg-app-surface-sidebar text-app-ink'
              : 'text-app-ink/60 hover:text-app-ink disabled:cursor-not-allowed disabled:text-app-ink/30'
          }`}
          onClick={() => setTab('group')}
        >
          그룹
        </button>
        <button
          type="button"
          className="app-text-control ml-auto rounded px-2 py-0.5 text-app-accent hover:bg-app-accent/10"
          onClick={onOpenDirectory}
        >
          임직원 디렉터리 열기
        </button>
      </div>

      <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
        <Search size={12} className="text-app-ink/50" />
        <input
          className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
          placeholder={tab === 'user' ? '이름 또는 이메일' : '그룹 이름'}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoFocus
        />
      </div>

      <div className="max-h-[240px] overflow-y-auto rounded-md border border-app-border bg-app-bg">
        {tab === 'user' ? (
          loading && candidates.length === 0 ? (
            <div className="app-text-caption px-3 py-3 text-app-ink/60">불러오는 중...</div>
          ) : candidates.filter((c) => !excludeIds.has(c.id)).length === 0 ? (
            <div className="app-text-caption px-3 py-3 text-app-ink/60">결과 없음</div>
          ) : (
            candidates
              .filter((c) => !excludeIds.has(c.id))
              .map((candidate) => {
                const checked = selection.users.has(candidate.id);
                return (
                  <label
                    key={candidate.id}
                    className="app-text-body-sm flex w-full cursor-pointer items-center gap-2 border-b border-app-border/50 px-2 py-1 transition-colors last:border-b-0 hover:bg-app-surface-sidebar"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        onSelectionChange(
                          toggleSubject(selection, {
                            id: candidate.id,
                            kind: 'user',
                            label: candidate.full_name || candidate.email,
                            secondary: candidate.email,
                          }),
                        )
                      }
                    />
                    <span className="font-medium text-app-ink">
                      {candidate.full_name || candidate.email}
                    </span>
                    <span className="ml-1 truncate text-app-ink/50">{candidate.email}</span>
                  </label>
                );
              })
          )
        ) : !canReadGroups ? (
          <div className="app-text-caption px-3 py-3 text-app-ink/60">
            그룹 디렉터리 읽기 권한이 없습니다.
          </div>
        ) : filteredGroups.length === 0 ? (
          <div className="app-text-caption px-3 py-3 text-app-ink/60">결과 없음</div>
        ) : (
          filteredGroups.map((group) => {
            const checked = selection.groups.has(group.id);
            return (
              <label
                key={group.id}
                className="app-text-body-sm flex w-full cursor-pointer items-center gap-2 border-b border-app-border/50 px-2 py-1 transition-colors last:border-b-0 hover:bg-app-surface-sidebar"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() =>
                    onSelectionChange(
                      toggleSubject(selection, {
                        id: group.id,
                        kind: 'group',
                        label: group.name,
                        secondary: group.slug,
                      }),
                    )
                  }
                />
                <UsersIcon size={11} className="text-app-ink/50" />
                <span className="font-medium text-app-ink">{group.name}</span>
                <span className="ml-1 truncate text-app-ink/50">{group.slug}</span>
              </label>
            );
          })
        )}
      </div>
    </div>
  );
}

function PeoplePickerModal({
  open,
  onClose,
  token,
  selection,
  onSelectionChange,
  excludeIds,
}: {
  open: boolean;
  onClose: () => void;
  token: string;
  selection: SubjectSelectionState;
  onSelectionChange: (next: SubjectSelectionState) => void;
  excludeIds: Set<string>;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title="임직원 디렉터리"
      description="검색과 필터로 사용자를 찾아 다중 선택합니다. 여기서 선택한 항목은 아래 추가 패널의 선택 목록에 누적됩니다."
      maxWidth="max-w-[1600px]"
      dismissOnInteractOutside={false}
      actions={
        <>
          <span className="app-text-body mr-auto text-app-ink/60">
            현재 선택: {selectionSize(selection)} 명
          </span>
          <Button variant="primary" onClick={onClose}>
            완료
          </Button>
        </>
      }
    >
      <div className="h-[70vh] overflow-hidden rounded-xl border border-app-border bg-app-bg">
        <PeopleDirectoryGrid
          token={token}
          selection={selection}
          onToggleSelect={(subject) =>
            onSelectionChange(toggleSubject(selection, subject))
          }
          excludeIds={excludeIds}
        />
      </div>
    </Dialog>
  );
}

function WorkspaceMembersDrawer({
  open,
  onOpenChange,
  workspace,
  token,
  canManage,
  currentUserId,
  onChanged,
  onError,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspace: WorkspaceItem | null;
  token: string;
  canManage: boolean;
  currentUserId: string;
  onChanged: () => void;
  onError: (msg: string) => void;
  onSuccess: (msg: string) => void;
}) {
  const [data, setData] = useState<WorkspaceMembersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const [pendingOnly, setPendingOnly] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [bulkRoleOpen, setBulkRoleOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelectedKeys(new Set());
  }, [open, workspace?.id, debouncedQuery, roleFilter, pendingOnly, page]);

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => setDebouncedQuery(query.trim()), 200);
    return () => window.clearTimeout(handle);
  }, [query, open]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, roleFilter, pendingOnly]);

  const reload = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    try {
      const response = await listWorkspaceMembers(token, workspace.id, {
        q: debouncedQuery || undefined,
        role: roleFilter ? [roleFilter] : undefined,
        page,
        pageSize,
        pendingOnly,
      });
      setData(response);
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, '멤버를 불러오지 못했습니다.'));
    } finally {
      setLoading(false);
    }
  }, [token, workspace, debouncedQuery, roleFilter, page, pageSize, pendingOnly, onError]);

  useEffect(() => {
    if (!open) return;
    void reload();
  }, [open, reload]);

  if (!workspace) return null;

  const memberSubjectIds = new Set((data?.items ?? []).map((item) => item.subject_id));

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  function toggleSelect(item: WorkspaceMemberItem) {
    const key = `${item.subject_type}:${item.subject_id}`;
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    if (!data) return;
    const allSelectableKeys = data.items
      .filter(
        (item) =>
          !(
            item.subject_type === 'user' &&
            item.subject_id === currentUserId
          ),
      )
      .map((item) => `${item.subject_type}:${item.subject_id}`);
    setSelectedKeys((current) => {
      if (allSelectableKeys.every((key) => current.has(key)) && allSelectableKeys.length > 0) {
        return new Set();
      }
      return new Set(allSelectableKeys);
    });
  }

  async function handleSingleRoleChange(item: WorkspaceMemberItem, role: string) {
    if (!workspace) return;
    setBusy(true);
    try {
      await updateWorkspaceMemberRole(token, workspace.id, item.subject_type, item.subject_id, role);
      onSuccess('역할을 변경했습니다.');
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, '역할을 변경하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleSingleRemove(item: WorkspaceMemberItem) {
    if (!workspace) return;
    setBusy(true);
    try {
      await removeWorkspaceMember(token, workspace.id, item.subject_type, item.subject_id);
      onSuccess('멤버를 제거했습니다.');
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, '멤버를 제거하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkRemove() {
    if (!workspace) return;
    if (selectedKeys.size === 0) return;
    setBusy(true);
    try {
      const subjects = Array.from(selectedKeys).map((key) => {
        const [subject_type, subject_id] = key.split(':') as ['user' | 'group', string];
        return { subject_type, subject_id };
      });
      const result = await bulkWorkspaceMembers(token, workspace.id, {
        action: 'remove',
        subjects,
      });
      if (result.failed.length > 0) {
        onError(`${result.succeeded}명 제거됨, ${result.failed.length}명 실패`);
      } else {
        onSuccess(`${result.succeeded}명을 제거했습니다.`);
      }
      setSelectedKeys(new Set());
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, '일괄 제거에 실패했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkRole(role: string) {
    if (!workspace) return;
    if (selectedKeys.size === 0) return;
    setBulkRoleOpen(false);
    setBusy(true);
    try {
      const subjects = Array.from(selectedKeys).map((key) => {
        const [subject_type, subject_id] = key.split(':') as ['user' | 'group', string];
        return { subject_type, subject_id, role };
      });
      const result = await bulkWorkspaceMembers(token, workspace.id, {
        action: 'update_role',
        subjects,
      });
      if (result.failed.length > 0) {
        onError(`${result.succeeded}명 변경됨, ${result.failed.length}명 실패`);
      } else {
        onSuccess(`${result.succeeded}명의 역할을 변경했습니다.`);
      }
      setSelectedKeys(new Set());
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, '일괄 역할 변경에 실패했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`${workspace.name} 멤버 관리`}
      description="검색, 필터, 일괄 작업으로 워크스페이스 멤버를 관리합니다."
      maxWidth="max-w-[1600px]"
      dismissOnInteractOutside={false}
    >
      <div className="space-y-4">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[220px] items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5">
            <Search size={14} className="text-app-ink/50" />
            <input
              className="app-text-body flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
              placeholder="이름, 이메일, 그룹 이름"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>

        {/* Role chips */}
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip
            label={`전체 ${data?.total ?? 0}`}
            active={roleFilter === null && !pendingOnly}
            onClick={() => {
              setRoleFilter(null);
              setPendingOnly(false);
            }}
          />
          {(['admin', 'member'] as const).map((role) => (
            <FilterChip
              key={role}
              label={`${WORKSPACE_ROLE_LABELS[role]} ${data?.role_counts[role] ?? 0}`}
              active={roleFilter === role && !pendingOnly}
              onClick={() => {
                setRoleFilter(role);
                setPendingOnly(false);
              }}
            />
          ))}
          {data && data.pending_count > 0 ? (
            <FilterChip
              label={`초대 대기 ${data.pending_count}`}
              active={pendingOnly}
              tone="warning"
              onClick={() => {
                setPendingOnly(true);
                setRoleFilter(null);
              }}
            />
          ) : null}
        </div>

        {/* Bulk action bar */}
        {selectedKeys.size > 0 ? (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-app-accent/40 bg-app-accent/10 px-3 py-2">
            <span className="app-text-body text-app-ink">
              {selectedKeys.size} 명 선택됨
            </span>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Button
                  variant="ghost"
                  onClick={() => setBulkRoleOpen((current) => !current)}
                  disabled={busy}
                >
                  역할 변경
                </Button>
                {bulkRoleOpen ? (
                  <div className="absolute right-0 top-full z-10 mt-1 min-w-[160px] rounded-md border border-app-border bg-app-bg shadow-lg">
                    {WORKSPACE_ROLE_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        className="app-text-body flex w-full items-center justify-between px-3 py-2 text-left text-app-ink hover:bg-app-surface-sidebar"
                        onClick={() => void handleBulkRole(option.value)}
                      >
                        <span>{option.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <Button
                variant="ghost"
                onClick={() => void handleBulkRemove()}
                disabled={busy}
                className="text-[var(--ui-color-danger)]"
              >
                제거
              </Button>
              <Button variant="ghost" onClick={() => setSelectedKeys(new Set())}>
                해제
              </Button>
            </div>
          </div>
        ) : null}

        {/* Table */}
        <div className="overflow-hidden rounded-xl border border-app-border">
          <table className="w-full">
            <thead className="bg-app-surface-sidebar">
              <tr>
                <th className="w-10 px-3 py-2 text-left">
                  {canManage ? (
                    <input
                      type="checkbox"
                      onChange={toggleSelectAll}
                      checked={
                        data !== null &&
                        data.items.length > 0 &&
                        data.items
                          .filter(
                            (item) =>
                              !(
                                item.subject_type === 'user' &&
                                item.subject_id === currentUserId
                              ),
                          )
                          .every((item) =>
                            selectedKeys.has(`${item.subject_type}:${item.subject_id}`),
                          )
                      }
                    />
                  ) : null}
                </th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">이름</th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">Role</th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">상태</th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">최근</th>
                <th className="w-10 px-2 py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {loading && !data ? (
                <tr>
                  <td colSpan={6} className="px-2 py-8 text-center text-app-ink/60">
                    불러오는 중...
                  </td>
                </tr>
              ) : (data?.items.length ?? 0) === 0 ? (
                <tr>
                  <td colSpan={6} className="px-2 py-8 text-center text-app-ink/60">
                    표시할 멤버가 없습니다.
                  </td>
                </tr>
              ) : (
                data!.items.map((item) => {
                  const key = `${item.subject_type}:${item.subject_id}`;
                  const isSelf =
                    item.subject_type === 'user' && item.subject_id === currentUserId;
                  return (
                    <tr key={key} className="border-b border-app-border/50">
                      <td className="px-2 py-1">
                        {canManage && !isSelf ? (
                          <input
                            type="checkbox"
                            checked={selectedKeys.has(key)}
                            onChange={() => toggleSelect(item)}
                          />
                        ) : null}
                      </td>
                      <td className="app-text-body-sm px-2 py-1">
                        {item.subject_type === 'group' ? (
                          <UsersIcon
                            size={11}
                            className="mr-1 inline text-app-ink/50 align-text-bottom"
                          />
                        ) : null}
                        <span className="font-medium text-app-ink">{item.subject_label}</span>
                        {item.subject_secondary ? (
                          <span className="ml-2 text-app-ink/50">{item.subject_secondary}</span>
                        ) : null}
                        {isSelf ? (
                          <span className="ml-2 text-app-ink/40">(본인)</span>
                        ) : null}
                      </td>
                      <td className="px-2 py-1">
                        <MemberRoleBadge role={item.role} />
                      </td>
                      <td className="app-text-body-sm px-2 py-1">
                        {item.subject_type === 'group' ? (
                          <span className="text-app-ink/60">그룹</span>
                        ) : item.user_status === 'invited' ? (
                          <Badge tone="amber">초대</Badge>
                        ) : item.user_status === 'suspended' ? (
                          <Badge tone="amber">정지</Badge>
                        ) : (
                          <span className="text-app-ink/60">활성</span>
                        )}
                      </td>
                      <td className="app-text-caption px-2 py-1 text-app-ink/60">
                        {formatDateLabel(item.last_login_at)}
                      </td>
                      <td className="px-2 py-1 text-right">
                        {canManage && !isSelf ? (
                          <DropdownMenu
                            trigger={
                              <button
                                type="button"
                                className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                                aria-label="멤버 작업"
                              >
                                <MoreHorizontal size={14} />
                              </button>
                            }
                            items={[
                              ...WORKSPACE_ROLE_OPTIONS.map((option) => ({
                                id: `role-${option.value}`,
                                label: (
                                  <span className="flex items-center justify-between gap-2">
                                    <span>{option.label}</span>
                                    {item.role === option.value ? (
                                      <Check size={14} className="text-app-accent" />
                                    ) : null}
                                  </span>
                                ),
                                onSelect: () => {
                                  if (item.role !== option.value) {
                                    void handleSingleRoleChange(item, option.value);
                                  }
                                },
                                disabled: busy,
                              })),
                              {
                                id: 'remove',
                                label: '워크스페이스에서 제거',
                                onSelect: () => void handleSingleRemove(item),
                                disabled: busy,
                                tone: 'danger' as const,
                                separatorBefore: true,
                              },
                            ]}
                          />
                        ) : null}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        {data && data.total > 0 ? (
          <div className="flex items-center justify-between gap-2">
            <span className="app-text-caption text-app-ink/60">
              {(data.page - 1) * data.page_size + 1}-
              {Math.min(data.page * data.page_size, data.total)} / {data.total}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                disabled={data.page <= 1 || busy}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                이전
              </Button>
              <span className="app-text-caption px-2 text-app-ink/60">
                {data.page} / {totalPages}
              </span>
              <Button
                variant="ghost"
                disabled={data.page >= totalPages || busy}
                onClick={() => setPage((p) => p + 1)}
              >
                다음
              </Button>
            </div>
          </div>
        ) : null}
      </div>

    </Dialog>
  );
}

function FilterChip({
  label,
  active,
  onClick,
  tone,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  tone?: 'warning';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`app-text-control rounded-full border px-3 py-1 transition-colors ${
        active
          ? tone === 'warning'
            ? 'border-amber-500 bg-amber-500/10 text-amber-600 dark:text-amber-300'
            : 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/70 hover:bg-app-surface-sidebar'
      }`}
    >
      {label}
    </button>
  );
}

const APP_ICONS: Record<string, LucideIcon> = {
  ai: Bot,
  docs: FileText,
  pms: ListTodo,
  planner: CalendarDays,
  meeting: Video,
};

const APP_ORDER: string[] = ['ai', 'docs', 'pms', 'planner', 'meeting'];

function ToggleSwitch({
  checked,
  disabled,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
        checked ? 'bg-app-accent' : 'bg-app-border'
      } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-[18px]' : 'translate-x-[2px]'
        }`}
      />
    </button>
  );
}

function AppToggleRow({
  appCode,
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  appCode: string;
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}) {
  const Icon = APP_ICONS[appCode] ?? FileText;
  return (
    <div className="flex items-center gap-2 px-3 py-1.5">
      <Icon size={14} className="shrink-0 text-app-ink/60" />
      <div className="min-w-0 flex-1">
        <span className="app-text-body-sm font-medium text-app-ink">{label}</span>
        <span className="app-text-caption ml-2 text-app-ink/50">{description}</span>
      </div>
      <ToggleSwitch
        ariaLabel={`${label} 토글`}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
      />
    </div>
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
  const [bindings, setBindings] = useState<WorkspaceBindingItem[]>([]);
  const [selectedEnabledApps, setSelectedEnabledApps] = useState<string[]>([]);
  const [originalEnabledApps, setOriginalEnabledApps] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [confirmState, setConfirmState] = useState<
    | null
    | {
        title: string;
        description: string;
        confirmLabel: string;
        variant: 'default' | 'danger';
        onConfirm: () => Promise<void>;
      }
  >(null);
  const [membersDrawerOpen, setMembersDrawerOpen] = useState(false);
  const [addPanelOpen, setAddPanelOpen] = useState(false);
  const [addPickerOpen, setAddPickerOpen] = useState(false);
  const [addSelection, setAddSelection] = useState<SubjectSelectionState>(emptySubjectSelection);
  const [addRole, setAddRole] = useState('member');
  const [addBusy, setAddBusy] = useState(false);

  const resetAddPanel = useCallback(() => {
    setAddPanelOpen(false);
    setAddPickerOpen(false);
    setAddSelection(emptySubjectSelection());
    setAddRole('member');
  }, []);

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
        const target = preserveSelection ?? selectedWorkspaceId;
        if (target && items.some((item) => item.id === target)) {
          setSelectedWorkspaceId(target);
        } else {
          const fallback =
            items.find((item) => item.active) ?? items[0] ?? null;
          setSelectedWorkspaceId(fallback?.id ?? null);
        }
      } catch (caughtError) {
        flashError(getErrorMessage(caughtError, '워크스페이스 목록을 불러오지 못했습니다.'));
      }
    },
    [token, selectedWorkspaceId, flashError],
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

  useEffect(() => {
    if (!selectedWorkspaceId) {
      setBindings([]);
      setSelectedEnabledApps([]);
      setOriginalEnabledApps([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const [nextBindings, nextApps] = await Promise.all([
          listWorkspaceBindings(token, selectedWorkspaceId),
          getWorkspaceApps(token, selectedWorkspaceId),
        ]);
        if (!cancelled) {
          setBindings(nextBindings);
          setSelectedEnabledApps(nextApps.enabled_apps);
          setOriginalEnabledApps(nextApps.enabled_apps);
        }
      } catch (caughtError) {
        if (!cancelled) {
          flashError(getErrorMessage(caughtError, '워크스페이스 상세를 불러오지 못했습니다.'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, selectedWorkspaceId, flashError]);

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

  const sortedBindings = useMemo(
    () =>
      [...bindings].sort((a, b) => {
        const rankDiff =
          (WORKSPACE_ROLE_RANK[a.role] ?? 99) - (WORKSPACE_ROLE_RANK[b.role] ?? 99);
        if (rankDiff !== 0) return rankDiff;
        return a.subject_label.localeCompare(b.subject_label);
      }),
    [bindings],
  );

  const groupBindings = useMemo(
    () => sortedBindings.filter((binding) => binding.subject_type === 'group'),
    [sortedBindings],
  );

  const previewBindings = useMemo(() => {
    const userBindings = sortedBindings.filter((binding) => binding.subject_type === 'user');
    // Show admins first as preview (max 5).
    const result: WorkspaceBindingItem[] = [];
    for (const binding of userBindings) {
      if (binding.role === 'admin') {
        result.push(binding);
      }
      if (result.length >= 5) break;
    }
    if (result.length === 0 && userBindings.length > 0) {
      // No admins among the loaded bindings — show top members instead.
      return userBindings.slice(0, 5);
    }
    return result;
  }, [sortedBindings]);

  const memberSubjectIds = useMemo(
    () => new Set(bindings.map((binding) => binding.subject_id)),
    [bindings],
  );

  const appsDirty = useMemo(() => {
    if (selectedEnabledApps.length !== originalEnabledApps.length) return true;
    const set = new Set(originalEnabledApps);
    return selectedEnabledApps.some((app) => !set.has(app));
  }, [selectedEnabledApps, originalEnabledApps]);

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

  async function handleEditWorkspace(payload: { name: string; description: string }) {
    if (!selectedWorkspace) return;
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await updateWorkspace(token, selectedWorkspace.id, {
        name: payload.name,
        description: payload.description,
        active: selectedWorkspace.active,
      });
      setWorkspaces((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditOpen(false);
      flashSuccess('워크스페이스 정보를 저장했습니다.');
    } catch (caughtError) {
      setEditError(getErrorMessage(caughtError, '워크스페이스를 저장하지 못했습니다.'));
    } finally {
      setEditBusy(false);
    }
  }

  async function handleToggleActive(workspace: WorkspaceItem, nextActive: boolean) {
    setBusy(true);
    try {
      const updated = await updateWorkspace(token, workspace.id, {
        name: workspace.name,
        description: workspace.description,
        active: nextActive,
      });
      setWorkspaces((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      flashSuccess(
        nextActive ? '워크스페이스를 다시 활성화했습니다.' : '워크스페이스를 보관함으로 옮겼습니다.',
      );
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '워크스페이스 상태를 변경하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteWorkspace(workspace: WorkspaceItem) {
    setBusy(true);
    try {
      await deleteWorkspace(token, workspace.id);
      setWorkspaces((current) => current.filter((item) => item.id !== workspace.id));
      const fallback =
        workspaces.find((item) => item.id !== workspace.id && item.active) ?? null;
      setSelectedWorkspaceId(fallback?.id ?? null);
      flashSuccess(`워크스페이스 "${workspace.name}" 를 영구 삭제했습니다.`);
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '워크스페이스를 삭제하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleAddMember(payload: {
    subject_id: string;
    subject_type: 'user' | 'group';
    role: string;
  }) {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    try {
      const item = await addWorkspaceMember(token, selectedWorkspaceId, payload);
      setBindings((current) => [...current, item]);
      setWorkspaces((current) =>
        current.map((workspace) =>
          workspace.id === selectedWorkspaceId
            ? { ...workspace, member_count: workspace.member_count + 1 }
            : workspace,
        ),
      );
      flashSuccess('멤버를 추가했습니다.');
    } catch (caughtError) {
      throw caughtError;
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkAddSelection() {
    if (!selectedWorkspaceId) return;
    const totalSelected = selectionSize(addSelection);
    if (totalSelected === 0) return;
    setAddBusy(true);
    try {
      const subjects = [
        ...Array.from(addSelection.users.values()).map((subject) => ({
          subject_type: 'user' as const,
          subject_id: subject.id,
          role: addRole,
        })),
        ...Array.from(addSelection.groups.values()).map((subject) => ({
          subject_type: 'group' as const,
          subject_id: subject.id,
          role: addRole,
        })),
      ];
      const result = await bulkWorkspaceMembers(token, selectedWorkspaceId, {
        action: 'add',
        subjects,
      });
      if (result.failed.length > 0) {
        flashError(`${result.succeeded}명 추가됨, ${result.failed.length}명 실패`);
      } else {
        flashSuccess(`${result.succeeded}명을 추가했습니다.`);
      }
      // Refresh detail panel preview
      const refreshed = await listWorkspaceBindings(token, selectedWorkspaceId);
      setBindings(refreshed);
      setWorkspaces((current) =>
        current.map((workspace) =>
          workspace.id === selectedWorkspaceId
            ? {
                ...workspace,
                member_count: workspace.member_count + result.succeeded,
              }
            : workspace,
        ),
      );
      resetAddPanel();
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '멤버를 추가하지 못했습니다.'));
    } finally {
      setAddBusy(false);
    }
  }

  async function handleChangeMemberRole(binding: WorkspaceBindingItem, role: string) {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    try {
      const updated = await updateWorkspaceMemberRole(
        token,
        selectedWorkspaceId,
        binding.subject_type,
        binding.subject_id,
        role,
      );
      setBindings((current) =>
        current.map((item) =>
          item.subject_type === binding.subject_type && item.subject_id === binding.subject_id
            ? updated
            : item,
        ),
      );
      flashSuccess('역할을 변경했습니다.');
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '역할을 변경하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveMember(binding: WorkspaceBindingItem) {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    try {
      await removeWorkspaceMember(
        token,
        selectedWorkspaceId,
        binding.subject_type,
        binding.subject_id,
      );
      setBindings((current) =>
        current.filter(
          (item) =>
            !(
              item.subject_type === binding.subject_type && item.subject_id === binding.subject_id
            ),
        ),
      );
      setWorkspaces((current) =>
        current.map((workspace) =>
          workspace.id === selectedWorkspaceId
            ? { ...workspace, member_count: Math.max(0, workspace.member_count - 1) }
            : workspace,
        ),
      );
      flashSuccess('멤버를 제거했습니다.');
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '멤버를 제거하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveApps() {
    if (!selectedWorkspaceId) return;
    setBusy(true);
    try {
      const response = await updateWorkspaceApps(token, selectedWorkspaceId, selectedEnabledApps);
      setSelectedEnabledApps(response.enabled_apps);
      setOriginalEnabledApps(response.enabled_apps);
      setWorkspaces((current) =>
        current.map((workspace) =>
          workspace.id === selectedWorkspaceId
            ? { ...workspace, enabled_apps: response.enabled_apps }
            : workspace,
        ),
      );
      flashSuccess('Enabled apps 를 저장했습니다.');
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, 'Enabled apps 를 저장하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  function openConfirm(spec: {
    title: string;
    description: string;
    confirmLabel: string;
    variant: 'default' | 'danger';
    onConfirm: () => Promise<void>;
  }) {
    setConfirmState(spec);
  }

  function getDeleteBlockReason(workspace: WorkspaceItem): string | null {
    if (workspace.active) {
      return '워크스페이스를 먼저 보관함으로 옮겨야 영구 삭제할 수 있습니다.';
    }
    const blockers: string[] = [];
    if (workspace.team_count > 0) blockers.push(`${workspace.team_count}개 space`);
    if (workspace.meeting_count > 0) blockers.push(`${workspace.meeting_count}개 회의`);
    if (workspace.doc_count > 0) blockers.push(`${workspace.doc_count}개 문서`);
    if (blockers.length === 0) return null;
    return `${blockers.join(', ')} 가 남아있습니다. 먼저 비워주세요.`;
  }

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
                        {workspace.key} · {workspace.member_count}명 · {workspace.enabled_apps.length}앱
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <section className="flex min-h-[560px] flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
          {!selectedWorkspace ? (
            <div className="flex h-full items-center justify-center px-8 py-16 text-center text-app-ink/60">
              <div className="space-y-2">
                <p className="app-text-title-md text-app-ink">워크스페이스를 선택하세요</p>
                <p className="app-text-body">
                  왼쪽 목록에서 워크스페이스를 선택하면 상세 정보를 볼 수 있습니다.
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
                {/* Hero */}
                <header className="border-b border-app-border px-4 py-3">
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="app-text-title-md truncate text-app-ink">
                          {selectedWorkspace.name}
                        </h2>
                        {selectedWorkspace.active ? (
                          <Badge tone="green">활성</Badge>
                        ) : (
                          <Badge tone="amber">보관됨</Badge>
                        )}
                        <code className="app-text-caption rounded bg-app-surface-sidebar px-1.5 py-0.5 font-mono text-app-ink/70">
                          {selectedWorkspace.key}
                        </code>
                        <button
                          type="button"
                          onClick={() => {
                            try {
                              navigator.clipboard?.writeText(selectedWorkspace.key);
                              flashSuccess('Key 를 복사했습니다.');
                            } catch {
                              flashError('Key 를 복사하지 못했습니다.');
                            }
                          }}
                          className="rounded p-0.5 text-app-ink/50 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                          aria-label="Key 복사"
                        >
                          <Copy size={11} />
                        </button>
                        <span className="app-text-caption text-app-ink/50">
                          · 멤버 {selectedWorkspace.member_count} · 만든 날짜{' '}
                          {formatDateLabel(selectedWorkspace.created_at)}
                        </span>
                      </div>
                      {selectedWorkspace.description ? (
                        <p className="app-text-body-sm mt-1 whitespace-pre-wrap text-app-ink/85">
                          {selectedWorkspace.description}
                        </p>
                      ) : canManage ? (
                        <button
                          type="button"
                          onClick={() => {
                            setEditError(null);
                            setEditOpen(true);
                          }}
                          className="app-text-body-sm mt-1 italic text-app-ink/40 transition-colors hover:text-app-ink/70"
                        >
                          + 설명 추가
                        </button>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {canManage ? (
                        <Button
                          variant="ghost"
                          onClick={() => {
                            setEditError(null);
                            setEditOpen(true);
                          }}
                        >
                          편집
                        </Button>
                      ) : null}
                      {canManage ? (
                        <DropdownMenu
                          trigger={
                            <button
                              type="button"
                              className="rounded p-1 text-app-ink/70 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                              aria-label="워크스페이스 작업"
                            >
                              <MoreHorizontal size={16} />
                            </button>
                          }
                          items={[
                            selectedWorkspace.active
                              ? {
                                  id: 'archive',
                                  label: '보관함으로 옮기기',
                                  onSelect: () =>
                                    openConfirm({
                                      title: '워크스페이스 보관',
                                      description: `"${selectedWorkspace.name}" 을 보관함으로 옮기면 사용자가 더 이상 접근하지 못합니다. 멤버와 데이터는 보존되며 언제든 다시 활성화할 수 있습니다.`,
                                      confirmLabel: '보관하기',
                                      variant: 'default',
                                      onConfirm: () =>
                                        handleToggleActive(selectedWorkspace, false),
                                    }),
                                }
                              : {
                                  id: 'unarchive',
                                  label: '다시 활성화',
                                  onSelect: () => handleToggleActive(selectedWorkspace, true),
                                },
                            ...(!selectedWorkspace.active
                              ? [
                                  (() => {
                                    const reason = getDeleteBlockReason(selectedWorkspace);
                                    return {
                                      id: 'delete',
                                      label: reason
                                        ? `영구 삭제 (${reason})`
                                        : '영구 삭제',
                                      separatorBefore: true,
                                      tone: 'danger' as const,
                                      disabled: Boolean(reason),
                                      onSelect: () =>
                                        openConfirm({
                                          title: '워크스페이스 영구 삭제',
                                          description: `"${selectedWorkspace.name}" 을 완전히 삭제하면 되돌릴 수 없습니다. 모든 멤버십과 enabled apps 가 함께 제거됩니다.`,
                                          confirmLabel: '영구 삭제',
                                          variant: 'danger',
                                          onConfirm: () =>
                                            handleDeleteWorkspace(selectedWorkspace),
                                        }),
                                    };
                                  })(),
                                ]
                              : []),
                          ]}
                        />
                      ) : null}
                    </div>
                  </div>
                </header>

                {/* Apps */}
                <section className="border-b border-app-border px-4 py-3">
                  <div className="mb-2 flex items-center justify-between">
                    <h3 className="app-text-control text-app-ink">
                      앱{' '}
                      <span className="app-text-caption ml-1 text-app-ink/50">
                        {selectedEnabledApps.length} / {APP_ORDER.length} 활성
                      </span>
                    </h3>
                  </div>
                  <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-bg">
                    {APP_ORDER.map((appCode) => {
                      const label =
                        WORKSPACE_ENABLED_APP_LABELS[
                          appCode as keyof typeof WORKSPACE_ENABLED_APP_LABELS
                        ] ?? appCode;
                      const description = APP_DESCRIPTIONS[appCode] ?? '';
                      const checked = selectedEnabledApps.includes(appCode);
                      return (
                        <AppToggleRow
                          key={appCode}
                          appCode={appCode}
                          label={label}
                          description={description}
                          checked={checked}
                          disabled={!canManage || busy}
                          onChange={(next) => {
                            setSelectedEnabledApps((current) =>
                              next
                                ? current.includes(appCode)
                                  ? current
                                  : [...current, appCode]
                                : current.filter((item) => item !== appCode),
                            );
                          }}
                        />
                      );
                    })}
                  </div>
                </section>

                {/* Groups (small set, all shown) */}
                {groupBindings.length > 0 ? (
                  <section className="border-b border-app-border px-4 py-3">
                    <h3 className="app-text-control mb-2 text-app-ink">
                      그룹{' '}
                      <span className="app-text-caption ml-1 text-app-ink/50">
                        {groupBindings.length}개 · 사용자에게 권한 상속
                      </span>
                    </h3>
                    <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-bg">
                      {groupBindings.map((binding) => (
                        <WorkspaceMemberRow
                          key={`${binding.subject_type}-${binding.subject_id}`}
                          binding={binding}
                          canManage={canManage}
                          isCurrentUser={false}
                          busy={busy}
                          onChangeRole={(role) =>
                            void handleChangeMemberRole(binding, role)
                          }
                          onRemove={() => void handleRemoveMember(binding)}
                        />
                      ))}
                    </div>
                  </section>
                ) : null}

                {/* Members preview + add panel + open drawer */}
                <section className="px-4 py-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h3 className="app-text-control text-app-ink">
                      멤버{' '}
                      <span className="app-text-caption ml-1 text-app-ink/50">
                        {selectedWorkspace.member_count}명 · 관리자 미리보기
                      </span>
                    </h3>
                    <div className="flex items-center gap-1.5">
                      {canManage ? (
                        <Button
                          variant="primary"
                          onClick={() => setAddPanelOpen((current) => !current)}
                        >
                          <Plus size={12} className="mr-1" />
                          멤버 추가
                        </Button>
                      ) : null}
                      <Button variant="ghost" onClick={() => setMembersDrawerOpen(true)}>
                        <UsersIcon size={12} className="mr-1" />
                        멤버 관리
                      </Button>
                    </div>
                  </div>

                  {addPanelOpen && canManage ? (
                    <div className="mb-3 rounded-md border border-app-accent/40 bg-app-accent/5 p-3">
                      <div className="mb-2 flex items-center justify-between">
                        <h4 className="app-text-control text-app-ink">새 멤버 추가</h4>
                        <button
                          type="button"
                          onClick={resetAddPanel}
                          className="rounded p-0.5 text-app-ink/60 hover:bg-app-surface-sidebar hover:text-app-ink"
                          aria-label="닫기"
                        >
                          ×
                        </button>
                      </div>
                      <SubjectPickerInline
                        workspaceId={selectedWorkspace.id}
                        token={token}
                        groups={groups}
                        excludeIds={memberSubjectIds}
                        selection={addSelection}
                        onSelectionChange={setAddSelection}
                        canReadGroups={canReadGroups}
                        onOpenDirectory={() => setAddPickerOpen(true)}
                      />
                      <div className="mt-2 space-y-2">
                        <div>
                          <div className="app-text-caption mb-1 text-app-ink/60">
                            선택 ({selectionSize(addSelection)})
                          </div>
                          <SelectedSubjectsBar
                            selection={addSelection}
                            onRemove={(kind, id) =>
                              setAddSelection((current) => removeSubject(current, kind, id))
                            }
                          />
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="app-text-caption text-app-ink/60">역할</span>
                            <Select
                              value={addRole}
                              onValueChange={setAddRole}
                              options={WORKSPACE_ROLE_OPTIONS.map((option) => ({
                                value: option.value,
                                label: option.label,
                              }))}
                            />
                          </div>
                          <div className="flex items-center gap-1.5">
                            <Button variant="ghost" onClick={resetAddPanel} disabled={addBusy}>
                              취소
                            </Button>
                            <Button
                              variant="primary"
                              disabled={addBusy || selectionSize(addSelection) === 0}
                              onClick={() => void handleBulkAddSelection()}
                            >
                              {addBusy
                                ? '추가 중...'
                                : `${selectionSize(addSelection)}명 추가`}
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {previewBindings.length === 0 ? (
                    <div className="rounded-md border border-dashed border-app-border bg-app-bg px-3 py-6 text-center">
                      <p className="app-text-body-sm text-app-ink/60">아직 멤버가 없습니다.</p>
                      {canManage ? (
                        <p className="app-text-caption mt-0.5 text-app-ink/40">
                          [멤버 추가] 를 눌러 팀원을 등록하세요.
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <div className="divide-y divide-app-border rounded-md border border-app-border bg-app-bg">
                      {previewBindings.map((binding) => (
                        <WorkspaceMemberRow
                          key={`${binding.subject_type}-${binding.subject_id}`}
                          binding={binding}
                          canManage={canManage}
                          isCurrentUser={
                            binding.subject_type === 'user' &&
                            binding.subject_id === currentUserId
                          }
                          busy={busy}
                          onChangeRole={(role) =>
                            void handleChangeMemberRole(binding, role)
                          }
                          onRemove={() => void handleRemoveMember(binding)}
                        />
                      ))}
                      {selectedWorkspace.member_count > previewBindings.length ? (
                        <button
                          type="button"
                          onClick={() => setMembersDrawerOpen(true)}
                          className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-accent transition-colors hover:bg-app-surface-sidebar"
                        >
                          전체 {selectedWorkspace.member_count}명 보기 →
                        </button>
                      ) : null}
                    </div>
                  )}
                </section>
              </div>

              {/* Sticky save bar (only for apps dirty state) */}
              {appsDirty ? (
                <div className="flex items-center justify-between gap-3 border-t border-app-border bg-app-surface-sidebar px-6 py-3">
                  <div className="flex items-center gap-2 text-app-ink/80">
                    <span className="h-2 w-2 rounded-full bg-amber-500" />
                    <span className="app-text-body">앱 변경 사항이 저장되지 않았습니다.</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => setSelectedEnabledApps(originalEnabledApps)}
                    >
                      되돌리기
                    </Button>
                    <Button
                      variant="primary"
                      disabled={busy || !canManage}
                      onClick={() => void handleSaveApps()}
                    >
                      변경 저장
                    </Button>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>

      <CreateWorkspaceModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={handleCreateWorkspace}
        busy={createBusy}
        error={createError}
      />
      <EditWorkspaceModal
        open={editOpen}
        workspace={selectedWorkspace}
        onOpenChange={setEditOpen}
        onSave={handleEditWorkspace}
        busy={editBusy}
        error={editError}
      />
      {confirmState ? (
        <ConfirmDialog
          open
          title={confirmState.title}
          description={confirmState.description}
          confirmLabel={confirmState.confirmLabel}
          cancelLabel="취소"
          variant={confirmState.variant}
          onConfirm={() => {
            const action = confirmState.onConfirm;
            setConfirmState(null);
            void action();
          }}
          onCancel={() => setConfirmState(null)}
        />
      ) : null}
      <WorkspaceMembersDrawer
        open={membersDrawerOpen}
        onOpenChange={setMembersDrawerOpen}
        workspace={selectedWorkspace}
        token={token}
        canManage={canManage}
        currentUserId={currentUserId}
        onChanged={() => {
          // Refresh detail-panel preview after drawer changes
          if (selectedWorkspaceId) {
            void listWorkspaceBindings(token, selectedWorkspaceId).then(setBindings).catch(() => {});
            void reloadWorkspaces(selectedWorkspaceId);
          }
        }}
        onError={flashError}
        onSuccess={flashSuccess}
      />
      <PeoplePickerModal
        open={addPickerOpen}
        onClose={() => setAddPickerOpen(false)}
        token={token}
        selection={addSelection}
        onSelectionChange={setAddSelection}
        excludeIds={memberSubjectIds}
      />
    </div>
  );
}

function SecuritySection({
  token,
  canReadUsers,
  canReadGroups,
  canWriteGroups,
  canReadPolicies,
  canWritePolicies,
}: {
  token: string;
  canReadUsers: boolean;
  canReadGroups: boolean;
  canWriteGroups: boolean;
  canReadPolicies: boolean;
  canWritePolicies: boolean;
}) {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [policies, setPolicies] = useState<FeaturePolicyItem[]>([]);
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
        canReadPolicies ? listFeaturePolicies(token) : Promise.resolve<FeaturePolicyItem[]>([]),
      ]);
      const [userResult, groupResult, workspaceResult, policyResult] = results;

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
  }, [canReadGroups, canReadPolicies, canReadUsers, token]);

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
                          {formatAppCodes(workspace.enabled_apps)} · {workspace.description || '설명 없음'}
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
          canReadUsers={auth.hasPermission('user.read')}
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
