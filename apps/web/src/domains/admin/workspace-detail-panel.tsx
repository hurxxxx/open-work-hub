import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check,
  Copy,
  MoreHorizontal,
  Plus,
  Search,
  Users as UsersIcon,
} from 'lucide-react';

import {
  Button,
  ConfirmDialog,
  Dialog,
  DropdownMenu,
  InlineNotice,
  Select,
} from '@aidoo/ui';

import {
  bulkWorkspaceMembers,
  deleteWorkspace,
  getWorkspaceApps,
  listWorkspaceBindings,
  listWorkspaceMemberCandidates,
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspace,
  updateWorkspaceApps,
  updateWorkspaceMemberRole,
  type AccessGroupItem,
  type WorkspaceBindingItem,
  type WorkspaceItem,
  type WorkspaceMemberCandidate,
  type WorkspaceMemberItem,
  type WorkspaceMembersResponse,
} from './admin-api';
import {
  APP_DESCRIPTIONS,
  APP_ICONS,
  APP_ORDER,
  Badge,
  FORM_FIELD_CLASS,
  FilterChip,
  MemberRoleBadge,
  PeopleDirectoryGrid,
  WORKSPACE_ENABLED_APP_LABELS,
  WORKSPACE_ROLE_LABELS,
  WORKSPACE_ROLE_OPTIONS,
  WORKSPACE_ROLE_RANK,
  emptySubjectSelection,
  formatDateLabel,
  getErrorMessage,
  removeSubject,
  selectionSize,
  toggleSubject,
  type SubjectSelectionState,
} from './admin-shared';

export interface WorkspaceDetailPanelCapabilities {
  canEditProfile: boolean;
  canManageApps: boolean;
  canManageMembers: boolean;
  canArchive: boolean;
  canDelete: boolean;
  /**
   * Whether the current user can browse the full employee directory
   * (`/api/v1/admin/users`). Platform admins can; workspace admins cannot.
   * When false, the inline subject picker hides the "directory" entry point
   * and members are added by name/email search via `listWorkspaceMemberCandidates`.
   */
  canBrowseDirectory: boolean;
}

export interface WorkspaceDetailPanelProps {
  workspace: WorkspaceItem | null;
  token: string;
  currentUserId: string;
  groups: AccessGroupItem[];
  canReadGroups: boolean;
  capabilities: WorkspaceDetailPanelCapabilities;
  onWorkspaceChanged: (next: WorkspaceItem) => void;
  onWorkspaceDeleted?: (workspaceId: string) => void;
  flashSuccess: (text: string) => void;
  flashError: (text: string) => void;
}

export function WorkspaceDetailPanel({
  workspace,
  token,
  currentUserId,
  groups,
  canReadGroups,
  capabilities,
  onWorkspaceChanged,
  onWorkspaceDeleted,
  flashSuccess,
  flashError,
}: WorkspaceDetailPanelProps) {
  const [bindings, setBindings] = useState<WorkspaceBindingItem[]>([]);
  const [selectedEnabledApps, setSelectedEnabledApps] = useState<string[]>([]);
  const [originalEnabledApps, setOriginalEnabledApps] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
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

  const workspaceId = workspace?.id ?? null;

  const resetAddPanel = useCallback(() => {
    setAddPanelOpen(false);
    setAddPickerOpen(false);
    setAddSelection(emptySubjectSelection());
    setAddRole('member');
  }, []);

  useEffect(() => {
    if (!workspaceId) {
      setBindings([]);
      setSelectedEnabledApps([]);
      setOriginalEnabledApps([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const [nextBindings, nextApps] = await Promise.all([
          listWorkspaceBindings(token, workspaceId),
          getWorkspaceApps(token, workspaceId),
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
  }, [token, workspaceId, flashError]);

  useEffect(() => {
    resetAddPanel();
  }, [workspaceId, resetAddPanel]);

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
    const result: WorkspaceBindingItem[] = [];
    for (const binding of userBindings) {
      if (binding.role === 'admin') {
        result.push(binding);
      }
      if (result.length >= 5) break;
    }
    if (result.length === 0 && userBindings.length > 0) {
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

  async function reloadBindings(): Promise<WorkspaceBindingItem[]> {
    if (!workspaceId) return [];
    const nextBindings = await listWorkspaceBindings(token, workspaceId);
    setBindings(nextBindings);
    return nextBindings;
  }

  async function handleEditWorkspace(payload: { name: string; description: string }) {
    if (!workspace) return;
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await updateWorkspace(token, workspace.id, {
        name: payload.name,
        description: payload.description,
        active: workspace.active,
      });
      onWorkspaceChanged(updated);
      setEditOpen(false);
      flashSuccess('워크스페이스 정보를 저장했습니다.');
    } catch (caughtError) {
      setEditError(getErrorMessage(caughtError, '워크스페이스를 저장하지 못했습니다.'));
    } finally {
      setEditBusy(false);
    }
  }

  async function handleToggleActive(target: WorkspaceItem, nextActive: boolean) {
    setBusy(true);
    try {
      const updated = await updateWorkspace(token, target.id, {
        name: target.name,
        description: target.description,
        active: nextActive,
      });
      onWorkspaceChanged(updated);
      flashSuccess(
        nextActive ? '워크스페이스를 다시 활성화했습니다.' : '워크스페이스를 보관함으로 옮겼습니다.',
      );
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '워크스페이스 상태를 변경하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteWorkspace(target: WorkspaceItem) {
    setBusy(true);
    try {
      await deleteWorkspace(token, target.id);
      onWorkspaceDeleted?.(target.id);
      flashSuccess(`워크스페이스 "${target.name}" 를 영구 삭제했습니다.`);
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '워크스페이스를 삭제하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleBulkAddSelection() {
    if (!workspaceId) return;
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
      const result = await bulkWorkspaceMembers(token, workspaceId, {
        action: 'add',
        subjects,
      });
      if (result.failed.length > 0) {
        flashError(`${result.succeeded}명 추가됨, ${result.failed.length}명 실패`);
      } else {
        flashSuccess(`${result.succeeded}명을 추가했습니다.`);
      }
      await reloadBindings();
      if (workspace) {
        onWorkspaceChanged({
          ...workspace,
          member_count: workspace.member_count + result.succeeded,
        });
      }
      resetAddPanel();
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '멤버를 추가하지 못했습니다.'));
    } finally {
      setAddBusy(false);
    }
  }

  async function handleChangeMemberRole(binding: WorkspaceBindingItem, role: string) {
    if (!workspaceId) return;
    setBusy(true);
    try {
      const updated = await updateWorkspaceMemberRole(
        token,
        workspaceId,
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
    if (!workspaceId) return;
    setBusy(true);
    try {
      await removeWorkspaceMember(
        token,
        workspaceId,
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
      if (workspace) {
        onWorkspaceChanged({
          ...workspace,
          member_count: Math.max(0, workspace.member_count - 1),
        });
      }
      flashSuccess('멤버를 제거했습니다.');
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, '멤버를 제거하지 못했습니다.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveApps() {
    if (!workspaceId || !workspace) return;
    setBusy(true);
    try {
      const response = await updateWorkspaceApps(token, workspaceId, selectedEnabledApps);
      setSelectedEnabledApps(response.enabled_apps);
      setOriginalEnabledApps(response.enabled_apps);
      onWorkspaceChanged({ ...workspace, enabled_apps: response.enabled_apps });
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

  function getDeleteBlockReason(target: WorkspaceItem): string | null {
    if (target.active) {
      return '워크스페이스를 먼저 보관함으로 옮겨야 영구 삭제할 수 있습니다.';
    }
    const blockers: string[] = [];
    if (target.team_count > 0) blockers.push(`${target.team_count}개 space`);
    if (target.meeting_count > 0) blockers.push(`${target.meeting_count}개 회의`);
    if (target.doc_count > 0) blockers.push(`${target.doc_count}개 문서`);
    if (blockers.length === 0) return null;
    return `${blockers.join(', ')} 가 남아있습니다. 먼저 비워주세요.`;
  }

  async function handleDrawerChanged() {
    await reloadBindings();
    if (workspaceId) {
      try {
        const fresh = await listWorkspaceMembers(token, workspaceId, { pageSize: 1, page: 1 });
        if (workspace) {
          onWorkspaceChanged({ ...workspace, member_count: fresh.total });
        }
      } catch {
        /* noop — drawer has its own error channel */
      }
    }
  }

  if (!workspace) {
    return (
      <div className="flex h-full items-center justify-center px-8 py-16 text-center text-app-ink/60">
        <div className="space-y-2">
          <p className="app-text-title-md text-app-ink">워크스페이스를 선택하세요</p>
          <p className="app-text-body">
            왼쪽 목록에서 워크스페이스를 선택하면 상세 정보를 볼 수 있습니다.
          </p>
        </div>
      </div>
    );
  }

  const dropdownItems: Parameters<typeof DropdownMenu>[0]['items'] = [];
  if (capabilities.canArchive) {
    dropdownItems.push(
      workspace.active
        ? {
            id: 'archive',
            label: '보관함으로 옮기기',
            onSelect: () =>
              openConfirm({
                title: '워크스페이스 보관',
                description: `"${workspace.name}" 을 보관함으로 옮기면 사용자가 더 이상 접근하지 못합니다. 멤버와 데이터는 보존되며 언제든 다시 활성화할 수 있습니다.`,
                confirmLabel: '보관하기',
                variant: 'default',
                onConfirm: () => handleToggleActive(workspace, false),
              }),
          }
        : {
            id: 'unarchive',
            label: '다시 활성화',
            onSelect: () => handleToggleActive(workspace, true),
          },
    );
  }
  if (capabilities.canDelete && !workspace.active) {
    const reason = getDeleteBlockReason(workspace);
    dropdownItems.push({
      id: 'delete',
      label: reason ? `영구 삭제 (${reason})` : '영구 삭제',
      separatorBefore: dropdownItems.length > 0,
      tone: 'danger' as const,
      disabled: Boolean(reason),
      onSelect: () =>
        openConfirm({
          title: '워크스페이스 영구 삭제',
          description: `"${workspace.name}" 을 완전히 삭제하면 되돌릴 수 없습니다. 모든 멤버십과 enabled apps 가 함께 제거됩니다.`,
          confirmLabel: '영구 삭제',
          variant: 'danger',
          onConfirm: () => handleDeleteWorkspace(workspace),
        }),
    });
  }

  return (
    <>
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {/* Hero */}
        <header className="border-b border-app-border px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="app-text-title-md truncate text-app-ink">{workspace.name}</h2>
                {workspace.active ? (
                  <Badge tone="green">활성</Badge>
                ) : (
                  <Badge tone="amber">보관됨</Badge>
                )}
                <code className="app-text-caption rounded bg-app-surface-sidebar px-1.5 py-0.5 font-mono text-app-ink/70">
                  {workspace.key}
                </code>
                <button
                  type="button"
                  onClick={() => {
                    try {
                      navigator.clipboard?.writeText(workspace.key);
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
                  · 멤버 {workspace.member_count} · 만든 날짜{' '}
                  {formatDateLabel(workspace.created_at)}
                </span>
              </div>
              {workspace.description ? (
                <p className="app-text-body-sm mt-1 whitespace-pre-wrap text-app-ink/85">
                  {workspace.description}
                </p>
              ) : capabilities.canEditProfile ? (
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
              {capabilities.canEditProfile ? (
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
              {dropdownItems.length > 0 ? (
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
                  items={dropdownItems}
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
                  disabled={!capabilities.canManageApps || busy}
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

        {/* Groups (read-only binding preview, all shown) */}
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
                  canManage={capabilities.canManageMembers}
                  isCurrentUser={false}
                  busy={busy}
                  onChangeRole={(role) => void handleChangeMemberRole(binding, role)}
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
                {workspace.member_count}명 · 관리자 미리보기
              </span>
            </h3>
            <div className="flex items-center gap-1.5">
              {capabilities.canManageMembers ? (
                <Button variant="primary" onClick={() => setAddPanelOpen((current) => !current)}>
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

          {addPanelOpen && capabilities.canManageMembers ? (
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
                workspaceId={workspace.id}
                token={token}
                groups={groups}
                excludeIds={memberSubjectIds}
                selection={addSelection}
                onSelectionChange={setAddSelection}
                canReadGroups={canReadGroups}
                onOpenDirectory={
                  capabilities.canBrowseDirectory ? () => setAddPickerOpen(true) : null
                }
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
              {capabilities.canManageMembers ? (
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
                  canManage={capabilities.canManageMembers}
                  isCurrentUser={
                    binding.subject_type === 'user' && binding.subject_id === currentUserId
                  }
                  busy={busy}
                  onChangeRole={(role) => void handleChangeMemberRole(binding, role)}
                  onRemove={() => void handleRemoveMember(binding)}
                />
              ))}
              {workspace.member_count > previewBindings.length ? (
                <button
                  type="button"
                  onClick={() => setMembersDrawerOpen(true)}
                  className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-accent transition-colors hover:bg-app-surface-sidebar"
                >
                  전체 {workspace.member_count}명 보기 →
                </button>
              ) : null}
            </div>
          )}
        </section>
      </div>

      {/* Sticky save bar (apps dirty state) */}
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
              disabled={busy || !capabilities.canManageApps}
              onClick={() => void handleSaveApps()}
            >
              변경 저장
            </Button>
          </div>
        </div>
      ) : null}

      <WorkspaceEditModal
        open={editOpen}
        workspace={workspace}
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
        workspace={workspace}
        token={token}
        canManage={capabilities.canManageMembers}
        currentUserId={currentUserId}
        onChanged={() => void handleDrawerChanged()}
        onError={flashError}
        onSuccess={flashSuccess}
      />
      {capabilities.canBrowseDirectory ? (
        <PeoplePickerModal
          open={addPickerOpen}
          onClose={() => setAddPickerOpen(false)}
          token={token}
          selection={addSelection}
          onSelectionChange={setAddSelection}
          excludeIds={memberSubjectIds}
        />
      ) : null}
    </>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

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
  const Icon = APP_ICONS[appCode] ?? (() => null);
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

export function WorkspaceMemberRow({
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

function SelectedSubjectsBar({
  selection,
  onRemove,
}: {
  selection: SubjectSelectionState;
  onRemove: (kind: 'user' | 'group', id: string) => void;
}) {
  const all = [
    ...Array.from(selection.groups.values()),
    ...Array.from(selection.users.values()),
  ];
  if (all.length === 0) {
    return <div className="app-text-caption text-app-ink/40">선택한 사용자가 없습니다.</div>;
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
  onOpenDirectory: (() => void) | null;
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
        {onOpenDirectory ? (
          <button
            type="button"
            className="app-text-control ml-auto rounded px-2 py-0.5 text-app-accent hover:bg-app-accent/10"
            onClick={onOpenDirectory}
          >
            임직원 디렉터리 열기
          </button>
        ) : null}
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
          onToggleSelect={(subject) => onSelectionChange(toggleSubject(selection, subject))}
          excludeIds={excludeIds}
        />
      </div>
    </Dialog>
  );
}

function WorkspaceEditModal({
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
            className={FORM_FIELD_CLASS}
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">설명</span>
          <textarea
            className={`${FORM_FIELD_CLASS} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={1000}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">Key</span>
          <input
            className={`${FORM_FIELD_CLASS} cursor-not-allowed bg-app-surface-sidebar text-app-ink/60`}
            value={workspace.key}
            readOnly
          />
        </label>
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
      </form>
    </Dialog>
  );
}

// ------------------------------------------------------------------
// Members management drawer (large; imported only by WorkspaceDetailPanel)
// ------------------------------------------------------------------

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
          !(item.subject_type === 'user' && item.subject_id === currentUserId),
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
            <span className="app-text-body text-app-ink">{selectedKeys.size} 명 선택됨</span>
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
                        {isSelf ? <span className="ml-2 text-app-ink/40">(본인)</span> : null}
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
