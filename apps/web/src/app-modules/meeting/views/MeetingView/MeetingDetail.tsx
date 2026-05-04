import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  CheckSquare,
  Download,
  FileText,
  Loader2,
  Mic,
  Paperclip,
  Pencil,
  PencilRuler,
  Plus,
  Search,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { Button, Dialog, useConfirm } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  LinkedRecordingList,
  type LinkedRecordingListItem,
} from '@/src/app-modules/recording/views/LinkedRecordingsList';
import { formatDateTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  RAIL_VISIBLE_STATUSES,
  attachDocToMeeting,
  attachTaskToMeeting,
  deleteMeeting,
  deleteMeetingFile,
  detachDocFromMeeting,
  detachTaskFromMeeting,
  fetchRecordingPlaybackBlobUrl,
  getMeeting,
  getRecordingPlaybackUrl,
  parseServerDateTime,
  deleteMeetingRecording,
  retryMeetingRecording,
  uploadMeetingFile,
  type MeetingDetail as MeetingDetailType,
  type MeetingRecording,
} from '../../api/meeting-api';
import {
  canAttachToMeeting,
  canEditMeeting,
  canInviteAttendees,
  canRemoveAttachment,
} from '../../api/meeting-permissions';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

import { AddAttendeesModal } from './AddAttendeesModal';
import { MeetingEditModal } from './MeetingEditModal';
import { MeetingInsightSection } from './MeetingInsightSection';
import { Section, EmptyRow } from './MeetingSection';
import { TaskPickerModal } from './TaskPickerModal';
import { DocPickerModal } from './DocPickerModal';
import { RecordingControls } from './RecordingControls';
import { RecordingProgressRail } from './RecordingProgressRail';
import { RecordingRecoveryBanner } from './RecordingRecoveryBanner';
import { openMeetingInsightInChat } from './openMeetingInsightInChat';
import { useChunkedRecorder } from './useChunkedRecorder';
import { useRecordingPoll } from './useRecordingPoll';
import { useRecordingRecovery } from './useRecordingRecovery';
import {
  WhiteboardEditorSurface,
  WhiteboardPickerModal,
  attachWhiteboardContextSlot,
  createWhiteboardContextSlot,
  detachWhiteboardContextSlot,
  type WhiteboardDetail,
  type WhiteboardHubItem,
} from '@/src/app-modules/whiteboard/public-api';

interface MeetingDetailProps {
  workspaceSlug: string;
  meetingId: string;
  onClose?: () => void;
  onChanged: () => void;
  onDeleted: () => void;
  showCloseButton?: boolean;
}

const STATUS_TRANSLATION_KEYS: Record<string, string> = {
  scheduled: 'meeting.scheduled',
  in_progress: 'meeting.inProgress',
  completed: 'meeting.completed',
  cancelled: 'meeting.cancelled',
};

const TRANSCRIPT_EXTRACTED_STATUSES = new Set([
  'summarizing',
  'extracting_insights',
  'generating_doc',
  'done',
]);

function transcriptStatusKey(recording: MeetingRecording): string {
  if (
    recording.transcript_extracted === true ||
    TRANSCRIPT_EXTRACTED_STATUSES.has(recording.transcription_status)
  ) {
    return 'meeting.recordingStatus.transcriptExtracted';
  }
  if (recording.transcription_status === 'transcribing') {
    return 'meeting.recordingStatus.transcriptExtracting';
  }
  if (recording.transcription_status === 'failed') {
    return 'meeting.recordingStatus.transcriptFailed';
  }
  return 'meeting.recordingStatus.transcriptQueued';
}

function formatRange(start: string, end: string, timeZone: string, locale: string): string {
  const s = parseServerDateTime(start);
  const e = parseServerDateTime(end);
  return `${formatDateTime(s, {
    locale,
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  })} – ${formatDateTime(e, {
    hour: '2-digit',
    locale,
    minute: '2-digit',
    timeZone,
  })}`;
}

export function MeetingDetail({
  workspaceSlug,
  meetingId,
  onClose,
  onChanged,
  onDeleted,
  showCloseButton = true,
}: MeetingDetailProps) {
  const { t, i18n } = useTranslation('apps');
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const navigate = useNavigate();
  const { confirm, confirmDialog } = useConfirm();
  const [meeting, setMeeting] = useState<MeetingDetailType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [addAttendeesOpen, setAddAttendeesOpen] = useState(false);
  const [whiteboardPickerOpen, setWhiteboardPickerOpen] = useState(false);
  const [whiteboardEditorOpen, setWhiteboardEditorOpen] = useState(false);
  const [whiteboardEditorBoardId, setWhiteboardEditorBoardId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await getMeeting(token, workspaceSlug, meetingId);
      setMeeting(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.loadFailed'));
      setMeeting(null);
    } finally {
      setLoading(false);
    }
  }, [meetingId, t, token, workspaceSlug]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const recovery = useRecordingRecovery(workspaceSlug, meetingId, token);
  const recorder = useChunkedRecorder({
    workspaceSlug,
    meetingId,
    token,
    onMeetingUpdated: (updated) => {
      setMeeting(updated);
      void recovery.refresh();
      onChanged();
    },
  });

  useRecordingPoll(
    token,
    workspaceSlug,
    meetingId,
    meeting,
    (updated) => {
      setMeeting(updated);
      onChanged();
    },
    user?.id,
  );

  // The single-recorder lock from another participant. When this is set the
  // local user cannot start a new recording — RecordingControls disables
  // the start button and renders an inline notice. Auto-clears when the
  // server stops returning the lock (recorder finishes OR stale window).
  const lockedByOther = (() => {
    if (!meeting?.active_recording_lock || !user) return null;
    if (meeting.active_recording_lock.user_id === user.id) return null;
    return meeting.active_recording_lock;
  })();

  const editable = canEditMeeting(user, meeting);
  const canAttach = canAttachToMeeting(user, meeting);
  const canInvite = canInviteAttendees(user, meeting);
  const meetingWhiteboardContext = useMemo(
    () => ({ app: 'meeting', type: 'meeting', id: meetingId }),
    [meetingId],
  );
  const activeWhiteboardId = whiteboardEditorBoardId ?? meeting?.whiteboard_link?.whiteboard_id ?? null;

  const updateWhiteboardLinkFromBoard = useCallback((board: WhiteboardDetail) => {
    setMeeting((current) => {
      if (!current) return current;
      return {
        ...current,
        whiteboard_link: {
          id: current.whiteboard_link?.id ?? '',
          whiteboard_id: board.id,
          whiteboard_title: board.title,
          added_by_id: current.whiteboard_link?.added_by_id ?? user?.id ?? null,
          created_at: current.whiteboard_link?.created_at ?? board.created_at,
          updated_at: board.updated_at,
        },
      };
    });
  }, [user?.id]);

  async function handleAttachTask(issue: { id: string }) {
    if (!token) return;
    const updated = await attachTaskToMeeting(token, workspaceSlug, meetingId, issue.id);
    setMeeting(updated);
    onChanged();
  }

  async function handleDetachTask(issueId: string) {
    if (!token) return;
    setBusy(true);
    try {
      const updated = await detachTaskFromMeeting(
        token,
        workspaceSlug,
        meetingId,
        issueId,
      );
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.detachTaskFailed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleAttachDoc(doc: { source_id: string }) {
    if (!token) return;
    const updated = await attachDocToMeeting(
      token,
      workspaceSlug,
      meetingId,
      doc.source_id,
    );
    setMeeting(updated);
    onChanged();
  }

  async function handleDetachDoc(docId: string) {
    if (!token) return;
    setBusy(true);
    try {
      const updated = await detachDocFromMeeting(token, workspaceSlug, meetingId, docId);
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.detachDocFailed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateWhiteboard() {
    if (!token || !meeting) return;
    setBusy(true);
    setError(null);
    try {
      const board = await createWhiteboardContextSlot(
        token,
        {
          ...meetingWhiteboardContext,
          title: t('meeting.detail.whiteboardDefaultTitle', { title: meeting.title }),
        },
        workspaceSlug,
      );
      updateWhiteboardLinkFromBoard(board);
      setWhiteboardEditorBoardId(board.id);
      setWhiteboardEditorOpen(true);
      onChanged();
      void refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.createWhiteboardFailed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleAttachWhiteboard(item: WhiteboardHubItem) {
    if (!token) return;
    const board = await attachWhiteboardContextSlot(
      token,
      {
        ...meetingWhiteboardContext,
        whiteboard_id: item.id,
      },
      workspaceSlug,
    );
    updateWhiteboardLinkFromBoard(board);
    setWhiteboardEditorBoardId(board.id);
    setWhiteboardEditorOpen(true);
    onChanged();
    void refresh();
  }

  async function handleDetachWhiteboard() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await detachWhiteboardContextSlot(token, meetingWhiteboardContext, workspaceSlug);
      setMeeting((current) => (current ? { ...current, whiteboard_link: null } : current));
      setWhiteboardEditorBoardId(null);
      setWhiteboardEditorOpen(false);
      onChanged();
      void refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.detachWhiteboardFailed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so the user can pick the same file again later.
    event.target.value = '';
    if (!file || !token) return;
    setUploading(true);
    setError(null);
    try {
      const updated = await uploadMeetingFile(token, workspaceSlug, meetingId, file);
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.uploadFileFailed'));
    } finally {
      setUploading(false);
    }
  }

  async function handleFileDelete(fileId: string) {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await deleteMeetingFile(token, workspaceSlug, meetingId, fileId);
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.deleteFileFailed'));
    } finally {
      setBusy(false);
    }
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // Force a real file download instead of opening in a new tab. We fetch the
  // MinIO presigned URL as a blob and trigger a synthetic anchor click with
  // the original filename. The <a download> attribute is ignored on cross-
  // origin URLs, which is why we take the blob roundtrip.
  async function handleFileDownload(file: {
    download_url: string;
    filename: string;
  }) {
    try {
      const response = await fetch(file.download_url);
      if (!response.ok) {
        throw new Error(t('meeting.detail.downloadFailedWithStatus', { status: response.status }));
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = file.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('meeting.detail.downloadFileFailed'),
      );
    }
  }

  async function handleDelete() {
    if (!token) return;
    const ok = await confirm({
      title: t('meeting.detail.deleteMeetingTitle'),
      description: t('meeting.detail.deleteMeetingDescription'),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deleteMeeting(token, workspaceSlug, meetingId);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.deleteMeetingFailed'));
      setBusy(false);
    }
  }

  async function loadRecordingPlayback(recordingId: string): Promise<string> {
    if (!token) {
      throw new Error(t('meeting.detail.playbackFailed'));
    }
    const playback = await getRecordingPlaybackUrl(
      token,
      workspaceSlug,
      meetingId,
      recordingId,
    );
    return fetchRecordingPlaybackBlobUrl(token, playback.url);
  }

  async function handleRetryRecording(recordingId: string) {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await retryMeetingRecording(
        token,
        workspaceSlug,
        meetingId,
        recordingId,
      );
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.retryRecordingFailed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteRecording(recordingId: string) {
    if (!token) return;
    const ok = await confirm({
      title: t('meeting.detail.deleteRecordingTitle'),
      description: t('meeting.detail.deleteRecordingDescription'),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await deleteMeetingRecording(
        token,
        workspaceSlug,
        meetingId,
        recordingId,
      );
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.detail.deleteRecordingFailed'));
    } finally {
      setBusy(false);
    }
  }

  if (loading && meeting === null) {
    return (
      <div className="flex h-full items-center justify-center text-app-ink/40">
        <Loader2 size={18} className="animate-spin" />
      </div>
    );
  }

  if (error && meeting === null) {
    return (
      <div className="p-6 text-app-ink/70">
        <div className="flex items-center justify-between">
          <p className="app-text-body">{error}</p>
          {showCloseButton && onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="text-app-ink/50 hover:text-app-ink"
              aria-label={t('common:actions.close')}
            >
              <X size={16} />
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  if (!meeting) return null;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex items-start justify-between border-b border-app-border px-5 py-4">
        <div className="min-w-0">
          <p className="app-text-overline text-app-accent">
            {STATUS_TRANSLATION_KEYS[meeting.status]
              ? t(STATUS_TRANSLATION_KEYS[meeting.status])
              : meeting.status}
          </p>
          <h2 className="app-text-title-md text-app-ink line-clamp-2">
            {meeting.title}
          </h2>
          <p className="app-text-caption mt-1 text-app-ink/60 dark:text-app-ink/70">
            {formatRange(meeting.start_at, meeting.end_at, timeZone, i18n.language)} · {meeting.organizer_name}
          </p>
        </div>
        <div className="ml-3 flex shrink-0 items-center gap-1">
          {editable ? (
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="rounded-md p-1.5 text-app-ink/50 hover:bg-app-surface-hover hover:text-app-ink"
              aria-label={t('meeting.edit')}
              title={t('common:actions.edit')}
            >
              <Pencil size={14} />
            </button>
          ) : null}
          {showCloseButton && onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-app-ink/50 hover:bg-app-surface-hover hover:text-app-ink"
              aria-label={t('common:actions.close')}
            >
              <X size={16} />
            </button>
          ) : null}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        <Section
          icon={<CheckSquare size={14} />}
          title={t('meeting.detail.linkedTasks')}
          count={meeting.task_links.length}
          onAdd={canAttach ? () => setTaskPickerOpen(true) : undefined}
          addLabel={t('common:actions.add')}
        >
          {meeting.task_links.length === 0 ? (
            <EmptyRow text={t('meeting.detail.noLinkedTasks')} />
          ) : (
            <ul className="space-y-1">
              {meeting.task_links.map((link) => (
                <li
                  key={link.id}
                  className="flex items-start justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="app-text-body line-clamp-1 text-app-ink">
                      <Link
                        to={buildWorkspaceAppPath(workspaceSlug, 'pms', `?issue=${encodeURIComponent(link.issue_id)}`)}
                        className="hover:text-app-accent hover:underline"
                      >
                        {link.issue_title || t('meeting.detail.untitled')}
                      </Link>
                    </p>
                    <p className="app-text-caption text-app-ink/40">
                      {link.list_key
                        ? `${link.list_key}-${link.issue_number}`
                        : '#'}
                    </p>
                    </div>
                  {canRemoveAttachment(user, meeting, link) ? (
                    <button
                      type="button"
                      onClick={() => handleDetachTask(link.issue_id)}
                      disabled={busy}
                      className="ml-2 shrink-0 text-app-ink/40 hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                      aria-label={t('meeting.detail.detachTask')}
                    >
                      <Trash2 size={14} />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          icon={<FileText size={14} />}
          title={t('meeting.detail.linkedDocs')}
          count={meeting.doc_links.length}
          onAdd={canAttach ? () => setDocPickerOpen(true) : undefined}
          addLabel={t('common:actions.add')}
        >
          {meeting.doc_links.length === 0 ? (
            <EmptyRow text={t('meeting.detail.noLinkedDocs')} />
          ) : (
            <ul className="space-y-1">
              {meeting.doc_links.map((link) => (
                <li
                  key={link.id}
                  className="flex items-start justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2"
                >
                  <p className="app-text-body line-clamp-1 text-app-ink">
                    <Link
                      to={buildWorkspaceAppPath(workspaceSlug, 'docs', link.doc_id)}
                      className="hover:text-app-accent hover:underline"
                    >
                      {link.doc_title || t('meeting.detail.untitled')}
                    </Link>
                  </p>
                  {canRemoveAttachment(user, meeting, link) ? (
                    <button
                      type="button"
                      onClick={() => handleDetachDoc(link.doc_id)}
                      disabled={busy}
                      className="ml-2 shrink-0 text-app-ink/40 hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                      aria-label={t('meeting.detail.detachDoc')}
                    >
                      <Trash2 size={14} />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          icon={<PencilRuler size={14} />}
          title={t('meeting.detail.whiteboard')}
          count={meeting.whiteboard_link ? 1 : 0}
          headerAction={
            canAttach ? (
              meeting.whiteboard_link ? (
                <button
                  type="button"
                  onClick={() => setWhiteboardPickerOpen(true)}
                  className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline"
                >
                  <Search size={12} />
                  {t('meeting.detail.replace')}
                </button>
              ) : (
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleCreateWhiteboard()}
                    disabled={busy}
                    className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline disabled:opacity-50"
                  >
                    <Plus size={12} />
                    {t('meeting.detail.createNew')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setWhiteboardPickerOpen(true)}
                    disabled={busy}
                    className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline disabled:opacity-50"
                  >
                    <Search size={12} />
                    {t('meeting.detail.selectExisting')}
                  </button>
                </div>
              )
            ) : undefined
          }
        >
          {meeting.whiteboard_link ? (
            <div className="flex items-start justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <button
                type="button"
                onClick={() => {
                  setWhiteboardEditorBoardId(meeting.whiteboard_link?.whiteboard_id ?? null);
                  setWhiteboardEditorOpen(true);
                }}
                className="min-w-0 flex-1 text-left"
              >
                <p className="app-text-body line-clamp-1 text-app-ink hover:text-app-accent">
                  {meeting.whiteboard_link.whiteboard_title}
                </p>
                <p className="app-text-caption text-app-ink/40">
                  {formatDateTime(meeting.whiteboard_link.updated_at, {
                    dateStyle: 'medium',
                    locale: i18n.language,
                    timeStyle: 'short',
                    timeZone,
                  })}
                </p>
              </button>
              <div className="ml-2 flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    setWhiteboardEditorBoardId(meeting.whiteboard_link?.whiteboard_id ?? null);
                    setWhiteboardEditorOpen(true);
                  }}
                  className="app-text-caption text-app-accent hover:underline"
                >
                  {t('common:actions.open')}
                </button>
                {canAttach ? (
                  <button
                    type="button"
                    onClick={() => void handleDetachWhiteboard()}
                    disabled={busy}
                    className="rounded-md p-1.5 text-app-ink/40 hover:bg-app-surface-hover hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                    aria-label={t('meeting.detail.detachWhiteboard')}
                    title={t('meeting.detail.detach')}
                  >
                    <Trash2 size={14} />
                  </button>
                ) : null}
              </div>
            </div>
          ) : (
            <EmptyRow text={t('meeting.detail.noWhiteboard')} />
          )}
        </Section>

        <Section
          icon={<Paperclip size={14} />}
          title={t('meeting.detail.files')}
          count={meeting.file_attachments.length}
          onAdd={
            canAttach
              ? () => fileInputRef.current?.click()
              : undefined
          }
          addLabel={uploading ? t('meeting.detail.uploading') : t('common:actions.add')}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
          />
          {meeting.file_attachments.length === 0 ? (
            <EmptyRow text={t('meeting.detail.noFiles')} />
          ) : (
            <ul className="space-y-1">
              {meeting.file_attachments.map((file) => (
                <li
                  key={file.id}
                  className="flex items-start justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <a
                      href={file.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="app-text-body line-clamp-1 text-app-ink hover:text-app-accent"
                      title={t('meeting.detail.previewNewTab')}
                    >
                      {file.filename}
                    </a>
                    <p className="app-text-caption text-app-ink/40">
                      {formatFileSize(file.size_bytes)} · {file.added_by_name}
                    </p>
                  </div>
                  <div className="ml-2 flex shrink-0 items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => handleFileDownload(file)}
                      className="rounded-md p-1.5 text-app-ink/40 hover:bg-app-surface-hover hover:text-app-ink"
                      aria-label={t('meeting.detail.downloadFile')}
                      title={t('meeting.detail.download')}
                    >
                      <Download size={14} />
                    </button>
                    {canRemoveAttachment(user, meeting, file) ? (
                      <button
                        type="button"
                        onClick={() => handleFileDelete(file.id)}
                        disabled={busy}
                        className="rounded-md p-1.5 text-app-ink/40 hover:bg-app-surface-hover hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                        aria-label={t('meeting.detail.deleteFile')}
                        title={t('common:actions.delete')}
                      >
                        <Trash2 size={14} />
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section icon={<Mic size={14} />} title={t('meeting.recordings')} count={meeting.recordings.length}>
          {canAttach ? (
            <RecordingControls
              browserSupported={recorder.browserSupported}
              taskLinks={meeting.task_links}
              isRecording={recorder.isRecording}
              isBusy={recorder.isBusy}
              elapsedSec={recorder.elapsedSec}
              queuedBytes={recorder.queuedBytes}
              uploadedBytes={recorder.uploadedBytes}
              persistWarning={recorder.persistWarning}
              lockedByOther={lockedByOther}
              onStart={(linkedTaskId) => recorder.startRecording(linkedTaskId)}
              onStop={recorder.stopRecording}
              onImportFile={(file, linkedTaskId) => recorder.importAudioFile(file, linkedTaskId)}
            />
          ) : null}

          {recorder.error ? (
            <p className="app-text-caption mt-2 text-[var(--ui-color-danger)]">{recorder.error}</p>
          ) : null}

          {recovery.items.length > 0 ? (
            <div className="mt-3 space-y-2">
              {recovery.items.map((item) => {
                const localSession = item.localSession;
                const remoteStaging = item.remoteStaging;
                return (
                  <RecordingRecoveryBanner
                    key={item.stagingId}
                    item={item}
                    onResumeUpload={
                      localSession && remoteStaging
                        ? () => {
                            void recorder.resumeUpload(item.stagingId);
                          }
                        : undefined
                    }
                    onContinueRecording={
                      localSession && remoteStaging
                        ? () => {
                            void recorder.continueRecording({
                              stagingId: item.stagingId,
                              idempotencyKey: localSession.idempotencyKey,
                              mimeType: localSession.mimeType,
                              linkedTaskId: localSession.linkedTaskId,
                              highestSeq: Math.max(
                                localSession.lastChunkSeq,
                                remoteStaging.highest_seq,
                              ),
                            });
                          }
                        : undefined
                    }
                    onDownload={
                      localSession
                        ? () => {
                            void recorder.downloadRecoveredSession(item.stagingId);
                          }
                        : undefined
                    }
                    onImport={
                      localSession
                        ? () => {
                            void recorder
                              .importRecoveredSession(item.stagingId, localSession.linkedTaskId)
                              .then(() => recovery.refresh());
                          }
                        : undefined
                    }
                    onDiscard={() => {
                      void recorder
                        .discardSession(item.stagingId, Boolean(remoteStaging))
                        .then(() => recovery.refresh());
                    }}
                    onFinalizeUploadedOnly={
                      !localSession && remoteStaging
                        ? () => {
                            void recorder
                              .finalizeUploadedOnly(item.stagingId)
                              .then(() => recovery.refresh());
                          }
                        : undefined
                    }
                  />
                );
              })}
            </div>
          ) : null}

          {meeting.recordings.length === 0 ? (
            <EmptyRow text={t('meeting.detail.noRecordings')} />
          ) : (
            <div className="mt-3">
              <LinkedRecordingList
                workspaceSlug={workspaceSlug}
                emptyText={t('meeting.detail.noRecordings')}
                disabled={busy}
                onLoadPlayback={loadRecordingPlayback}
                onRetry={handleRetryRecording}
                onDelete={handleDeleteRecording}
                onError={(err) => {
                  setError(err instanceof Error ? err.message : t('meeting.detail.playbackFailed'));
                }}
                items={meeting.recordings.map((recording): LinkedRecordingListItem => {
                  const canManageRecording = Boolean(
                    user && (
                      recording.uploaded_by_id === user.id
                      || meeting.organizer_id === user.id
                    ),
                  );
                  const baseLabel =
                    recording.source === 'manual_upload'
                      ? t('meeting.detail.uploadedAudio')
                      : t('meeting.detail.meetingRecording');
                  const recordingLabel = t('meeting.detail.recordingWithSequence', {
                    label: baseLabel,
                    sequence: recording.sequence_no,
                  });
                  return {
                    id: recording.id,
                    title: recordingLabel,
                    subtitle: `${formatFileSize(recording.file_size)} · ${recording.mime_type}`,
                    statusLine: `${t('meeting.recordingStatus.audioSaved')} · ${t(transcriptStatusKey(recording))}`,
                    rawTranscriptDocId: recording.raw_transcript_doc_id,
                    minutesDocId: recording.minutes_doc_id,
                    canDelete: canManageRecording,
                    canRetry: canManageRecording && recording.transcription_status === 'failed',
                    progress: RAIL_VISIBLE_STATUSES.has(recording.transcription_status) ? (
                      <RecordingProgressRail recording={recording} />
                    ) : null,
                    doneLabel: recording.transcription_status === 'done'
                      ? t('meeting.detail.minutesDone')
                      : null,
                  };
                })}
              />
            </div>
          )}
          {recovery.error ? (
            <p className="app-text-caption mt-2 text-[var(--ui-color-danger)]">{recovery.error}</p>
          ) : null}
          {recovery.loading ? (
            <p className="app-text-caption mt-2 text-app-ink/50">
              {t('meeting.detail.recoveryChecking')}
            </p>
          ) : null}
        </Section>

        {meeting.recordings.length > 0 ? (
          <MeetingInsightSection
            meeting={meeting}
            workspaceSlug={workspaceSlug}
            token={token}
            timeZone={timeZone}
            onOpenInChat={async (insight) => {
              if (!token) {
                throw new Error(t('meeting.detail.chatRequiresLogin'));
              }
              await openMeetingInsightInChat({
                navigate,
                token,
                workspaceSlug,
                meeting,
                insight,
              });
            }}
          />
        ) : null}

        <Section
          icon={<Users size={14} />}
          title={t('meeting.form.attendees')}
          count={meeting.attendees.length}
          onAdd={canInvite ? () => setAddAttendeesOpen(true) : undefined}
          addLabel={t('common:actions.add')}
        >
          {meeting.attendees.length === 0 ? (
            <EmptyRow text={t('meeting.detail.noAttendees')} />
          ) : (
            <ul className="space-y-1">
              {meeting.attendees.map((attendee) => (
                <li
                  key={attendee.id}
                  className="flex items-center justify-between rounded-md bg-app-surface-sidebar px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="app-text-body line-clamp-1 text-app-ink">
                      {attendee.full_name}
                    </p>
                    <p className="app-text-caption text-app-ink/50 dark:text-app-ink/60">
                      {attendee.email}
                    </p>
                  </div>
                  <span className="app-text-overline text-app-ink/60 dark:text-app-ink/70">
                    {attendee.response}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {meeting.agenda ? (
          <section>
            <h3 className="app-text-overline mb-2 text-app-ink/60 dark:text-app-ink/70">
              {t('meeting.form.agenda')}
            </h3>
            <p className="app-text-body whitespace-pre-wrap text-app-ink/80">
              {meeting.agenda}
            </p>
          </section>
        ) : null}
      </div>

      {editable ? (
        <footer className="border-t border-app-border px-5 py-3">
          <Button
            variant="secondary"
            onClick={handleDelete}
            disabled={busy}
            className="w-full"
          >
            <Trash2 size={14} className="mr-1" />
            {t('meeting.detail.deleteMeeting')}
          </Button>
        </footer>
      ) : null}

      <TaskPickerModal
        isOpen={taskPickerOpen}
        onClose={() => setTaskPickerOpen(false)}
        onPick={handleAttachTask}
        excludeIssueIds={meeting.task_links.map((link) => link.issue_id)}
        workspaceSlug={workspaceSlug}
      />
      <DocPickerModal
        isOpen={docPickerOpen}
        onClose={() => setDocPickerOpen(false)}
        onPick={handleAttachDoc}
        excludeDocIds={meeting.doc_links.map((link) => link.doc_id)}
        workspaceSlug={workspaceSlug}
      />
      <WhiteboardPickerModal
        isOpen={whiteboardPickerOpen}
        onClose={() => setWhiteboardPickerOpen(false)}
        onPick={handleAttachWhiteboard}
        excludeWhiteboardIds={meeting.whiteboard_link ? [meeting.whiteboard_link.whiteboard_id] : []}
        workspaceSlug={workspaceSlug}
      />
      <Dialog
        closeLabel={t('common:actions.close')}
        open={whiteboardEditorOpen && activeWhiteboardId !== null}
        onOpenChange={(open) => {
          if (!open) setWhiteboardEditorOpen(false);
        }}
        title={t('meeting.detail.whiteboardDialogTitle')}
        description={t('meeting.detail.whiteboardDialogDescription')}
        fullSize
        dismissOnInteractOutside={false}
        actions={
          <Button variant="secondary" onClick={() => setWhiteboardEditorOpen(false)}>
            {t('common:actions.close')}
          </Button>
        }
      >
        {activeWhiteboardId ? (
          <div className="flex h-[calc(92vh-8.5rem)] min-h-[520px] min-w-0">
            <WhiteboardEditorSurface
              key={activeWhiteboardId}
              boardId={activeWhiteboardId}
              workspaceSlug={workspaceSlug}
              showArchive={false}
              showDetach={canAttach}
              onDetach={handleDetachWhiteboard}
              onClose={() => setWhiteboardEditorOpen(false)}
              onBoardUpdated={updateWhiteboardLinkFromBoard}
              className="min-w-0"
            />
          </div>
        ) : null}
      </Dialog>
      <MeetingEditModal
        isOpen={editOpen}
        meeting={meeting}
        onClose={() => setEditOpen(false)}
        onSaved={(updated) => {
          setMeeting(updated);
          setEditOpen(false);
          onChanged();
        }}
        workspaceSlug={workspaceSlug}
      />
      <AddAttendeesModal
        isOpen={addAttendeesOpen}
        meeting={meeting}
        workspaceSlug={workspaceSlug}
        onClose={() => setAddAttendeesOpen(false)}
        onAdded={(updated) => {
          setMeeting(updated);
          setAddAttendeesOpen(false);
          onChanged();
        }}
      />
      {confirmDialog}
    </div>
  );
}
