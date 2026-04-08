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
  type PmsIssue,
  type PmsComment,
  type PmsActivityLog,
  type PmsAttachment,
  type PmsChecklistItem,
  type PmsTimeEntry,
  type PmsProjectMember,
  type PmsMilestone,
  type PmsLabel,
} from '@/src/domains/pms/pms-api';
import { toLocalDateInputValue } from '@/src/domains/pms/pms-filters';
import { ISSUE_STATUSES, STATUS_TONE, initials, formatDate } from './pms-constants';

const PRIORITIES = ['low', 'medium', 'high', 'critical'] as const;
const PRIORITY_LABELS: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' };
const STATUS_LABELS: Record<string, string> = { backlog: 'Backlog', todo: 'Todo', in_progress: 'In Progress', done: 'Done', canceled: 'Canceled' };

const selectClass = 'bg-transparent text-sm text-clickup-text border border-clickup-border rounded-md px-2 py-1 focus:outline-none focus:border-clickup-purple cursor-pointer hover:border-clickup-text/30 transition-colors';

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export const TaskDetail = ({
  issue,
  members = [],
  milestones = [],
  projectLabels = [],
  onClose,
  onUpdate,
}: {
  issue: PmsIssue;
  members?: PmsProjectMember[];
  milestones?: PmsMilestone[];
  projectLabels?: PmsLabel[];
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
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [descFullscreen, setDescFullscreen] = useState(false);
  const [subtaskMenuOpen, setSubtaskMenuOpen] = useState<string | null>(null);
  const [labelPickerOpen, setLabelPickerOpen] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectedLabelIds = issueState.labels.map((label) => label.id);

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
      if (!token) return null;

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
    [issueState, onUpdate, token],
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
      if (!token) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      setSaveError(null);
      saveTimerRef.current = setTimeout(() => {
        updateIssue(token, issueState.id, { description_blocks: content })
          .then(async (updatedIssue) => {
            setIssueState(updatedIssue);
            await Promise.resolve(onUpdate?.());
            const mediaIds = extractMediaIds(content);
            if (mediaIds.length > 0) {
              linkMedia(token, mediaIds, 'issue', issueState.id).catch(() => {});
            }
          })
          .catch((error) => {
            setSaveError(getErrorMessage(error, '설명을 저장하지 못했습니다.'));
          });
      }, 500);
    },
    [issueState.id, onUpdate, token],
  );

  const handleUnlinkSubtask = useCallback(async (subtaskId: string) => {
    if (!token) return;
    setSaveError(null);
    try {
      await updateIssue(token, subtaskId, { parent_id: null });
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '서브태스크 연결을 해제하지 못했습니다.'));
    }
  }, [token, onUpdate]);

  const handleArchiveSubtask = useCallback(async (subtaskId: string) => {
    if (!token) return;
    setSaveError(null);
    try {
      await updateIssue(token, subtaskId, { archived: true });
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      setSubtaskMenuOpen(null);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '서브태스크를 보관하지 못했습니다.'));
    }
  }, [token, onUpdate]);

  const handleDeleteSubtask = useCallback(async (subtaskId: string) => {
    if (!token) return;
    setSaveError(null);
    try {
      await deleteIssue(token, subtaskId);
      setSubtasks(prev => prev.filter(s => s.id !== subtaskId));
      setSubtaskMenuOpen(null);
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '서브태스크를 삭제하지 못했습니다.'));
    }
  }, [token, onUpdate]);

  const handleToggleIssueArchive = useCallback(() => {
    const nextArchived = !issueState.archived;
    void persistIssueUpdate(
      { archived: nextArchived },
      (current) => ({ ...current, archived: nextArchived }),
      nextArchived ? '이슈를 보관하지 못했습니다.' : '이슈를 복구하지 못했습니다.',
    );
  }, [issueState.archived, persistIssueUpdate]);

  const handleAddSubtask = useCallback(async () => {
    if (!token || !newSubtaskTitle.trim()) return;
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
  }, [token, issue.id, issue.project_id, newSubtaskTitle, onUpdate]);

  // ── Checklist handlers ──────────────────────────────────────────

  const handleAddChecklistItem = useCallback(async () => {
    if (!token || !newChecklistText.trim()) return;
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
  }, [token, issue.id, newChecklistText, checklistItems.length, onUpdate]);

  const handleToggleChecklistItem = useCallback(async (item: PmsChecklistItem) => {
    if (!token) return;
    const newCompleted = !item.completed;
    setChecklistItems(prev => prev.map(ci => ci.id === item.id ? { ...ci, completed: newCompleted } : ci));
    try {
      await updateChecklistItem(token, item.id, { completed: newCompleted });
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setChecklistItems(prev => prev.map(ci => ci.id === item.id ? { ...ci, completed: !newCompleted } : ci));
      setSaveError(getErrorMessage(error, '체크리스트 항목을 변경하지 못했습니다.'));
    }
  }, [token, onUpdate]);

  const handleSaveChecklistEdit = useCallback(async (itemId: string) => {
    if (!token || !editingChecklistText.trim()) return;
    try {
      await updateChecklistItem(token, itemId, { text: editingChecklistText.trim() });
      setChecklistItems(prev => prev.map(ci => ci.id === itemId ? { ...ci, text: editingChecklistText.trim() } : ci));
      setEditingChecklistId(null);
    } catch (error) {
      setSaveError(getErrorMessage(error, '체크리스트 항목을 수정하지 못했습니다.'));
    }
  }, [token, editingChecklistText]);

  const handleDeleteChecklistItem = useCallback(async (itemId: string) => {
    if (!token) return;
    try {
      await deleteChecklistItem(token, itemId);
      setChecklistItems(prev => prev.filter(ci => ci.id !== itemId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '체크리스트 항목을 삭제하지 못했습니다.'));
    }
  }, [token, onUpdate]);

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
    if (!token || !timeLogMinutes) return;
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
  }, [token, issue.id, timeLogMinutes, timeLogDesc, onUpdate]);

  const handleDeleteTimeEntry = useCallback(async (entryId: string) => {
    if (!token) return;
    try {
      await deleteTimeEntry(token, entryId);
      setTimeEntries(prev => prev.filter(te => te.id !== entryId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '시간 기록을 삭제하지 못했습니다.'));
    }
  }, [token, onUpdate]);

  const handleToggleLabel = useCallback((labelId: string) => {
    const nextLabelIds = selectedLabelIds.includes(labelId)
      ? selectedLabelIds.filter(id => id !== labelId)
      : [...selectedLabelIds, labelId];
    const nextLabels = projectLabels.filter((label) => nextLabelIds.includes(label.id));
    void persistIssueUpdate(
      { label_ids: nextLabelIds },
      (current) => ({ ...current, labels: nextLabels }),
      '라벨을 저장하지 못했습니다.',
    );
  }, [persistIssueUpdate, projectLabels, selectedLabelIds]);

  const handleCommentSubmit = useCallback(() => {
    if (!token || !commentDraft.trim()) return;
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
  }, [token, issue.id, commentDraft, onUpdate]);

  const handleFileUpload = useCallback(async (files: FileList | File[]) => {
    if (!token) return;
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
  }, [token, issue.id, onUpdate]);

  const handleDeleteAttachment = useCallback(async (attachmentId: string) => {
    if (!token) return;
    setSaveError(null);
    try {
      await deleteAttachment(token, attachmentId);
      setAttachments(prev => prev.filter(a => a.id !== attachmentId));
      await Promise.resolve(onUpdate?.());
    } catch (error) {
      setSaveError(getErrorMessage(error, '첨부파일을 삭제하지 못했습니다.'));
    }
  }, [token, onUpdate]);

  // Description fullscreen mode
  if (descFullscreen) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-6 py-3 border-b border-clickup-border shrink-0">
          <button
            onClick={() => setDescFullscreen(false)}
            className="flex items-center gap-2 text-sm text-clickup-text/60 hover:text-clickup-text transition-colors"
          >
            ← Back to task
          </button>
          <span className="text-sm font-medium text-clickup-text">{issueState.title}</span>
          <Button variant="ghost" size="icon" onClick={() => setDescFullscreen(false)}><Minimize2 size={16} /></Button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-6 max-w-4xl mx-auto w-full">
          <h1 className="text-2xl font-bold text-clickup-text mb-6">{issueState.title}</h1>
          <BlockEditor
            initialContent={issueState.description_blocks as BlockContent | undefined}
            onChange={handleDescriptionChange}
            placeholder="Start writing..."
            className="[&_.bn-editor]:min-h-[400px] [&_.bn-editor]:px-1"
            uploadFile={uploadFile}
            resolveFileUrl={resolveFileUrl}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-clickup-border shrink-0">
        <div className="flex items-center gap-2 text-xs text-clickup-text/50">
          <span>Team Space</span>
          <ChevronRight size={12} />
          <span className="text-clickup-text/70">{issueState.reference}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleToggleIssueArchive}
            className="rounded-md border border-clickup-border px-2.5 py-1 text-xs text-clickup-text/60 hover:border-clickup-text/30 hover:text-clickup-text transition-colors"
          >
            {issueState.archived ? 'Restore' : 'Archive'}
          </button>
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
              <h1 className="text-xl font-bold text-clickup-text">{issueState.title}</h1>
              {issueState.archived && (
                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-300">
                  Archived
                </span>
              )}
            </div>

            {saveError ? <InlineSaveError message={saveError} /> : null}

            {/* Meta fields — 2-column grid like ClickUp */}
            <div className="grid grid-cols-[auto_1fr_auto_1fr] items-center gap-x-6 gap-y-3">
              <MetaLabel>Status</MetaLabel>
              <select value={issueState.status} onChange={e => patchField('status', e.target.value)} className={selectClass}>
                {ISSUE_STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS[s] ?? s}</option>)}
              </select>
              <MetaLabel>Assignee</MetaLabel>
              <select value={issueState.assignee_id ?? ''} onChange={e => patchField('assignee_id', e.target.value || null)} className={selectClass}>
                <option value="">Unassigned</option>
                {members.map(m => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
              </select>

              <MetaLabel>Start</MetaLabel>
              <input type="date" value={issueState.start_date ?? ''} onChange={e => patchField('start_date', e.target.value || null)} className={selectClass} />
              <MetaLabel>Due</MetaLabel>
              <input type="date" value={issueState.due_date ?? ''} onChange={e => patchField('due_date', e.target.value || null)} className={selectClass} />

              <MetaLabel>Priority</MetaLabel>
              <select value={issueState.priority} onChange={e => patchField('priority', e.target.value)} className={selectClass}>
                {PRIORITIES.map(p => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
              </select>
              <MetaLabel>Milestone</MetaLabel>
              <select value={issueState.milestone_id ?? ''} onChange={e => patchField('milestone_id', e.target.value || null)} className={selectClass}>
                <option value="">None</option>
                {milestones.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
              </select>

              <MetaLabel>Labels</MetaLabel>
              <div className="col-span-3 relative">
                <button
                  onClick={() => setLabelPickerOpen(prev => !prev)}
                  className="flex flex-wrap gap-1 min-h-[28px] items-center hover:bg-clickup-hover/50 rounded px-1 py-0.5 transition-colors w-full text-left"
                >
                  {selectedLabelIds.length > 0 ? (
                    selectedLabelIds.map(id => {
                      const label = projectLabels.find(l => l.id === id);
                      return label ? (
                        <span
                          key={id}
                          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white"
                          style={{ backgroundColor: label.color }}
                        >
                          {label.name}
                        </span>
                      ) : null;
                    })
                  ) : (
                    <span className="flex items-center gap-1 text-sm text-clickup-text/40"><Tag size={12} /> Add labels...</span>
                  )}
                </button>
                {labelPickerOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setLabelPickerOpen(false)} />
                    <div className="absolute left-0 top-8 z-20 w-48 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1">
                      {projectLabels.length === 0 ? (
                        <p className="px-3 py-2 text-xs text-clickup-text/40">No labels in this project</p>
                      ) : (
                        projectLabels.map(label => (
                          <button
                            key={label.id}
                            onClick={() => handleToggleLabel(label.id)}
                            className="flex items-center gap-2 w-full px-3 py-1.5 text-sm text-clickup-text hover:bg-clickup-hover transition-colors"
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
                <h3 className="text-sm font-semibold text-clickup-text">Description</h3>
                <Button variant="ghost" size="icon" onClick={() => setDescFullscreen(true)} title="Full screen">
                  <Maximize2 size={14} />
                </Button>
              </div>
              <div className="rounded-lg border border-clickup-border overflow-hidden">
                <BlockEditor
                  initialContent={issueState.description_blocks as BlockContent | undefined}
                  onChange={handleDescriptionChange}
                  placeholder="Add a description..."
                  className="[&_.bn-editor]:min-h-[120px] [&_.bn-editor]:px-3 [&_.bn-editor]:py-2"
                  uploadFile={uploadFile}
                  resolveFileUrl={resolveFileUrl}
                />
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Checklist */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <CheckSquare size={14} className="text-clickup-text/50" />
                <h3 className="text-sm font-semibold text-clickup-text">
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
                          className="h-3.5 w-3.5 rounded border-clickup-border accent-clickup-purple cursor-pointer shrink-0"
                        />
                        {editingChecklistId === ci.id ? (
                          <input
                            type="text"
                            value={editingChecklistText}
                            onChange={e => setEditingChecklistText(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleSaveChecklistEdit(ci.id);
                              if (e.key === 'Escape') setEditingChecklistId(null);
                            }}
                            onBlur={() => handleSaveChecklistEdit(ci.id)}
                            autoFocus
                            className="flex-1 bg-transparent text-sm text-clickup-text focus:outline-none border-b border-clickup-purple py-0.5"
                          />
                        ) : (
                          <span
                            className={`text-sm flex-1 cursor-pointer ${ci.completed ? 'line-through text-clickup-text/40' : 'text-clickup-text'}`}
                            onClick={() => { setEditingChecklistId(ci.id); setEditingChecklistText(ci.text); }}
                          >
                            {ci.text}
                          </span>
                        )}
                        <button
                          onClick={() => handleDeleteChecklistItem(ci.id)}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-red-400 transition-all p-0.5 rounded"
                          title="Delete"
                        >
                          <X size={13} />
                        </button>
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
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && newChecklistText.trim()) handleAddChecklistItem(); }}
                  placeholder="+ Add checklist item..."
                  className="flex-1 bg-transparent text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none border-b border-transparent focus:border-clickup-purple py-1 transition-colors"
                />
                {newChecklistText.trim() && (
                  <Button variant="ghost" size="icon" onClick={handleAddChecklistItem} disabled={addingChecklist}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Subtasks */}
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-clickup-text">
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
                      <span className="text-xs text-clickup-text/40 font-mono">{sub.reference}</span>
                      <span className={`text-sm flex-1 ${sub.status === 'done' ? 'line-through text-clickup-text/40' : 'text-clickup-text'}`}>
                        {sub.title}
                      </span>
                      <Badge tone={STATUS_TONE[sub.status] ?? 'neutral'}>{sub.status_label}</Badge>
                      {sub.assignee_name && (
                        <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[8px] font-bold text-white">
                          {initials(sub.assignee_name)}
                        </div>
                      )}
                      {/* ··· context menu */}
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
                            <div className="absolute right-0 top-full z-20 w-36 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1 text-sm">
                              <button
                                onClick={(e) => { e.stopPropagation(); handleUnlinkSubtask(sub.id); setSubtaskMenuOpen(null); }}
                                className="flex items-center gap-2 w-full px-3 py-1.5 text-clickup-text/70 hover:bg-clickup-hover hover:text-clickup-text transition-colors"
                              >
                                <Unlink size={13} />
                                Unlink
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleArchiveSubtask(sub.id); }}
                                className="flex items-center gap-2 w-full px-3 py-1.5 text-clickup-text/70 hover:bg-clickup-hover hover:text-clickup-text transition-colors"
                              >
                                <Archive size={13} />
                                Archive
                              </button>
                              <hr className="border-clickup-border my-1" />
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDeleteSubtask(sub.id); }}
                                className="flex items-center gap-2 w-full px-3 py-1.5 text-red-400 hover:bg-clickup-hover hover:text-red-500 transition-colors"
                              >
                                <Trash2 size={13} />
                                Delete
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newSubtaskTitle}
                  onChange={e => setNewSubtaskTitle(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && newSubtaskTitle.trim()) handleAddSubtask(); }}
                  placeholder="+ Add subtask..."
                  className="flex-1 bg-transparent text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none border-b border-transparent focus:border-clickup-purple py-1 transition-colors"
                />
                {newSubtaskTitle.trim() && (
                  <Button variant="ghost" size="icon" onClick={handleAddSubtask} disabled={addingSubtask}>
                    <Send size={14} />
                  </Button>
                )}
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Attachments */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Paperclip size={14} className="text-clickup-text/50" />
                <h3 className="text-sm font-semibold text-clickup-text">Attachments</h3>
                <span className="text-xs text-clickup-text/40">{attachments.length}</span>
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
                          <p className="text-sm text-clickup-text truncate">{att.filename}</p>
                          <p className="text-[10px] text-clickup-text/40">
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
                        <button
                          onClick={() => handleDeleteAttachment(att.id)}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-red-400 transition-all"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); if (e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files); }}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg py-4 text-center text-sm cursor-pointer transition-colors ${
                  dragOver ? 'border-clickup-purple bg-clickup-purple/5 text-clickup-purple' : 'border-clickup-border text-clickup-text/40 hover:border-clickup-text/30'
                }`}
              >
                {uploading ? (
                  <Loader2 size={16} className="animate-spin mx-auto text-clickup-purple" />
                ) : (
                  <span>{dragOver ? 'Drop to upload' : 'Click or drag files to upload'}</span>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={e => { if (e.target.files?.length) { handleFileUpload(e.target.files); e.target.value = ''; } }}
                />
              </div>
            </div>

            <hr className="border-clickup-border" />

            {/* Time Tracking */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Clock size={14} className="text-clickup-text/50" />
                <h3 className="text-sm font-semibold text-clickup-text">Time Tracking</h3>
              </div>

              {/* Estimate + Progress */}
              <div className="flex items-center gap-3 text-xs">
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
                    <div key={te.id} className="flex items-center gap-2 px-3 py-1.5 border-b border-clickup-border last:border-b-0 text-[11px] group hover:bg-clickup-hover/50">
                      <span className="text-clickup-text font-medium">{formatDuration(te.duration_minutes)}</span>
                      <span className="text-clickup-text/40">{te.entry_date}</span>
                      <span className="text-clickup-text/50 flex-1 truncate">{te.description || te.user_name}</span>
                      <button
                        onClick={() => handleDeleteTimeEntry(te.id)}
                        className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-red-400 transition-all p-0.5"
                      >
                        <X size={11} />
                      </button>
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
                  placeholder="Hours..."
                  className="w-20 bg-transparent text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none border-b border-transparent focus:border-clickup-purple py-1 transition-colors"
                />
                <input
                  type="text"
                  value={timeLogDesc}
                  onChange={e => setTimeLogDesc(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && timeLogMinutes) handleLogTime(); }}
                  placeholder="Description..."
                  className="flex-1 bg-transparent text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none border-b border-transparent focus:border-clickup-purple py-1 transition-colors"
                />
                {timeLogMinutes && (
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
            <h3 className="text-sm font-semibold text-clickup-text">Activity</h3>
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
                      <p className="text-xs text-clickup-text/60">{log.message}</p>
                      <span className="text-[10px] text-clickup-text/30">{formatDate(log.created_at)}</span>
                    </div>
                  </div>
                ))}

                {comments.map(comment => (
                  <div key={comment.id} className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-clickup-purple flex items-center justify-center text-[8px] font-bold text-white shrink-0 mt-0.5">
                      {initials(comment.author_name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-xs font-bold text-clickup-text">{comment.author_name}</span>
                      {comment.body_blocks ? (
                        <BlockViewer content={comment.body_blocks as BlockContent} className="mt-0.5 text-xs" resolveFileUrl={resolveFileUrl} />
                      ) : (
                        <p className="text-xs text-clickup-text/60 mt-0.5">{comment.body}</p>
                      )}
                      <span className="text-[10px] text-clickup-text/30">{formatDate(comment.created_at)}</span>
                    </div>
                  </div>
                ))}

                {activityLogs.length === 0 && comments.length === 0 && (
                  <p className="text-sm text-clickup-text/30 text-center py-8">No activity yet</p>
                )}
              </>
            )}
          </div>

          {/* Comment input — sticky bottom */}
          <div className="flex items-center gap-2 px-4 py-3 border-t border-clickup-border shrink-0">
            <div className="w-6 h-6 rounded-full bg-clickup-purple flex items-center justify-center text-[8px] font-bold text-white shrink-0">
              ME
            </div>
            <input
              type="text"
              value={commentDraft}
              onChange={e => setCommentDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleCommentSubmit(); }}
              placeholder="Write a comment..."
              className="flex-1 bg-transparent border border-clickup-border rounded-lg px-3 py-1.5 text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none focus:border-clickup-purple transition-colors"
            />
            <Button variant="ghost" size="icon" className="shrink-0" onClick={handleCommentSubmit}>
              <Send size={14} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

function MetaLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-medium text-clickup-text/50 uppercase tracking-wider whitespace-nowrap">{children}</span>
  );
}

function InlineSaveError({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-300">
      {message}
    </div>
  );
}
