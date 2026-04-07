import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Building2,
  KeyRound,
  LockKeyhole,
  Search,
  Shield,
  Sparkles,
  UserPlus,
  Users,
  Workflow,
} from 'lucide-react';

import { Button, InlineNotice, Select } from '@aidoo/ui';

import {
  createAdminUser,
  createGroup,
  createTeam,
  createWorkspace,
  listAdminUsers,
  listAuditLogs,
  listFeaturePolicies,
  listGroups,
  listOrgUnits,
  listTeamMembers,
  listTeams,
  listWorkspaceBindings,
  listWorkspaces,
  replaceTeamMembers,
  replaceWorkspaceBindings,
  resetUserPassword,
  updateFeaturePolicies,
  type AccessGroupItem,
  type AuditLogItem,
  type FeaturePolicyItem,
  type OrgUnitItem,
  type TeamItem,
  type WorkspaceBindingItem,
  type WorkspaceItem,
} from './admin-api';
import type { AuthUser } from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';

type AdminSection = 'general' | 'people' | 'teams' | 'workspaces' | 'security' | 'audit';

const NONE_OPTION_VALUE = '__none__';
const fieldClassName =
  'w-full rounded-lg border border-clickup-border bg-clickup-bg px-3 py-2 text-sm text-clickup-text outline-none transition-colors focus:border-clickup-purple';

const sectionMeta: Record<
  AdminSection,
  { title: string; description: string; learnMoreLabel?: string }
> = {
  general: {
    title: 'General settings',
    description: '공통 사용자, 팀, 워크스페이스, 권한 정책의 현재 상태를 한곳에서 확인합니다.',
  },
  people: {
    title: 'Manage people',
    description: '',
    learnMoreLabel: 'Learn more',
  },
  teams: {
    title: 'Teams',
    description: 'View-only users added to Teams will be converted to paid users.',
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
        <header className="flex flex-col gap-4 border-b border-clickup-border pb-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-[1.7rem] font-semibold tracking-tight text-clickup-text">{meta.title}</h1>
              {meta.learnMoreLabel ? (
                <button className="text-xs font-medium text-clickup-purple hover:underline" type="button">
                  {meta.learnMoreLabel}
                </button>
              ) : null}
            </div>
            {meta.description ? <p className="max-w-3xl text-sm text-gray-500">{meta.description}</p> : null}
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
          <h2 className="text-lg font-semibold text-clickup-text">{title}</h2>
          {description ? <p className="mt-1 text-sm text-gray-500">{description}</p> : null}
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
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

function HeadCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-clickup-border px-4 py-3 text-left text-xs font-medium text-gray-500">
      {children}
    </th>
  );
}

function BodyCell({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <td className={`border-b border-clickup-border px-4 py-3 align-top text-sm text-clickup-text ${className}`.trim()}>
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
          <div className="text-sm font-medium text-clickup-text">{title}</div>
          <div className="text-sm text-gray-500">{description}</div>
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
      ? 'border-clickup-purple/20 bg-clickup-purple/10 text-clickup-purple'
      : tone === 'green'
        ? 'border-green-500/20 bg-green-500/10 text-green-600 dark:text-green-400'
        : tone === 'amber'
          ? 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-300'
          : 'border-clickup-border bg-clickup-sidebar text-gray-500';

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${toneClassName}`.trim()}>
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
  const [summary, setSummary] = useState({
    userCount: 0,
    adminCount: 0,
    groupCount: 0,
    workspaceCount: 0,
    teamCount: 0,
    policyCount: 0,
    enabledPolicyCount: 0,
    auditCount: 0,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [users, groups, workspaces, teams, policies, audits] = await Promise.all([
          listAdminUsers(token),
          listGroups(token),
          listWorkspaces(token),
          listTeams(token),
          listFeaturePolicies(token),
          listAuditLogs(token),
        ]);
        if (cancelled) {
          return;
        }
        setSummary({
          userCount: users.items.length,
          adminCount: users.items.filter((item) => item.is_admin).length,
          groupCount: groups.length,
          workspaceCount: workspaces.length,
          teamCount: teams.length,
          policyCount: policies.length,
          enabledPolicyCount: policies.filter((item) => item.enabled).length,
          auditCount: audits.length,
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
  }, [token]);

  return (
    <div className="space-y-6">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}



      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SurfaceCard
          title="Current operating model"
          description="현재 공통 계정 체계와 작업 영역 운영 방식을 한 번에 확인할 수 있는 요약입니다."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-4">
              <div className="text-sm font-semibold text-clickup-text">Identity</div>
              <div className="mt-3 space-y-2 text-sm text-gray-500">
                <div>사용자 계정 {summary.userCount}개</div>
                <div>관리자 {summary.adminCount}명</div>
                <div>권한 그룹 {summary.groupCount}개</div>
              </div>
            </div>
            <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-4">
              <div className="text-sm font-semibold text-clickup-text">Work model</div>
              <div className="mt-3 space-y-2 text-sm text-gray-500">
                <div>워크스페이스 {summary.workspaceCount}개</div>
                <div>실행 팀 {summary.teamCount}개</div>
                <div>기능 정책 {summary.policyCount}개</div>
              </div>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard
          title="Admin notes"
          description="설정 앱과 마이페이지의 역할을 분리한 현재 UX 원칙입니다."
        >
          <div className="space-y-3 text-sm text-gray-500">
            <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-4">
              프로필 아바타는 개인 설정으로만 이동하고, 조직 운영 기능은 모두 Settings 앱 안에서 다룹니다.
            </div>
            <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-4">
              사용자, 팀, 워크스페이스, 권한 정책은 좌측 서브사이드바를 기준으로 분리합니다.
            </div>
            <div className="rounded-xl border border-clickup-border bg-clickup-sidebar p-4">
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
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [orgUnits, setOrgUnits] = useState<OrgUnitItem[]>([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'admin' | 'member'>('all');
  const [selectedOrgUnitId, setSelectedOrgUnitId] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState(NONE_OPTION_VALUE);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [userResponse, groupItems, orgUnitItems] = await Promise.all([
        listAdminUsers(token),
        listGroups(token),
        listOrgUnits(token),
      ]);
      setUsers(userResponse.items);
      setGroups(groupItems);
      setOrgUnits(orgUnitItems);
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
    void load();
  }, [token]);

  const filteredUsers = useMemo(() => {
    const normalizedQuery = search.trim().toLowerCase();
    return users.filter((user) => {
      const matchesQuery =
        normalizedQuery.length === 0 ||
        user.email.toLowerCase().includes(normalizedQuery) ||
        user.display_name.toLowerCase().includes(normalizedQuery) ||
        user.full_name.toLowerCase().includes(normalizedQuery) ||
        (user.primary_org_unit?.name ?? '').toLowerCase().includes(normalizedQuery);

      const matchesRole =
        roleFilter === 'all' ||
        (roleFilter === 'admin' ? user.is_admin : !user.is_admin);

      return matchesQuery && matchesRole;
    });
  }, [roleFilter, search, users]);

  async function handleCreateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    try {
      const response = await createAdminUser(token, {
        email: email.trim(),
        full_name: fullName.trim(),
        display_name: displayName.trim() || undefined,
        primary_org_unit_id: selectedOrgUnitId || undefined,
        group_ids: selectedGroupId !== NONE_OPTION_VALUE ? [selectedGroupId] : [],
      });
      setEmail('');
      setFullName('');
      setDisplayName('');
      setInviteOpen(false);
      setMessage(`사용자를 생성했습니다. 임시 비밀번호: ${response.temporary_password}`);
      await load();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '사용자를 생성하지 못했습니다.'));
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

  function handleExport() {
    const header = ['Name', 'Email', 'Role', 'Last active', 'Invited by', 'Invited on', 'Teams'];
    const rows = filteredUsers.map((user) => [
      user.display_name || user.full_name,
      user.email,
      user.is_admin ? 'Owner' : 'Member',
      formatDateLabel(user.last_login_at),
      'System',
      formatDateLabel(user.created_at),
      user.workspace_roles.map((item) => item.name).join(', ') || '-',
    ]);
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
  }

  return (
    <div className="space-y-6">
      <SectionMessage error={error} message={message} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-clickup-border pb-4">
        <ToolbarField className="min-w-[280px] max-w-md flex-1">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
            <input
              className={`w-full rounded-md border border-transparent bg-transparent pl-9 py-1.5 text-sm text-clickup-text outline-none transition-colors hover:border-clickup-border focus:border-clickup-purple focus:bg-clickup-bg`}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search or invite by email"
              value={search}
            />
          </label>
        </ToolbarField>
        <div className="flex items-center gap-2">
          <button
            className="rounded-md border border-transparent px-3 py-1.5 text-sm font-medium text-gray-500 transition-colors hover:border-clickup-border hover:bg-clickup-hover hover:text-clickup-text"
            onClick={handleExport}
            type="button"
          >
            Export
          </button>
          <button
            className="inline-flex items-center gap-1.5 rounded-md bg-clickup-text px-3 py-1.5 text-sm font-medium text-clickup-bg transition-opacity hover:opacity-90 dark:bg-white dark:text-black"
            onClick={() => {
              setInviteOpen((current) => !current);
              requestAnimationFrame(() => {
                document.getElementById('admin-user-email')?.focus();
              });
            }}
            type="button"
          >
            <span>+</span>
            <span>Invite people</span>
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 py-2">
        <button
          className="inline-flex items-center gap-1.5 rounded p-1 text-sm font-medium text-clickup-text hover:bg-clickup-hover"
          type="button"
        >
          <span>All Users ({users.length})</span>
          <span className="text-[10px] text-gray-500">▾</span>
        </button>
      </div>

      <div className="w-full">

        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr>
              <HeadCell>Name</HeadCell>
              <HeadCell>Email</HeadCell>
              <HeadCell>Role</HeadCell>
              <HeadCell>Last active</HeadCell>
              <HeadCell>Invited by</HeadCell>
              <HeadCell>Invited on</HeadCell>
              <HeadCell>Teams</HeadCell>
              <HeadCell>Actions</HeadCell>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="border-b border-clickup-border px-4 py-3 text-sm text-gray-500" colSpan={8}>
                <button
                  className="transition-colors hover:text-clickup-text"
                  onClick={() => setInviteOpen(true)}
                  type="button"
                >
                  + Invite people
                </button>
              </td>
            </tr>
            {filteredUsers.length === 0 ? (
              <EmptyRow
                colSpan={8}
                description="검색어를 바꾸거나 초대 버튼으로 사용자를 추가하세요."
                title="조건에 맞는 사용자가 없습니다."
              />
            ) : (
              filteredUsers.map((user) => (
                <tr key={user.id}>
                  <BodyCell>
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-clickup-sidebar text-[11px] font-semibold text-gray-500">
                        {getInitials(user.display_name || user.full_name)}
                      </div>
                      <div>
                        <div className="font-medium text-clickup-text">{user.display_name || user.full_name}</div>
                        {user.is_admin ? (
                          <div className="mt-0.5">
                            <Badge tone="default">Owner</Badge>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </BodyCell>
                  <BodyCell>{user.email}</BodyCell>
                  <BodyCell>{user.is_admin ? 'Owner' : 'Member'}</BodyCell>
                  <BodyCell>{formatDateLabel(user.last_login_at)}</BodyCell>
                  <BodyCell>System</BodyCell>
                  <BodyCell>{formatDateLabel(user.created_at)}</BodyCell>
                  <BodyCell>{user.workspace_roles.length > 0 ? user.workspace_roles.map((item) => item.name).join(', ') : '-'}</BodyCell>
                  <BodyCell className="w-14 text-right">
                    <button
                      className="rounded-md px-2 py-1 text-gray-500 transition-colors hover:bg-clickup-hover hover:text-clickup-text"
                      onClick={() => {
                        void handleResetPassword(user.id);
                      }}
                      type="button"
                    >
                      ...
                    </button>
                  </BodyCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {inviteOpen ? (
        <div className="rounded-xl border border-clickup-border bg-clickup-card px-5 py-5">
          <div className="mb-4">
            <div className="text-sm font-semibold text-clickup-text">Invite people</div>
            <div className="mt-1 text-sm text-gray-500">관리자가 계정을 만들고 기본 조직과 그룹을 함께 배정합니다.</div>
          </div>
          <form className="grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)_220px_220px_auto]" onSubmit={(event) => void handleCreateUser(event)}>
            <input
              className={fieldClassName}
              id="admin-user-email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Email"
              value={email}
            />
            <input
              className={fieldClassName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Full name"
              value={fullName}
            />
            <input
              className={fieldClassName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Display name"
              value={displayName}
            />
            <Select
              onValueChange={setSelectedOrgUnitId}
              options={orgUnits.map((item) => ({ value: item.id, label: item.name }))}
              value={selectedOrgUnitId}
            />
            <Select
              onValueChange={setSelectedGroupId}
              options={[
                { value: NONE_OPTION_VALUE, label: 'No group' },
                ...groups.map((item) => ({ value: item.id, label: item.name })),
              ]}
              value={selectedGroupId}
            />
            <div className="flex justify-end">
              <Button type="submit" variant="primary">Invite</Button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function TeamsSection({ token }: { token: string }) {
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [selectedTeamId, setSelectedTeamId] = useState('');
  const [selectedUserId, setSelectedUserId] = useState(NONE_OPTION_VALUE);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [teamMembers, setTeamMembers] = useState<AuthUser[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [workspaceItems, teamItems, userResponse] = await Promise.all([
        listWorkspaces(token),
        listTeams(token),
        listAdminUsers(token),
      ]);
      setWorkspaces(workspaceItems);
      setTeams(teamItems);
      setUsers(userResponse.items);
      setSelectedWorkspaceId((current) => current || workspaceItems[0]?.id || '');
      setSelectedUserId((current) => current || NONE_OPTION_VALUE);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '팀 정보를 불러오지 못했습니다.'));
    }
  }

  async function loadMembers(teamId: string) {
    try {
      setTeamMembers(await listTeamMembers(token, teamId));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '팀 멤버를 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    void load();
  }, [token]);

  useEffect(() => {
    if (!selectedTeamId) {
      setTeamMembers([]);
      return;
    }
    void loadMembers(selectedTeamId);
  }, [selectedTeamId, token]);
  const selectedTeam = useMemo(
    () => teams.find((item) => item.id === selectedTeamId) ?? null,
    [selectedTeamId, teams],
  );

  async function handleCreateTeam(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkspaceId) {
      return;
    }

    setMessage(null);
    setError(null);

    try {
      await createTeam(token, selectedWorkspaceId, {
        name: name.trim(),
        description: description.trim(),
      });
      setName('');
      setDescription('');
      setMessage('팀을 생성했습니다.');
      setCreateOpen(false);
      await load();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '팀을 생성하지 못했습니다.'));
    }
  }

  async function handleAddTeamMember() {
    if (!selectedTeamId || !selectedUserId || selectedUserId === NONE_OPTION_VALUE) {
      return;
    }

    setMessage(null);
    setError(null);

    try {
      const nextIds = Array.from(new Set([...teamMembers.map((item) => item.id), selectedUserId]));
      const members = await replaceTeamMembers(token, selectedTeamId, nextIds);
      setTeamMembers(members);
      setMessage('팀 멤버를 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '팀 멤버를 저장하지 못했습니다.'));
    }
  }

  return (
    <div className="space-y-6">
      <SectionMessage error={error} message={message} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-clickup-border pb-4">
        <div>
          <div className="text-sm font-semibold text-clickup-text">Create team</div>
          <div className="text-[13px] text-gray-500">팀은 항상 워크스페이스에 속합니다. View-only users added to Teams will be converted to paid users.</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="inline-flex items-center gap-1.5 rounded-md bg-clickup-text px-3 py-1.5 text-sm font-medium text-clickup-bg transition-opacity hover:opacity-90 dark:bg-white dark:text-black"
            onClick={() => setCreateOpen((current) => !current)}
            type="button"
          >
            <span>+</span>
            <span>{createOpen ? 'Close' : 'Create Team'}</span>
          </button>
        </div>
      </div>

      <div className="w-full">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr>
              <HeadCell>Name</HeadCell>
              <HeadCell>Alias</HeadCell>
              <HeadCell>Source</HeadCell>
              <HeadCell>Members</HeadCell>
              <HeadCell>Actions</HeadCell>
            </tr>
          </thead>
          <tbody>
            {teams.length === 0 ? (
              <EmptyRow
                colSpan={5}
                description="상단의 Create Team 버튼으로 첫 팀을 추가하세요."
                title="등록된 팀이 없습니다."
              />
            ) : (
              teams.map((team) => (
                <tr
                  key={team.id}
                  className={selectedTeamId === team.id ? 'bg-clickup-hover/70' : undefined}
                >
                  <BodyCell>
                    <button
                      className="flex items-center gap-3 text-left"
                      onClick={() => setSelectedTeamId(team.id)}
                      type="button"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-clickup-sidebar text-[11px] font-semibold text-gray-500">
                        {getInitials(team.name)}
                      </div>
                      <div>
                        <div className="font-medium text-clickup-text">{team.name}</div>
                        <div className="mt-0.5 text-xs text-gray-500">{team.member_count} members</div>
                      </div>
                    </button>
                  </BodyCell>
                  <BodyCell>@{team.key}</BodyCell>
                  <BodyCell>
                    <Badge tone="green">Manual</Badge>
                  </BodyCell>
                  <BodyCell>{team.member_count}</BodyCell>
                  <BodyCell className="w-12 text-right">
                    <button
                      className="rounded-md px-2 py-1 text-gray-500 transition-colors hover:bg-clickup-hover hover:text-clickup-text"
                      onClick={() => setSelectedTeamId(team.id)}
                      type="button"
                    >
                      ...
                    </button>
                  </BodyCell>
                </tr>
              ))
            )}
            <tr>
              <td className="px-4 py-3 text-sm text-gray-500" colSpan={5}>
                <button
                  className="transition-colors hover:text-clickup-text"
                  onClick={() => setCreateOpen(true)}
                  type="button"
                >
                  + Create Team
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {createOpen ? (
        <div className="border-t border-b border-clickup-border px-5 py-5 mb-6">
          <form className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)_minmax(0,1fr)_auto]" onSubmit={(event) => void handleCreateTeam(event)}>
            <Select
              onValueChange={setSelectedWorkspaceId}
              options={workspaces.map((item) => ({ value: item.id, label: item.name }))}
              value={selectedWorkspaceId}
            />
            <input
              className={fieldClassName}
              onChange={(event) => setName(event.target.value)}
              placeholder="Team name"
              value={name}
            />
            <input
              className={fieldClassName}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Description"
              value={description}
            />
            <div className="flex justify-end">
              <Button type="submit" variant="primary">Create</Button>
            </div>
          </form>
        </div>
      ) : null}

      {selectedTeam ? (
        <div className="rounded-xl border border-clickup-border bg-clickup-card px-5 py-5">
          <div className="flex flex-col gap-3 border-b border-clickup-border pb-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-sm font-semibold text-clickup-text">{selectedTeam.name}</div>
              <div className="mt-1 text-sm text-gray-500">
                Workspace {selectedTeam.workspace_key} / Alias @{selectedTeam.key}
              </div>
            </div>
            <Badge tone="green">Manual</Badge>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[260px_auto]">
            <Select
              onValueChange={setSelectedUserId}
              options={[
                { value: NONE_OPTION_VALUE, label: 'Add member by email' },
                ...users.map((item) => ({ value: item.id, label: item.email })),
              ]}
              value={selectedUserId}
            />
            <div className="flex justify-end lg:justify-start">
              <Button onClick={() => { void handleAddTeamMember(); }} variant="secondary">Add member</Button>
            </div>
          </div>

          <div className="mt-4 grid gap-2">
            {teamMembers.length === 0 ? (
              <div className="rounded-lg border border-dashed border-clickup-border px-4 py-5 text-sm text-gray-500">
                아직 팀 멤버가 없습니다.
              </div>
            ) : (
              teamMembers.map((member) => (
                <div
                  key={member.id}
                  className="flex items-center justify-between border-b border-clickup-border py-3 last:border-b-0"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-clickup-sidebar text-[11px] font-semibold text-gray-500">
                      {getInitials(member.display_name || member.full_name)}
                    </div>
                    <div>
                      <div className="font-medium text-clickup-text">{member.display_name || member.full_name}</div>
                      <div className="mt-0.5 text-xs text-gray-500">{member.email}</div>
                    </div>
                  </div>
                  <Badge tone={member.is_admin ? 'purple' : 'default'}>
                    {member.is_admin ? 'Admin' : 'Member'}
                  </Badge>
                </div>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function WorkspacesSection({ token }: { token: string }) {
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

  async function load() {
    try {
      const [workspaceItems, userResponse, groupItems] = await Promise.all([
        listWorkspaces(token),
        listAdminUsers(token),
        listGroups(token),
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
  }, [token]);

  async function handleCreateWorkspace(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
    if (!selectedWorkspaceId) {
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
          role: 'viewer',
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
      setMessage('워크스페이스 바인딩을 저장했습니다.');
      setSelectedUserId(NONE_OPTION_VALUE);
      setSelectedGroupId(NONE_OPTION_VALUE);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '워크스페이스 바인딩을 저장하지 못했습니다.'));
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
              onChange={(event) => setName(event.target.value)}
              placeholder="Workspace name"
              value={name}
            />
            <input
              className={fieldClassName}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Description"
              value={description}
            />
            <div className="flex justify-end">
              <Button type="submit" variant="primary">Create workspace</Button>
            </div>
          </form>
        </SurfaceCard>

        <SurfaceCard
          description="사용자 또는 그룹을 선택한 워크스페이스에 연결합니다."
          title="Workspace access bindings"
        >
          <div className="grid gap-3">
            <Select
              onValueChange={async (value) => {
                setSelectedWorkspaceId(value);
                setBindings(await listWorkspaceBindings(token, value));
              }}
              options={workspaces.map((item) => ({ value: item.id, label: item.name }))}
              value={selectedWorkspaceId}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <Select
                onValueChange={setSelectedUserId}
                options={[
                  { value: NONE_OPTION_VALUE, label: 'No user selected' },
                  ...users.map((item) => ({ value: item.id, label: item.email })),
                ]}
                value={selectedUserId}
              />
              <Select
                onValueChange={setSelectedGroupId}
                options={[
                  { value: NONE_OPTION_VALUE, label: 'No group selected' },
                  ...groups.map((item) => ({ value: item.id, label: item.name })),
                ]}
                value={selectedGroupId}
              />
            </div>
            <div className="flex justify-end">
              <Button onClick={() => { void handleAddBindings(); }} variant="primary">Save bindings</Button>
            </div>
            <div className="grid gap-2">
              {bindings.length === 0 ? (
                <div className="rounded-xl border border-dashed border-clickup-border bg-clickup-sidebar px-4 py-6 text-sm text-gray-500">
                  아직 바인딩이 없습니다.
                </div>
              ) : (
                bindings.map((binding) => (
                  <div
                    key={`${binding.subject_type}-${binding.subject_id}`}
                    className="flex items-center justify-between rounded-xl border border-clickup-border bg-clickup-sidebar px-4 py-3"
                  >
                    <div>
                      <div className="font-medium text-clickup-text">{binding.subject_label}</div>
                      <div className="mt-1 text-xs text-gray-500">{binding.subject_type}</div>
                    </div>
                    <Badge tone="purple">{binding.role}</Badge>
                  </div>
                ))
              )}
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard
        description="등록된 워크스페이스와 연결된 팀 수를 요약합니다."
        title="Workspace directory"
      >
        <TableShell>
          <thead>
            <tr>
              <HeadCell>Name</HeadCell>
              <HeadCell>Key</HeadCell>
              <HeadCell>Description</HeadCell>
              <HeadCell>Teams</HeadCell>
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
                    <div className="font-medium text-clickup-text">{workspace.name}</div>
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

function SecuritySection({ token }: { token: string }) {
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [policies, setPolicies] = useState<FeaturePolicyItem[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [permissions, setPermissions] = useState('group.read,workspace.read');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [groupItems, policyItems] = await Promise.all([
        listGroups(token),
        listFeaturePolicies(token),
      ]);
      setGroups(groupItems);
      setPolicies(policyItems);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '권한 설정을 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    void load();
  }, [token]);

  async function handleCreateGroup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    try {
      await createGroup(token, {
        name: name.trim(),
        description: description.trim(),
        permissions: permissions
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      });
      setName('');
      setDescription('');
      setMessage('그룹을 생성했습니다.');
      await load();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹을 생성하지 못했습니다.'));
    }
  }

  async function handleSavePolicies() {
    setMessage(null);
    setError(null);

    try {
      const response = await updateFeaturePolicies(
        token,
        policies.map((policy) => ({
          id: policy.id,
          enabled: policy.enabled,
          required_permissions: policy.required_permissions,
          allowed_workspace_keys: policy.allowed_workspace_keys,
          allowed_group_slugs: policy.allowed_group_slugs,
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
          description="권한 코드를 쉼표로 입력해 그룹 권한을 빠르게 정의합니다."
          title="Create access group"
        >
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
              onChange={(event) => setPermissions(event.target.value)}
              placeholder="permission.read, permission.write"
              value={permissions}
            />
            <div className="flex justify-end">
              <Button type="submit" variant="primary">Create group</Button>
            </div>
          </form>
        </SurfaceCard>

        <SurfaceCard
          description="그룹에 부여된 권한과 현재 멤버 수를 확인합니다."
          title="Access groups"
        >
          <TableShell>
            <thead>
              <tr>
                <HeadCell>Name</HeadCell>
                <HeadCell>Slug</HeadCell>
                <HeadCell>Permissions</HeadCell>
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
                      <div className="font-medium text-clickup-text">{group.name}</div>
                      <div className="mt-1 text-xs text-gray-500">{group.description || '설명 없음'}</div>
                    </BodyCell>
                    <BodyCell>{group.slug}</BodyCell>
                    <BodyCell>{group.permissions.join(', ') || 'None'}</BodyCell>
                    <BodyCell>{group.member_count}</BodyCell>
                  </tr>
                ))
              )}
            </tbody>
          </TableShell>
        </SurfaceCard>
      </div>

      <SurfaceCard
        actions={<Button onClick={() => { void handleSavePolicies(); }} variant="primary">Save policies</Button>}
        description="각 워크스페이스와 도구 노출을 개별 정책으로 토글합니다."
        title="Feature access policies"
      >
        <div className="grid gap-3">
          {policies.map((policy) => (
            <label
              key={policy.id}
              className="flex items-start gap-4 rounded-xl border border-clickup-border bg-clickup-sidebar px-4 py-4"
            >
              <input
                checked={policy.enabled}
                className="mt-1"
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
                  <strong className="text-sm text-clickup-text">{policy.name}</strong>
                  <Badge tone={policy.enabled ? 'green' : 'default'}>
                    {policy.enabled ? 'enabled' : 'disabled'}
                  </Badge>
                </div>
                <div className="mt-1 text-sm text-gray-500">{policy.description}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <Badge>{policy.code}</Badge>
                  {policy.required_permissions.map((permission) => (
                    <Badge key={`${policy.id}-${permission}`}>{permission}</Badge>
                  ))}
                </div>
              </div>
            </label>
          ))}
        </div>
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
            <div className="rounded-xl border border-dashed border-clickup-border bg-clickup-sidebar px-4 py-8 text-center text-sm text-gray-500">
              표시할 감사 이벤트가 없습니다.
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-clickup-border bg-clickup-sidebar px-5 py-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-clickup-text">{item.summary}</div>
                      <Badge tone="purple">{item.action}</Badge>
                    </div>
                    <div className="text-sm text-gray-500">
                      {item.entity_kind} / {item.entity_id ?? 'n/a'} / {item.actor_name ?? 'system'}
                    </div>
                  </div>
                  <div className="text-sm text-gray-500">
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
    () =>
      [
        'admin.access',
        'user.read',
        'group.read',
        'workspace.read',
        'team.read',
        'feature_policy.read',
        'audit.read',
      ].some((permission) => auth.hasPermission(permission)),
    [auth],
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
    case 'teams':
      content = <TeamsSection token={token} />;
      break;
    case 'workspaces':
      content = <WorkspacesSection token={token} />;
      break;
    case 'security':
      content = <SecuritySection token={token} />;
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
