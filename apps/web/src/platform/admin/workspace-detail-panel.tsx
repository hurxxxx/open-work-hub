import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  listWorkspaceBindings,
  listWorkspaceMemberCandidates,
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspace,
  updateWorkspaceMemberRole,
  type AccessGroupItem,
  type WorkspaceBindingItem,
  type WorkspaceItem,
  type WorkspaceMemberCandidate,
  type WorkspaceMemberItem,
  type WorkspaceMembersResponse,
} from './admin-api';
import {
  Badge,
  FORM_FIELD_CLASS,
  FilterChip,
  MemberRoleBadge,
  PeopleDirectoryGrid,
  WORKSPACE_ROLE_RANK,
  emptySubjectSelection,
  formatDateLabel,
  getErrorMessage,
  getWorkspaceRoleLabel,
  getWorkspaceRoleOptions,
  removeSubject,
  selectionSize,
  toggleSubject,
  type SubjectSelectionState,
} from './admin-shared';

export interface WorkspaceDetailPanelCapabilities {
  canEditProfile: boolean;
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
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [bindings, setBindings] = useState<WorkspaceBindingItem[]>([]);
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
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const nextBindings = await listWorkspaceBindings(token, workspaceId);
        if (!cancelled) {
          setBindings(nextBindings);
        }
      } catch (caughtError) {
        if (!cancelled) {
          flashError(getErrorMessage(caughtError, t('admin.workspace.detailLoadFailed')));
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
        return a.subject_label.localeCompare(b.subject_label, locale);
      }),
    [bindings, locale],
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
      flashSuccess(t('admin.workspace.profileSaved'));
    } catch (caughtError) {
      setEditError(getErrorMessage(caughtError, t('admin.workspace.profileSaveFailed')));
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
        nextActive ? t('admin.workspace.reactivated') : t('admin.workspace.archived'),
      );
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, t('admin.workspace.statusChangeFailed')));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteWorkspace(target: WorkspaceItem) {
    setBusy(true);
    try {
      await deleteWorkspace(token, target.id);
      onWorkspaceDeleted?.(target.id);
      flashSuccess(t('admin.workspace.deleted', { name: target.name }));
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, t('admin.workspace.deleteFailed')));
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
        flashError(t('admin.workspace.members.bulkAddPartial', { succeeded: result.succeeded, failed: result.failed.length }));
      } else {
        flashSuccess(t('admin.workspace.members.bulkAdded', { count: result.succeeded }));
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
      flashError(getErrorMessage(caughtError, t('admin.workspace.members.addFailed')));
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
      flashSuccess(t('admin.workspace.members.roleChanged'));
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, t('admin.workspace.members.roleChangeFailed')));
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
      flashSuccess(t('admin.workspace.members.removed'));
    } catch (caughtError) {
      flashError(getErrorMessage(caughtError, t('admin.workspace.members.removeFailed')));
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
      return t('admin.workspace.deleteBlockActive');
    }
    const blockers: string[] = [];
    if (target.team_count > 0) blockers.push(t('admin.workspace.blockerSpaces', { count: target.team_count }));
    if (target.meeting_count > 0) blockers.push(t('admin.workspace.blockerMeetings', { count: target.meeting_count }));
    if (target.doc_count > 0) blockers.push(t('admin.workspace.blockerDocs', { count: target.doc_count }));
    if (blockers.length === 0) return null;
    return t('admin.workspace.deleteBlockRemaining', { items: blockers.join(', ') });
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
          <p className="app-text-title-md text-app-ink">{t('admin.workspace.noSelectionTitle')}</p>
          <p className="app-text-body">
            {t('admin.workspace.noSelectionDescription')}
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
            label: t('admin.workspace.archiveAction'),
            onSelect: () =>
              openConfirm({
                title: t('admin.workspace.archiveConfirmTitle'),
                description: t('admin.workspace.archiveConfirmDescription', { name: workspace.name }),
                confirmLabel: t('admin.workspace.archiveConfirm'),
                variant: 'default',
                onConfirm: () => handleToggleActive(workspace, false),
              }),
          }
        : {
            id: 'unarchive',
            label: t('admin.workspace.reactivateAction'),
            onSelect: () => handleToggleActive(workspace, true),
          },
    );
  }
  if (capabilities.canDelete && !workspace.active) {
    const reason = getDeleteBlockReason(workspace);
    dropdownItems.push({
      id: 'delete',
      label: reason ? t('admin.workspace.deleteActionWithReason', { reason }) : t('common:actions.deletePermanently'),
      separatorBefore: dropdownItems.length > 0,
      tone: 'danger' as const,
      disabled: Boolean(reason),
      onSelect: () =>
        openConfirm({
          title: t('admin.workspace.deleteConfirmTitle'),
          description: t('admin.workspace.deleteConfirmDescription', { name: workspace.name }),
          confirmLabel: t('common:actions.deletePermanently'),
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
                  <Badge tone="green">{t('admin.shared.status.activeShort')}</Badge>
                ) : (
                  <Badge tone="amber">{t('admin.workspace.archivedStatus')}</Badge>
                )}
                <code className="app-text-caption rounded bg-app-surface-sidebar px-1.5 py-0.5 font-mono text-app-ink/70">
                  {workspace.key}
                </code>
                <button
                  type="button"
                  onClick={() => {
                    try {
                      navigator.clipboard?.writeText(workspace.key);
                      flashSuccess(t('admin.workspace.keyCopied'));
                    } catch {
                      flashError(t('admin.workspace.keyCopyFailed'));
                    }
                  }}
                  className="rounded p-0.5 text-app-ink/50 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                  aria-label={t('admin.workspace.copyKey')}
                >
                  <Copy size={11} />
                </button>
                <span className="app-text-caption text-app-ink/50">
                  {t('admin.workspace.heroMeta', { count: workspace.member_count, date: formatDateLabel(workspace.created_at, locale) })}
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
                  {t('admin.workspace.addDescription')}
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
                  {t('common:actions.edit')}
                </Button>
              ) : null}
              {dropdownItems.length > 0 ? (
                <DropdownMenu
                  trigger={
                    <button
                      type="button"
                      className="rounded p-1 text-app-ink/70 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                      aria-label={t('admin.workspace.actions')}
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

        {/* Groups (read-only binding preview, all shown) */}
        {groupBindings.length > 0 ? (
          <section className="border-b border-app-border px-4 py-3">
            <h3 className="app-text-control mb-2 text-app-ink">
              {t('admin.shared.directory.group')}{' '}
              <span className="app-text-caption ml-1 text-app-ink/50">
                {t('admin.workspace.groupBindingMeta', { count: groupBindings.length })}
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

        {/* Members preview + open drawer */}
        <section className="px-4 py-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="app-text-control text-app-ink">
              {t('admin.workspace.members.title')}{' '}
              <span className="app-text-caption ml-1 text-app-ink/50">
                {t('admin.workspace.members.previewMeta', { count: workspace.member_count })}
              </span>
            </h3>
            <div className="flex items-center gap-1.5">
              {capabilities.canManageMembers ? (
                <Button variant="primary" onClick={() => setAddPanelOpen(true)}>
                  <Plus size={12} className="mr-1" />
                  {t('admin.workspace.members.add')}
                </Button>
              ) : null}
              <Button variant="ghost" onClick={() => setMembersDrawerOpen(true)}>
                <UsersIcon size={12} className="mr-1" />
                {t('admin.workspace.members.manage')}
              </Button>
            </div>
          </div>

          {previewBindings.length === 0 ? (
            <div className="rounded-md border border-dashed border-app-border bg-app-bg px-3 py-6 text-center">
              <p className="app-text-body-sm text-app-ink/60">{t('admin.workspace.members.emptyYet')}</p>
              {capabilities.canManageMembers ? (
                <p className="app-text-caption mt-0.5 text-app-ink/40">
                  {t('admin.workspace.members.emptyHint')}
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
                  {t('admin.workspace.members.viewAll', { count: workspace.member_count })}
                </button>
              ) : null}
            </div>
          )}
        </section>
      </div>

      <WorkspaceEditModal
        open={editOpen}
        workspace={workspace}
        onOpenChange={setEditOpen}
        onSave={handleEditWorkspace}
        busy={editBusy}
        error={editError}
      />
      {capabilities.canManageMembers ? (
        <WorkspaceAddMemberModal
          open={addPanelOpen}
          onOpenChange={(next) => {
            if (!next) {
              resetAddPanel();
            } else {
              setAddPanelOpen(true);
            }
          }}
          workspaceId={workspace.id}
          token={token}
          groups={groups}
          canReadGroups={canReadGroups}
          canBrowseDirectory={capabilities.canBrowseDirectory}
          excludeIds={memberSubjectIds}
          selection={addSelection}
          onSelectionChange={setAddSelection}
          role={addRole}
          onRoleChange={setAddRole}
          busy={addBusy}
          onOpenDirectory={() => setAddPickerOpen(true)}
          onSubmit={handleBulkAddSelection}
          onCancel={resetAddPanel}
        />
      ) : null}
      {confirmState ? (
        <ConfirmDialog
          open
          title={confirmState.title}
          description={confirmState.description}
          confirmLabel={confirmState.confirmLabel}
          cancelLabel={t('common:actions.cancel')}
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
  const { t } = useTranslation('apps');
  const roleOptions = getWorkspaceRoleOptions(t);
  const showMenu = canManage && !isCurrentUser;
  const items: Parameters<typeof DropdownMenu>[0]['items'] = [
    ...roleOptions.map((option) => ({
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
      label: t('admin.workspace.members.removeFromWorkspace'),
      onSelect: onRemove,
      disabled: busy,
      tone: 'danger' as const,
      separatorBefore: true,
    },
  ];

  return (
    <div className="flex items-center gap-2 px-3 py-1.5">
      {binding.subject_type === 'group' ? (
        <UsersIcon size={12} className="shrink-0 text-app-ink/50" aria-label={t('admin.shared.directory.group')} />
      ) : (
        <span
          className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-app-ink/30"
          aria-label={t('admin.shared.directory.user')}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="app-text-body-sm truncate text-app-ink">
          <span className="font-medium">{binding.subject_label}</span>
          {binding.subject_secondary ? (
            <span className="ml-2 text-app-ink/50">{binding.subject_secondary}</span>
          ) : null}
          {isCurrentUser ? <span className="ml-2 text-app-ink/40">{t('admin.workspace.members.currentUser')}</span> : null}
        </div>
      </div>
      <MemberRoleBadge role={binding.role} />
      {showMenu ? (
        <DropdownMenu
          trigger={
            <button
              type="button"
              className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
              aria-label={t('admin.workspace.members.actions')}
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
  const { t } = useTranslation('apps');
  const all = [
    ...Array.from(selection.groups.values()),
    ...Array.from(selection.users.values()),
  ];
  if (all.length === 0) {
    return <div className="app-text-caption text-app-ink/40">{t('admin.workspace.addMembers.noSelection')}</div>;
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
            aria-label={t('admin.workspace.addMembers.removeSelection', { label: subject.label })}
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
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
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
      .sort((left, right) => left.name.localeCompare(right.name, locale))
      .slice(0, 50);
  }, [groups, debouncedQuery, excludeIds, locale]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
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
          {t('admin.shared.directory.user')}
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
          {t('admin.shared.directory.group')}
        </button>
        {onOpenDirectory ? (
          <button
            type="button"
            className="app-text-control ml-auto rounded px-2 py-0.5 text-app-accent hover:bg-app-accent/10"
            onClick={onOpenDirectory}
          >
            {t('admin.workspace.addMembers.openDirectory')}
          </button>
        ) : null}
      </div>

      <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
        <Search size={12} className="text-app-ink/50" />
        <input
          className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
          placeholder={tab === 'user' ? t('admin.workspace.addMembers.userSearchPlaceholder') : t('admin.workspace.addMembers.groupSearchPlaceholder')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoFocus
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-app-border bg-app-bg">
        {tab === 'user' ? (
          loading && candidates.length === 0 ? (
            <div className="app-text-caption px-3 py-3 text-app-ink/60">{t('common:feedback.loading')}</div>
          ) : candidates.filter((c) => !excludeIds.has(c.id)).length === 0 ? (
            <div className="app-text-caption px-3 py-3 text-app-ink/60">{t('common:empty.noResults')}</div>
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
            {t('admin.workspace.addMembers.groupReadDenied')}
          </div>
        ) : filteredGroups.length === 0 ? (
          <div className="app-text-caption px-3 py-3 text-app-ink/60">{t('common:empty.noResults')}</div>
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

function WorkspaceAddMemberModal({
  open,
  onOpenChange,
  workspaceId,
  token,
  groups,
  canReadGroups,
  canBrowseDirectory,
  excludeIds,
  selection,
  onSelectionChange,
  role,
  onRoleChange,
  busy,
  onOpenDirectory,
  onSubmit,
  onCancel,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  token: string;
  groups: AccessGroupItem[];
  canReadGroups: boolean;
  canBrowseDirectory: boolean;
  excludeIds: Set<string>;
  selection: SubjectSelectionState;
  onSelectionChange: (next: SubjectSelectionState) => void;
  role: string;
  onRoleChange: (role: string) => void;
  busy: boolean;
  onOpenDirectory: () => void;
  onSubmit: () => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation('apps');
  const count = selectionSize(selection);
  const roleOptions = getWorkspaceRoleOptions(t);
  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={onOpenChange}
      title={t('admin.workspace.addMembers.title')}
      description={t('admin.workspace.addMembers.description')}
      fullSize
      dismissOnInteractOutside={false}
      actions={
        <>
          <span className="app-text-body mr-auto text-app-ink/60">{t('admin.workspace.addMembers.selectedCount', { count })}</span>
          <div className="flex items-center gap-2">
            <span className="app-text-caption text-app-ink/60">{t('admin.workspace.members.role')}</span>
            <Select
              value={role}
              onValueChange={onRoleChange}
              options={roleOptions.map((option) => ({
                value: option.value,
                label: option.label,
              }))}
            />
          </div>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" disabled={busy || count === 0} onClick={() => void onSubmit()}>
            {busy ? t('admin.workspace.addMembers.adding') : t('admin.workspace.addMembers.addCount', { count })}
          </Button>
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-4">
        <SubjectPickerInline
          workspaceId={workspaceId}
          token={token}
          groups={groups}
          excludeIds={excludeIds}
          selection={selection}
          onSelectionChange={onSelectionChange}
          canReadGroups={canReadGroups}
          onOpenDirectory={canBrowseDirectory ? onOpenDirectory : null}
        />
        <div className="shrink-0">
          <div className="app-text-caption mb-1 text-app-ink/60">
            {t('admin.workspace.addMembers.selectedCount', { count })}
          </div>
          <SelectedSubjectsBar
            selection={selection}
            onRemove={(kind, id) =>
              onSelectionChange(removeSubject(selection, kind, id))
            }
          />
        </div>
      </div>
    </Dialog>
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
  const { t } = useTranslation('apps');
  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t('admin.workspace.directory.title')}
      description={t('admin.workspace.directory.description')}
      fullSize
      dismissOnInteractOutside={false}
      actions={
        <>
          <span className="app-text-body mr-auto text-app-ink/60">
            {t('admin.workspace.directory.currentSelection', { count: selectionSize(selection) })}
          </span>
          <Button variant="primary" onClick={onClose}>
            {t('admin.workspace.directory.done')}
          </Button>
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-app-border bg-app-bg">
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
  const { t } = useTranslation('apps');
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
        closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={onOpenChange}
      title={t('admin.workspace.editTitle')}
      description={t('admin.workspace.editDescription')}
      dismissOnInteractOutside={false}
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {t('common:actions.cancel')}
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="edit-workspace-form"
            disabled={busy || !name.trim()}
          >
            {busy ? t('common:actions.saving') : t('common:actions.save')}
          </Button>
        </>
      }
    >
      <form id="edit-workspace-form" className="grid gap-4" onSubmit={(e) => void handleSubmit(e)}>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">{t('admin.workspace.nameLabel')}</span>
          <input
            className={FORM_FIELD_CLASS}
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">{t('admin.workspace.descriptionLabel')}</span>
          <textarea
            className={`${FORM_FIELD_CLASS} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={1000}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">{t('admin.workspace.keyLabel')}</span>
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
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const roleOptions = getWorkspaceRoleOptions(t);
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
      onError(getErrorMessage(caughtError, t('admin.workspace.members.loadFailed')));
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
      onSuccess(t('admin.workspace.members.roleChanged'));
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, t('admin.workspace.members.roleChangeFailed')));
    } finally {
      setBusy(false);
    }
  }

  async function handleSingleRemove(item: WorkspaceMemberItem) {
    if (!workspace) return;
    setBusy(true);
    try {
      await removeWorkspaceMember(token, workspace.id, item.subject_type, item.subject_id);
      onSuccess(t('admin.workspace.members.removed'));
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, t('admin.workspace.members.removeFailed')));
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
        onError(t('admin.workspace.members.bulkRemovePartial', { succeeded: result.succeeded, failed: result.failed.length }));
      } else {
        onSuccess(t('admin.workspace.members.bulkRemoved', { count: result.succeeded }));
      }
      setSelectedKeys(new Set());
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, t('admin.workspace.members.bulkRemoveFailed')));
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
        onError(t('admin.workspace.members.bulkRolePartial', { succeeded: result.succeeded, failed: result.failed.length }));
      } else {
        onSuccess(t('admin.workspace.members.bulkRoleChanged', { count: result.succeeded }));
      }
      setSelectedKeys(new Set());
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, t('admin.workspace.members.bulkRoleFailed')));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={onOpenChange}
      title={t('admin.workspace.members.manageTitle', { name: workspace.name })}
      description={t('admin.workspace.members.manageDescription')}
      fullSize
      dismissOnInteractOutside={false}
    >
      <div className="flex h-full min-h-0 flex-col gap-4">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[220px] items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5">
            <Search size={14} className="text-app-ink/50" />
            <input
              className="app-text-body flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
              placeholder={t('admin.workspace.members.searchPlaceholder')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>

        {/* Role chips */}
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip
            label={t('admin.workspace.members.filterAll', { count: data?.total ?? 0 })}
            active={roleFilter === null && !pendingOnly}
            onClick={() => {
              setRoleFilter(null);
              setPendingOnly(false);
            }}
          />
          {(['admin', 'member'] as const).map((role) => (
            <FilterChip
              key={role}
              label={t('admin.workspace.members.filterRole', { role: getWorkspaceRoleLabel(role, t), count: data?.role_counts[role] ?? 0 })}
              active={roleFilter === role && !pendingOnly}
              onClick={() => {
                setRoleFilter(role);
                setPendingOnly(false);
              }}
            />
          ))}
          {data && data.pending_count > 0 ? (
            <FilterChip
              label={t('admin.workspace.members.filterPending', { count: data.pending_count })}
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
            <span className="app-text-body text-app-ink">{t('admin.workspace.members.selectedCount', { count: selectedKeys.size })}</span>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Button
                  variant="ghost"
                  onClick={() => setBulkRoleOpen((current) => !current)}
                  disabled={busy}
                >
                  {t('admin.workspace.members.changeRole')}
                </Button>
                {bulkRoleOpen ? (
                  <div className="absolute right-0 top-full z-10 mt-1 min-w-[160px] rounded-md border border-app-border bg-app-bg shadow-lg">
                    {roleOptions.map((option) => (
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
                {t('common:actions.delete')}
              </Button>
              <Button variant="ghost" onClick={() => setSelectedKeys(new Set())}>
                {t('admin.workspace.members.clearSelection')}
              </Button>
            </div>
          </div>
        ) : null}

        {/* Table */}
        <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-app-border">
          <table className="w-full">
            <thead className="sticky top-0 z-10 bg-app-surface-sidebar">
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
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.workspace.members.name')}</th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.workspace.members.role')}</th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.status')}</th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">{t('admin.shared.directory.recent')}</th>
                <th className="w-10 px-2 py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {loading && !data ? (
                <tr>
                  <td colSpan={6} className="px-2 py-8 text-center text-app-ink/60">
                    {t('common:feedback.loading')}
                  </td>
                </tr>
              ) : (data?.items.length ?? 0) === 0 ? (
                <tr>
                  <td colSpan={6} className="px-2 py-8 text-center text-app-ink/60">
                    {t('admin.workspace.members.empty')}
                  </td>
                </tr>
              ) : (
                (data?.items ?? []).map((item) => {
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
                        {isSelf ? <span className="ml-2 text-app-ink/40">{t('admin.workspace.members.currentUser')}</span> : null}
                      </td>
                      <td className="px-2 py-1">
                        <MemberRoleBadge role={item.role} />
                      </td>
                      <td className="app-text-body-sm px-2 py-1">
                        {item.subject_type === 'group' ? (
                          <span className="text-app-ink/60">{t('admin.shared.directory.group')}</span>
                        ) : item.user_status === 'invited' ? (
                          <Badge tone="amber">{t('admin.shared.status.invitedShort')}</Badge>
                        ) : item.user_status === 'suspended' ? (
                          <Badge tone="amber">{t('admin.shared.status.suspendedShort')}</Badge>
                        ) : (
                          <span className="text-app-ink/60">{t('admin.shared.status.activeShort')}</span>
                        )}
                      </td>
                      <td className="app-text-caption px-2 py-1 text-app-ink/60">
                        {formatDateLabel(item.last_login_at, locale)}
                      </td>
                      <td className="px-2 py-1 text-right">
                        {canManage && !isSelf ? (
                          <DropdownMenu
                            trigger={
                              <button
                                type="button"
                                className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                                aria-label={t('admin.workspace.members.actions')}
                              >
                                <MoreHorizontal size={14} />
                              </button>
                            }
                            items={[
                              ...roleOptions.map((option) => ({
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
                                label: t('admin.workspace.members.removeFromWorkspace'),
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
                {t('admin.shared.pagination.previous')}
              </Button>
              <span className="app-text-caption px-2 text-app-ink/60">
                {data.page} / {totalPages}
              </span>
              <Button
                variant="ghost"
                disabled={data.page >= totalPages || busy}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('admin.shared.pagination.next')}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
