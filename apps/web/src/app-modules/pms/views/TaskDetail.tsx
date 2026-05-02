import { useState, useEffect, useCallback, useRef } from 'react';
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
  Clock,
  Unlink,
  Paperclip,
  Download,
  FileIcon,
} from 'lucide-react';
import { Badge, Button, BlockEditor, BlockViewer } from '@aidoo/ui';
import type { BlockContent } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { linkMedia, extractMediaIds } from '@/src/platform/media/media-api';
import {
  getIssueDetail,
  updateIssue,
  deleteIssue,
  createIssueComment,
  createTaskListIssue,
  listIssueActivityLogs,
  uploadAttachment,
  deleteAttachment,
  createChecklistItem,
  updateChecklistItem,
  deleteChecklistItem,
  createTimeEntry,
  deleteTimeEntry,
  createDependency,
  deleteDependency,
  listTaskListIssues,
  type PmsIssue,
  type PmsComment,
  type PmsActivityLog,
  type PmsAttachment,
  type PmsChecklistItem,
  type PmsTimeEntry,
  type PmsDependency,
  type PmsTaskListMember,
  type PmsMilestone,
  type PmsLabel,
  type PmsTaskListStatus,
} from '../api/pms-api';
import { toLocalDateInputValue } from '../api/pms-filters';
import { getStatusSlugs, getStatusTone, getStatusLabel, initials, formatDate } from './pms-constants';

const PRIORITIES = ['low', 'medium', 'high', 'critical'] as const;
const PRIORITY_LABEL_KEYS: Record<string, string> = {
  critical: 'pms.priorityCritical',
  high: 'pms.priorityHigh',
  low: 'pms.priorityLow',
  medium: 'pms.priorityMedium',
};
const DEFAULT_STATUS_LABEL_KEYS: Record<string, string> = {
  backlog: 'pms.filter.status.backlog',
  canceled: 'pms.filter.status.canceled',
  done: 'pms.filter.status.done',
  in_progress: 'pms.filter.status.inProgress',
  todo: 'pms.filter.status.todo',
};
const RECURRENCE_OPTIONS = [
  { value: 'daily', labelKey: 'pms.taskDetail.recurrence.daily' },
  { value: 'weekly', labelKey: 'pms.taskDetail.recurrence.weekly' },
  { value: 'biweekly', labelKey: 'pms.taskDetail.recurrence.biweekly' },
  { value: 'monthly', labelKey: 'pms.taskDetail.recurrence.monthly' },
] as const;

const selectClass = 'app-text-body w-full min-w-0 bg-transparent text-app-ink border border-app-border rounded-md px-2 py-1 focus:outline-none focus:border-app-accent cursor-pointer hover:border-app-ink/30 transition-colors';
const disabledFieldClass = `${selectClass} disabled:cursor-not-allowed disabled:opacity-60`;

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export const TaskDetail = ({
  issue,
  members = [],
  milestones = [],
  taskListLabels = [],
  taskListStatuses,
  spaceName,
  canEdit = true,
  onClose,
  onUpdate,
}: {
  issue: PmsIssue;
  members?: PmsTaskListMember[];
  milestones?: PmsMilestone[];
  taskListLabels?: PmsLabel[];
  taskListStatuses?: PmsTaskListStatus[];
  spaceName?: string | null;
  canEdit?: boolean;
  onClose: () => void;
  onUpdate?: () => void | Promise<void>;
}) => {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const [issueState, setIssueState] = useState(issue);
  const [comments, setComments] = useState<PmsComment[]>([]);
  const [activityLogs, setActivityLogs] = useState<PmsActivityLog[]>([]);
  const [subtasks, setSubtasks] = useState<PmsIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState('');
  const [newSubtaskTitle, setNewSubtaskTitle] = useState('');
  const [addingSubtask, setAddingSubtask] = useState(false);
  const [checklistItems, setChecklistItems] = useState<PmsChecklistItem[]>([]);
  const [newChecklistText, setNewChecklistText] = useState('');
  const [addingChecklist, setAddingChecklist] = useState(false);
  const [editingChecklistId, setEditingChecklistId] = useState<string | null>(null);
  const [editingChecklistText, setEditingChecklistText] = useState('');
  const [timeEntries, setTimeEntries] = useState<PmsTimeEntry[]>([]);
  const [timeLogMinutes, setTimeLogMinutes] = useState('');
  const [timeLogDesc, setTimeLogDesc] = useState('');
  const [loggingTime, setLoggingTime] = useState(false);
  const [attachments, setAttachments] = useState<PmsAttachment[]>([]);
  const [dependencies, setDependencies] = useState<PmsDependency[]>([]);
  const [depSearchQuery, setDepSearchQuery] = useState('');
  const [depSearchResults, setDepSearchResults] = useState<PmsIssue[]>([]);
  const [depSearching, setDepSearching] = useState(false);
  const [addingDep, setAddingDep] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [descFullscreen, setDescFullscreen] = useState(false);
  const [subtaskMenuOpen, setSubtaskMenuOpen] = useState<string | null>(null);
  const [labelPickerOpen, setLabelPickerOpen] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mobilePanel, setMobilePanel] = useState<'details' | 'activity'>('details');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectedLabelIds = issueState.labels.map((label) => label.id);
  const statusLabel = useCallback(
    (slug: string) => {
      const configuredStatus = taskListStatuses?.find((status) => status.slug === slug);
      if (configuredStatus) return configuredStatus.name;
      const labelKey = DEFAULT_STATUS_LABEL_KEYS[slug];
      return labelKey ? t(labelKey) : getStatusLabel(slug, taskListStatuses);
    },
    [taskListStatuses, t],
  );

  useEffect(() => {
    if (canEdit) {
      return;
    }

    setLabelPickerOpen(false);
    setMentionOpen(false);
    setSubtaskMenuOpen(null);
    setDescFullscreen(false);
  }, [canEdit]);

  useEffect(() => {
    setIssueState(issue);
    setSaveError(null);
  }, [issue]);

  useEffect(() => () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([
      getIssueDetail(token, issue.id),
      listIssueActivityLogs(token, issue.id),
    ])
      .then(([detail, logs]) => {
        setComments(detail.comments);
        setActivityLogs(logs.items);
        setSubtasks((detail.subtasks ?? []).filter((subtask) => !subtask.archived));
        setAttachments(detail.attachments ?? []);
        setDependencies(detail.dependencies ?? []);
        setChecklistItems(detail.checklist_items ?? []);
        setTimeEntries(detail.time_entries ?? []);
      })
      .finally(() => setLoading(false));
  }, [token, issue.id]);

  const persistIssueUpdate = useCallback(
    async (
      payload: Record<string, unknown>,
      applyOptimistic: (current: PmsIssue) => PmsIssue,
      fallbackMessage: string,
    ) => {
      if (!token || !canEdit) return null;

      const previousIssue = issueState;
      setSaveError(null);
      setIssueState((current) => applyOptimistic(current));

      try {
        const updatedIssue = await updateIssue(token, issueState.id, payload);
        setIssueState(updatedIssue);
        await Promise.resolve(onUpdate?.());
        return updatedIssue;
      } catch (error) {
        setIssueState(previousIssue);
        setSaveError(getErrorMessage(error, fallbackMessage));
        return null;
      }
    },
    [canEdit, issueState, onUpdate, token],
  );

  const patchField = useCallback(
    (field: keyof PmsIssue | 'label_ids' | 'description_blocks' | 'parent_id' | 'archived', value: unknown) => {
      void persistIssueUpdate(
        { [field]: value },
        (current) => ({ ...current, [field]: value } as PmsIssue),
        t('pms.taskDetail.errors.saveIssueFailed'),
      );
    },
    [persistIssueUpdate, t],
  );

  const handleDescriptionChange = useCallback(
    (content: BlockContent) => {
      if (!token || !canEdit) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      setSaveError(null);
      saveTimerRef.current = setTimeout(() => {
        updateIssue(token, issueState.id, { description_blocks: content })
          .then(async (updatedIssue) => {
            setIssueState(updatedIssue);
            await Promise.resolve(onUpdate?.());
            const mediaIds = extractMediaIds(content);
            if (mediaIds.length > 0) {
              linkMedia(token, mediaIds, 'issue', issueState.id).catch(() => undefined);
            }
          })
          .catch((error) => {
            setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.saveDescriptionFailed')));
          });
      }, 500);
    },
    [canEdit, issueState.id, onUpdate, token, t],
  );

  const handleUnlinkSubtask = useCallback(async (subtaskId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await updateIssue(token, subtaskId, { parent_id: null });
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.unlinkSubtaskFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

  const handleArchiveSubtask = useCallback(async (subtaskId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await updateIssue(token, subtaskId, { archived: true });
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      setSubtaskMenuOpen(null);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.archiveSubtaskFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

  const handleDeleteSubtask = useCallback(async (subtaskId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await deleteIssue(token, subtaskId);
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      setSubtaskMenuOpen(null);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.deleteSubtaskFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

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

  const handleAddSubtask = useCallback(async () => {
    if (!token || !canEdit || !newSubtaskTitle.trim()) return;
    setAddingSubtask(true);
    setSaveError(null);
    try {
      const sub = await createTaskListIssue(token, issue.list_id, {
        title: newSubtaskTitle.trim(),
        description: '',
        status: 'todo',
        priority: 'medium',
        assignee_id: null,
        milestone_id: null,
        due_date: null,
        parent_id: issue.id,
      });
      setSubtasks(prev => [...prev, sub]);
      setNewSubtaskTitle('');
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.createSubtaskFailed')));
    } finally {
      setAddingSubtask(false);
    }
  }, [canEdit, token, issue.id, issue.list_id, newSubtaskTitle, onUpdate, t]);

  // ── Checklist handlers ──────────────────────────────────────────

  const handleAddChecklistItem = useCallback(async () => {
    if (!token || !canEdit || !newChecklistText.trim()) return;
    setAddingChecklist(true);
    setSaveError(null);
    try {
      const item = await createChecklistItem(token, issue.id, {
        text: newChecklistText.trim(),
        sort_order: checklistItems.length,
      });
      setChecklistItems(prev => [...prev, item]);
      setNewChecklistText('');
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.addChecklistFailed')));
    } finally {
      setAddingChecklist(false);
    }
  }, [canEdit, token, issue.id, newChecklistText, checklistItems.length, onUpdate, t]);

  const handleToggleChecklistItem = useCallback(async (item: PmsChecklistItem) => {
    if (!token || !canEdit) return;
    const newCompleted = !item.completed;
    setChecklistItems(prev => prev.map(ci => ci.id === item.id ? { ...ci, completed: newCompleted } : ci));
    try {
      await updateChecklistItem(token, item.id, { completed: newCompleted });
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setChecklistItems(prev => prev.map(ci => ci.id === item.id ? { ...ci, completed: !newCompleted } : ci));
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.updateChecklistFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

  const handleSaveChecklistEdit = useCallback(async (itemId: string) => {
    if (!token || !canEdit || !editingChecklistText.trim()) return;
    try {
      await updateChecklistItem(token, itemId, { text: editingChecklistText.trim() });
      setChecklistItems(prev => prev.map(ci => ci.id === itemId ? { ...ci, text: editingChecklistText.trim() } : ci));
      setEditingChecklistId(null);
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.editChecklistFailed')));
    }
  }, [canEdit, token, editingChecklistText, t]);

  const handleDeleteChecklistItem = useCallback(async (itemId: string) => {
    if (!token || !canEdit) return;
    try {
      await deleteChecklistItem(token, itemId);
      setChecklistItems(prev => prev.filter(ci => ci.id !== itemId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.deleteChecklistFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

  const checklistDone = checklistItems.filter(ci => ci.completed).length;
  const checklistTotal = checklistItems.length;

  // ── Time tracking helpers ───────────────────────────────────────

  const formatDuration = (minutes: number): string => {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (h === 0) return `${m}m`;
    if (m === 0) return `${h}h`;
    return `${h}h ${m}m`;
  };

  const totalTimeSpent = timeEntries.reduce((sum, te) => sum + te.duration_minutes, 0);

  const handleLogTime = useCallback(async () => {
    if (!token || !canEdit || !timeLogMinutes) return;
    const mins = Math.round(parseFloat(timeLogMinutes) * 60);
    if (isNaN(mins) || mins <= 0) return;
    setLoggingTime(true);
    setSaveError(null);
    try {
      const entry = await createTimeEntry(token, issue.id, {
        duration_minutes: mins,
        description: timeLogDesc.trim(),
        entry_date: toLocalDateInputValue(),
      });
      setTimeEntries(prev => [entry, ...prev]);
      setTimeLogMinutes('');
      setTimeLogDesc('');
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.logTimeFailed')));
    } finally {
      setLoggingTime(false);
    }
  }, [canEdit, token, issue.id, timeLogMinutes, timeLogDesc, onUpdate, t]);

  const handleDeleteTimeEntry = useCallback(async (entryId: string) => {
    if (!token || !canEdit) return;
    try {
      await deleteTimeEntry(token, entryId);
      setTimeEntries(prev => prev.filter(te => te.id !== entryId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.deleteTimeFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

  // ── Dependency handlers ──────────────────────────────────────────
  const handleDepSearch = useCallback(async (query: string) => {
    setDepSearchQuery(query);
    if (!token || !canEdit || !query.trim()) { setDepSearchResults([]); return; }
    setDepSearching(true);
    try {
      const res = await listTaskListIssues(token, issue.list_id, { q: query.trim() });
      setDepSearchResults(res.items.filter(i => i.id !== issue.id));
    } catch { setDepSearchResults([]); }
    finally { setDepSearching(false); }
  }, [canEdit, token, issue.id, issue.list_id]);

  const handleAddDependency = useCallback(async (targetId: string) => {
    if (!token || !canEdit) return;
    setAddingDep(true);
    try {
      const dep = await createDependency(token, { predecessor_id: targetId, successor_id: issue.id });
      setDependencies(prev => [...prev, dep]);
      setDepSearchQuery('');
      setDepSearchResults([]);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.addDependencyFailed')));
    } finally { setAddingDep(false); }
  }, [canEdit, token, issue.id, onUpdate, t]);

  const handleToggleLabel = useCallback((labelId: string) => {
    if (!canEdit) return;
    const nextLabelIds = selectedLabelIds.includes(labelId)
      ? selectedLabelIds.filter(id => id !== labelId)
      : [...selectedLabelIds, labelId];
    const nextLabels = taskListLabels.filter((label) => nextLabelIds.includes(label.id));
    void persistIssueUpdate(
      { label_ids: nextLabelIds },
      (current) => ({ ...current, labels: nextLabels }),
      t('pms.taskDetail.errors.saveLabelsFailed'),
    );
  }, [canEdit, persistIssueUpdate, taskListLabels, selectedLabelIds, t]);

  const handleCommentSubmit = useCallback(() => {
    if (!token || !canEdit || !commentDraft.trim()) return;
    setSaveError(null);
    createIssueComment(token, issue.id, commentDraft.trim())
      .then(async (newComment) => {
        setComments(prev => [...prev, newComment]);
        setCommentDraft('');
        await Promise.resolve(onUpdate?.());
      })
      .catch((error) => {
        setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.createCommentFailed')));
      });
  }, [canEdit, token, issue.id, commentDraft, onUpdate, t]);

  const handleFileUpload = useCallback(async (files: FileList | File[]) => {
    if (!token || !canEdit) return;
    setUploading(true);
    setSaveError(null);
    try {
      for (const file of Array.from(files)) {
        const att = await uploadAttachment(token, issue.id, file);
        setAttachments(prev => [...prev, att]);
      }
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.uploadFileFailed')));
    } finally {
      setUploading(false);
      setDragOver(false);
    }
  }, [canEdit, token, issue.id, onUpdate, t]);

  const handleDeleteAttachment = useCallback(async (attachmentId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await deleteAttachment(token, attachmentId);
      setAttachments(prev => prev.filter(a => a.id !== attachmentId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, t('pms.taskDetail.errors.deleteAttachmentFailed')));
    }
  }, [canEdit, token, onUpdate, t]);

  // Description fullscreen mode
  if (descFullscreen) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-6 py-3 border-b border-app-border shrink-0">
          <button
            onClick={() => setDescFullscreen(false)}
            className="app-text-body flex items-center gap-2 text-app-ink/60 transition-colors hover:text-app-ink"
          >
            {t('pms.taskDetail.backToTask')}
          </button>
          <span className="app-text-control text-app-ink">{issueState.title}</span>
          <Button variant="ghost" size="icon" onClick={() => setDescFullscreen(false)}><Minimize2 size={16} /></Button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-6 max-w-4xl mx-auto w-full">
          <h1 className="app-text-title-lg mb-6 text-app-ink">{issueState.title}</h1>
          {canEdit ? (
            <BlockEditor
              initialContent={issueState.description_blocks as BlockContent | undefined}
              onChange={handleDescriptionChange}
              placeholder={t('pms.taskDetail.startWritingPlaceholder')}
              className="[&_.bn-editor]:min-h-[400px] [&_.bn-editor]:px-1"
              uploadFile={uploadFile}
              resolveFileUrl={resolveFileUrl}
            />
          ) : (
            <BlockViewer
              content={(issueState.description_blocks as BlockContent | null) ?? []}
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
          <span className="truncate">{spaceName || t('pms.spaceOverview.fallbackSpaceName')}</span>
          <ChevronRight size={12} />
          <span className="shrink-0 text-app-ink/70">{issueState.reference}</span>
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
              {issueState.archived ? t('pms.bulk.restore') : t('common:actions.archive')}
            </button>
          )}
          <Button variant="ghost" size="icon" aria-label={t('pms.taskDetail.share')}><Share2 size={16} /></Button>
          <Button variant="ghost" size="icon" aria-label={t('pms.taskDetail.moreOptions')}><MoreHorizontal size={16} /></Button>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t('common:actions.close')}><X size={16} /></Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1 border-b border-app-border bg-app-bg px-4 py-2 lg:hidden">
        <button
          type="button"
          onClick={() => setMobilePanel('details')}
          className={`app-text-control-sm rounded-md px-3 py-2 transition-colors ${
            mobilePanel === 'details'
              ? 'bg-app-surface-hover text-app-ink'
              : 'text-app-ink/50 hover:text-app-ink'
          }`}
        >
          {t('pms.taskDetail.details')}
        </button>
        <button
          type="button"
          onClick={() => setMobilePanel('activity')}
          className={`app-text-control-sm rounded-md px-3 py-2 transition-colors ${
            mobilePanel === 'activity'
              ? 'bg-app-surface-hover text-app-ink'
              : 'text-app-ink/50 hover:text-app-ink'
          }`}
        >
          {t('pms.taskDetail.activity')}
        </button>
      </div>

      {/* Responsive layout: mobile tabs, desktop split view */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Left: main content */}
        <div
          data-testid="task-detail-details-panel"
          className={`${mobilePanel === 'details' ? 'flex' : 'hidden'} min-h-0 flex-1 flex-col overflow-y-auto custom-scrollbar lg:flex lg:border-r lg:border-app-border`}
        >
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-4 pb-[calc(1rem+env(safe-area-inset-bottom))] lg:px-8 lg:py-6">
            {/* Title */}
            <div className="flex min-w-0 flex-wrap items-start gap-2">
              <h1 data-testid="task-detail-title" className="app-text-title-lg min-w-0 flex-1 break-words text-app-ink">{issueState.title}</h1>
              {issueState.archived && (
                <span className="app-text-overline rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-300">
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
              <select value={issueState.status} onChange={e => patchField('status', e.target.value)} className={disabledFieldClass} disabled={!canEdit}>
                {getStatusSlugs(taskListStatuses).map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}
              </select>
              <MetaLabel>{t('pms.filter.assigneeLabel')}</MetaLabel>
              <select value={issueState.assignee_id ?? ''} onChange={e => patchField('assignee_id', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit}>
                <option value="">{t('pms.taskDetail.unassigned')}</option>
                {members.map(m => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
              </select>

              <MetaLabel>{t('planner.start')}</MetaLabel>
              <input type="date" value={issueState.start_date ?? ''} onChange={e => patchField('start_date', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit} />
              <MetaLabel>{t('pms.taskDetail.due')}</MetaLabel>
              <input type="date" value={issueState.due_date ?? ''} onChange={e => patchField('due_date', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit} />

              <MetaLabel>{t('pms.filter.priorityLabel')}</MetaLabel>
              <select value={issueState.priority} onChange={e => patchField('priority', e.target.value)} className={disabledFieldClass} disabled={!canEdit}>
                {PRIORITIES.map(p => <option key={p} value={p}>{t(PRIORITY_LABEL_KEYS[p])}</option>)}
              </select>
              <MetaLabel>{t('pms.filter.milestoneLabel')}</MetaLabel>
              <select value={issueState.milestone_id ?? ''} onChange={e => patchField('milestone_id', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit}>
                <option value="">{t('common:empty.none')}</option>
                {milestones.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
              </select>

              <MetaLabel>{t('pms.taskDetail.repeat')}</MetaLabel>
              <select
                value={issueState.recurrence_rule ?? ''}
                onChange={e => patchField('recurrence_rule', e.target.value || null)}
                className={disabledFieldClass}
                disabled={!canEdit}
              >
                <option value="">{t('common:empty.none')}</option>
                {RECURRENCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
                ))}
              </select>
              <MetaLabel>{t('pms.bulk.labelsLabel')}</MetaLabel>
              <div className="relative min-w-0 lg:col-span-3">
                <button
                  type="button"
                  onClick={() => {
                    if (!canEdit) return;
                    setLabelPickerOpen(prev => !prev);
                  }}
                  className={`flex min-h-[28px] w-full flex-wrap items-center gap-1 rounded px-1 py-0.5 text-left transition-colors ${
                    canEdit ? 'hover:bg-app-surface-hover/50' : 'cursor-default'
                  }`}
                  disabled={!canEdit}
                >
                  {selectedLabelIds.length > 0 ? (
                    selectedLabelIds.map(id => {
                      const label = taskListLabels.find(l => l.id === id);
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
                      {canEdit ? t('pms.taskDetail.addLabelsPlaceholder') : t('pms.taskDetail.noLabels')}
                    </span>
                  )}
                </button>
                {labelPickerOpen && canEdit && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setLabelPickerOpen(false)} />
                    <div className="absolute left-0 top-8 z-20 w-48 bg-app-bg border border-app-border rounded-lg shadow-xl py-1">
                      {taskListLabels.length === 0 ? (
                        <p className="app-text-caption px-3 py-2 text-app-ink/40">{t('pms.taskDetail.noLabelsInList')}</p>
                      ) : (
                        taskListLabels.map(label => (
                          <button
                            key={label.id}
                            onClick={() => handleToggleLabel(label.id)}
                            className="app-text-body flex w-full items-center gap-2 px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover"
                          >
                            <span
                              className="w-3 h-3 rounded-full shrink-0"
                              style={{ backgroundColor: label.color }}
                            />
                            <span className="flex-1 text-left">{label.name}</span>
                            {selectedLabelIds.includes(label.id) && <Check size={12} className="text-app-accent" />}
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
              <div className="flex items-center justify-between">
                <h3 className="app-text-title-md text-app-ink">{t('pms.description')}</h3>
                <Button variant="ghost" size="icon" onClick={() => setDescFullscreen(true)} title={t('pms.taskDetail.fullScreen')}>
                  <Maximize2 size={14} />
                </Button>
              </div>
              <div className="rounded-lg border border-app-border overflow-hidden">
                {canEdit ? (
                  <BlockEditor
                    initialContent={issueState.description_blocks as BlockContent | undefined}
                    onChange={handleDescriptionChange}
                    placeholder={t('pms.descriptionPlaceholder')}
                    className="[&_.bn-editor]:min-h-[120px] [&_.bn-editor]:px-3 [&_.bn-editor]:py-2"
                    uploadFile={uploadFile}
                    resolveFileUrl={resolveFileUrl}
                  />
                ) : (
                  <div className="px-3 py-2">
                    <BlockViewer
                      content={(issueState.description_blocks as BlockContent | null) ?? []}
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
                  <div className="w-full h-1.5 bg-app-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                      style={{ width: `${checklistTotal > 0 ? (checklistDone / checklistTotal) * 100 : 0}%` }}
                    />
                  </div>
                  <div className="border border-app-border rounded-lg">
                    {checklistItems.map(ci => (
                      <div
                        key={ci.id}
                        className="flex items-center gap-3 px-3 py-2 border-b border-app-border last:border-b-0 hover:bg-app-surface-hover/50 transition-colors group first:rounded-t-lg last:rounded-b-lg"
                      >
                        <input
                          type="checkbox"
                          checked={ci.completed}
                          onChange={() => handleToggleChecklistItem(ci)}
                          disabled={!canEdit}
                          className="h-3.5 w-3.5 rounded border-app-border accent-app-accent cursor-pointer shrink-0"
                        />
                        {editingChecklistId === ci.id ? (
                          <input
                            type="text"
                            value={editingChecklistText}
                            onChange={e => setEditingChecklistText(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); handleSaveChecklistEdit(ci.id); }
                              if (e.key === 'Escape') setEditingChecklistId(null);
                            }}
                            onBlur={() => { if (canEdit) { void handleSaveChecklistEdit(ci.id); } }}
                            autoFocus
                            className="app-text-body flex-1 border-b border-app-accent bg-transparent py-0.5 text-app-ink focus:outline-none"
                          />
                        ) : (
                          <span
                            className={`app-text-body flex-1 ${canEdit ? 'cursor-pointer' : 'cursor-default'} ${ci.completed ? 'line-through text-app-ink/40' : 'text-app-ink'}`}
                            onClick={() => {
                              if (!canEdit) return;
                              setEditingChecklistId(ci.id);
                              setEditingChecklistText(ci.text);
                            }}
                          >
                            {ci.text}
                          </span>
                        )}
                        {canEdit ? (
                          <button
                            onClick={() => { void handleDeleteChecklistItem(ci.id); }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-red-400 transition-all p-0.5 rounded"
                            title={t('common:actions.delete')}
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
                  type="text"
                  value={newChecklistText}
                  onChange={e => setNewChecklistText(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && newChecklistText.trim()) { e.preventDefault(); handleAddChecklistItem(); } }}
                  placeholder={canEdit ? t('pms.taskDetail.addChecklistPlaceholder') : t('pms.taskDetail.checklistReadOnly')}
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && newChecklistText.trim() && (
                  <Button variant="ghost" size="icon" onClick={handleAddChecklistItem} disabled={addingChecklist}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Subtasks */}
            <div className="space-y-2">
              <h3 className="app-text-title-md text-app-ink">
                {t('pms.taskDetail.subtasks')} {subtasks.length > 0 && <span className="text-app-ink/40 font-normal">({subtasks.length})</span>}
              </h3>

              {subtasks.length > 0 && (
                <div className="border border-app-border rounded-lg">
                  {subtasks.map(sub => (
                    <div
                      key={sub.id}
                      className="flex items-center gap-3 px-3 py-2 border-b border-app-border last:border-b-0 hover:bg-app-surface-hover/50 transition-colors group relative first:rounded-t-lg last:rounded-b-lg"
                    >
                      <input
                        type="checkbox"
                        checked={sub.status === 'done'}
                        readOnly
                        className="h-3.5 w-3.5 rounded border-app-border accent-app-accent cursor-pointer"
                      />
                      <span className="app-text-caption font-mono text-app-ink/40">{sub.reference}</span>
                      <span className={`app-text-body flex-1 ${sub.status === 'done' ? 'line-through text-app-ink/40' : 'text-app-ink'}`}>
                        {sub.title}
                      </span>
                      <Badge tone={getStatusTone(sub.status, taskListStatuses)}>{sub.status_label}</Badge>
                      {sub.assignee_name && (
                        <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[8px] font-bold text-white">
                          {initials(sub.assignee_name)}
                        </div>
                      )}
                      {/* ··· context menu */}
                      {canEdit ? (
                        <div className="relative">
                          <button
                            onClick={(e) => { e.stopPropagation(); setSubtaskMenuOpen(prev => prev === sub.id ? null : sub.id); }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-app-ink transition-all p-0.5 rounded"
                            title={t('pms.taskDetail.moreOptions')}
                          >
                            <MoreHorizontal size={14} />
                          </button>
                          {subtaskMenuOpen === sub.id && (
                            <>
                              <div className="fixed inset-0 z-10" onClick={() => setSubtaskMenuOpen(null)} />
                              <div className="app-text-body absolute right-0 top-full z-20 w-36 rounded-lg border border-app-border bg-app-bg py-1 shadow-xl">
                                <button
                                  onClick={(e) => { e.stopPropagation(); void handleUnlinkSubtask(sub.id); setSubtaskMenuOpen(null); }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink transition-colors"
                                >
                                  <Unlink size={13} />
                                  {t('pms.taskDetail.unlink')}
                                </button>
                                <button
                                  onClick={(e) => { e.stopPropagation(); void handleArchiveSubtask(sub.id); }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink transition-colors"
                                >
                                  <Archive size={13} />
                                  {t('common:actions.archive')}
                                </button>
                                <hr className="border-app-border my-1" />
                                <button
                                  onClick={(e) => { e.stopPropagation(); void handleDeleteSubtask(sub.id); }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-red-400 hover:bg-app-surface-hover hover:text-red-500 transition-colors"
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
                  type="text"
                  value={newSubtaskTitle}
                  onChange={e => setNewSubtaskTitle(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && newSubtaskTitle.trim()) { e.preventDefault(); handleAddSubtask(); } }}
                  placeholder={canEdit ? t('pms.taskDetail.addSubtaskPlaceholder') : t('pms.taskDetail.subtasksReadOnly')}
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && newSubtaskTitle.trim() && (
                  <Button variant="ghost" size="icon" onClick={handleAddSubtask} disabled={addingSubtask}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Dependencies */}
            <div className="space-y-2">
              <h3 className="app-text-title-md text-app-ink flex items-center gap-2">
                <Unlink size={16} className="text-app-ink/50" />
                {t('pms.taskDetail.dependencies')}
                {dependencies.length > 0 && <span className="text-app-ink/40 font-normal">({dependencies.length})</span>}
              </h3>
              {dependencies.length > 0 && (
                <div className="space-y-1">
                  {dependencies.map(dep => {
                    const isBlocking = dep.predecessor_id === issue.id;
                    const linkedId = isBlocking ? dep.successor_id : dep.predecessor_id;
                    return (
                      <div key={dep.id} className="app-text-body flex items-center gap-2 rounded-md px-2 py-1.5 group hover:bg-app-surface-hover">
                        <span className="app-text-overline w-16 shrink-0 text-app-ink/50">
                          {isBlocking ? t('pms.taskDetail.blocks') : t('pms.taskDetail.blockedBy')}
                        </span>
                        <span className="app-text-caption flex-1 truncate font-mono text-app-ink/60">{linkedId.slice(0, 8)}…</span>
                        {canEdit ? (
                          <button
                            onClick={async () => {
                              if (!token) return;
                              await deleteDependency(token, dep.id);
                              setDependencies(prev => prev.filter(d => d.id !== dep.id));
                              await Promise.resolve(onUpdate?.());
                            }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-red-400 transition-all"
                            title={t('pms.taskDetail.removeDependency')}
                          >
                            <X size={13} />
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="relative">
                <input
                  type="text"
                  value={depSearchQuery}
                  onChange={e => handleDepSearch(e.target.value)}
                  placeholder={canEdit ? t('pms.taskDetail.addDependencyPlaceholder') : t('pms.taskDetail.dependenciesReadOnly')}
                  className="app-text-body w-full border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && depSearchResults.length > 0 && (
                  <div className="absolute left-0 top-full z-20 mt-1 w-full max-h-40 overflow-y-auto rounded-lg border border-app-border bg-app-bg shadow-xl py-1">
                    {depSearchResults.map(r => (
                      <button
                        key={r.id}
                        type="button"
                        disabled={addingDep || dependencies.some(d => d.predecessor_id === r.id || d.successor_id === r.id)}
                        onClick={() => handleAddDependency(r.id)}
                        className="app-text-body w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-app-surface-hover disabled:opacity-40"
                      >
                        <span className="app-text-caption font-mono text-app-ink/50">{r.reference}</span>
                        <span className="truncate">{r.title}</span>
                      </button>
                    ))}
                  </div>
                )}
                {depSearching && <Loader2 size={14} className="absolute right-1 top-1.5 animate-spin text-app-ink/30" />}
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Attachments */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Paperclip size={14} className="text-app-ink/50" />
                <h3 className="app-text-title-md text-app-ink">{t('pms.taskDetail.attachments')}</h3>
                <span className="app-text-caption text-app-ink/40">{attachments.length}</span>
              </div>

              {attachments.length > 0 && (
                <div className="space-y-1">
                  {attachments.map(att => {
                    const isImage = att.content_type.startsWith('image/');
                    return (
                      <div key={att.id} className="flex items-center gap-3 py-1.5 px-2 rounded-md hover:bg-app-surface-hover group transition-colors">
                        {isImage ? (
                          <img
                            src={att.download_url}
                            alt={att.filename}
                            className="w-8 h-8 rounded object-cover border border-app-border"
                          />
                        ) : (
                          <div className="w-8 h-8 rounded bg-app-surface-sidebar border border-app-border flex items-center justify-center">
                            <FileIcon size={14} className="text-app-ink/40" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="app-text-body truncate text-app-ink">{att.filename}</p>
                          <p className="app-text-micro text-app-ink/40">
                            {att.size_bytes < 1024 ? `${att.size_bytes} B` : att.size_bytes < 1048576 ? `${(att.size_bytes / 1024).toFixed(1)} KB` : `${(att.size_bytes / 1048576).toFixed(1)} MB`}
                            {' · '}{att.uploaded_by_name}
                          </p>
                        </div>
                        <a
                          href={att.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={t('pms.taskDetail.downloadAttachment', { filename: att.filename })}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-ink transition-all"
                        >
                          <Download size={14} />
                        </a>
                        {canEdit ? (
                          <button
                            onClick={() => { void handleDeleteAttachment(att.id); }}
                            className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-red-400 transition-all"
                          >
                            <Trash2 size={14} />
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}

              <div
                onDragOver={canEdit ? (e) => { e.preventDefault(); setDragOver(true); } : undefined}
                onDragLeave={canEdit ? () => setDragOver(false) : undefined}
                onDrop={canEdit ? (e) => { e.preventDefault(); if (e.dataTransfer.files.length) { void handleFileUpload(e.dataTransfer.files); } } : undefined}
                onClick={canEdit ? () => fileInputRef.current?.click() : undefined}
                className={`app-text-body rounded-lg border-2 border-dashed py-4 text-center transition-colors ${
                  canEdit
                    ? dragOver
                      ? 'cursor-pointer border-app-accent bg-app-accent/5 text-app-accent'
                      : 'cursor-pointer border-app-border text-app-ink/40 hover:border-app-ink/30'
                    : 'cursor-default border-app-border text-app-ink/30'
                }`}
              >
                {uploading ? (
                  <Loader2 size={16} className="animate-spin mx-auto text-app-accent" />
                ) : (
                  <span>{canEdit ? (dragOver ? t('pms.taskDetail.dropToUpload') : t('pms.taskDetail.clickOrDragToUpload')) : t('pms.taskDetail.attachmentsReadOnly')}</span>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  disabled={!canEdit}
                  onChange={e => { if (e.target.files?.length) { void handleFileUpload(e.target.files); e.target.value = ''; } }}
                />
              </div>
            </div>

            <hr className="border-app-border" />

            {/* Time Tracking */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Clock size={14} className="text-app-ink/50" />
                <h3 className="app-text-title-md text-app-ink">{t('pms.taskDetail.timeTracking')}</h3>
              </div>

              {/* Estimate + Progress */}
              <div className="app-text-caption flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-app-ink/50">{t('pms.taskDetail.estimate')}</span>
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    value={issueState.estimate_hours ?? ''}
                    onChange={e => {
                      const v = e.target.value ? parseFloat(e.target.value) : null;
                      patchField('estimate_hours', v);
                    }}
                    placeholder="—"
                    className="w-14 bg-transparent text-app-ink border-b border-app-border focus:border-app-accent focus:outline-none text-center py-0.5"
                    disabled={!canEdit}
                  />
                  <span className="text-app-ink/40">{t('pms.taskDetail.hoursUnit')}</span>
                </div>
                <span className="text-app-ink/30">|</span>
                <span className="text-app-ink/60">
                  {t('pms.taskDetail.spent')}: <span className="text-app-ink font-medium">{formatDuration(totalTimeSpent)}</span>
                </span>
              </div>

              {issueState.estimate_hours && issueState.estimate_hours > 0 && (
                <div className="w-full h-1.5 bg-app-border rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${totalTimeSpent > issueState.estimate_hours * 60 ? 'bg-red-500' : 'bg-blue-500'}`}
                    style={{ width: `${Math.min((totalTimeSpent / (issueState.estimate_hours * 60)) * 100, 100)}%` }}
                  />
                </div>
              )}

              {/* Time entries list */}
              {timeEntries.length > 0 && (
                <div className="border border-app-border rounded-lg max-h-32 overflow-y-auto custom-scrollbar">
                  {timeEntries.map(te => (
                    <div key={te.id} className="app-text-caption flex items-center gap-2 border-b border-app-border px-3 py-1.5 group last:border-b-0 hover:bg-app-surface-hover/50">
                      <span className="text-app-ink font-medium">{formatDuration(te.duration_minutes)}</span>
                      <span className="text-app-ink/40">{te.entry_date}</span>
                      <span className="text-app-ink/50 flex-1 truncate">{te.description || te.user_name}</span>
                      {canEdit ? (
                        <button
                          onClick={() => { void handleDeleteTimeEntry(te.id); }}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-red-400 transition-all p-0.5"
                        >
                          <X size={11} />
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}

              {/* Log time input */}
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.25"
                  min="0"
                  value={timeLogMinutes}
                  onChange={e => setTimeLogMinutes(e.target.value)}
                  placeholder={canEdit ? t('pms.taskDetail.hoursPlaceholder') : t('pms.taskDetail.timeTrackingReadOnly')}
                  className="app-text-body w-20 border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                <input
                  type="text"
                  value={timeLogDesc}
                  onChange={e => setTimeLogDesc(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && timeLogMinutes) { e.preventDefault(); handleLogTime(); } }}
                  placeholder={canEdit ? t('pms.taskDetail.timeDescriptionPlaceholder') : t('pms.taskDetail.timeTrackingReadOnly')}
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && timeLogMinutes && (
                  <Button variant="ghost" size="icon" onClick={handleLogTime} disabled={loggingTime}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right: Activity sidebar */}
        <div
          data-testid="task-detail-activity-panel"
          className={`${mobilePanel === 'activity' ? 'flex' : 'hidden'} min-h-0 w-full flex-1 flex-col bg-app-bg lg:flex lg:w-[340px] lg:flex-none lg:shrink-0`}
        >
          <div className="px-4 py-3 border-b border-app-border">
            <h3 className="app-text-title-md text-app-ink">{t('pms.taskDetail.activity')}</h3>
          </div>

          {/* Activity list */}
          <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-3 space-y-3">
            {loading ? (
              <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-app-ink/40" /></div>
            ) : (
              <>
                {activityLogs.map(log => (
                  <div key={log.id} className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-app-surface-sidebar border border-app-border flex items-center justify-center text-[8px] font-bold text-app-ink/60 shrink-0 mt-0.5">
                      {initials(log.actor_name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="app-text-caption text-app-ink/60">{log.message}</p>
                      <span className="app-text-micro text-app-ink/30">{formatDate(log.created_at)}</span>
                    </div>
                  </div>
                ))}

                {comments.map(comment => (
                  <div key={comment.id} className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-app-accent flex items-center justify-center text-[8px] font-bold text-app-bg shrink-0 mt-0.5">
                      {initials(comment.author_name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="app-text-caption font-bold text-app-ink">{comment.author_name}</span>
                      {comment.body_blocks ? (
                        <BlockViewer content={comment.body_blocks as BlockContent} className="app-text-caption mt-0.5" resolveFileUrl={resolveFileUrl} />
                      ) : (
                        <p className="app-text-caption mt-0.5 text-app-ink/60">{comment.body}</p>
                      )}
                      <span className="app-text-micro text-app-ink/30">{formatDate(comment.created_at)}</span>
                    </div>
                  </div>
                ))}

                {activityLogs.length === 0 && comments.length === 0 && (
                  <p className="app-text-body py-8 text-center text-app-ink/30">{t('pms.taskDetail.noActivity')}</p>
                )}
              </>
            )}
          </div>

          {/* Comment input — sticky bottom */}
          <div className="relative flex items-center gap-2 border-t border-app-border px-4 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shrink-0 lg:pb-3">
            <div className="w-6 h-6 rounded-full bg-app-accent flex items-center justify-center text-[8px] font-bold text-app-bg shrink-0">
              {t('pms.taskDetail.me')}
            </div>
            <div className="flex-1 relative">
              <input
                type="text"
                value={commentDraft}
                onChange={e => {
                  if (!canEdit) return;
                  setCommentDraft(e.target.value);
                  // Show mention dropdown when @ is typed
                  const val = e.target.value;
                  const atIdx = val.lastIndexOf('@');
                  if (atIdx >= 0 && atIdx === val.length - 1) {
                    setMentionOpen(true);
                    setMentionQuery('');
                  } else if (atIdx >= 0 && !val.slice(atIdx + 1).includes(' ')) {
                    setMentionOpen(true);
                    setMentionQuery(val.slice(atIdx + 1).toLowerCase());
                  } else {
                    setMentionOpen(false);
                  }
                }}
                onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && !mentionOpen) { e.preventDefault(); handleCommentSubmit(); } if (e.key === 'Escape') setMentionOpen(false); }}
                placeholder={canEdit ? t('pms.taskDetail.commentPlaceholder') : t('pms.taskDetail.commentsReadOnly')}
                className="app-text-body w-full rounded-lg border border-app-border bg-transparent px-3 py-1.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                disabled={!canEdit}
              />
              {mentionOpen && canEdit && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMentionOpen(false)} />
                  <div className="absolute bottom-full left-0 mb-1 z-20 w-56 bg-app-bg border border-app-border rounded-lg shadow-xl py-1 max-h-40 overflow-y-auto">
                    {members
                      .filter(m => !mentionQuery || m.full_name.toLowerCase().includes(mentionQuery))
                      .map(m => (
                        <button
                          key={m.user_id}
                          onClick={() => {
                            const atIdx = commentDraft.lastIndexOf('@');
                            const before = commentDraft.slice(0, atIdx);
                            setCommentDraft(`${before}@${m.user_id} `);
                            setMentionOpen(false);
                          }}
                          className="app-text-body flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
                        >
                          <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[8px] font-bold text-white">
                            {initials(m.full_name)}
                          </div>
                          {m.full_name}
                        </button>
                      ))}
                    {members.filter(m => !mentionQuery || m.full_name.toLowerCase().includes(mentionQuery)).length === 0 && (
                      <p className="app-text-caption px-3 py-2 text-app-ink/40">{t('pms.taskDetail.noMatches')}</p>
                    )}
                  </div>
                </>
              )}
            </div>
            {canEdit ? (
              <Button variant="ghost" size="icon" className="shrink-0" onClick={handleCommentSubmit}>
                <Send size={14} />
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

function MetaLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="app-text-overline whitespace-nowrap text-app-ink/50">{children}</span>
  );
}

function InlineSaveError({ message }: { message: string }) {
  return (
    <div className="app-text-body rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-red-300">
      {message}
    </div>
  );
}
