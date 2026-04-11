import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Button, InlineNotice } from '@aidoo/ui';

import { useAuth } from '@/src/domains/auth/auth-provider';
import { workspaceRoleAllows } from '@/src/domains/auth/auth-api';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import {
  createTeam,
  getWorkspaceApps,
  listTeams,
  listWorkspaceBindings,
  listWorkspaceMemberCandidates,
  listWorkspaces,
  replaceWorkspaceBindings,
  updateWorkspace,
  updateWorkspaceApps,
  type TeamItem,
  type WorkspaceBindingItem,
  type WorkspaceItem,
  type WorkspaceMemberCandidate,
} from '@/src/domains/admin/admin-api';

const FIELD_CLASS_NAME =
  'app-text-body w-full rounded-lg border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none transition-colors focus:border-app-accent';

const APP_OPTIONS = [
  { code: 'ai', label: 'AI' },
  { code: 'docs', label: 'Docs' },
  { code: 'pms', label: 'PMS' },
  { code: 'planner', label: 'Planner' },
  { code: 'meeting', label: 'Meeting' },
] as const;

const WORKSPACE_ROLE_OPTIONS = [
  { value: 'member', label: 'Member' },
  { value: 'admin', label: 'Admin' },
] as const;

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function sortBindings(bindings: WorkspaceBindingItem[]): WorkspaceBindingItem[] {
  return [...bindings].sort((left, right) => {
    if (left.subject_type !== right.subject_type) {
      return left.subject_type.localeCompare(right.subject_type);
    }
    return left.subject_label.localeCompare(right.subject_label, 'ko');
  });
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-app-border bg-app-surface p-5">
      <div className="mb-4 space-y-1">
        <h2 className="app-text-title-md text-app-ink">{title}</h2>
        {description ? (
          <p className="app-text-body text-app-ink/60">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function WorkspaceSettingsView() {
  const { workspaceSlug } = useParams();
  const { token, user } = useAuth();
  const [workspace, setWorkspace] = useState<WorkspaceItem | null>(null);
  const [bindings, setBindings] = useState<WorkspaceBindingItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [memberCandidates, setMemberCandidates] = useState<WorkspaceMemberCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [enabledApps, setEnabledApps] = useState<string[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState('');
  const [selectedRole, setSelectedRole] = useState('member');
  const [candidateQuery, setCandidateQuery] = useState('');
  const [newSpaceName, setNewSpaceName] = useState('');
  const [newSpaceDescription, setNewSpaceDescription] = useState('');

  const currentWorkspaceSummary = useMemo(
    () => user?.workspaces.find((item) => item.slug === workspaceSlug) ?? null,
    [user?.workspaces, workspaceSlug],
  );
  const canManageWorkspace = workspaceRoleAllows(currentWorkspaceSummary?.role, 'admin');

  async function loadWorkspaceData(searchQuery = '') {
    if (!token || !workspaceSlug) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const workspaceItems = await listWorkspaces(token);
      const nextWorkspace = workspaceItems.find((item) => item.key === workspaceSlug) ?? null;
      if (!nextWorkspace) {
        setWorkspace(null);
        setBindings([]);
        setTeams([]);
        setMemberCandidates([]);
        return;
      }

      const [appsResponse, bindingsResponse, teamsResponse, candidatesResponse] = await Promise.all([
        getWorkspaceApps(token, nextWorkspace.id),
        listWorkspaceBindings(token, nextWorkspace.id),
        listTeams(token, nextWorkspace.id),
        canManageWorkspace ? listWorkspaceMemberCandidates(token, nextWorkspace.id, searchQuery) : Promise.resolve([]),
      ]);

      setWorkspace({ ...nextWorkspace, enabled_apps: appsResponse.enabled_apps });
      setName(nextWorkspace.name);
      setDescription(nextWorkspace.description);
      setEnabledApps(appsResponse.enabled_apps);
      setBindings(sortBindings(bindingsResponse));
      setTeams(teamsResponse);
      setMemberCandidates(candidatesResponse);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '워크스페이스 설정을 불러오지 못했습니다.'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkspaceData(candidateQuery);
  }, [candidateQuery, canManageWorkspace, token, workspaceSlug]);

  const directBindings = bindings.filter((item) => item.subject_type === 'user');
  const groupBindings = bindings.filter((item) => item.subject_type === 'group');

  if (!workspaceSlug || !currentWorkspaceSummary) {
    return <AccessDeniedView description="현재 계정은 이 workspace 설정에 접근할 수 없습니다." />;
  }

  if (!canManageWorkspace) {
    return <AccessDeniedView description="이 workspace 설정은 admin 이상만 접근할 수 있습니다." />;
  }

  async function saveProfile() {
    if (!token || !workspace) return;
    setMessage(null);
    setError(null);
    try {
      const updated = await updateWorkspace(token, workspace.id, {
        key: workspace.key,
        name: name.trim(),
        description: description.trim(),
        active: workspace.active,
      });
      setWorkspace(updated);
      setName(updated.name);
      setDescription(updated.description);
      setMessage('Workspace profile 을 저장했습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, 'Workspace profile 을 저장하지 못했습니다.'));
    }
  }

  async function saveEnabledApps() {
    if (!token || !workspace) return;
    setMessage(null);
    setError(null);
    try {
      const response = await updateWorkspaceApps(token, workspace.id, enabledApps);
      setEnabledApps(response.enabled_apps);
      setWorkspace((current) => (current ? { ...current, enabled_apps: response.enabled_apps } : current));
      setMessage('Enabled apps 를 저장했습니다.');
      await loadWorkspaceData(candidateQuery);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, 'Enabled apps 를 저장하지 못했습니다.'));
    }
  }

  async function saveBindings(nextBindings: WorkspaceBindingItem[], successMessage: string) {
    if (!token || !workspace) return;
    setMessage(null);
    setError(null);
    try {
      const response = await replaceWorkspaceBindings(token, workspace.id, {
        users: nextBindings
          .filter((item) => item.subject_type === 'user')
          .map((item) => ({ subject_id: item.subject_id, role: item.role })),
        groups: nextBindings
          .filter((item) => item.subject_type === 'group')
          .map((item) => ({ subject_id: item.subject_id, role: item.role })),
      });
      setBindings(sortBindings(response));
      setMessage(successMessage);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, 'Workspace membership 을 저장하지 못했습니다.'));
    }
  }

  async function addDirectMember() {
    const candidate = memberCandidates.find((item) => item.id === selectedCandidateId);
    if (!candidate) return;
    const nextBindings = sortBindings([
      ...bindings.filter((item) => item.subject_id !== candidate.id),
      {
        subject_id: candidate.id,
        subject_type: 'user',
        subject_label: candidate.email,
        role: selectedRole,
      },
    ]);
    await saveBindings(nextBindings, 'Workspace member 를 추가했습니다.');
    setSelectedCandidateId('');
    setSelectedRole('member');
  }

  async function updateDirectMemberRole(subjectId: string, role: string) {
    const nextBindings = sortBindings(
      bindings.map((item) => (
        item.subject_type === 'user' && item.subject_id === subjectId
          ? { ...item, role }
          : item
      )),
    );
    await saveBindings(nextBindings, 'Workspace member role 을 저장했습니다.');
  }

  async function removeDirectMember(subjectId: string) {
    const nextBindings = bindings.filter(
      (item) => !(item.subject_type === 'user' && item.subject_id === subjectId),
    );
    await saveBindings(nextBindings, 'Workspace member 를 제거했습니다.');
  }

  async function handleCreateSpace() {
    if (!token || !workspace || !newSpaceName.trim()) return;
    setMessage(null);
    setError(null);
    try {
      const created = await createTeam(token, workspace.id, {
        name: newSpaceName.trim(),
        description: newSpaceDescription.trim(),
      });
      setTeams((current) => [...current, created].sort((left, right) => left.name.localeCompare(right.name, 'ko')));
      setNewSpaceName('');
      setNewSpaceDescription('');
      setMessage('새 space 를 만들었습니다.');
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '새 space 를 만들지 못했습니다.'));
    }
  }

  return (
    <div className="custom-scrollbar h-full overflow-y-auto p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="space-y-2 border-b border-app-border pb-6">
          <div className="app-text-overline text-app-ink/50">Workspace Settings</div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="app-text-title-lg text-app-ink">{workspace?.name ?? currentWorkspaceSummary.name}</h1>
              <p className="app-text-body mt-1 text-app-ink/60">
                실제 협업 공간 단위의 멤버십, enabled apps, space 구성을 관리합니다.
              </p>
            </div>
            <div className="rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 text-right">
              <div className="app-text-caption text-app-ink/50">Your role</div>
              <div className="app-text-body-sm text-app-ink">{currentWorkspaceSummary.role}</div>
            </div>
          </div>
        </header>

        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        {loading ? <InlineNotice tone="info">Workspace settings 를 불러오는 중입니다.</InlineNotice> : null}

        <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <SectionCard
            title="Workspace Profile"
            description="이 협업 공간의 이름과 설명을 관리합니다."
          >
            <div className="grid gap-4">
              <div className="grid gap-1">
                <span className="app-text-caption text-app-ink/50">Slug</span>
                <div className="rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
                  {workspace?.key ?? workspaceSlug}
                </div>
              </div>
              <div className="grid gap-1">
                <span className="app-text-caption text-app-ink/50">Name</span>
                <input
                  className={FIELD_CLASS_NAME}
                  onChange={(event) => setName(event.target.value)}
                  value={name}
                />
              </div>
              <div className="grid gap-1">
                <span className="app-text-caption text-app-ink/50">Description</span>
                <textarea
                  className={`${FIELD_CLASS_NAME} min-h-[110px] resize-y`}
                  onChange={(event) => setDescription(event.target.value)}
                  value={description}
                />
              </div>
              <div className="flex justify-end">
                <Button onClick={() => { void saveProfile(); }} variant="primary">
                  Save profile
                </Button>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="Enabled Apps"
            description="사용자별 토글이 아니라 workspace 전체에서 노출할 앱을 정합니다."
          >
            <div className="grid gap-2">
              {APP_OPTIONS.map((option) => (
                <label
                  className="app-text-control inline-flex items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                  key={option.code}
                >
                  <input
                    checked={enabledApps.includes(option.code)}
                    onChange={() => {
                      setEnabledApps((current) => (
                        current.includes(option.code)
                          ? current.filter((item) => item !== option.code)
                          : [...current, option.code]
                      ));
                    }}
                    type="checkbox"
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <Button onClick={() => { void saveEnabledApps(); }} variant="primary">
                Save apps
              </Button>
            </div>
          </SectionCard>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <SectionCard
            title="Workspace Members"
            description="직접 멤버십을 관리합니다. 그룹 기반 멤버십은 아래에서 읽기 전용으로 표시합니다."
          >
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-[1.2fr_0.7fr_auto]">
                <div className="grid gap-1">
                  <span className="app-text-caption text-app-ink/50">Find user</span>
                  <input
                    className={FIELD_CLASS_NAME}
                    onChange={(event) => setCandidateQuery(event.target.value)}
                    placeholder="이름 또는 이메일로 검색"
                    value={candidateQuery}
                  />
                </div>
                <div className="grid gap-1">
                  <span className="app-text-caption text-app-ink/50">Add user</span>
                  <select
                    className={FIELD_CLASS_NAME}
                    onChange={(event) => setSelectedCandidateId(event.target.value)}
                    value={selectedCandidateId}
                  >
                    <option value="">사용자를 선택하세요</option>
                    {memberCandidates
                      .filter((item) => !directBindings.some((binding) => binding.subject_id === item.id))
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.full_name} ({item.email})
                        </option>
                      ))}
                  </select>
                </div>
                <div className="grid gap-1">
                  <span className="app-text-caption text-app-ink/50">Role</span>
                  <select
                    className={FIELD_CLASS_NAME}
                    onChange={(event) => setSelectedRole(event.target.value)}
                    value={selectedRole}
                  >
                    {WORKSPACE_ROLE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex justify-end">
                <Button
                  disabled={!selectedCandidateId}
                  onClick={() => { void addDirectMember(); }}
                  variant="primary"
                >
                  Add member
                </Button>
              </div>

              <div className="space-y-2">
                {directBindings.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-app-border bg-app-surface-sidebar px-4 py-5 text-app-ink/60">
                    직접 할당된 멤버가 없습니다.
                  </div>
                ) : directBindings.map((binding) => (
                  <div
                    className="grid gap-3 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3 md:grid-cols-[1fr_180px_auto]"
                    key={`${binding.subject_type}-${binding.subject_id}`}
                  >
                    <div>
                      <div className="app-text-body-sm text-app-ink">{binding.subject_label}</div>
                      <div className="app-text-caption mt-1 text-app-ink/50">direct membership</div>
                    </div>
                    <select
                      className={FIELD_CLASS_NAME}
                      onChange={(event) => {
                        void updateDirectMemberRole(binding.subject_id, event.target.value);
                      }}
                      value={binding.role}
                    >
                      {WORKSPACE_ROLE_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                      ))}
                    </select>
                    <div className="flex justify-end">
                      <Button
                        onClick={() => { void removeDirectMember(binding.subject_id); }}
                        variant="secondary"
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="Inherited Access"
            description="그룹을 통해 유입되는 멤버십과 workspace 내부 spaces 를 보여줍니다."
          >
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="app-text-caption text-app-ink/50">Group bindings</div>
                {groupBindings.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-app-border bg-app-surface-sidebar px-4 py-4 text-app-ink/60">
                    그룹 기반 binding 이 없습니다.
                  </div>
                ) : groupBindings.map((binding) => (
                  <div
                    className="flex items-center justify-between rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3"
                    key={`${binding.subject_type}-${binding.subject_id}`}
                  >
                    <div>
                      <div className="app-text-body-sm text-app-ink">{binding.subject_label}</div>
                      <div className="app-text-caption mt-1 text-app-ink/50">group · {binding.role}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="space-y-2 border-t border-app-border pt-4">
                <div className="app-text-caption text-app-ink/50">Spaces</div>
                {teams.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-app-border bg-app-surface-sidebar px-4 py-4 text-app-ink/60">
                    아직 space 가 없습니다.
                  </div>
                ) : teams.map((team) => (
                  <div
                    className="flex items-center justify-between rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3"
                    key={team.id}
                  >
                    <div>
                      <div className="app-text-body-sm text-app-ink">{team.name}</div>
                      <div className="app-text-caption mt-1 text-app-ink/50">
                        {team.description || '설명 없음'} · {team.member_count} members
                      </div>
                    </div>
                  </div>
                ))}

                <div className="grid gap-3 border-t border-app-border pt-4">
                  <input
                    className={FIELD_CLASS_NAME}
                    onChange={(event) => setNewSpaceName(event.target.value)}
                    placeholder="New space name"
                    value={newSpaceName}
                  />
                  <input
                    className={FIELD_CLASS_NAME}
                    onChange={(event) => setNewSpaceDescription(event.target.value)}
                    placeholder="Description"
                    value={newSpaceDescription}
                  />
                  <div className="flex justify-end">
                    <Button
                      disabled={!newSpaceName.trim()}
                      onClick={() => { void handleCreateSpace(); }}
                      variant="primary"
                    >
                      Create space
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
