import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
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
} from '@open-alm/ui';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { UserSearchMultiSelect } from '@/src/platform/users/UserSearchMultiSelect';

import {
  bulkWorkspaceMembers,
  listWorkspaceBindings,
  listWorkspaceMemberCandidates,
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspace,
  updateWorkspaceMemberRole,
  type WorkspaceBindingItem,
  type WorkspaceItem,
  type WorkspaceMemberCandidate,
} from './admin-api';
import {
  Badge,
  FORM_FIELD_CLASS,
  FilterChip,
  MemberRoleBadge,
  PeopleDirectoryGrid,
  formatDateLabel,
  getErrorMessage,
  getWorkspaceRoleLabel,
  getWorkspaceRoleOptions,
  removeSubject,
  selectionSize,
  toggleSubject,
  type SubjectSelectionState,
} from './admin-shared';
import {
  createWorkspaceAddMemberState,
  filterWorkspaceMemberCandidates,
  patchWorkspaceAddMemberState,
  previewWorkspaceBindings,
  selectedWorkspaceMemberSubjects,
  sortWorkspaceBindings,
  workspaceMemberKey,
  workspaceMemberSubjectIds,
  workspaceRoleSelectOptions,
  type WorkspaceAddMemberState,
} from './workspace-members-model';
import {
  addWorkspaceMembersWorkflow,
  changeWorkspaceMemberRoleWorkflow,
  loadWorkspaceMemberCandidatesWorkflow,
  nextWorkspaceMemberCount,
  refreshWorkspaceMemberCountWorkflow,
  reloadWorkspaceBindingsWorkflow,
  removeWorkspaceMemberWorkflow,
  workspaceBindingsWithUpdatedMember,
  workspaceBindingsWithoutMember,
  type WorkspaceMembersWorkflowPorts,
} from './workspace-members-workflow';
import { useWorkspaceMembersDrawerController } from './useWorkspaceMembersDrawerController';

export interface WorkspaceDetailPanelCapabilities {
  canEditProfile: boolean;
  canManageMembers: boolean;
  canArchive: boolean;
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
  capabilities: WorkspaceDetailPanelCapabilities;
  onWorkspaceChanged: (next: WorkspaceItem) => void;
  flashSuccess: (text: string) => void;
  flashError: (text: string) => void;
}

type WorkspaceBindingsState = {
  workspaceId: string | null;
  items: WorkspaceBindingItem[];
};

const EMPTY_WORKSPACE_BINDINGS: WorkspaceBindingItem[] = [];

function createWorkspaceMembersWorkflowPorts(
  token: string,
): WorkspaceMembersWorkflowPorts {
  return {
    listBindings: (workspaceId) => listWorkspaceBindings(token, workspaceId),
    listMembers: (workspaceId, params) =>
      listWorkspaceMembers(token, workspaceId, params),
    listCandidates: (workspaceId, query) =>
      listWorkspaceMemberCandidates(token, workspaceId, query),
    bulkMembers: (workspaceId, payload) =>
      bulkWorkspaceMembers(token, workspaceId, payload),
    updateMemberRole: (workspaceId, subjectType, subjectId, role) =>
      updateWorkspaceMemberRole(
        token,
        workspaceId,
        subjectType,
        subjectId,
        role,
      ),
    removeMember: (workspaceId, subjectType, subjectId) =>
      removeWorkspaceMember(token, workspaceId, subjectType, subjectId),
  };
}

export function WorkspaceDetailPanel(props: WorkspaceDetailPanelProps) {
  return <>{useWorkspaceDetailPanelElement(props)}</>;
}

function useWorkspaceDetailPanelElement({
  workspace,
  token,
  currentUserId,
  capabilities,
  onWorkspaceChanged,
  flashSuccess,
  flashError,
}: WorkspaceDetailPanelProps): ReactNode {
  const { t, i18n } = useTranslation('apps');
  const { user } = useAuth();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const memberWorkflowPorts = useMemo(
    () => createWorkspaceMembersWorkflowPorts(token),
    [token],
  );
  const [bindingsState, setBindingsState] = useState<WorkspaceBindingsState>({
    workspaceId: null,
    items: [],
  });
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [confirmState, setConfirmState] = useState<null | {
    title: string;
    description: string;
    confirmLabel: string;
    variant: 'default' | 'danger';
    onConfirm: () => Promise<void>;
  }>(null);
  const [membersDrawerOpen, setMembersDrawerOpen] = useState(false);
  const [addState, setAddState] = useState<WorkspaceAddMemberState>(() =>
    createWorkspaceAddMemberState(null),
  );
  const [addBusy, setAddBusy] = useState(false);

  const workspaceId = workspace?.id ?? null;
  const bindings =
    bindingsState.workspaceId === workspaceId
      ? bindingsState.items
      : EMPTY_WORKSPACE_BINDINGS;
  const defaultAddState = useMemo(
    () => createWorkspaceAddMemberState(workspaceId),
    [workspaceId],
  );
  const activeAddState =
    addState.workspaceId === workspaceId ? addState : defaultAddState;
  const {
    panelOpen: addPanelOpen,
    pickerOpen: addPickerOpen,
    role: addRole,
    selection: addSelection,
  } = activeAddState;

  const updateAddState = useCallback(
    (patch: Partial<Omit<WorkspaceAddMemberState, 'workspaceId'>>) => {
      setAddState((current) =>
        patchWorkspaceAddMemberState(current, workspaceId, patch),
      );
    },
    [workspaceId],
  );

  const resetAddPanel = useCallback(() => {
    setAddState(createWorkspaceAddMemberState(workspaceId));
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    void (async () => {
      try {
        const nextBindings = await reloadWorkspaceBindingsWorkflow({
          workspaceId,
          ports: memberWorkflowPorts,
        });
        if (!cancelled) {
          setBindingsState({ workspaceId, items: nextBindings });
        }
      } catch (caughtError) {
        if (!cancelled) {
          flashError(
            getErrorMessage(caughtError, t('admin.workspace.detailLoadFailed')),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [memberWorkflowPorts, workspaceId, flashError, t]);

  const sortedBindings = useMemo(
    () => sortWorkspaceBindings(bindings, locale),
    [bindings, locale],
  );

  const previewBindings = useMemo(
    () => previewWorkspaceBindings(sortedBindings),
    [sortedBindings],
  );

  const memberSubjectIds = useMemo(
    () => workspaceMemberSubjectIds(bindings),
    [bindings],
  );

  async function reloadBindings(): Promise<WorkspaceBindingItem[]> {
    if (!workspaceId) return [];
    const nextBindings = await reloadWorkspaceBindingsWorkflow({
      workspaceId,
      ports: memberWorkflowPorts,
    });
    setBindingsState({ workspaceId, items: nextBindings });
    return nextBindings;
  }

  async function handleEditWorkspace(payload: {
    name: string;
    description: string;
  }) {
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
      setEditError(
        getErrorMessage(caughtError, t('admin.workspace.profileSaveFailed')),
      );
    } finally {
      setEditBusy(false);
    }
  }

  async function handleToggleActive(
    target: WorkspaceItem,
    nextActive: boolean,
  ) {
    setBusy(true);
    try {
      const updated = await updateWorkspace(token, target.id, {
        name: target.name,
        description: target.description,
        active: nextActive,
      });
      onWorkspaceChanged(updated);
      flashSuccess(
        nextActive
          ? t('admin.workspace.reactivated')
          : t('admin.workspace.archived'),
      );
    } catch (caughtError) {
      flashError(
        getErrorMessage(caughtError, t('admin.workspace.statusChangeFailed')),
      );
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
      const { outcome, bindings: nextBindings, memberCountDelta } =
        await addWorkspaceMembersWorkflow({
          workspaceId,
          selection: addSelection,
          role: addRole,
          ports: memberWorkflowPorts,
        });
      if (outcome.partial) {
        flashError(
          t('admin.workspace.members.bulkAddPartial', {
            succeeded: outcome.succeeded,
            failed: outcome.failedCount,
          }),
        );
      } else {
        flashSuccess(
          t('admin.workspace.members.bulkAdded', {
            count: outcome.succeeded,
          }),
        );
      }
      setBindingsState({
        workspaceId,
        items: nextBindings,
      });
      if (workspace) {
        onWorkspaceChanged({
          ...workspace,
          member_count: nextWorkspaceMemberCount(
            workspace.member_count,
            memberCountDelta,
          ),
        });
      }
      resetAddPanel();
    } catch (caughtError) {
      flashError(
        getErrorMessage(caughtError, t('admin.workspace.members.addFailed')),
      );
    } finally {
      setAddBusy(false);
    }
  }

  async function handleChangeMemberRole(
    binding: WorkspaceBindingItem,
    role: string,
  ) {
    if (!workspaceId) return;
    setBusy(true);
    try {
      const { updated } = await changeWorkspaceMemberRoleWorkflow({
        workspaceId,
        member: binding,
        role,
        ports: memberWorkflowPorts,
      });
      setBindingsState((current) => ({
        workspaceId,
        items: workspaceBindingsWithUpdatedMember(
          current.workspaceId === workspaceId ? current.items : [],
          binding,
          updated,
        ),
      }));
      flashSuccess(t('admin.workspace.members.roleChanged'));
    } catch (caughtError) {
      flashError(
        getErrorMessage(
          caughtError,
          t('admin.workspace.members.roleChangeFailed'),
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveMember(binding: WorkspaceBindingItem) {
    if (!workspaceId) return;
    setBusy(true);
    try {
      const { memberCountDelta } = await removeWorkspaceMemberWorkflow({
        workspaceId,
        member: binding,
        ports: memberWorkflowPorts,
      });
      setBindingsState((current) => ({
        workspaceId,
        items: workspaceBindingsWithoutMember(
          current.workspaceId === workspaceId ? current.items : [],
          binding,
        ),
      }));
      if (workspace) {
        onWorkspaceChanged({
          ...workspace,
          member_count: nextWorkspaceMemberCount(
            workspace.member_count,
            memberCountDelta,
          ),
        });
      }
      flashSuccess(t('admin.workspace.members.removed'));
    } catch (caughtError) {
      flashError(
        getErrorMessage(caughtError, t('admin.workspace.members.removeFailed')),
      );
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

  async function handleDrawerChanged() {
    await reloadBindings();
    if (workspaceId) {
      try {
        const memberCount = await refreshWorkspaceMemberCountWorkflow({
          workspaceId,
          ports: memberWorkflowPorts,
        });
        if (workspace) {
          onWorkspaceChanged({ ...workspace, member_count: memberCount });
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
          <p className="app-text-title-md text-app-ink">
            {t('admin.workspace.noSelectionTitle')}
          </p>
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
                description: t('admin.workspace.archiveConfirmDescription', {
                  name: workspace.name,
                }),
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
  return (
    <>
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {/* Hero */}
        <header className="border-b border-app-border px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="app-text-title-md truncate text-app-ink">
                  {workspace.name}
                </h2>
                {workspace.active ? (
                  <Badge tone="green">
                    {t('admin.shared.status.activeShort')}
                  </Badge>
                ) : (
                  <Badge tone="amber">
                    {t('admin.workspace.archivedStatus')}
                  </Badge>
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
                  {t('admin.workspace.heroMeta', {
                    count: workspace.member_count,
                    date: formatDateLabel(
                      workspace.created_at,
                      locale,
                      timeZone,
                    ),
                  })}
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

        {/* Members preview + open drawer */}
        <section className="px-4 py-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="app-text-control text-app-ink">
              {t('admin.workspace.members.title')}{' '}
              <span className="app-text-caption ml-1 text-app-ink/50">
                {t('admin.workspace.members.previewMeta', {
                  count: workspace.member_count,
                })}
              </span>
            </h3>
            <div className="flex items-center gap-1.5">
              {capabilities.canManageMembers ? (
                <Button
                  variant="primary"
                  onClick={() => updateAddState({ panelOpen: true })}
                >
                  <Plus size={12} className="mr-1" />
                  {t('admin.workspace.members.add')}
                </Button>
              ) : null}
              <Button
                variant="ghost"
                onClick={() => setMembersDrawerOpen(true)}
              >
                <UsersIcon size={12} className="mr-1" />
                {t('admin.workspace.members.manage')}
              </Button>
            </div>
          </div>

          {previewBindings.length === 0 ? (
            <div className="rounded-md border border-dashed border-app-border bg-app-bg px-3 py-6 text-center">
              <p className="app-text-body-sm text-app-ink/60">
                {t('admin.workspace.members.emptyYet')}
              </p>
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
              {workspace.member_count > previewBindings.length ? (
                <button
                  type="button"
                  onClick={() => setMembersDrawerOpen(true)}
                  className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-accent transition-colors hover:bg-app-surface-sidebar"
                >
                  {t('admin.workspace.members.viewAll', {
                    count: workspace.member_count,
                  })}
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
              updateAddState({ panelOpen: true });
            }
          }}
          workspaceId={workspace.id}
          memberWorkflowPorts={memberWorkflowPorts}
          canBrowseDirectory={capabilities.canBrowseDirectory}
          currentUserId={currentUserId}
          excludeIds={memberSubjectIds}
          selection={addSelection}
          onSelectionChange={(selection) => updateAddState({ selection })}
          role={addRole}
          onRoleChange={(role) => updateAddState({ role })}
          busy={addBusy}
          onOpenDirectory={() => updateAddState({ pickerOpen: true })}
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
        memberWorkflowPorts={memberWorkflowPorts}
        canManage={capabilities.canManageMembers}
        currentUserId={currentUserId}
        onChanged={() => void handleDrawerChanged()}
        onError={flashError}
        onSuccess={flashSuccess}
      />
      {capabilities.canBrowseDirectory ? (
        <PeoplePickerModal
          open={addPickerOpen}
          onClose={() => updateAddState({ pickerOpen: false })}
          token={token}
          selection={addSelection}
          onSelectionChange={(selection) => updateAddState({ selection })}
          excludeIds={memberSubjectIds}
        />
      ) : null}
    </>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

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
            <span className="app-text-caption text-app-ink/60">
              {option.description}
            </span>
          </span>
          {binding.role === option.value ? (
            <Check size={14} className="text-app-accent" />
          ) : null}
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
      <span
        className="inline-block size-1.5 shrink-0 rounded-full bg-app-ink/30"
        aria-label={t('admin.shared.directory.user')}
      />
      <div className="min-w-0 flex-1">
        <div className="app-text-body-sm truncate text-app-ink">
          <span className="font-medium">{binding.subject_label}</span>
          {binding.subject_secondary ? (
            <span className="ml-2 text-app-ink/50">
              {binding.subject_secondary}
            </span>
          ) : null}
          {isCurrentUser ? (
            <span className="ml-2 text-app-ink/40">
              {t('admin.workspace.members.currentUser')}
            </span>
          ) : null}
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
  onRemove: (kind: 'user', id: string) => void;
}) {
  const { t } = useTranslation('apps');
  const all = selectedWorkspaceMemberSubjects(selection);
  if (all.length === 0) {
    return (
      <div className="app-text-caption text-app-ink/40">
        {t('admin.workspace.addMembers.noSelection')}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {all.map((subject) => (
        <span
          key={`${subject.kind}-${subject.id}`}
          className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-0.5 text-app-ink"
        >
          <span>{subject.label}</span>
          <button
            type="button"
            className="text-app-ink/50 hover:text-app-ink"
            onClick={() => onRemove(subject.kind, subject.id)}
            aria-label={t('admin.workspace.addMembers.removeSelection', {
              label: subject.label,
            })}
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
  memberWorkflowPorts,
  currentUserId,
  excludeIds,
  selection,
  onSelectionChange,
  onOpenDirectory,
}: {
  workspaceId: string;
  memberWorkflowPorts: Pick<WorkspaceMembersWorkflowPorts, 'listCandidates'>;
  currentUserId: string;
  excludeIds: Set<string>;
  selection: SubjectSelectionState;
  onSelectionChange: (next: SubjectSelectionState) => void;
  onOpenDirectory: (() => void) | null;
}) {
  const { t } = useTranslation('apps');
  const [query, setQuery] = useState('');
  const [candidates, setCandidates] = useState<WorkspaceMemberCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [queryFocused, setQueryFocused] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const handle = window.setTimeout(() => {
      setLoading(true);
      void (async () => {
        try {
          const items = await loadWorkspaceMemberCandidatesWorkflow({
            workspaceId,
            query,
            ports: memberWorkflowPorts,
          });
          if (!cancelled) {
            setCandidates(items);
          }
        } catch {
          // silent
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [memberWorkflowPorts, query, workspaceId]);

  const filteredCandidates = useMemo(
    () => filterWorkspaceMemberCandidates(candidates, excludeIds),
    [candidates, excludeIds],
  );
  const selectedUsers = useMemo(
    () =>
      Array.from(selection.users.values()).map((subject) => ({
        id: subject.id,
        email: subject.secondary ?? '',
        full_name: subject.label,
      })),
    [selection.users],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex items-center gap-1.5">
        <span className="app-text-control rounded bg-app-surface-sidebar px-2 py-0.5 text-app-ink">
          {t('admin.shared.directory.user')}
        </span>
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

      <UserSearchMultiSelect
        candidates={filteredCandidates}
        labels={{
          currentUser: t('pms.taskDetail.me'),
          noUserMatch: t('common:empty.noResults'),
          removeItem: (name) =>
            t('admin.workspace.addMembers.removeSelection', { label: name }),
          searchPlaceholder: t(
            'admin.workspace.addMembers.userSearchPlaceholder',
          ),
          searchPrompt: t('admin.workspace.addMembers.userSearchPlaceholder'),
          searching: t('common:feedback.loading'),
        }}
        loading={loading}
        currentUserId={currentUserId}
        onAddUser={(candidate) =>
          onSelectionChange(
            toggleSubject(selection, {
              id: candidate.id,
              kind: 'user',
              label: candidate.full_name || candidate.email,
              secondary: candidate.email,
            }),
          )
        }
        onQueryChange={setQuery}
        onQueryFocusChange={setQueryFocused}
        onRemoveUser={(userId) =>
          onSelectionChange(removeSubject(selection, 'user', userId))
        }
        query={query}
        queryFocused={queryFocused || Boolean(query.trim())}
        selectedUsers={selectedUsers}
      />
    </div>
  );
}

function WorkspaceAddMemberModal({
  open,
  onOpenChange,
  workspaceId,
  memberWorkflowPorts,
  canBrowseDirectory,
  currentUserId,
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
  memberWorkflowPorts: Pick<WorkspaceMembersWorkflowPorts, 'listCandidates'>;
  canBrowseDirectory: boolean;
  currentUserId: string;
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
          <span className="app-text-body mr-auto text-app-ink/60">
            {t('admin.workspace.addMembers.selectedCount', { count })}
          </span>
          <div className="flex items-center gap-2">
            <span className="app-text-caption text-app-ink/60">
              {t('admin.workspace.members.role')}
            </span>
            <Select
              value={role}
              onValueChange={onRoleChange}
              options={workspaceRoleSelectOptions(roleOptions)}
            />
          </div>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {t('common:actions.cancel')}
          </Button>
          <Button
            variant="primary"
            disabled={busy || count === 0}
            onClick={() => void onSubmit()}
          >
            {busy
              ? t('admin.workspace.addMembers.adding')
              : t('admin.workspace.addMembers.addCount', { count })}
          </Button>
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-4">
        <SubjectPickerInline
          workspaceId={workspaceId}
          memberWorkflowPorts={memberWorkflowPorts}
          currentUserId={currentUserId}
          excludeIds={excludeIds}
          selection={selection}
          onSelectionChange={onSelectionChange}
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
            {t('admin.workspace.directory.currentSelection', {
              count: selectionSize(selection),
            })}
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
          onToggleSelect={(subject) =>
            onSelectionChange(toggleSubject(selection, subject))
          }
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
  const [draft, setDraft] = useState<{
    workspaceId: string;
    name: string;
    description: string;
  } | null>(null);

  if (!workspace) {
    return null;
  }

  const name =
    draft?.workspaceId === workspace.id ? draft.name : workspace.name;
  const description =
    draft?.workspaceId === workspace.id
      ? draft.description
      : workspace.description;
  const updateDraft = (
    patch: Partial<{ name: string; description: string }>,
  ) => {
    setDraft({
      workspaceId: workspace.id,
      name,
      description,
      ...patch,
    });
  };

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
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
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
      <form
        id="edit-workspace-form"
        className="grid gap-4"
        onSubmit={(e) => void handleSubmit(e)}
      >
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">
            {t('admin.workspace.nameLabel')}
          </span>
          <input
            className={FORM_FIELD_CLASS}
            value={name}
            onChange={(event) => updateDraft({ name: event.target.value })}
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">
            {t('admin.workspace.descriptionLabel')}
          </span>
          <textarea
            className={`${FORM_FIELD_CLASS} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) =>
              updateDraft({ description: event.target.value })
            }
            maxLength={1000}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">
            {t('admin.workspace.keyLabel')}
          </span>
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

interface WorkspaceMembersDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspace: WorkspaceItem | null;
  memberWorkflowPorts: WorkspaceMembersWorkflowPorts;
  canManage: boolean;
  currentUserId: string;
  onChanged: () => void;
  onError: (msg: string) => void;
  onSuccess: (msg: string) => void;
}

function WorkspaceMembersDrawer(props: WorkspaceMembersDrawerProps) {
  return <>{useWorkspaceMembersDrawerElement(props)}</>;
}

function useWorkspaceMembersDrawerElement({
  open,
  onOpenChange,
  workspace,
  memberWorkflowPorts,
  canManage,
  currentUserId,
  onChanged,
  onError,
  onSuccess,
}: WorkspaceMembersDrawerProps): ReactNode {
  const { t, i18n } = useTranslation('apps');
  const { user } = useAuth();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const roleOptions = getWorkspaceRoleOptions(t);
  const controller = useWorkspaceMembersDrawerController({
    open,
    workspace,
    currentUserId,
    ports: memberWorkflowPorts,
    messages: {
      loadFailed: t('admin.workspace.members.loadFailed'),
      roleChanged: t('admin.workspace.members.roleChanged'),
      roleChangeFailed: t('admin.workspace.members.roleChangeFailed'),
      removed: t('admin.workspace.members.removed'),
      removeFailed: t('admin.workspace.members.removeFailed'),
      bulkRemovePartial: (succeeded, failed) =>
        t('admin.workspace.members.bulkRemovePartial', {
          succeeded,
          failed,
        }),
      bulkRemoved: (count) =>
        t('admin.workspace.members.bulkRemoved', { count }),
      bulkRemoveFailed: t('admin.workspace.members.bulkRemoveFailed'),
      bulkRolePartial: (succeeded, failed) =>
        t('admin.workspace.members.bulkRolePartial', {
          succeeded,
          failed,
        }),
      bulkRoleChanged: (count) =>
        t('admin.workspace.members.bulkRoleChanged', { count }),
      bulkRoleFailed: t('admin.workspace.members.bulkRoleFailed'),
    },
    onChanged,
    onError,
    onSuccess,
  });
  const {
    bulkRoleOpen,
    busy,
    data,
    loading,
    pendingOnly,
    query,
    roleFilter,
  } = controller.state;
  const {
    activeSelectedKeys,
    allSelectableSelected,
    totalPages,
  } = controller.derived;

  if (!workspace) return null;

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
              aria-label={t('admin.workspace.members.searchPlaceholder')}
              onChange={(event) =>
                controller.actions.setQuery(event.target.value)
              }
            />
          </div>
        </div>

        {/* Role chips */}
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip
            label={t('admin.workspace.members.filterAll', {
              count: data?.total ?? 0,
            })}
            active={roleFilter === null && !pendingOnly}
            onClick={() => {
              controller.actions.setRoleFilter(null);
            }}
          />
          {(['admin', 'member'] as const).map((role) => (
            <FilterChip
              key={role}
              label={t('admin.workspace.members.filterRole', {
                role: getWorkspaceRoleLabel(role, t),
                count: data?.role_counts[role] ?? 0,
              })}
              active={roleFilter === role && !pendingOnly}
              onClick={() => {
                controller.actions.setRoleFilter(role);
              }}
            />
          ))}
          {data && data.pending_count > 0 ? (
            <FilterChip
              label={t('admin.workspace.members.filterPending', {
                count: data.pending_count,
              })}
              active={pendingOnly}
              tone="warning"
              onClick={() => {
                controller.actions.setPendingOnly(true);
              }}
            />
          ) : null}
        </div>

        {/* Bulk action bar */}
        {activeSelectedKeys.size > 0 ? (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-app-accent/40 bg-app-accent/10 px-3 py-2">
            <span className="app-text-body text-app-ink">
              {t('admin.workspace.members.selectedCount', {
                count: activeSelectedKeys.size,
              })}
            </span>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Button
                  variant="ghost"
                  onClick={() =>
                    controller.actions.setBulkRoleOpen((current) => !current)
                  }
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
                        onClick={() =>
                          void controller.actions.bulkRole(option.value)
                        }
                      >
                        <span>{option.label}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <Button
                variant="ghost"
                onClick={() => void controller.actions.bulkRemove()}
                disabled={busy}
                className="text-[var(--ui-color-danger)]"
              >
                {t('common:actions.delete')}
              </Button>
              <Button
                variant="ghost"
                onClick={controller.actions.clearSelection}
              >
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
                      aria-label={t('admin.workspace.members.selectAll')}
                      onChange={controller.actions.toggleSelectAll}
                      checked={allSelectableSelected}
                    />
                  ) : null}
                </th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                  {t('admin.workspace.members.name')}
                </th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                  {t('admin.workspace.members.role')}
                </th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                  {t('admin.shared.directory.status')}
                </th>
                <th className="app-text-overline px-2 py-1.5 text-left text-app-ink/60">
                  {t('admin.shared.directory.recent')}
                </th>
                <th className="w-10 px-2 py-1.5">
                  <span className="sr-only">
                    {t('admin.workspace.members.actions')}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && !data ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-2 py-8 text-center text-app-ink/60"
                  >
                    {t('common:feedback.loading')}
                  </td>
                </tr>
              ) : (data?.items.length ?? 0) === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-2 py-8 text-center text-app-ink/60"
                  >
                    {t('admin.workspace.members.empty')}
                  </td>
                </tr>
              ) : (
                (data?.items ?? []).map((item) => {
                  const key = workspaceMemberKey(item);
                  const isSelf =
                    item.subject_type === 'user' &&
                    item.subject_id === currentUserId;
                  return (
                    <tr key={key} className="border-b border-app-border/50">
                      <td className="px-2 py-1">
                        {canManage && !isSelf ? (
                          <input
                            type="checkbox"
                            aria-label={t(
                              'admin.workspace.members.selectMember',
                              {
                                name: item.subject_label,
                              },
                            )}
                            checked={activeSelectedKeys.has(key)}
                            onChange={() =>
                              controller.actions.toggleSelect(item)
                            }
                          />
                        ) : null}
                      </td>
                      <td className="app-text-body-sm px-2 py-1">
                        <span className="font-medium text-app-ink">
                          {item.subject_label}
                        </span>
                        {item.subject_secondary ? (
                          <span className="ml-2 text-app-ink/50">
                            {item.subject_secondary}
                          </span>
                        ) : null}
                        {isSelf ? (
                          <span className="ml-2 text-app-ink/40">
                            {t('admin.workspace.members.currentUser')}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-2 py-1">
                        <MemberRoleBadge role={item.role} />
                      </td>
                      <td className="app-text-body-sm px-2 py-1">
                        {item.user_status === 'invited' ? (
                          <Badge tone="amber">
                            {t('admin.shared.status.invitedShort')}
                          </Badge>
                        ) : item.user_status === 'suspended' ? (
                          <Badge tone="amber">
                            {t('admin.shared.status.suspendedShort')}
                          </Badge>
                        ) : (
                          <span className="text-app-ink/60">
                            {t('admin.shared.status.activeShort')}
                          </span>
                        )}
                      </td>
                      <td className="app-text-caption px-2 py-1 text-app-ink/60">
                        {formatDateLabel(
                          item.last_login_at,
                          locale,
                          timeZone,
                        )}
                      </td>
                      <td className="px-2 py-1 text-right">
                        {canManage && !isSelf ? (
                          <DropdownMenu
                            trigger={
                              <button
                                type="button"
                                className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                                aria-label={t(
                                  'admin.workspace.members.actions',
                                )}
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
                                      <Check
                                        size={14}
                                        className="text-app-accent"
                                      />
                                    ) : null}
                                  </span>
                                ),
                                onSelect: () => {
                                  if (item.role !== option.value) {
                                    void controller.actions.singleRoleChange(
                                      item,
                                      option.value,
                                    );
                                  }
                                },
                                disabled: busy,
                              })),
                              {
                                id: 'remove',
                                label: t(
                                  'admin.workspace.members.removeFromWorkspace',
                                ),
                                onSelect: () =>
                                  void controller.actions.singleRemove(item),
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
                onClick={() =>
                  controller.actions.setPage((p) => Math.max(1, p - 1))
                }
              >
                {t('admin.shared.pagination.previous')}
              </Button>
              <span className="app-text-caption px-2 text-app-ink/60">
                {data.page} / {totalPages}
              </span>
              <Button
                variant="ghost"
                disabled={data.page >= totalPages || busy}
                onClick={() => controller.actions.setPage((p) => p + 1)}
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
