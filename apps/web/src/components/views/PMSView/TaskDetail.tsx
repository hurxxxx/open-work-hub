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
  Unlink,
  Paperclip,
  Download,
  FileIcon,
} from 'lucide-react';
import { Badge, Button, BlockEditor, BlockViewer } from '@aidoo/ui';
import type { BlockContent } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  getIssueDetail,
  updateIssue,
  deleteIssue,
  createIssueComment,
  createProjectIssue,
  listIssueActivityLogs,
  uploadAttachment,
  deleteAttachment,
  type PmsIssue,
  type PmsComment,
  type PmsActivityLog,
  type PmsAttachment,
  type PmsProjectMember,
  type PmsMilestone,
  type PmsLabel,
} from '@/src/domains/pms/pms-api';
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
  const [issueState, setIssueState] = useState(issue);
  const [comments, setComments] = useState<PmsComment[]>([]);
  const [activityLogs, setActivityLogs] = useState<PmsActivityLog[]>([]);
  const [subtasks, setSubtasks] = useState<PmsIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState('');
  const [newSubtaskTitle, setNewSubtaskTitle] = useState('');
  const [addingSubtask, setAddingSubtask] = useState(false);
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
        setSubtasks(detail.subtasks);
        setAttachments(detail.attachments ?? []);
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
            <h1 className="text-xl font-bold text-clickup-text">{issueState.title}</h1>

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
                />
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
                        <BlockViewer content={comment.body_blocks as BlockContent} className="mt-0.5 text-xs" />
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
