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
import { useAuth } from '@/src/domains/auth/auth-provider';
import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import { linkMedia, extractMediaIds } from '@/src/domains/media/media-api';
import {
  getIssueDetail,
  updateIssue,
  deleteIssue,
  createIssueComment,
  createProjectIssue,
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
  listProjectIssues,
  type PmsIssue,
  type PmsComment,
  type PmsActivityLog,
  type PmsAttachment,
  type PmsChecklistItem,
  type PmsTimeEntry,
  type PmsDependency,
  type PmsProjectMember,
  type PmsMilestone,
  type PmsLabel,
  type PmsProjectStatus,
} from '@/src/domains/pms/pms-api';
import { toLocalDateInputValue } from '@/src/domains/pms/pms-filters';
import { getStatusSlugs, getStatusTone, getStatusLabel, initials, formatDate } from './pms-constants';

const PRIORITIES = ['low', 'medium', 'high', 'critical'] as const;
const PRIORITY_LABELS: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' };

const selectClass = 'app-text-body bg-transparent text-clickup-text border border-clickup-border rounded-md px-2 py-1 focus:outline-none focus:border-clickup-purple cursor-pointer hover:border-clickup-text/30 transition-colors';
const disabledFieldClass = `${selectClass} disabled:cursor-not-allowed disabled:opacity-60`;

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export const TaskDetail = ({
  issue,
  members = [],
  milestones = [],
  projectLabels = [],
  projectStatuses,
  spaceName,
  canEdit = true,
  onClose,
  onUpdate,
}: {
  issue: PmsIssue;
  members?: PmsProjectMember[];
  milestones?: PmsMilestone[];
  projectLabels?: PmsLabel[];
  projectStatuses?: PmsProjectStatus[];
  spaceName?: string | null;
  canEdit?: boolean;
  onClose: () => void;
  onUpdate?: () => void | Promise<void>;
}) => {
  const { token } = useAuth();
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
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectedLabelIds = issueState.labels.map((label) => label.id);

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
        '이슈 변경사항을 저장하지 못했습니다.',
      );
    },
    [persistIssueUpdate],
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
            setSaveError(getErrorMessage(error, '설명을 저장하지 못했습니다.'));
          });
      }, 500);
    },
    [canEdit, issueState.id, onUpdate, token],
  );

  const handleUnlinkSubtask = useCallback(async (subtaskId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await updateIssue(token, subtaskId, { parent_id: null });
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '서브태스크 연결을 해제하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

  const handleArchiveSubtask = useCallback(async (subtaskId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await updateIssue(token, subtaskId, { archived: true });
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      setSubtaskMenuOpen(null);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '서브태스크를 보관하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

  const handleDeleteSubtask = useCallback(async (subtaskId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await deleteIssue(token, subtaskId);
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      setSubtaskMenuOpen(null);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '서브태스크를 삭제하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

  const handleToggleIssueArchive = useCallback(() => {
    if (!canEdit) return;
    const nextArchived = !issueState.archived;
    void persistIssueUpdate(
      { archived: nextArchived },
      (current) => ({ ...current, archived: nextArchived }),
      nextArchived ? '이슈를 보관하지 못했습니다.' : '이슈를 복구하지 못했습니다.',
    );
  }, [canEdit, issueState.archived, persistIssueUpdate]);

  const handleAddSubtask = useCallback(async () => {
    if (!token || !canEdit || !newSubtaskTitle.trim()) return;
    setAddingSubtask(true);
    setSaveError(null);
    try {
      const sub = await createProjectIssue(token, issue.project_id, {
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
      setSaveError(getErrorMessage(error, '서브태스크를 생성하지 못했습니다.'));
    } finally {
      setAddingSubtask(false);
    }
  }, [canEdit, token, issue.id, issue.project_id, newSubtaskTitle, onUpdate]);

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
      setSaveError(getErrorMessage(error, '체크리스트 항목을 추가하지 못했습니다.'));
    } finally {
      setAddingChecklist(false);
    }
  }, [canEdit, token, issue.id, newChecklistText, checklistItems.length, onUpdate]);

  const handleToggleChecklistItem = useCallback(async (item: PmsChecklistItem) => {
    if (!token || !canEdit) return;
    const newCompleted = !item.completed;
    setChecklistItems(prev => prev.map(ci => ci.id === item.id ? { ...ci, completed: newCompleted } : ci));
    try {
      await updateChecklistItem(token, item.id, { completed: newCompleted });
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setChecklistItems(prev => prev.map(ci => ci.id === item.id ? { ...ci, completed: !newCompleted } : ci));
      setSaveError(getErrorMessage(error, '체크리스트 항목을 변경하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

  const handleSaveChecklistEdit = useCallback(async (itemId: string) => {
    if (!token || !canEdit || !editingChecklistText.trim()) return;
    try {
      await updateChecklistItem(token, itemId, { text: editingChecklistText.trim() });
      setChecklistItems(prev => prev.map(ci => ci.id === itemId ? { ...ci, text: editingChecklistText.trim() } : ci));
      setEditingChecklistId(null);
    } catch (error) {
      setSaveError(getErrorMessage(error, '체크리스트 항목을 수정하지 못했습니다.'));
    }
  }, [canEdit, token, editingChecklistText]);

  const handleDeleteChecklistItem = useCallback(async (itemId: string) => {
    if (!token || !canEdit) return;
    try {
      await deleteChecklistItem(token, itemId);
      setChecklistItems(prev => prev.filter(ci => ci.id !== itemId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '체크리스트 항목을 삭제하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

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
      setSaveError(getErrorMessage(error, '시간을 기록하지 못했습니다.'));
    } finally {
      setLoggingTime(false);
    }
  }, [canEdit, token, issue.id, timeLogMinutes, timeLogDesc, onUpdate]);

  const handleDeleteTimeEntry = useCallback(async (entryId: string) => {
    if (!token || !canEdit) return;
    try {
      await deleteTimeEntry(token, entryId);
      setTimeEntries(prev => prev.filter(te => te.id !== entryId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '시간 기록을 삭제하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

  // ── Dependency handlers ──────────────────────────────────────────
  const handleDepSearch = useCallback(async (query: string) => {
    setDepSearchQuery(query);
    if (!token || !canEdit || !query.trim()) { setDepSearchResults([]); return; }
    setDepSearching(true);
    try {
      const res = await listProjectIssues(token, issue.project_id, { q: query.trim() });
      setDepSearchResults(res.items.filter(i => i.id !== issue.id));
    } catch { setDepSearchResults([]); }
    finally { setDepSearching(false); }
  }, [canEdit, token, issue.id, issue.project_id]);

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
      setSaveError(getErrorMessage(error, '의존성을 추가하지 못했습니다.'));
    } finally { setAddingDep(false); }
  }, [canEdit, token, issue.id, onUpdate]);

  const handleToggleLabel = useCallback((labelId: string) => {
    if (!canEdit) return;
    const nextLabelIds = selectedLabelIds.includes(labelId)
      ? selectedLabelIds.filter(id => id !== labelId)
      : [...selectedLabelIds, labelId];
    const nextLabels = projectLabels.filter((label) => nextLabelIds.includes(label.id));
    void persistIssueUpdate(
      { label_ids: nextLabelIds },
      (current) => ({ ...current, labels: nextLabels }),
      '라벨을 저장하지 못했습니다.',
    );
  }, [canEdit, persistIssueUpdate, projectLabels, selectedLabelIds]);

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
        setSaveError(getErrorMessage(error, '댓글을 등록하지 못했습니다.'));
      });
  }, [canEdit, token, issue.id, commentDraft, onUpdate]);

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
      setSaveError(getErrorMessage(error, '파일을 업로드하지 못했습니다.'));
    } finally {
      setUploading(false);
      setDragOver(false);
    }
  }, [canEdit, token, issue.id, onUpdate]);

  const handleDeleteAttachment = useCallback(async (attachmentId: string) => {
    if (!token || !canEdit) return;
    setSaveError(null);
    try {
      await deleteAttachment(token, attachmentId);
      setAttachments(prev => prev.filter(a => a.id !== attachmentId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '첨부파일을 삭제하지 못했습니다.'));
    }
  }, [canEdit, token, onUpdate]);

  // Description fullscreen mode
  if (descFullscreen) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-6 py-3 border-b border-clickup-border shrink-0">
          <button
            onClick={() => setDescFullscreen(false)}
            className="app-text-body flex items-center gap-2 text-clickup-text/60 transition-colors hover:text-clickup-text"
          >
            ← Back to task
          </button>
          <span className="app-text-control text-clickup-text">{issueState.title}</span>
          <Button variant="ghost" size="icon" onClick={() => setDescFullscreen(false)}><Minimize2 size={16} /></Button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-6 max-w-4xl mx-auto w-full">
          <h1 className="app-text-title-lg mb-6 text-clickup-text">{issueState.title}</h1>
          {canEdit ? (
            <BlockEditor
              initialContent={issueState.description_blocks as BlockContent | undefined}
              onChange={handleDescriptionChange}
              placeholder="Start writing..."
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
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-clickup-border shrink-0">
        <div className="app-text-caption flex items-center gap-2 text-clickup-text/50">
          <span>{spaceName || 'Space'}</span>
          <ChevronRight size={12} />
          <span className="text-clickup-text/70">{issueState.reference}</span>
        </div>
        <div className="flex items-center gap-1">
          {!canEdit ? (
            <span className="app-text-overline rounded-full border border-clickup-border px-2 py-1 text-clickup-text/50">
              Read only
            </span>
          ) : (
            <button
              type="button"
              onClick={handleToggleIssueArchive}
              className="app-text-control-sm rounded-md border border-clickup-border px-2.5 py-1 text-clickup-text/60 transition-colors hover:border-clickup-text/30 hover:text-clickup-text"
            >
              {issueState.archived ? 'Restore' : 'Archive'}
            </button>
          )}
          <Button variant="ghost" size="icon"><Share2 size={16} /></Button>
          <Button variant="ghost" size="icon"><MoreHorizontal size={16} /></Button>
          <Button variant="ghost" size="icon" onClick={onClose}><X size={16} /></Button>
        </div>
      </div>

      {/* Two-column layout: left content + right activity */}
      <div className="flex-1 flex min-h-0">
        {/* Left: main content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar border-r border-clickup-border">
          <div className="px-8 py-6 max-w-3xl mx-auto space-y-6">
            {/* Title */}
            <div className="flex items-center gap-2">
              <h1 className="app-text-title-lg text-clickup-text">{issueState.title}</h1>
              {issueState.archived && (
                <span className="app-text-overline rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-300">
                  Archived
                </span>
              )}
            </div>

            {saveError ? <InlineSaveError message={saveError} /> : null}

            {/* Meta fields — 2-column grid like ClickUp */}
            <div className="grid grid-cols-[auto_1fr_auto_1fr] items-center gap-x-6 gap-y-3">
              <MetaLabel>Status</MetaLabel>
              <select value={issueState.status} onChange={e => patchField('status', e.target.value)} className={disabledFieldClass} disabled={!canEdit}>
                {getStatusSlugs(projectStatuses).map(s => <option key={s} value={s}>{getStatusLabel(s, projectStatuses)}</option>)}
              </select>
              <MetaLabel>Assignee</MetaLabel>
              <select value={issueState.assignee_id ?? ''} onChange={e => patchField('assignee_id', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit}>
                <option value="">Unassigned</option>
                {members.map(m => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
              </select>

              <MetaLabel>Start</MetaLabel>
              <input type="date" value={issueState.start_date ?? ''} onChange={e => patchField('start_date', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit} />
              <MetaLabel>Due</MetaLabel>
              <input type="date" value={issueState.due_date ?? ''} onChange={e => patchField('due_date', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit} />

              <MetaLabel>Priority</MetaLabel>
              <select value={issueState.priority} onChange={e => patchField('priority', e.target.value)} className={disabledFieldClass} disabled={!canEdit}>
                {PRIORITIES.map(p => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
              </select>
              <MetaLabel>Milestone</MetaLabel>
              <select value={issueState.milestone_id ?? ''} onChange={e => patchField('milestone_id', e.target.value || null)} className={disabledFieldClass} disabled={!canEdit}>
                <option value="">None</option>
                {milestones.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
              </select>

              <MetaLabel>Repeat</MetaLabel>
              <select
                value={issueState.recurrence_rule ?? ''}
                onChange={e => patchField('recurrence_rule', e.target.value || null)}
                className={disabledFieldClass}
                disabled={!canEdit}
              >
                <option value="">None</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="biweekly">Biweekly</option>
                <option value="monthly">Monthly</option>
              </select>
              <MetaLabel>Labels</MetaLabel>
              <div className="col-span-3 relative">
                <button
                  type="button"
                  onClick={() => {
                    if (!canEdit) return;
                    setLabelPickerOpen(prev => !prev);
                  }}
                  className={`flex min-h-[28px] w-full flex-wrap items-center gap-1 rounded px-1 py-0.5 text-left transition-colors ${
                    canEdit ? 'hover:bg-clickup-hover/50' : 'cursor-default'
                  }`}
                  disabled={!canEdit}
                >
                  {selectedLabelIds.length > 0 ? (
                    selectedLabelIds.map(id => {
                      const label = projectLabels.find(l => l.id === id);
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
                    <span className="app-text-body flex items-center gap-1 text-clickup-text/40">
                      <Tag size={12} />
                      {canEdit ? 'Add labels...' : 'No labels'}
                    </span>
                  )}
                </button>
                {labelPickerOpen && canEdit && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setLabelPickerOpen(false)} />
                    <div className="absolute left-0 top-8 z-20 w-48 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1">
                      {projectLabels.length === 0 ? (
                        <p className="app-text-caption px-3 py-2 text-clickup-text/40">No labels in this project</p>
                      ) : (
                        projectLabels.map(label => (
                          <button
                            key={label.id}
                            onClick={() => handleToggleLabel(label.id)}
                            className="app-text-body flex w-full items-center gap-2 px-3 py-1.5 text-clickup-text transition-colors hover:bg-clickup-hover"
                          >
                            <span
                              className="w-3 h-3 rounded-full shrink-0"
                              style={{ backgroundColor: label.color }}
                            />
                            <span className="flex-1 text-left">{label.name}</span>
                            {selectedLabelIds.includes(label.id) && <Check size={12} className="text-clickup-purple" />}
                          </button>
                        ))
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Description with fullscreen button */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="app-text-title-md text-clickup-text">Description</h3>
                <Button variant="ghost" size="icon" onClick={() => setDescFullscreen(true)} title="Full screen">
                  <Maximize2 size={14} />
                </Button>
              </div>
              <div className="rounded-lg border border-clickup-border overflow-hidden">
                {canEdit ? (
                  <BlockEditor
                    initialContent={issueState.description_blocks as BlockContent | undefined}
                    onChange={handleDescriptionChange}
                    placeholder="Add a description..."
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

            <hr className="border-clickup-border" />

            {/* Checklist */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <CheckSquare size={14} className="text-clickup-text/50" />
                <h3 className="app-text-title-md text-clickup-text">
                  Checklist
                  {checklistTotal > 0 && (
                    <span className="text-clickup-text/40 font-normal ml-1">
                      ({checklistDone}/{checklistTotal})
                    </span>
                  )}
                </h3>
              </div>

              {checklistTotal > 0 && (
                <>
                  <div className="w-full h-1.5 bg-clickup-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                      style={{ width: `${checklistTotal > 0 ? (checklistDone / checklistTotal) * 100 : 0}%` }}
                    />
                  </div>
                  <div className="border border-clickup-border rounded-lg">
                    {checklistItems.map(ci => (
                      <div
                        key={ci.id}
                        className="flex items-center gap-3 px-3 py-2 border-b border-clickup-border last:border-b-0 hover:bg-clickup-hover/50 transition-colors group first:rounded-t-lg last:rounded-b-lg"
                      >
                        <input
                          type="checkbox"
                          checked={ci.completed}
                          onChange={() => handleToggleChecklistItem(ci)}
                          disabled={!canEdit}
                          className="h-3.5 w-3.5 rounded border-clickup-border accent-clickup-purple cursor-pointer shrink-0"
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
                            className="app-text-body flex-1 border-b border-clickup-purple bg-transparent py-0.5 text-clickup-text focus:outline-none"
                          />
                        ) : (
                          <span
                            className={`app-text-body flex-1 ${canEdit ? 'cursor-pointer' : 'cursor-default'} ${ci.completed ? 'line-through text-clickup-text/40' : 'text-clickup-text'}`}
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
                            className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-red-400 transition-all p-0.5 rounded"
                            title="Delete"
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
                  placeholder={canEdit ? '+ Add checklist item...' : 'Checklist is read-only'}
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-clickup-text placeholder:text-clickup-text/40 transition-colors focus:border-clickup-purple focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && newChecklistText.trim() && (
                  <Button variant="ghost" size="icon" onClick={handleAddChecklistItem} disabled={addingChecklist}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Subtasks */}
            <div className="space-y-2">
              <h3 className="app-text-title-md text-clickup-text">
                Subtasks {subtasks.length > 0 && <span className="text-clickup-text/40 font-normal">({subtasks.length})</span>}
              </h3>

              {subtasks.length > 0 && (
                <div className="border border-clickup-border rounded-lg">
                  {subtasks.map(sub => (
                    <div
                      key={sub.id}
                      className="flex items-center gap-3 px-3 py-2 border-b border-clickup-border last:border-b-0 hover:bg-clickup-hover/50 transition-colors group relative first:rounded-t-lg last:rounded-b-lg"
                    >
                      <input
                        type="checkbox"
                        checked={sub.status === 'done'}
                        readOnly
                        className="h-3.5 w-3.5 rounded border-clickup-border accent-clickup-purple cursor-pointer"
                      />
                      <span className="app-text-caption font-mono text-clickup-text/40">{sub.reference}</span>
                      <span className={`app-text-body flex-1 ${sub.status === 'done' ? 'line-through text-clickup-text/40' : 'text-clickup-text'}`}>
                        {sub.title}
                      </span>
                      <Badge tone={getStatusTone(sub.status, projectStatuses)}>{sub.status_label}</Badge>
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
                            className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-clickup-text transition-all p-0.5 rounded"
                            title="More options"
                          >
                            <MoreHorizontal size={14} />
                          </button>
                          {subtaskMenuOpen === sub.id && (
                            <>
                              <div className="fixed inset-0 z-10" onClick={() => setSubtaskMenuOpen(null)} />
                              <div className="app-text-body absolute right-0 top-full z-20 w-36 rounded-lg border border-clickup-border bg-clickup-bg py-1 shadow-xl">
                                <button
                                  onClick={(e) => { e.stopPropagation(); void handleUnlinkSubtask(sub.id); setSubtaskMenuOpen(null); }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-clickup-text/70 hover:bg-clickup-hover hover:text-clickup-text transition-colors"
                                >
                                  <Unlink size={13} />
                                  Unlink
                                </button>
                                <button
                                  onClick={(e) => { e.stopPropagation(); void handleArchiveSubtask(sub.id); }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-clickup-text/70 hover:bg-clickup-hover hover:text-clickup-text transition-colors"
                                >
                                  <Archive size={13} />
                                  Archive
                                </button>
                                <hr className="border-clickup-border my-1" />
                                <button
                                  onClick={(e) => { e.stopPropagation(); void handleDeleteSubtask(sub.id); }}
                                  className="flex items-center gap-2 w-full px-3 py-1.5 text-red-400 hover:bg-clickup-hover hover:text-red-500 transition-colors"
                                >
                                  <Trash2 size={13} />
                                  Delete
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
                  placeholder={canEdit ? '+ Add subtask...' : 'Subtasks are read-only'}
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-clickup-text placeholder:text-clickup-text/40 transition-colors focus:border-clickup-purple focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && newSubtaskTitle.trim() && (
                  <Button variant="ghost" size="icon" onClick={handleAddSubtask} disabled={addingSubtask}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Dependencies */}
            <div className="space-y-2">
              <h3 className="app-text-title-md text-clickup-text flex items-center gap-2">
                <Unlink size={16} className="text-clickup-text/50" />
                Dependencies
                {dependencies.length > 0 && <span className="text-clickup-text/40 font-normal">({dependencies.length})</span>}
              </h3>
              {dependencies.length > 0 && (
                <div className="space-y-1">
                  {dependencies.map(dep => {
                    const isBlocking = dep.predecessor_id === issue.id;
                    const linkedId = isBlocking ? dep.successor_id : dep.predecessor_id;
                    return (
                      <div key={dep.id} className="app-text-body flex items-center gap-2 rounded-md px-2 py-1.5 group hover:bg-clickup-hover">
                        <span className="app-text-overline w-16 shrink-0 text-clickup-text/50">
                          {isBlocking ? 'Blocks' : 'Blocked by'}
                        </span>
                        <span className="app-text-caption flex-1 truncate font-mono text-clickup-text/60">{linkedId.slice(0, 8)}…</span>
                        {canEdit ? (
                          <button
                            onClick={async () => {
                              if (!token) return;
                              await deleteDependency(token, dep.id);
                              setDependencies(prev => prev.filter(d => d.id !== dep.id));
                              await Promise.resolve(onUpdate?.());
                            }}
                            className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-red-400 transition-all"
                            title="Remove dependency"
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
                  placeholder={canEdit ? '+ Add dependency (search issue)...' : 'Dependencies are read-only'}
                  className="app-text-body w-full border-b border-transparent bg-transparent py-1 text-clickup-text placeholder:text-clickup-text/40 transition-colors focus:border-clickup-purple focus:outline-none"
                  disabled={!canEdit}
                />
                {canEdit && depSearchResults.length > 0 && (
                  <div className="absolute left-0 top-full z-20 mt-1 w-full max-h-40 overflow-y-auto rounded-lg border border-clickup-border bg-clickup-bg shadow-xl py-1">
                    {depSearchResults.map(r => (
                      <button
                        key={r.id}
                        type="button"
                        disabled={addingDep || dependencies.some(d => d.predecessor_id === r.id || d.successor_id === r.id)}
                        onClick={() => handleAddDependency(r.id)}
                        className="app-text-body w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-clickup-hover disabled:opacity-40"
                      >
                        <span className="app-text-caption font-mono text-clickup-text/50">{r.reference}</span>
                        <span className="truncate">{r.title}</span>
                      </button>
                    ))}
                  </div>
                )}
                {depSearching && <Loader2 size={14} className="absolute right-1 top-1.5 animate-spin text-clickup-text/30" />}
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Attachments */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Paperclip size={14} className="text-clickup-text/50" />
                <h3 className="app-text-title-md text-clickup-text">Attachments</h3>
                <span className="app-text-caption text-clickup-text/40">{attachments.length}</span>
              </div>

              {attachments.length > 0 && (
                <div className="space-y-1">
                  {attachments.map(att => {
                    const isImage = att.content_type.startsWith('image/');
                    return (
                      <div key={att.id} className="flex items-center gap-3 py-1.5 px-2 rounded-md hover:bg-clickup-hover group transition-colors">
                        {isImage ? (
                          <img
                            src={att.download_url}
                            alt={att.filename}
                            className="w-8 h-8 rounded object-cover border border-clickup-border"
                          />
                        ) : (
                          <div className="w-8 h-8 rounded bg-clickup-sidebar border border-clickup-border flex items-center justify-center">
                            <FileIcon size={14} className="text-clickup-text/40" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="app-text-body truncate text-clickup-text">{att.filename}</p>
                          <p className="app-text-micro text-clickup-text/40">
                            {att.size_bytes < 1024 ? `${att.size_bytes} B` : att.size_bytes < 1048576 ? `${(att.size_bytes / 1024).toFixed(1)} KB` : `${(att.size_bytes / 1048576).toFixed(1)} MB`}
                            {' · '}{att.uploaded_by_name}
                          </p>
                        </div>
                        <a
                          href={att.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`${att.filename} 다운로드`}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-clickup-text transition-all"
                        >
                          <Download size={14} />
                        </a>
                        {canEdit ? (
                          <button
                            onClick={() => { void handleDeleteAttachment(att.id); }}
                            className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-red-400 transition-all"
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
                      ? 'cursor-pointer border-clickup-purple bg-clickup-purple/5 text-clickup-purple'
                      : 'cursor-pointer border-clickup-border text-clickup-text/40 hover:border-clickup-text/30'
                    : 'cursor-default border-clickup-border text-clickup-text/30'
                }`}
              >
                {uploading ? (
                  <Loader2 size={16} className="animate-spin mx-auto text-clickup-purple" />
                ) : (
                  <span>{canEdit ? (dragOver ? 'Drop to upload' : 'Click or drag files to upload') : 'Attachments are read-only'}</span>
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

            <hr className="border-clickup-border" />

            {/* Time Tracking */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Clock size={14} className="text-clickup-text/50" />
                <h3 className="app-text-title-md text-clickup-text">Time Tracking</h3>
              </div>

              {/* Estimate + Progress */}
              <div className="app-text-caption flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-clickup-text/50">Estimate:</span>
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
                    className="w-14 bg-transparent text-clickup-text border-b border-clickup-border focus:border-clickup-purple focus:outline-none text-center py-0.5"
                    disabled={!canEdit}
                  />
                  <span className="text-clickup-text/40">h</span>
                </div>
                <span className="text-clickup-text/30">|</span>
                <span className="text-clickup-text/60">
                  Spent: <span className="text-clickup-text font-medium">{formatDuration(totalTimeSpent)}</span>
                </span>
              </div>

              {issueState.estimate_hours && issueState.estimate_hours > 0 && (
                <div className="w-full h-1.5 bg-clickup-border rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${totalTimeSpent > issueState.estimate_hours * 60 ? 'bg-red-500' : 'bg-blue-500'}`}
                    style={{ width: `${Math.min((totalTimeSpent / (issueState.estimate_hours * 60)) * 100, 100)}%` }}
                  />
                </div>
              )}

              {/* Time entries list */}
              {timeEntries.length > 0 && (
                <div className="border border-clickup-border rounded-lg max-h-32 overflow-y-auto custom-scrollbar">
                  {timeEntries.map(te => (
                    <div key={te.id} className="app-text-caption flex items-center gap-2 border-b border-clickup-border px-3 py-1.5 group last:border-b-0 hover:bg-clickup-hover/50">
                      <span className="text-clickup-text font-medium">{formatDuration(te.duration_minutes)}</span>
                      <span className="text-clickup-text/40">{te.entry_date}</span>
                      <span className="text-clickup-text/50 flex-1 truncate">{te.description || te.user_name}</span>
                      {canEdit ? (
                        <button
                          onClick={() => { void handleDeleteTimeEntry(te.id); }}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-red-400 transition-all p-0.5"
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
                  placeholder={canEdit ? 'Hours...' : 'Time tracking is read-only'}
                  className="app-text-body w-20 border-b border-transparent bg-transparent py-1 text-clickup-text placeholder:text-clickup-text/40 transition-colors focus:border-clickup-purple focus:outline-none"
                  disabled={!canEdit}
                />
                <input
                  type="text"
                  value={timeLogDesc}
                  onChange={e => setTimeLogDesc(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && timeLogMinutes) { e.preventDefault(); handleLogTime(); } }}
                  placeholder={canEdit ? 'Description...' : 'Time tracking is read-only'}
                  className="app-text-body flex-1 border-b border-transparent bg-transparent py-1 text-clickup-text placeholder:text-clickup-text/40 transition-colors focus:border-clickup-purple focus:outline-none"
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
        <div className="w-[340px] shrink-0 flex flex-col bg-clickup-bg">
          <div className="px-4 py-3 border-b border-clickup-border">
            <h3 className="app-text-title-md text-clickup-text">Activity</h3>
          </div>

          {/* Activity list */}
          <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-3 space-y-3">
            {loading ? (
              <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-clickup-text/40" /></div>
            ) : (
              <>
                {activityLogs.map(log => (
                  <div key={log.id} className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-clickup-sidebar border border-clickup-border flex items-center justify-center text-[8px] font-bold text-clickup-text/60 shrink-0 mt-0.5">
                      {initials(log.actor_name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="app-text-caption text-clickup-text/60">{log.message}</p>
                      <span className="app-text-micro text-clickup-text/30">{formatDate(log.created_at)}</span>
                    </div>
                  </div>
                ))}

                {comments.map(comment => (
                  <div key={comment.id} className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-clickup-purple flex items-center justify-center text-[8px] font-bold text-white shrink-0 mt-0.5">
                      {initials(comment.author_name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="app-text-caption font-bold text-clickup-text">{comment.author_name}</span>
                      {comment.body_blocks ? (
                        <BlockViewer content={comment.body_blocks as BlockContent} className="app-text-caption mt-0.5" resolveFileUrl={resolveFileUrl} />
                      ) : (
                        <p className="app-text-caption mt-0.5 text-clickup-text/60">{comment.body}</p>
                      )}
                      <span className="app-text-micro text-clickup-text/30">{formatDate(comment.created_at)}</span>
                    </div>
                  </div>
                ))}

                {activityLogs.length === 0 && comments.length === 0 && (
                  <p className="app-text-body py-8 text-center text-clickup-text/30">No activity yet</p>
                )}
              </>
            )}
          </div>

          {/* Comment input — sticky bottom */}
          <div className="relative flex items-center gap-2 px-4 py-3 border-t border-clickup-border shrink-0">
            <div className="w-6 h-6 rounded-full bg-clickup-purple flex items-center justify-center text-[8px] font-bold text-white shrink-0">
              ME
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
                placeholder={canEdit ? 'Write a comment... (type @ to mention)' : 'Comments are read-only'}
                className="app-text-body w-full rounded-lg border border-clickup-border bg-transparent px-3 py-1.5 text-clickup-text placeholder:text-clickup-text/40 transition-colors focus:border-clickup-purple focus:outline-none"
                disabled={!canEdit}
              />
              {mentionOpen && canEdit && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMentionOpen(false)} />
                  <div className="absolute bottom-full left-0 mb-1 z-20 w-56 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1 max-h-40 overflow-y-auto">
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
                          className="app-text-body flex w-full items-center gap-2 px-3 py-1.5 text-left text-clickup-text transition-colors hover:bg-clickup-hover"
                        >
                          <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[8px] font-bold text-white">
                            {initials(m.full_name)}
                          </div>
                          {m.full_name}
                        </button>
                      ))}
                    {members.filter(m => !mentionQuery || m.full_name.toLowerCase().includes(mentionQuery)).length === 0 && (
                      <p className="app-text-caption px-3 py-2 text-clickup-text/40">No matches</p>
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
    <span className="app-text-overline whitespace-nowrap text-clickup-text/50">{children}</span>
  );
}

function InlineSaveError({ message }: { message: string }) {
  return (
    <div className="app-text-body rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-red-300">
      {message}
    </div>
  );
}
