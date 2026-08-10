import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Plus,
  Pencil,
  Trash2,
  Check,
  Loader2,
  GripVertical,
  MoreHorizontal,
  Info,
} from 'lucide-react';
import { Button, Dialog, InlineNotice } from '@open-alm/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { UserSearchMultiSelect } from '@/src/platform/users/UserSearchMultiSelect';
import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  listTaskListLabels,
  listPmsUsers,
  listSpaceMembers,
  type PmsLabel,
  type PmsSpaceMember,
  type PmsStatusCategory,
  type PmsTaskListStatus,
  type PmsUserSummary,
} from '../api/pms-api';
import { StatusIconGlyph } from './StatusIcon';
import {
  LABEL_PRESET_COLORS,
  useTaskListLabelsController,
} from './useTaskListLabelsController';
import {
  NO_MEMBER_SELECTION,
  useTaskListMembersController,
} from './useTaskListMembersController';
import { useTaskListWorkflowStatusesController } from './useTaskListWorkflowStatusesController';
import {
  canMutateTaskListSettingsMember,
  roleOptionsForTaskListSettings,
} from './task-list-members-model';

const CATEGORY_OPTIONS = [
  { value: 'not_started', labelKey: 'pms.settings.category.notStarted' },
  { value: 'active', labelKey: 'pms.settings.category.active' },
  { value: 'done', labelKey: 'pms.settings.category.done' },
  { value: 'closed', labelKey: 'pms.settings.category.closed' },
] as const satisfies readonly { value: PmsStatusCategory; labelKey: string }[];

const SETTINGS_TABS = ['members', 'labels', 'workflow'] as const;

type TaskListSettingsPanelProps = {
  taskListId: string;
  taskListName?: string | null;
  teamId: string | null;
  workspaceSlug?: string | null;
  currentUserRole: string | null;
  onClose: () => void;
  onLabelsChanged?: (labels: PmsLabel[]) => void;
  onMembersChanged?: (members: PmsSpaceMember[]) => void;
  onStatusesChanged?: (statuses: PmsTaskListStatus[]) => void;
};

export function TaskListSettingsPanel(props: TaskListSettingsPanelProps) {
  return renderTaskListSettingsPanel(useTaskListSettingsModel(props));
}

function useTaskListSettingsModel({
  taskListId,
  taskListName,
  teamId,
  workspaceSlug,
  currentUserRole,
  onClose,
  onLabelsChanged,
  onMembersChanged,
  onStatusesChanged,
}: TaskListSettingsPanelProps) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [activeTab, setActiveTab] =
    useState<(typeof SETTINGS_TABS)[number]>('workflow');
  const [availableUsers, setAvailableUsers] = useState<PmsUserSummary[]>([]);
  const [memberQuery, setMemberQuery] = useState('');
  const [memberQueryFocused, setMemberQueryFocused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const {
    creating,
    editColor,
    editName,
    editingId,
    handleCreate,
    handleDelete,
    handleSaveEdit,
    labels,
    newColor,
    newName,
    replaceLabels,
    setEditColor,
    setEditName,
    setEditingId,
    setNewColor,
    setNewName,
    startEdit,
  } = useTaskListLabelsController({
    errorMessages: {
      createFailed: t('pms.settings.errors.createLabelFailed'),
      deleteFailed: t('pms.settings.errors.deleteLabelFailed'),
      updateFailed: t('pms.settings.errors.updateLabelFailed'),
    },
    onError: setError,
    onLabelsChanged,
    taskListId,
    token,
  });
  const {
    addingMember,
    handleAddMember,
    handleRemoveMember,
    handleRoleChange,
    members,
    replaceMembers,
    selectedRole,
    selectedUserId,
    setSelectedRole,
    setSelectedUserId,
  } = useTaskListMembersController({
    availableUsers,
    candidatePlaceholder: t('pms.settings.addMemberByEmail'),
    errorMessages: {
      addFailed: t('pms.settings.errors.addMemberFailed'),
      removeFailed: t('pms.settings.errors.removeMemberFailed'),
      updateRoleFailed: t('pms.settings.errors.updateMemberRoleFailed'),
    },
    onError: setError,
    onMembersChanged,
    teamId,
    token,
    workspaceSlug,
  });
  const workflowStatuses = useTaskListWorkflowStatusesController({
    currentUserRole,
    messages: {
      createFailed: t('pms.settings.errors.createStatusFailed'),
      loadFailed: t('pms.settings.errors.loadFailed'),
      updateFailed: t('pms.settings.errors.updateStatusFailed'),
      updateModeFailed: t('pms.settings.errors.updateStatusModeFailed'),
    },
    onError: setError,
    onStatusesChanged,
    taskListId,
    teamId,
    token,
  });
  const canManageAdmins = currentUserRole === 'owner';
  const availableRoleOptions = useMemo(
    () => roleOptionsForTaskListSettings(canManageAdmins),
    [canManageAdmins],
  );
  const memberIds = useMemo(
    () => new Set(members.map((member) => member.user_id)),
    [members],
  );
  const selectedUser = useMemo(
    () =>
      selectedUserId === NO_MEMBER_SELECTION
        ? null
        : (availableUsers.find((item) => item.id === selectedUserId) ?? null),
    [availableUsers, selectedUserId],
  );
  const memberCandidateUsers = useMemo(
    () =>
      selectUserOptionsForPicker({
        users: availableUsers,
        query: memberQuery,
        currentUserId: user?.id,
        excludeIds: memberIds,
        limit: 8,
      }),
    [availableUsers, memberIds, memberQuery, user?.id],
  );

  const loadAll = useCallback(async () => {
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      const [memberRes, userItems, labelRes] = await Promise.all([
        teamId
          ? listSpaceMembers(token, teamId, workspaceSlug)
          : Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }),
        listPmsUsers(token, workspaceSlug),
        listTaskListLabels(token, taskListId),
      ]);
      replaceMembers(memberRes.items);
      setAvailableUsers(userItems);
      replaceLabels(labelRes.items);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('pms.settings.errors.loadFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [
    replaceLabels,
    replaceMembers,
    taskListId,
    teamId,
    token,
    workspaceSlug,
    t,
  ]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return {
    activeTab,
    addingMember,
    availableRoleOptions,
    canEditWorkflow: workflowStatuses.canEditWorkflow,
    canManageAdmins,
    creating,
    creatingStatus: workflowStatuses.creatingStatus,
    editColor,
    editName,
    editStatusCategory: workflowStatuses.editStatusCategory,
    editStatusColor: workflowStatuses.editStatusColor,
    editStatusName: workflowStatuses.editStatusName,
    editingId,
    editingStatusId: workflowStatuses.editingStatusId,
    error,
    handleAddMember,
    handleCreate,
    handleCreateStatus: workflowStatuses.handleCreateStatus,
    handleDelete,
    handleRemoveMember,
    handleRoleChange,
    handleSaveEdit,
    handleSaveEditStatus: workflowStatuses.handleSaveEditStatus,
    handleStatusModeChange: workflowStatuses.handleStatusModeChange,
    labels,
    loading: loading || workflowStatuses.loadingStatuses,
    locale,
    memberCandidateUsers,
    memberQuery,
    memberQueryFocused,
    members,
    newColor,
    newName,
    newStatusCategory: workflowStatuses.newStatusCategory,
    newStatusColor: workflowStatuses.newStatusColor,
    newStatusName: workflowStatuses.newStatusName,
    onClose,
    selectedRole,
    selectedUser,
    selectedUserId,
    setActiveTab,
    setEditColor,
    setEditName,
    setEditStatusColor: workflowStatuses.setEditStatusColor,
    setEditStatusName: workflowStatuses.setEditStatusName,
    setEditingId,
    setEditingStatusId: workflowStatuses.setEditingStatusId,
    setMemberQuery,
    setMemberQueryFocused,
    setNewColor,
    setNewName,
    setNewStatusCategory: workflowStatuses.setNewStatusCategory,
    setNewStatusColor: workflowStatuses.setNewStatusColor,
    setNewStatusName: workflowStatuses.setNewStatusName,
    setSelectedRole,
    setSelectedUserId,
    startEdit,
    startEditStatus: workflowStatuses.startEditStatus,
    statuses: workflowStatuses.statuses,
    statusesByCategory: workflowStatuses.statusesByCategory,
    statusMode: workflowStatuses.statusMode,
    t,
    taskListName,
    teamId,
    timeZone,
    user,
    workflowReadOnly: workflowStatuses.workflowReadOnly,
  };
}

function renderTaskListSettingsPanel({
  activeTab,
  addingMember,
  availableRoleOptions,
  canEditWorkflow,
  canManageAdmins,
  creating,
  creatingStatus,
  editColor,
  editName,
  editStatusCategory,
  editStatusColor,
  editStatusName,
  editingId,
  editingStatusId,
  error,
  handleAddMember,
  handleCreate,
  handleCreateStatus,
  handleDelete,
  handleRemoveMember,
  handleRoleChange,
  handleSaveEdit,
  handleSaveEditStatus,
  handleStatusModeChange,
  labels,
  loading,
  locale,
  memberCandidateUsers,
  memberQuery,
  memberQueryFocused,
  members,
  newColor,
  newName,
  newStatusCategory,
  newStatusColor,
  newStatusName,
  onClose,
  selectedRole,
  selectedUser,
  selectedUserId,
  setActiveTab,
  setEditColor,
  setEditName,
  setEditStatusColor,
  setEditStatusName,
  setEditingId,
  setEditingStatusId,
  setMemberQuery,
  setMemberQueryFocused,
  setNewColor,
  setNewName,
  setNewStatusCategory,
  setNewStatusColor,
  setNewStatusName,
  setSelectedRole,
  setSelectedUserId,
  startEdit,
  startEditStatus,
  statuses,
  statusesByCategory,
  statusMode,
  t,
  taskListName,
  teamId,
  timeZone,
  user,
  workflowReadOnly,
}: ReturnType<typeof useTaskListSettingsModel>) {
  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      maxWidth="max-w-3xl"
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      open
      title={t('pms.settings.title')}
    >
      <div className="-mx-5 -mt-4 mb-0 flex flex-wrap gap-1 border-b border-app-border px-5 py-2">
        {SETTINGS_TABS.map((tab) => (
          <button
            type="button"
            key={tab}
            className={`app-text-control-sm rounded-md px-3 py-1.5 transition-colors ${
              activeTab === tab
                ? 'bg-app-bg text-app-ink shadow-sm'
                : 'text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink'
            }`}
            onClick={() => setActiveTab(tab)}
          >
            {t(`pms.settings.tabs.${tab}`)}
          </button>
        ))}
      </div>

      <div className="flex h-[min(68vh,42rem)] min-h-[28rem] flex-col">
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <div className="mt-4 min-h-0 flex-1">
          {activeTab === 'members' ? (
            <section className="flex h-full min-h-0 flex-col gap-3">
              <h3 className="app-text-overline text-app-ink/50">
                {t('pms.settings.members')}
              </h3>

              {teamId ? (
                <div className="grid gap-2 rounded-lg border border-app-border bg-app-surface-sidebar p-3">
                  <UserSearchMultiSelect
                    candidates={memberCandidateUsers}
                    density="compact"
                    labels={{
                      currentUser: t('pms.taskDetail.me'),
                      noUserMatch: t('pms.noMatchingUsers'),
                      removeItem: (name) => t('pms.removeMember', { name }),
                      searchPlaceholder: t('pms.searchUser'),
                      searchPrompt: t('pms.noUsersToAdd'),
                      searching: t('pms.searchUser'),
                    }}
                    currentUserId={user?.id}
                    onAddUser={(nextUser) => {
                      setSelectedUserId(nextUser.id);
                      setMemberQuery('');
                    }}
                    onQueryChange={setMemberQuery}
                    onQueryFocusChange={setMemberQueryFocused}
                    onRemoveUser={() => setSelectedUserId(NO_MEMBER_SELECTION)}
                    query={memberQuery}
                    queryFocused={
                      memberQueryFocused &&
                      (Boolean(memberQuery.trim()) ||
                        memberCandidateUsers.length > 0)
                    }
                    selectedUsers={selectedUser ? [selectedUser] : []}
                  />
                  <div className="flex items-center gap-2">
                    <select
                      aria-label={t('pms.spaceMembers.changeRole')}
                      value={selectedRole}
                      onChange={(event) => setSelectedRole(event.target.value)}
                      className="app-field-input-sm flex-1"
                    >
                      {availableRoleOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {t(option.labelKey)}
                        </option>
                      ))}
                    </select>
                    <Button
                      disabled={
                        selectedUserId === NO_MEMBER_SELECTION || addingMember
                      }
                      onClick={() => {
                        void handleAddMember();
                      }}
                      variant="secondary"
                    >
                      {t('common:actions.add')}
                    </Button>
                  </div>
                </div>
              ) : null}

              {loading ? (
                <div className="flex justify-center py-6">
                  <Loader2 size={18} className="animate-spin text-app-ink/40" />
                </div>
              ) : (
                <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1 custom-scrollbar">
                  {members.map((member) => {
                    const canMutateMember = canMutateTaskListSettingsMember({
                      canManageAdmins,
                      currentUserId: user?.id,
                      member,
                    });
                    return (
                      <div
                        key={member.user_id}
                        className="flex min-h-11 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2.5 py-1.5"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex min-w-0 items-baseline gap-2">
                            <span className="app-text-body-sm min-w-0 truncate font-medium text-app-ink">
                              {member.full_name}
                            </span>
                            <span className="app-text-caption min-w-0 truncate text-app-ink/45">
                              {member.email}
                            </span>
                          </div>
                          <div className="app-text-micro text-app-ink/35">
                            {t('pms.settings.joined', {
                              date: formatDateTime(member.joined_at, {
                                dateStyle: 'medium',
                                locale,
                                timeZone,
                              }),
                            })}
                          </div>
                        </div>
                        <select
                          aria-label={t('pms.spaceMembers.changeRole')}
                          disabled={!canMutateMember}
                          value={member.role}
                          onChange={(event) => {
                            void handleRoleChange(
                              member.user_id,
                              event.target.value,
                            );
                          }}
                          className="app-field-input-sm max-w-24 shrink-0"
                        >
                          {availableRoleOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {t(option.labelKey)}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          disabled={!canMutateMember}
                          onClick={() => {
                            void handleRemoveMember(member.user_id);
                          }}
                          className="flex size-7 shrink-0 items-center justify-center rounded text-app-ink/35 transition-colors hover:bg-app-danger/10 hover:text-app-danger-text disabled:cursor-not-allowed disabled:text-app-ink/20"
                          title={t('pms.settings.removeMember')}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          ) : null}

          {/* Labels section */}
          {activeTab === 'labels' ? (
            <section className="flex h-full min-h-0 flex-col gap-3">
              <h3 className="app-text-overline text-app-ink/50">
                {t('pms.settings.labels')}
              </h3>

              {loading ? (
                <div className="flex justify-center py-6">
                  <Loader2 size={18} className="animate-spin text-app-ink/40" />
                </div>
              ) : (
                <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1 custom-scrollbar">
                  {labels.map((label) => (
                    <div
                      key={label.id}
                      className="flex items-center gap-2 py-1.5 group"
                    >
                      {editingId === label.id ? (
                        <>
                          <ColorDot color={editColor} />
                          <input
                            aria-label={t('pms.settings.editLabel', {
                              name: label.name,
                            })}
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveEdit();
                              if (e.key === 'Escape') setEditingId(null);
                            }}
                            className="app-text-body flex-1 rounded border border-app-border bg-app-surface-sidebar px-2 py-0.5 text-app-ink focus:border-app-accent focus:outline-none"
                          />
                          <ColorPicker
                            value={editColor}
                            onChange={setEditColor}
                          />
                          <button
                            type="button"
                            onClick={handleSaveEdit}
                            className="text-app-accent hover:opacity-80"
                            aria-label={t('pms.settings.saveLabel')}
                          >
                            <Check size={14} />
                          </button>
                        </>
                      ) : (
                        <>
                          <ColorDot color={label.color} />
                          <span className="app-text-body flex-1 text-app-ink">
                            {label.name}
                          </span>
                          <button
                            type="button"
                            onClick={() => startEdit(label)}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-ink transition-all"
                            aria-label={t('pms.settings.editLabel', {
                              name: label.name,
                            })}
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(label.id)}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-danger-text transition-all"
                            aria-label={t('pms.settings.deleteLabel', {
                              name: label.name,
                            })}
                          >
                            <Trash2 size={13} />
                          </button>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Add new label */}
              <div className="flex items-center gap-2 pt-1">
                <ColorDot color={newColor} />
                <input
                  aria-label={t('pms.settings.newLabelNamePlaceholder')}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newName.trim()) handleCreate();
                  }}
                  placeholder={t('pms.settings.newLabelNamePlaceholder')}
                  className="app-text-body flex-1 border-b border-app-border bg-transparent py-0.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                />
                <ColorPicker value={newColor} onChange={setNewColor} />
                {newName.trim() && (
                  <button
                    type="button"
                    onClick={handleCreate}
                    disabled={creating}
                    className="text-app-accent hover:opacity-80 disabled:opacity-40"
                    aria-label={t('pms.settings.addLabel')}
                  >
                    {creating ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Plus size={14} />
                    )}
                  </button>
                )}
              </div>
            </section>
          ) : null}

          {/* Statuses section */}
          {activeTab === 'workflow' ? (
            <section className="-mx-5 -mb-4 flex h-[calc(100%+1rem)] min-h-0 flex-col">
              <div className="grid min-h-0 flex-1 md:grid-cols-[240px_1fr]">
                <aside className="border-b border-app-border px-5 py-6 md:border-b-0 md:border-r">
                  <div className="space-y-6">
                    <div>
                      <div className="app-text-caption mb-3 flex items-center gap-1.5 text-app-ink/50">
                        {t('pms.settings.statusType')}
                        <Info size={12} />
                      </div>
                      <div className="grid gap-3">
                        <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
                          <input
                            checked={statusMode === 'inherit'}
                            disabled={!teamId || !canEditWorkflow}
                            name="status-mode"
                            onChange={() => {
                              void handleStatusModeChange('inherit');
                            }}
                            type="radio"
                          />
                          {t('pms.settings.inheritFromSpace')}
                        </label>
                        <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
                          <input
                            checked={statusMode === 'custom'}
                            disabled={!canEditWorkflow}
                            name="status-mode"
                            onChange={() => {
                              void handleStatusModeChange('custom');
                            }}
                            type="radio"
                          />
                          {t('pms.settings.useCustomStatuses')}
                        </label>
                      </div>
                    </div>

                    <div>
                      <label
                        className="app-text-caption mb-2 block text-app-ink/50"
                        htmlFor="status-template"
                      >
                        {t('pms.settings.statusTemplate')}
                      </label>
                      <select
                        className="app-field-input"
                        disabled
                        id="status-template"
                        onChange={() => undefined}
                        value=""
                      >
                        <option value="">
                          {statusMode === 'custom'
                            ? t('pms.settings.customTemplateEdited')
                            : t('pms.settings.selectTemplate')}
                        </option>
                      </select>
                    </div>
                  </div>
                </aside>

                <div className="min-h-0 overflow-y-auto px-6 py-5">
                  {statusMode === 'inherit' ? (
                    <p className="app-text-caption mb-5 max-w-[22rem] text-app-ink/50">
                      {t('pms.settings.statusManagerHint')}
                    </p>
                  ) : null}

                  {loading ? (
                    <div className="flex justify-center py-10">
                      <Loader2
                        size={18}
                        className="animate-spin text-app-ink/40"
                      />
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {CATEGORY_OPTIONS.map((category) => {
                        const categoryStatuses =
                          statusesByCategory.get(category.value) ?? [];
                        const canAddToCategory =
                          !workflowReadOnly && category.value !== 'closed';
                        const isAddingThisCategory =
                          newStatusCategory === category.value &&
                          canAddToCategory;
                        return (
                          <div key={category.value}>
                            <div className="mb-2 flex items-center justify-between">
                              <div className="app-text-caption flex items-center gap-1.5 text-app-ink/50">
                                {t(category.labelKey)}
                                <Info size={11} />
                              </div>
                              <button
                                type="button"
                                className="flex size-6 items-center justify-center rounded text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:text-app-ink/20"
                                disabled={!canAddToCategory}
                                onClick={() => {
                                  setNewStatusCategory(category.value);
                                  setNewStatusName('');
                                }}
                                title={t('pms.settings.addStatus')}
                              >
                                <Plus size={15} />
                              </button>
                            </div>

                            <div className="space-y-2">
                              {categoryStatuses.map((ps) => (
                                <div
                                  key={ps.id}
                                  className="group flex min-h-9 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 py-2 shadow-sm"
                                >
                                  {editingStatusId === ps.id ? (
                                    <>
                                      <GripVertical
                                        size={14}
                                        className="shrink-0 text-app-ink/30"
                                      />
                                      <StatusIconGlyph
                                        label={editStatusName || ps.name}
                                        status={ps.slug}
                                        taskListStatuses={[
                                          {
                                            ...ps,
                                            color: editStatusColor,
                                            category: editStatusCategory,
                                          },
                                        ]}
                                      />
                                      <input
                                        aria-label={t(
                                          'pms.settings.editStatus',
                                          { name: ps.name },
                                        )}
                                        value={editStatusName}
                                        onChange={(e) =>
                                          setEditStatusName(e.target.value)
                                        }
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter')
                                            handleSaveEditStatus();
                                          if (e.key === 'Escape')
                                            setEditingStatusId(null);
                                        }}
                                        className="app-text-body-sm min-w-0 flex-1 rounded border border-app-border bg-app-bg px-2 py-1 text-app-ink focus:border-app-accent focus:outline-none"
                                      />
                                      <ColorPicker
                                        value={editStatusColor}
                                        onChange={setEditStatusColor}
                                      />
                                      <button
                                        type="button"
                                        onClick={handleSaveEditStatus}
                                        className="text-app-accent hover:opacity-80"
                                        aria-label={t(
                                          'pms.settings.saveStatus',
                                        )}
                                      >
                                        <Check size={14} />
                                      </button>
                                    </>
                                  ) : (
                                    <>
                                      <GripVertical
                                        size={14}
                                        className="shrink-0 text-app-ink/30"
                                      />
                                      <StatusIconGlyph
                                        label={ps.name}
                                        status={ps.slug}
                                        taskListStatuses={statuses}
                                      />
                                      <span className="app-text-body-sm min-w-0 flex-1 truncate font-medium text-app-ink">
                                        {ps.name}
                                      </span>
                                      {!workflowReadOnly ? (
                                        <button
                                          type="button"
                                          onClick={() => startEditStatus(ps)}
                                          className="flex size-7 items-center justify-center rounded text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                                          aria-label={t(
                                            'pms.settings.editStatus',
                                            { name: ps.name },
                                          )}
                                        >
                                          <MoreHorizontal size={15} />
                                        </button>
                                      ) : null}
                                    </>
                                  )}
                                </div>
                              ))}

                              {canAddToCategory ? (
                                isAddingThisCategory ? (
                                  <div className="flex min-h-9 items-center gap-2 rounded-md border border-dashed border-app-border px-3 py-2">
                                    <GripVertical
                                      size={14}
                                      className="shrink-0 text-app-ink/20"
                                    />
                                    <StatusIconGlyph
                                      label={
                                        newStatusName ||
                                        t(
                                          'pms.settings.newStatusNamePlaceholder',
                                        )
                                      }
                                      status={newStatusName || category.value}
                                      taskListStatuses={[
                                        {
                                          id: 'new',
                                          slug: newStatusName || category.value,
                                          name:
                                            newStatusName ||
                                            t(
                                              'pms.settings.newStatusNamePlaceholder',
                                            ),
                                          color: newStatusColor,
                                          category: newStatusCategory,
                                          sort_order: statuses.length,
                                        },
                                      ]}
                                    />
                                    <input
                                      aria-label={t(
                                        'pms.settings.newStatusNamePlaceholder',
                                      )}
                                      value={newStatusName}
                                      onChange={(e) =>
                                        setNewStatusName(e.target.value)
                                      }
                                      onKeyDown={(e) => {
                                        if (
                                          e.key === 'Enter' &&
                                          newStatusName.trim()
                                        )
                                          handleCreateStatus();
                                        if (e.key === 'Escape')
                                          setNewStatusName('');
                                      }}
                                      placeholder={t(
                                        'pms.settings.newStatusNamePlaceholder',
                                      )}
                                      className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink placeholder:text-app-ink/40 focus:outline-none"
                                    />
                                    <ColorPicker
                                      value={newStatusColor}
                                      onChange={setNewStatusColor}
                                    />
                                    <button
                                      type="button"
                                      onClick={handleCreateStatus}
                                      disabled={
                                        !newStatusName.trim() || creatingStatus
                                      }
                                      className="text-app-accent hover:opacity-80 disabled:opacity-40"
                                      aria-label={t('pms.settings.addStatus')}
                                    >
                                      {creatingStatus ? (
                                        <Loader2
                                          size={14}
                                          className="animate-spin"
                                        />
                                      ) : (
                                        <Plus size={14} />
                                      )}
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    type="button"
                                    className="app-control h-9 w-full border-dashed text-app-ink/50 hover:border-app-accent/50 hover:text-app-ink"
                                    onClick={() => {
                                      setNewStatusCategory(category.value);
                                      setNewStatusName('');
                                    }}
                                  >
                                    <Plus size={15} />
                                    {t('pms.settings.addStatusRow')}
                                  </button>
                                )
                              ) : null}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between gap-3 border-t border-app-border px-5 py-3">
                <button
                  className="app-text-body-sm text-app-ink/50 underline underline-offset-2 hover:text-app-ink"
                  type="button"
                >
                  {t('pms.settings.learnMoreStatuses')}
                </button>
                <div className="flex items-center gap-2">
                  <button
                    className="app-control text-app-ink/35"
                    disabled
                    type="button"
                  >
                    {t('pms.settings.saveAsTemplate')}
                  </button>
                  <Button
                    disabled={loading}
                    onClick={onClose}
                    variant="primary"
                  >
                    {t('pms.settings.applyChanges')}
                  </Button>
                </div>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </Dialog>
  );
}

function ColorDot({ color }: { color: string }) {
  return (
    <span
      className="size-3 shrink-0 rounded-full"
      style={{ backgroundColor: color }}
    />
  );
}

function ColorPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (c: string) => void;
}) {
  return (
    <div className="flex gap-0.5">
      {LABEL_PRESET_COLORS.map((c) => (
        <button
          type="button"
          key={c}
          onClick={() => onChange(c)}
          className={`size-3 rounded-full transition-transform ${value === c ? 'scale-125 ring-1 ring-white/50' : 'hover:scale-110'}`}
          aria-label={c}
          style={{ backgroundColor: c }}
          title={c}
        />
      ))}
    </div>
  );
}
