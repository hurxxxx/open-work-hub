import { useState, useCallback } from 'react';
import {
  X,
  Maximize2,
  Minimize2,
  Share2,
  MoreHorizontal,
  Send,
  Loader2,
  ChevronRight,
  Archive,
  Trash2,
  Tag,
  Check,
  CheckSquare,
  Unlink,
  Paperclip,
  Download,
  FileIcon,
  Plus,
  ExternalLink,
} from 'lucide-react';
import { Badge, Button, BlockEditor, BlockViewer } from '@open-work-hub/ui';
import type { BlockContent } from '@open-work-hub/ui';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { DateInput } from '@/src/components/date/DateInput';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { LinkedRecordingsForTarget } from '@/src/app-modules/recording/public-api';
import {
  type PmsTask,
  type PmsTaskListMember,
  type PmsMilestone,
  type PmsLabel,
  type PmsTaskListStatus,
} from '../api/pms-api';
import {
  getStatusSlugs,
  getStatusTone,
  initials,
  formatDate,
} from './pms-constants';
import { InlineSaveError, MetaLabel, UserRolePicker } from './TaskDetailFields';
import { TaskDocPickerModal } from './TaskDocPickerModal';
import { useTaskDetailAttachments } from './useTaskDetailAttachments';
import { TaskDetailActivityPanel } from './TaskDetailActivityPanel';
import { useTaskDetailChecklist } from './useTaskDetailChecklist';
import { useTaskDetailComments } from './useTaskDetailComments';
import { useTaskDetailIssueEditing } from './useTaskDetailIssueEditing';
import { useTaskDetailLinkedDocs } from './useTaskDetailLinkedDocs';
import { useTaskDetailResources } from './useTaskDetailResources';
import { useTaskDetailSubtasks } from './useTaskDetailSubtasks';

const PRIORITIES = ['low', 'medium', 'high', 'critical'] as const;
const PRIORITY_LABEL_KEYS: Record<string, string> = {
  critical: 'pms.priorityCritical',
  high: 'pms.priorityHigh',
  low: 'pms.priorityLow',
  medium: 'pms.priorityMedium',
};
const RECURRENCE_OPTIONS = [
  { value: 'daily', labelKey: 'pms.taskDetail.recurrence.daily' },
  { value: 'weekly', labelKey: 'pms.taskDetail.recurrence.weekly' },
  { value: 'biweekly', labelKey: 'pms.taskDetail.recurrence.biweekly' },
  { value: 'monthly', labelKey: 'pms.taskDetail.recurrence.monthly' },
] as const;
const EMPTY_MEMBERS: PmsTaskListMember[] = [];
const EMPTY_MILESTONES: PmsMilestone[] = [];
const EMPTY_TASK_LIST_LABELS: PmsLabel[] = [];

const selectClass = 'app-field-input min-w-0 cursor-pointer';
const disabledFieldClass = `${selectClass} disabled:cursor-not-allowed disabled:opacity-60`;
const selectOptionClass = 'bg-app-surface text-app-ink';

type TaskDetailProps = {
  task: PmsTask;
  members?: PmsTaskListMember[];
  milestones?: PmsMilestone[];
  taskListLabels?: PmsLabel[];
  taskListStatuses?: PmsTaskListStatus[];
  spaceName?: string | null;
  spaceId?: string | null;
  workspaceSlug?: string | null;
  canEdit?: boolean;
  onClose: () => void;
  onUpdate?: () => void | Promise<void>;
};

export function TaskDetail(props: TaskDetailProps) {
  return useTaskDetailContent(props);
}

function useTaskDetailContent({
  task,
  members = EMPTY_MEMBERS,
  milestones = EMPTY_MILESTONES,
  taskListLabels = EMPTY_TASK_LIST_LABELS,
  taskListStatuses,
  spaceName,
  spaceId = null,
  workspaceSlug: workspaceSlugProp = null,
  canEdit = true,
  onClose,
  onUpdate,
}: TaskDetailProps) {
  const { workspaceSlug: routeWorkspaceSlug } = useParams();
  const workspaceSlug = workspaceSlugProp ?? routeWorkspaceSlug ?? null;
  const { token, user } = useAuth();
  const { t } = useTranslation('apps');
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const {
    commitTitleChange,
    descriptionBlocksRef,
    handleDescriptionChange,
    issueState,
    memberNamesForIds,
    patchField,
    persistIssueUpdate,
    saveError,
    selectedAssigneeIds,
    selectedFollowerIds,
    selectedLabelIds,
    setSaveError,
    setTitleDraft,
    statusLabel,
    titleDraft,
    toggleIssueUserRole,
  } = useTaskDetailIssueEditing({
    canEdit,
    members,
    onUpdate,
    task,
    taskListStatuses,
    token,
    t,
  });
  const [descFullscreen, setDescFullscreen] = useState(false);
  const [labelPickerOpen, setLabelPickerOpen] = useState(false);
  const [userRolePickerOpen, setUserRolePickerOpen] = useState<
    'assignees' | 'followers' | null
  >(null);
  const [mobilePanel, setMobilePanel] = useState<'details' | 'activity'>(
    'details',
  );
  const {
    state: {
      activityLogs,
      attachments,
      checklistItems,
      comments,
      linkedDocs,
      loading,
      subtasks,
    },
    setAttachments,
    setChecklistItems,
    setComments,
    setLinkedDocs,
    setSubtasks,
  } = useTaskDetailResources({
    taskId: task.id,
    token,
    workspaceSlug,
  });
  const {
    addingSubtask,
    handleAddSubtask,
    handleArchiveSubtask,
    handleDeleteSubtask,
    handleUnlinkSubtask,
    newSubtaskTitle,
    setNewSubtaskTitle,
    setSubtaskMenuOpen,
    subtaskMenuOpen,
  } = useTaskDetailSubtasks({
    canEdit,
    onUpdate,
    parentTask: task,
    setSaveError,
    setSubtasks,
    taskListStatuses,
    token,
    t,
  });
  const {
    addingChecklist,
    checklistDone,
    checklistTotal,
    editingChecklistId,
    editingChecklistText,
    handleAddChecklistItem,
    handleDeleteChecklistItem,
    handleSaveChecklistEdit,
    handleToggleChecklistItem,
    newChecklistText,
    setEditingChecklistId,
    setEditingChecklistText,
    setNewChecklistText,
  } = useTaskDetailChecklist({
    canEdit,
    checklistItems,
    onUpdate,
    setChecklistItems,
    setSaveError,
    taskId: task.id,
    token,
    t,
  });
  const {
    dragOver,
    formatAttachmentSize,
    handleDeleteAttachment,
    handleFileUpload,
    setDragOver,
    uploading,
  } = useTaskDetailAttachments({
    canEdit,
    onUpdate,
    setAttachments,
    setSaveError,
    taskId: task.id,
    token,
    t,
  });
  const {
    closeMention,
    commentDraft,
    handleCommentDraftChange,
    handleCommentSubmit,
    handleMentionPick,
    mentionCandidates,
    mentionOpen,
  } = useTaskDetailComments({
    canEdit,
    members,
    onUpdate,
    setComments,
    setSaveError,
    taskId: task.id,
    token,
    t,
  });
  const {
    buildDocPath,
    docPickerOpen,
    handleLinkDoc,
    handlePromoteDescriptionToDoc,
    handleUnlinkDoc,
    promotingDescription,
    setDocPickerOpen,
  } = useTaskDetailLinkedDocs({
    canEdit,
    descriptionBlocksRef,
    issue: issueState,
    onUpdate,
    setLinkedDocs,
    setSaveError,
    spaceId,
    token,
    t,
    workspaceSlug,
  });

  const handleToggleIssueArchive = useCallback(() => {
    if (!canEdit) return;
    const nextArchived = !issueState.archived;
    void persistIssueUpdate(
      { archived: nextArchived },
      (current) => ({ ...current, archived: nextArchived }),
      nextArchived
        ? t('pms.taskDetail.errors.archiveIssueFailed')
        : t('pms.taskDetail.errors.restoreIssueFailed'),
    );
  }, [canEdit, issueState.archived, persistIssueUpdate, t]);

  const handleToggleLabel = useCallback(
    (labelId: string) => {
      if (!canEdit) return;
      const nextLabelIds = selectedLabelIds.includes(labelId)
        ? selectedLabelIds.filter((id) => id !== labelId)
        : [...selectedLabelIds, labelId];
      const nextLabels = taskListLabels.filter((label) =>
        nextLabelIds.includes(label.id),
      );
      void persistIssueUpdate(
        { label_ids: nextLabelIds },
        (current) => ({ ...current, labels: nextLabels }),
        t('pms.taskDetail.errors.saveLabelsFailed'),
      );
    },
    [canEdit, persistIssueUpdate, taskListLabels, selectedLabelIds, t],
  );

  // Description fullscreen mode
  if (descFullscreen) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-6 py-3 border-b border-app-border shrink-0">
          <button
            type="button"
            onClick={() => setDescFullscreen(false)}
            className="app-text-body flex items-center gap-2 text-app-ink/60 transition-colors hover:text-app-ink"
          >
            {t('pms.taskDetail.backToTask')}
          </button>
          <span className="app-text-control text-app-ink">
            {issueState.title}
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDescFullscreen(false)}
          >
            <Minimize2 size={16} />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-6 max-w-4xl mx-auto w-full">
          <h1 className="app-text-title-lg mb-6 text-app-ink">
            {issueState.title}
          </h1>
          {canEdit ? (
            <BlockEditor
              initialContent={
                issueState.description_blocks as BlockContent | undefined
              }
              onChange={handleDescriptionChange}
              placeholder={t('pms.taskDetail.startWritingPlaceholder')}
              className="[&_.bn-editor]:min-h-[400px] [&_.bn-editor]:px-1"
              uploadFile={uploadFile}
              resolveFileUrl={resolveFileUrl}
            />
          ) : (
            <BlockViewer
              content={
                (issueState.description_blocks as BlockContent | null) ?? []
              }
              resolveFileUrl={resolveFileUrl}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-3 border-b border-app-border px-4 py-3 shrink-0 lg:px-5">
        <div className="app-text-caption flex min-w-0 items-center gap-2 text-app-ink/50">
          <span className="truncate">
            {spaceName || t('pms.spaceOverview.fallbackSpaceName')}
          </span>
          <ChevronRight size={12} />
          <span className="truncate text-app-ink/70">{issueState.title}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {!canEdit ? (
            <span className="app-text-overline rounded-full border border-app-border px-2 py-1 text-app-ink/50">
              {t('pms.taskDetail.readOnly')}
            </span>
          ) : (
            <button
              type="button"
              onClick={handleToggleIssueArchive}
              className="app-text-control-sm rounded-md border border-app-border px-2.5 py-1 text-app-ink/60 transition-colors hover:border-app-ink/30 hover:text-app-ink"
            >
              {issueState.archived
                ? t('pms.bulk.restore')
                : t('common:actions.archive')}
            </button>
          )}
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('pms.taskDetail.share')}
          >
            <Share2 size={16} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('pms.taskDetail.moreOptions')}
          >
            <MoreHorizontal size={16} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label={t('common:actions.close')}
          >
            <X size={16} />
          </Button>
        </div>
      </div>

      <div
        aria-label={t('pms.taskDetail.mobileSections')}
        className="grid grid-cols-2 gap-1 border-b border-app-border bg-app-bg px-4 py-2 lg:hidden"
        role="tablist"
      >
        <button
          type="button"
          onClick={() => setMobilePanel('details')}
          aria-controls="task-detail-details-panel"
          aria-selected={mobilePanel === 'details'}
          className={`app-text-control-sm rounded-md px-3 py-2 transition-colors ${
            mobilePanel === 'details'
              ? 'bg-app-surface-hover text-app-ink'
              : 'text-app-ink/50 hover:text-app-ink'
          }`}
          role="tab"
        >
          {t('pms.taskDetail.details')}
        </button>
        <button
          type="button"
          onClick={() => setMobilePanel('activity')}
          aria-controls="task-detail-activity-panel"
          aria-selected={mobilePanel === 'activity'}
          className={`app-text-control-sm rounded-md px-3 py-2 transition-colors ${
            mobilePanel === 'activity'
              ? 'bg-app-surface-hover text-app-ink'
              : 'text-app-ink/50 hover:text-app-ink'
          }`}
          role="tab"
        >
          {t('pms.taskDetail.activity')}
        </button>
      </div>

      {/* Responsive layout: mobile tabs, desktop split view */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Left: main content */}
        <div
          id="task-detail-details-panel"
          data-testid="task-detail-details-panel"
          className={`${mobilePanel === 'details' ? 'flex' : 'hidden'} min-h-0 flex-1 flex-col overflow-y-auto custom-scrollbar lg:flex lg:border-r lg:border-app-border`}
          role="tabpanel"
        >
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-4 pb-[calc(1rem+env(safe-area-inset-bottom))] lg:px-8 lg:py-6">
            {/* Title */}
            <div className="flex min-w-0 flex-wrap items-start gap-2">
              {canEdit ? (
                <input
                  aria-label={t('pms.taskName')}
                  data-testid="task-detail-title"
                  className="app-text-title-lg min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-app-ink outline-none transition-colors hover:border-app-border focus:border-app-accent focus:bg-app-surface-sidebar/40"
                  maxLength={180}
                  onBlur={() => {
                    void commitTitleChange();
                  }}
                  onChange={(event) => setTitleDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === 'Enter' &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      event.currentTarget.blur();
                    }
                    if (event.key === 'Escape') {
                      setTitleDraft(issueState.title);
                      event.currentTarget.blur();
                    }
                  }}
                  value={titleDraft}
                />
              ) : (
                <h1
                  data-testid="task-detail-title"
                  className="app-text-title-lg min-w-0 flex-1 break-words text-app-ink"
                >
                  {issueState.title}
                </h1>
              )}
              {issueState.archived && (
                <span className="app-text-overline rounded-full border border-app-warning/30 bg-app-warning/10 px-2 py-0.5 text-app-warning-text">
                  {t('pms.filter.archive.archived')}
                </span>
              )}
            </div>

            {saveError ? <InlineSaveError message={saveError} /> : null}

            {/* Meta fields */}
            <div
              data-testid="task-detail-meta-grid"
              className="grid grid-cols-[88px_minmax(0,1fr)] items-center gap-x-3 gap-y-3 rounded-lg border border-app-border p-3 lg:grid-cols-[auto_1fr_auto_1fr] lg:gap-x-6 lg:rounded-none lg:border-0 lg:p-0"
            >
              <MetaLabel>{t('pms.filter.statusLabel')}</MetaLabel>
              <select
                aria-label={t('pms.filter.statusLabel')}
                value={issueState.status}
                onChange={(e) => patchField('status', e.target.value)}
                className={disabledFieldClass}
                disabled={!canEdit}
              >
                {getStatusSlugs(taskListStatuses).map((s) => (
                  <option className={selectOptionClass} key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
              <MetaLabel>{t('pms.taskDetail.assignees')}</MetaLabel>
              <UserRolePicker
                canEdit={canEdit}
                currentUserId={user?.id}
                currentUserLabel={t('pms.taskDetail.me')}
                emptyLabel={t('pms.taskDetail.unassigned')}
                isOpen={userRolePickerOpen === 'assignees'}
                label={t('pms.taskDetail.assignees')}
                members={members}
                noMatchesLabel={t('pms.taskDetail.noMatches')}
                noMembersLabel={t('pms.taskDetail.noRoleMembers')}
                onOpenChange={(open) =>
                  setUserRolePickerOpen(open ? 'assignees' : null)
                }
                onToggle={(userId) => toggleIssueUserRole('assignees', userId)}
                removeItemLabel={(name) => t('pms.removeMember', { name })}
                searchPlaceholder={t('pms.searchUser')}
                selectedIds={selectedAssigneeIds}
                selectedNames={memberNamesForIds(
                  selectedAssigneeIds,
                  issueState.assignee_names ?? [],
                )}
              />
              <MetaLabel>{t('pms.taskDetail.followers')}</MetaLabel>
              <UserRolePicker
                canEdit={canEdit}
                currentUserId={user?.id}
                currentUserLabel={t('pms.taskDetail.me')}
                emptyLabel={t('pms.taskDetail.noFollowers')}
                isOpen={userRolePickerOpen === 'followers'}
                label={t('pms.taskDetail.followers')}
                members={members}
                noMatchesLabel={t('pms.taskDetail.noMatches')}
                noMembersLabel={t('pms.taskDetail.noRoleMembers')}
                onOpenChange={(open) =>
                  setUserRolePickerOpen(open ? 'followers' : null)
                }
                onToggle={(userId) => toggleIssueUserRole('followers', userId)}
                removeItemLabel={(name) => t('pms.removeMember', { name })}
                searchPlaceholder={t('pms.searchUser')}
                selectedIds={selectedFollowerIds}
                selectedNames={memberNamesForIds(
                  selectedFollowerIds,
                  issueState.follower_names ?? [],
                )}
              />

              <MetaLabel>{t('planner.start')}</MetaLabel>
              <DateInput
                value={issueState.start_date ?? ''}
                onValueChange={(value) =>
                  patchField('start_date', value || null)
                }
                className={disabledFieldClass}
                disabled={!canEdit}
              />
              <MetaLabel>{t('pms.taskDetail.due')}</MetaLabel>
              <DateInput
                value={issueState.due_date ?? ''}
                onValueChange={(value) => patchField('due_date', value || null)}
                className={disabledFieldClass}
                disabled={!canEdit}
              />
              <MetaLabel>{t('pms.taskDetail.completedDate')}</MetaLabel>
              <DateInput
                aria-label={t('pms.taskDetail.completedDate')}
                value={issueState.completed_date ?? ''}
                onValueChange={(value) =>
                  patchField('completed_date', value || null)
                }
                className={disabledFieldClass}
                disabled={!canEdit}
              />

              <MetaLabel>{t('pms.filter.priorityLabel')}</MetaLabel>
              <select
                aria-label={t('pms.filter.priorityLabel')}
                value={issueState.priority}
                onChange={(e) => patchField('priority', e.target.value)}
                className={disabledFieldClass}
                disabled={!canEdit}
              >
                {PRIORITIES.map((p) => (
                  <option className={selectOptionClass} key={p} value={p}>
                    {t(PRIORITY_LABEL_KEYS[p])}
                  </option>
                ))}
              </select>
              <MetaLabel>{t('pms.filter.milestoneLabel')}</MetaLabel>
              <select
                aria-label={t('pms.filter.milestoneLabel')}
                value={issueState.milestone_id ?? ''}
                onChange={(e) =>
                  patchField('milestone_id', e.target.value || null)
                }
                className={disabledFieldClass}
                disabled={!canEdit}
              >
                <option className={selectOptionClass} value="">
                  {t('common:empty.none')}
                </option>
                {milestones.map((m) => (
                  <option className={selectOptionClass} key={m.id} value={m.id}>
                    {m.title}
                  </option>
                ))}
              </select>

              <MetaLabel>{t('pms.taskDetail.repeat')}</MetaLabel>
              <select
                aria-label={t('pms.taskDetail.repeat')}
                value={issueState.recurrence_rule ?? ''}
                onChange={(e) =>
                  patchField('recurrence_rule', e.target.value || null)
                }
                className={disabledFieldClass}
                disabled={!canEdit}
              >
                <option className={selectOptionClass} value="">
                  {t('common:empty.none')}
                </option>
                {RECURRENCE_OPTIONS.map((option) => (
                  <option
                    className={selectOptionClass}
                    key={option.value}
                    value={option.value}
                  >
                    {t(option.labelKey)}
                  </option>
                ))}
              </select>
              <MetaLabel>{t('pms.bulk.labelsLabel')}</MetaLabel>
              <div className="relative min-w-0 lg:col-span-3">
                <button
                  type="button"
                  onClick={() => {
                    if (!canEdit) return;
                    setLabelPickerOpen((prev) => !prev);
                  }}
                  className={`flex min-h-[28px] w-full flex-wrap items-center gap-1 rounded px-1 py-0.5 text-left transition-colors ${
                    canEdit ? 'hover:bg-app-surface-hover/50' : 'cursor-default'
                  }`}
                  disabled={!canEdit}
                >
                  {selectedLabelIds.length > 0 ? (
                    selectedLabelIds.map((id) => {
                      const label = taskListLabels.find((l) => l.id === id);
                      return label ? (
                        <span
                          key={id}
                          className="app-text-caption inline-flex items-center rounded px-2 py-0.5 font-medium text-white"
                          style={{ backgroundColor: label.color }}
                        >
                          {label.name}
                        </span>
                      ) : null;
                    })
                  ) : (
                    <span className="app-text-body flex items-center gap-1 text-app-ink/40">
                      <Tag size={12} />
                      {canEdit
                        ? t('pms.taskDetail.addLabelsPlaceholder')
                        : t('pms.taskDetail.noLabels')}
                    </span>
                  )}
                </button>
                {labelPickerOpen && canEdit && (
                  <>
                    <button
                      aria-label={t('common:actions.close')}
                      type="button"
                      className="fixed inset-0 z-10"
                      onClick={() => setLabelPickerOpen(false)}
                    />
                    <div className="absolute left-0 top-8 z-20 w-48 bg-app-bg border border-app-border rounded-lg shadow-xl py-1">
                      {taskListLabels.length === 0 ? (
                        <p className="app-text-caption px-3 py-2 text-app-ink/40">
                          {t('pms.taskDetail.noLabelsInList')}
                        </p>
                      ) : (
                        taskListLabels.map((label) => (
                          <button
                            type="button"
                            key={label.id}
                            onClick={() => handleToggleLabel(label.id)}
                            className="app-text-body flex w-full items-center gap-2 px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover"
                          >
                            <span
                              className="size-3 rounded-full shrink-0"
                              style={{ backgroundColor: label.color }}
                            />
                            <span className="flex-1 text-left">
                              {label.name}
                            </span>
                            {selectedLabelIds.includes(label.id) && (
                              <Check size={12} className="text-app-accent" />
                            )}
                          </button>
                        ))
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Description with fullscreen button */}
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <h3 className="app-text-title-md text-app-ink">
                  {t('pms.description')}
                </h3>
                <div className="flex shrink-0 items-center gap-1">
                  {canEdit ? (
                    <Button
                      variant="ghost"
                      onClick={handlePromoteDescriptionToDoc}
                      disabled={promotingDescription}
                    >
                      {promotingDescription ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <FileIcon size={14} />
                      )}
                      {promotingDescription
                        ? t('pms.taskDetail.promoteDescriptionBusy')
                        : t('pms.taskDetail.promoteDescriptionToDoc')}
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setDescFullscreen(true)}
                    title={t('pms.taskDetail.fullScreen')}
                  >
                    <Maximize2 size={14} />
                  </Button>
                </div>
              </div>
              <div className="rounded-lg border border-app-border overflow-hidden">
                {canEdit ? (
                  <BlockEditor
                    initialContent={
                      issueState.description_blocks as BlockContent | undefined
                    }
                    onChange={handleDescriptionChange}
                    placeholder={t('pms.descriptionPlaceholder')}
                    className="[&_.bn-editor]:min-h-[120px] [&_.bn-editor]:px-3 [&_.bn-editor]:py-2"
                    uploadFile={uploadFile}
                    resolveFileUrl={resolveFileUrl}
                  />
                ) : (
                  <div className="px-3 py-2">
                    <BlockViewer
                      content={
                        (issueState.description_blocks as BlockContent | null) ??
                        []
                      }
                      resolveFileUrl={resolveFileUrl}
                    />
                  </div>
                )}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Checklist */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <CheckSquare size={14} className="text-app-ink/50" />
                <h3 className="app-text-title-md text-app-ink">
                  {t('pms.taskDetail.checklist')}
                  {checklistTotal > 0 && (
                    <span className="text-app-ink/40 font-normal ml-1">
                      ({checklistDone}/{checklistTotal})
                    </span>
                  )}
                </h3>
              </div>

              {checklistTotal > 0 && (
                <>
                  <div className="h-1.5 overflow-hidden rounded-full bg-app-border">
                    <div
                      className="h-full bg-app-success rounded-full transition-all duration-300"
                      style={{
                        width: `${checklistTotal > 0 ? (checklistDone / checklistTotal) * 100 : 0}%`,
                      }}
                    />
                  </div>
                  <div className="border border-app-border rounded-lg">
                    {checklistItems.map((ci) => (
                      <div
                        key={ci.id}
                        className="flex items-center gap-3 px-3 py-2 border-b border-app-border last:border-b-0 hover:bg-app-surface-hover/50 transition-colors group first:rounded-t-lg last:rounded-b-lg"
                      >
                        <input
                          aria-label={ci.text}
                          type="checkbox"
                          checked={ci.completed}
                          onChange={() => handleToggleChecklistItem(ci)}
                          disabled={!canEdit}
                          className="size-3.5 shrink-0 cursor-pointer rounded border-app-border accent-app-accent"
                        />
                        {editingChecklistId === ci.id ? (
                          <input
                            aria-label={t('pms.taskDetail.checklist')}
                            type="text"
                            value={editingChecklistText}
                            onChange={(e) =>
                              setEditingChecklistText(e.target.value)
                            }
                            onKeyDown={(e) => {
                              if (
                                e.key === 'Enter' &&
                                !e.nativeEvent.isComposing
                              ) {
                                e.preventDefault();
                                handleSaveChecklistEdit(ci.id);
                              }
                              if (e.key === 'Escape')
                                setEditingChecklistId(null);
                            }}
                            onBlur={() => {
                              if (canEdit) {
                                void handleSaveChecklistEdit(ci.id);
                              }
                            }}
                            className="app-text-body flex-1 border-b border-app-accent bg-transparent py-0.5 text-app-ink focus:outline-none"
                          />
                        ) : (
                          <button
                            type="button"
                            className={`app-text-body flex-1 bg-transparent p-0 text-left ${canEdit ? 'cursor-pointer' : 'cursor-default'} ${ci.completed ? 'line-through text-app-ink/40' : 'text-app-ink'}`}
                            disabled={!canEdit}
                            onClick={() => {
                              if (!canEdit) return;
                              setEditingChecklistId(ci.id);
                              setEditingChecklistText(ci.text);
                            }}
                          >
                            {ci.text}
                          </button>
                        )}
                        {canEdit ? (
                          <button
                            type="button"
                            onClick={() => {
                              void handleDeleteChecklistItem(ci.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-app-danger-text transition-all p-0.5 rounded"
                            title={t('common:actions.delete')}
                            aria-label={t('common:actions.delete')}
                          >
                            <X size={13} />
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </>
              )}

              <div className="flex items-center gap-2">
                <input
                  aria-label={t('pms.taskDetail.addChecklistPlaceholder')}
                  type="text"
                  value={newChecklistText}
                  onChange={(e) => setNewChecklistText(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === 'Enter' &&
                      !e.nativeEvent.isComposing &&
                      newChecklistText.trim()
                    ) {
                      e.preventDefault();
                      handleAddChecklistItem();
                    }
                  }}
                  placeholder={
                    canEdit
                      ? t('pms.taskDetail.addChecklistPlaceholder')
                      : t('pms.taskDetail.checklistReadOnly')
                  }
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && newChecklistText.trim() && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleAddChecklistItem}
                    disabled={addingChecklist}
                  >
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Subtasks */}
            <div className="space-y-2">
              <h3 className="app-text-title-md text-app-ink">
                {t('pms.taskDetail.subtasks')}{' '}
                {subtasks.length > 0 && (
                  <span className="text-app-ink/40 font-normal">
                    ({subtasks.length})
                  </span>
                )}
              </h3>

              {subtasks.length > 0 && (
                <div className="border border-app-border rounded-lg">
                  {subtasks.map((sub) => (
                    <div
                      key={sub.id}
                      className="flex items-center gap-3 px-3 py-2 border-b border-app-border last:border-b-0 hover:bg-app-surface-hover/50 transition-colors group relative first:rounded-t-lg last:rounded-b-lg"
                    >
                      <input
                        aria-label={sub.title}
                        type="checkbox"
                        checked={sub.status === 'done'}
                        readOnly
                        className="size-3.5 cursor-pointer rounded border-app-border accent-app-accent"
                      />
                      <span
                        className={`app-text-body flex-1 ${sub.status === 'done' ? 'line-through text-app-ink/40' : 'text-app-ink'}`}
                      >
                        {sub.title}
                      </span>
                      <Badge tone={getStatusTone(sub.status, taskListStatuses)}>
                        {statusLabel(sub.status)}
                      </Badge>
                      {sub.assignee_name && (
                        <div className="flex size-5 items-center justify-center rounded-full bg-app-info text-[8px] font-bold text-white">
                          {initials(sub.assignee_name)}
                        </div>
                      )}
                      {/* ··· context menu */}
                      {canEdit ? (
                        <div className="relative">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSubtaskMenuOpen((prev) =>
                                prev === sub.id ? null : sub.id,
                              );
                            }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-app-ink transition-all p-0.5 rounded"
                            title={t('pms.taskDetail.moreOptions')}
                            aria-label={t('pms.taskDetail.moreOptions')}
                          >
                            <MoreHorizontal size={14} />
                          </button>
                          {subtaskMenuOpen === sub.id && (
                            <>
                              <button
                                aria-label={t('common:actions.close')}
                                type="button"
                                className="fixed inset-0 z-10"
                                onClick={() => setSubtaskMenuOpen(null)}
                              />
                              <div className="app-text-body absolute right-0 top-full z-20 w-36 rounded-lg border border-app-border bg-app-bg py-1 shadow-xl">
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleUnlinkSubtask(sub.id);
                                    setSubtaskMenuOpen(null);
                                  }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink transition-colors"
                                >
                                  <Unlink size={13} />
                                  {t('pms.taskDetail.unlink')}
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleArchiveSubtask(sub.id);
                                  }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink transition-colors"
                                >
                                  <Archive size={13} />
                                  {t('common:actions.archive')}
                                </button>
                                <hr className="border-app-border my-1" />
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleDeleteSubtask(sub.id);
                                  }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-app-danger-text hover:bg-app-surface-hover hover:text-app-danger transition-colors"
                                >
                                  <Trash2 size={13} />
                                  {t('common:actions.delete')}
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2">
                <input
                  aria-label={t('pms.taskDetail.addSubtaskPlaceholder')}
                  type="text"
                  value={newSubtaskTitle}
                  onChange={(e) => setNewSubtaskTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === 'Enter' &&
                      !e.nativeEvent.isComposing &&
                      newSubtaskTitle.trim()
                    ) {
                      e.preventDefault();
                      handleAddSubtask();
                    }
                  }}
                  placeholder={
                    canEdit
                      ? t('pms.taskDetail.addSubtaskPlaceholder')
                      : t('pms.taskDetail.subtasksReadOnly')
                  }
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && newSubtaskTitle.trim() && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleAddSubtask}
                    disabled={addingSubtask}
                  >
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Linked docs */}
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="app-text-title-md flex items-center gap-2 text-app-ink">
                    <FileIcon size={16} className="text-app-ink/50" />
                    {t('pms.taskDetail.linkedDocs')}
                    {linkedDocs.length > 0 && (
                      <span className="font-normal text-app-ink/40">
                        ({linkedDocs.length})
                      </span>
                    )}
                  </h3>
                  <p className="app-text-caption mt-0.5 text-app-ink/40">
                    {t('pms.taskDetail.linkedDocsHint')}
                  </p>
                </div>
                {canEdit ? (
                  <Button
                    variant="ghost"
                    onClick={() => setDocPickerOpen(true)}
                  >
                    <Plus size={14} />
                    {t('pms.taskDetail.addLinkedDoc')}
                  </Button>
                ) : null}
              </div>
              {linkedDocs.length > 0 ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {linkedDocs.map((doc) => {
                    const docPath = buildDocPath(doc.doc_id);
                    const sourceLabel = t(
                      `pms.taskDetail.docSource.${doc.source_kind}`,
                      {
                        defaultValue: doc.source_kind,
                      },
                    );
                    return (
                      <div
                        key={doc.id}
                        className="group rounded-lg border border-app-border bg-app-surface-sidebar/50 px-3 py-2.5 transition-colors hover:border-app-ink/20 hover:bg-app-surface-hover"
                      >
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink/50">
                            <FileIcon size={16} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <a
                              href={docPath}
                              className="app-text-body line-clamp-2 font-medium text-app-ink transition-colors hover:text-app-accent"
                            >
                              {doc.doc_title ||
                                t('pms.taskDetail.docPickerUntitled')}
                            </a>
                            <div className="app-text-caption mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-app-ink/40">
                              <span>
                                {t(`docs.docType.${doc.doc_type}`, {
                                  defaultValue: doc.doc_type,
                                })}
                              </span>
                              <span aria-hidden="true">·</span>
                              <span>{sourceLabel}</span>
                              {doc.updated_at ? (
                                <>
                                  <span aria-hidden="true">·</span>
                                  <span>
                                    {t('pms.taskDetail.docUpdatedAt', {
                                      date: formatDate(doc.updated_at),
                                    })}
                                  </span>
                                </>
                              ) : null}
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            <a
                              href={docPath}
                              className="rounded-md p-1 text-app-ink/35 transition-colors hover:bg-app-bg hover:text-app-ink"
                              title={t('pms.taskDetail.openLinkedDoc')}
                              aria-label={t('pms.taskDetail.openLinkedDoc')}
                            >
                              <ExternalLink size={14} />
                            </a>
                            {canEdit ? (
                              <button
                                type="button"
                                onClick={() => {
                                  void handleUnlinkDoc(doc.doc_id);
                                }}
                                className="rounded-md p-1 text-app-ink/30 transition-colors hover:bg-app-bg hover:text-app-danger-text"
                                title={t('pms.taskDetail.unlinkDoc')}
                                aria-label={t('pms.taskDetail.unlinkDoc')}
                              >
                                <X size={14} />
                              </button>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : canEdit ? (
                <div className="app-text-body rounded-lg border border-dashed border-app-border px-3 py-4 text-center text-app-ink/40">
                  {t('pms.taskDetail.linkedDocsEmpty')}
                </div>
              ) : (
                <p className="app-text-body text-app-ink/40">
                  {t('pms.taskDetail.linkedDocsReadOnly')}
                </p>
              )}
            </div>

            <hr className="border-app-border" />

            {workspaceSlug ? (
              <>
                <LinkedRecordingsForTarget
                  workspaceSlug={workspaceSlug}
                  targetApp="pms"
                  targetType="task"
                  targetId={task.id}
                  title={t('recording.linked.title')}
                  emptyText={t('recording.linked.empty')}
                />

                <hr className="border-app-border" />
              </>
            ) : null}

            {/* Attachments */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Paperclip size={14} className="text-app-ink/50" />
                <h3 className="app-text-title-md text-app-ink">
                  {t('pms.taskDetail.attachments')}
                </h3>
                <span className="app-text-caption text-app-ink/40">
                  {attachments.length}
                </span>
              </div>

              {attachments.length > 0 && (
                <div className="space-y-1">
                  {attachments.map((att) => {
                    const isImage = att.content_type.startsWith('image/');
                    return (
                      <div
                        key={att.id}
                        className="flex items-center gap-3 py-1.5 px-2 rounded-md hover:bg-app-surface-hover group transition-colors"
                      >
                        {isImage ? (
                          <img
                            src={att.download_url}
                            alt={att.filename}
                            className="size-8 rounded border border-app-border object-cover"
                          />
                        ) : (
                          <div className="flex size-8 items-center justify-center rounded border border-app-border bg-app-surface-sidebar">
                            <FileIcon size={14} className="text-app-ink/40" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="app-text-body truncate text-app-ink">
                            {att.filename}
                          </p>
                          <p className="app-text-micro text-app-ink/40">
                            {formatAttachmentSize(att.size_bytes)}
                            {' · '}
                            {att.uploaded_by_name}
                          </p>
                        </div>
                        <a
                          href={att.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={t('pms.taskDetail.downloadAttachment', {
                            filename: att.filename,
                          })}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-ink transition-all"
                        >
                          <Download size={14} />
                        </a>
                        {canEdit ? (
                          <button
                            type="button"
                            onClick={() => {
                              void handleDeleteAttachment(att.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-danger-text transition-all"
                            aria-label={t('common:actions.delete')}
                          >
                            <Trash2 size={14} />
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}

              <label
                aria-label={
                  canEdit
                    ? t('pms.taskDetail.clickOrDragToUpload')
                    : t('pms.taskDetail.attachmentsReadOnly')
                }
                onDragOver={
                  canEdit
                    ? (e) => {
                        e.preventDefault();
                        setDragOver(true);
                      }
                    : undefined
                }
                onDragLeave={canEdit ? () => setDragOver(false) : undefined}
                onDrop={
                  canEdit
                    ? (e) => {
                        e.preventDefault();
                        if (e.dataTransfer.files.length) {
                          void handleFileUpload(e.dataTransfer.files);
                        }
                      }
                    : undefined
                }
                className={`app-text-body rounded-lg border-2 border-dashed py-4 text-center transition-colors ${
                  canEdit
                    ? dragOver
                      ? 'cursor-pointer border-app-accent bg-app-accent/5 text-app-accent'
                      : 'cursor-pointer border-app-border text-app-ink/40 hover:border-app-ink/30'
                    : 'cursor-default border-app-border text-app-ink/30'
                }`}
              >
                {uploading ? (
                  <Loader2
                    size={16}
                    className="animate-spin mx-auto text-app-accent"
                  />
                ) : (
                  <span>
                    {canEdit
                      ? dragOver
                        ? t('pms.taskDetail.dropToUpload')
                        : t('pms.taskDetail.clickOrDragToUpload')
                      : t('pms.taskDetail.attachmentsReadOnly')}
                  </span>
                )}
                <input
                  aria-label={t('pms.taskDetail.attachments')}
                  type="file"
                  multiple
                  className="hidden"
                  disabled={!canEdit}
                  onChange={(e) => {
                    if (e.target.files?.length) {
                      void handleFileUpload(e.target.files);
                      e.target.value = '';
                    }
                  }}
                />
              </label>
            </div>
          </div>
        </div>

        <TaskDetailActivityPanel
          activityLogs={activityLogs}
          canEdit={canEdit}
          commentDraft={commentDraft}
          comments={comments}
          isVisible={mobilePanel === 'activity'}
          loading={loading}
          mentionCandidates={mentionCandidates}
          mentionOpen={mentionOpen}
          members={members}
          onCloseMention={closeMention}
          onCommentDraftChange={handleCommentDraftChange}
          onCommentSubmit={handleCommentSubmit}
          onMentionPick={handleMentionPick}
          resolveFileUrl={resolveFileUrl}
        />
      </div>
      <TaskDocPickerModal
        isOpen={docPickerOpen}
        onClose={() => setDocPickerOpen(false)}
        onPick={(doc) => handleLinkDoc(doc.id)}
        excludeDocIds={linkedDocs.map((doc) => doc.doc_id)}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}
