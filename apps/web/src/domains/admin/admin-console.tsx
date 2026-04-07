import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button, InlineNotice, Input, Panel, Select } from '@aidoo/ui';

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
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import type { AuthUser } from '@/src/domains/auth/auth-api';

type AdminSection = 'users' | 'groups' | 'workspaces' | 'teams' | 'feature-access' | 'audit';

const adminTabs: Array<{ id: AdminSection; label: string; path: string }> = [
  { id: 'users', label: '사용자', path: '/admin/users' },
  { id: 'groups', label: '그룹', path: '/admin/groups' },
  { id: 'workspaces', label: '워크스페이스', path: '/admin/workspaces' },
  { id: 'teams', label: '팀', path: '/admin/teams' },
  { id: 'feature-access', label: '기능 접근', path: '/admin/feature-access' },
  { id: 'audit', label: '감사로그', path: '/admin/audit' },
];
const NONE_OPTION_VALUE = '__none__';

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

function AdminLayout({
  section,
  children,
}: {
  section: AdminSection;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-4 p-6">
      <Panel
        eyebrow="Admin"
        title="관리 콘솔"
        description="공통 사용자, 그룹, 워크스페이스, 팀, 기능 노출 정책을 관리합니다."
      >
        <div className="flex flex-wrap gap-2">
          {adminTabs.map((tab) => (
            <Link
              key={tab.id}
              className={
                section === tab.id
                  ? 'rounded-[var(--ui-radius-sm)] bg-[var(--ui-color-accent)] px-3 py-2 text-sm font-semibold text-white no-underline'
                  : 'rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] px-3 py-2 text-sm font-semibold text-[var(--ui-color-ink)] no-underline'
              }
              to={tab.path}
            >
              {tab.label}
            </Link>
          ))}
        </div>
      </Panel>
      {children}
    </div>
  );
}

function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        {children}
      </table>
    </div>
  );
}

function HeadCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-[var(--ui-color-border)] px-3 py-2 text-left font-semibold text-[var(--ui-color-ink-muted)]">
      {children}
    </th>
  );
}

function BodyCell({ children }: { children: React.ReactNode }) {
  return (
    <td className="border-b border-[var(--ui-color-border)] px-3 py-2 align-top text-[var(--ui-color-ink)]">
      {children}
    </td>
  );
}

function UsersSection({ token }: { token: string }) {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [orgUnits, setOrgUnits] = useState<OrgUnitItem[]>([]);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [displayName, setDisplayName] = useState('');
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
      setSelectedOrgUnitId(orgUnitItems[0]?.id ?? '');
      setSelectedGroupId(groupItems[0]?.id ?? NONE_OPTION_VALUE);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '사용자 정보를 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    void load();
  }, [token]);

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

  return (
    <>
      <Panel
        eyebrow="Users"
        title="사용자 생성"
        description="관리자가 계정을 만들고 임시 비밀번호를 발급합니다."
      >
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {error ? <InlineNotice className="mb-3" tone="danger">{error}</InlineNotice> : null}
        <form className="grid gap-3 md:grid-cols-5" onSubmit={(event) => void handleCreateUser(event)}>
          <Input onChange={(event) => setEmail(event.target.value)} placeholder="email" value={email} />
          <Input onChange={(event) => setFullName(event.target.value)} placeholder="성명" value={fullName} />
          <Input onChange={(event) => setDisplayName(event.target.value)} placeholder="표시 이름" value={displayName} />
          <Select
            onValueChange={setSelectedOrgUnitId}
            options={orgUnits.map((item) => ({ value: item.id, label: item.name }))}
            value={selectedOrgUnitId}
          />
          <Select
            onValueChange={setSelectedGroupId}
            options={[
              { value: NONE_OPTION_VALUE, label: '그룹 없음' },
              ...groups.map((item) => ({ value: item.id, label: item.name })),
            ]}
            value={selectedGroupId}
          />
          <div className="md:col-span-5">
            <Button type="submit" variant="primary">사용자 생성</Button>
          </div>
        </form>
      </Panel>

      <Panel
        eyebrow="Users"
        title="사용자 목록"
        description="현재 등록된 사용자와 그룹/권한 상태입니다."
      >
        <TableShell>
          <thead>
            <tr>
              <HeadCell>이메일</HeadCell>
              <HeadCell>이름</HeadCell>
              <HeadCell>조직</HeadCell>
              <HeadCell>그룹</HeadCell>
              <HeadCell>상태</HeadCell>
              <HeadCell>동작</HeadCell>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <BodyCell>{user.email}</BodyCell>
                <BodyCell>{user.display_name}</BodyCell>
                <BodyCell>{user.primary_org_unit?.name ?? '미지정'}</BodyCell>
                <BodyCell>{user.group_slugs.join(', ') || '없음'}</BodyCell>
                <BodyCell>{user.status}</BodyCell>
                <BodyCell>
                  <Button
                    onClick={() => {
                      void handleResetPassword(user.id);
                    }}
                    size="dense"
                    variant="secondary"
                  >
                    비밀번호 초기화
                  </Button>
                </BodyCell>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </Panel>
    </>
  );
}

function GroupsSection({ token }: { token: string }) {
  const [groups, setGroups] = useState<AccessGroupItem[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [permissions, setPermissions] = useState('group.read,workspace.read');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setGroups(await listGroups(token));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '그룹 목록을 불러오지 못했습니다.'));
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

  return (
    <>
      <Panel eyebrow="Groups" title="권한 그룹 생성" description="전사 공통 접근 그룹을 관리합니다.">
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {error ? <InlineNotice className="mb-3" tone="danger">{error}</InlineNotice> : null}
        <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void handleCreateGroup(event)}>
          <Input onChange={(event) => setName(event.target.value)} placeholder="그룹 이름" value={name} />
          <Input onChange={(event) => setDescription(event.target.value)} placeholder="설명" value={description} />
          <Input onChange={(event) => setPermissions(event.target.value)} placeholder="perm,perm" value={permissions} />
          <div className="md:col-span-3">
            <Button type="submit" variant="primary">그룹 생성</Button>
          </div>
        </form>
      </Panel>

      <Panel eyebrow="Groups" title="그룹 목록">
        <TableShell>
          <thead>
            <tr>
              <HeadCell>이름</HeadCell>
              <HeadCell>슬러그</HeadCell>
              <HeadCell>권한</HeadCell>
              <HeadCell>멤버 수</HeadCell>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={group.id}>
                <BodyCell>{group.name}</BodyCell>
                <BodyCell>{group.slug}</BodyCell>
                <BodyCell>{group.permissions.join(', ')}</BodyCell>
                <BodyCell>{group.member_count}</BodyCell>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </Panel>
    </>
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
  const [selectedUserId, setSelectedUserId] = useState('');
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

      if (selectedUserId && selectedUserId !== NONE_OPTION_VALUE) {
        nextUsers.push({
          subject_id: selectedUserId,
          subject_type: 'user',
          subject_label: users.find((item) => item.id === selectedUserId)?.email ?? selectedUserId,
          role: 'member',
        });
      }
      if (selectedGroupId && selectedGroupId !== NONE_OPTION_VALUE) {
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
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '워크스페이스 바인딩을 저장하지 못했습니다.'));
    }
  }

  return (
    <>
      <Panel eyebrow="Workspaces" title="워크스페이스 생성">
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {error ? <InlineNotice className="mb-3" tone="danger">{error}</InlineNotice> : null}
        <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void handleCreateWorkspace(event)}>
          <Input onChange={(event) => setName(event.target.value)} placeholder="워크스페이스 이름" value={name} />
          <Input onChange={(event) => setDescription(event.target.value)} placeholder="설명" value={description} />
          <div className="flex items-center">
            <Button type="submit" variant="primary">워크스페이스 생성</Button>
          </div>
        </form>
      </Panel>

      <Panel eyebrow="Bindings" title="워크스페이스 접근 바인딩">
        <div className="grid gap-3 md:grid-cols-3">
          <Select
            onValueChange={async (value) => {
              setSelectedWorkspaceId(value);
              setBindings(await listWorkspaceBindings(token, value));
            }}
            options={workspaces.map((item) => ({ value: item.id, label: item.name }))}
            value={selectedWorkspaceId}
          />
          <Select
            onValueChange={setSelectedUserId}
            options={[
              { value: NONE_OPTION_VALUE, label: '사용자 선택 안 함' },
              ...users.map((item) => ({ value: item.id, label: item.email })),
            ]}
            value={selectedUserId || NONE_OPTION_VALUE}
          />
          <Select
            onValueChange={setSelectedGroupId}
            options={[
              { value: NONE_OPTION_VALUE, label: '그룹 선택 안 함' },
              ...groups.map((item) => ({ value: item.id, label: item.name })),
            ]}
            value={selectedGroupId}
          />
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button onClick={() => { void handleAddBindings(); }} variant="primary">바인딩 저장</Button>
        </div>
        <div className="mt-4 grid gap-2">
          {bindings.map((binding) => (
            <div
              key={`${binding.subject_type}-${binding.subject_id}`}
              className="rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] px-3 py-2 text-sm text-[var(--ui-color-ink)]"
            >
              {binding.subject_type}: {binding.subject_label} ({binding.role})
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

function TeamsSection({ token }: { token: string }) {
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [selectedTeamId, setSelectedTeamId] = useState('');
  const [selectedUserId, setSelectedUserId] = useState('');
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
      setSelectedTeamId((current) => current || teamItems[0]?.id || '');
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
      await load();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '팀을 생성하지 못했습니다.'));
    }
  }

  async function handleAddTeamMember() {
    if (!selectedTeamId || !selectedUserId) {
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
    <>
      <Panel eyebrow="Teams" title="팀 생성">
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {error ? <InlineNotice className="mb-3" tone="danger">{error}</InlineNotice> : null}
        <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void handleCreateTeam(event)}>
          <Select
            onValueChange={setSelectedWorkspaceId}
            options={workspaces.map((item) => ({ value: item.id, label: item.name }))}
            value={selectedWorkspaceId}
          />
          <Input onChange={(event) => setName(event.target.value)} placeholder="팀 이름" value={name} />
          <Input onChange={(event) => setDescription(event.target.value)} placeholder="설명" value={description} />
          <div className="md:col-span-3">
            <Button type="submit" variant="primary">팀 생성</Button>
          </div>
        </form>
      </Panel>

      <Panel eyebrow="Teams" title="팀 멤버십">
        <div className="grid gap-3 md:grid-cols-3">
          <Select
            onValueChange={setSelectedTeamId}
            options={teams.map((item) => ({ value: item.id, label: `${item.name} (${item.workspace_key})` }))}
            value={selectedTeamId}
          />
          <Select
            onValueChange={setSelectedUserId}
            options={users.map((item) => ({ value: item.id, label: item.email }))}
            value={selectedUserId}
          />
          <div className="flex items-center">
            <Button onClick={() => { void handleAddTeamMember(); }} variant="primary">멤버 추가</Button>
          </div>
        </div>
        <div className="mt-4 grid gap-2">
          {teamMembers.map((member) => (
            <div
              key={member.id}
              className="rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] px-3 py-2 text-sm text-[var(--ui-color-ink)]"
            >
              {member.email} / {member.display_name}
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

function FeaturePoliciesSection({ token }: { token: string }) {
  const [policies, setPolicies] = useState<FeaturePolicyItem[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setPolicies(await listFeaturePolicies(token));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '기능 정책을 불러오지 못했습니다.'));
    }
  }

  useEffect(() => {
    void load();
  }, [token]);

  async function handleSave() {
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
    <Panel eyebrow="Feature Access" title="기능 노출 정책">
      {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
      {error ? <InlineNotice className="mb-3" tone="danger">{error}</InlineNotice> : null}
      <div className="grid gap-3">
        {policies.map((policy) => (
          <label
            key={policy.id}
            className="flex items-start gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] p-3 text-sm text-[var(--ui-color-ink)]"
          >
            <input
              checked={policy.enabled}
              onChange={(event) => {
                setPolicies((current) =>
                  current.map((item) =>
                    item.id === policy.id ? { ...item, enabled: event.target.checked } : item,
                  ),
                );
              }}
              type="checkbox"
            />
            <div className="grid gap-1">
              <strong>{policy.name}</strong>
              <span>{policy.description}</span>
              <span className="text-[var(--ui-color-ink-muted)]">
                code: {policy.code}
              </span>
            </div>
          </label>
        ))}
        <div>
          <Button onClick={() => { void handleSave(); }} variant="primary">정책 저장</Button>
        </div>
      </div>
    </Panel>
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
    <Panel eyebrow="Audit" title="감사로그">
      {error ? <InlineNotice className="mb-3" tone="danger">{error}</InlineNotice> : null}
      <div className="grid gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <strong>{item.summary}</strong>
              <span className="text-[var(--ui-color-ink-muted)]">
                {new Date(item.created_at).toLocaleString()}
              </span>
            </div>
            <div className="mt-1 text-xs text-[var(--ui-color-ink-muted)]">
              {item.action} / {item.entity_kind} / {item.actor_name ?? 'system'}
            </div>
          </div>
        ))}
      </div>
    </Panel>
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
  switch (section) {
    case 'users':
      content = <UsersSection token={token} />;
      break;
    case 'groups':
      content = <GroupsSection token={token} />;
      break;
    case 'workspaces':
      content = <WorkspacesSection token={token} />;
      break;
    case 'teams':
      content = <TeamsSection token={token} />;
      break;
    case 'feature-access':
      content = <FeaturePoliciesSection token={token} />;
      break;
    case 'audit':
      content = <AuditSection token={token} />;
      break;
    default:
      content = null;
  }

  return <AdminLayout section={section}>{content}</AdminLayout>;
}
