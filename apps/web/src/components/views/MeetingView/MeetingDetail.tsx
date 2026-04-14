import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckSquare,
  Download,
  FileText,
  Loader2,
  Mic,
  Paperclip,
  Pencil,
  Plus,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { Button, useConfirm } from '@aidoo/ui';

import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  attachDocToMeeting,
  attachTaskToMeeting,
  deleteMeeting,
  deleteMeetingFile,
  detachDocFromMeeting,
  detachTaskFromMeeting,
  getMeeting,
  getRecordingPlaybackUrl,
  parseServerDateTime,
  retryMeetingRecording,
  uploadMeetingFile,
  type MeetingDetail as MeetingDetailType,
} from '@/src/domains/meeting/meeting-api';
import {
  canAttachToMeeting,
  canEditMeeting,
  canRemoveAttachment,
} from '@/src/domains/meeting/meeting-permissions';
import { buildWorkspaceAppPath } from '@/src/domains/workspaces/workspace-utils';

import { MeetingEditModal } from './MeetingEditModal';
import { TaskPickerModal } from './TaskPickerModal';
import { DocPickerModal } from './DocPickerModal';
import { RecordingControls } from './RecordingControls';
import { RecordingProgressRail } from './RecordingProgressRail';
import { RecordingRecoveryBanner } from './RecordingRecoveryBanner';
import { useChunkedRecorder } from './useChunkedRecorder';
import { useRecordingPoll } from './useRecordingPoll';
import { useRecordingRecovery } from './useRecordingRecovery';

interface MeetingDetailProps {
  workspaceSlug: string;
  meetingId: string;
  onClose?: () => void;
  onChanged: () => void;
  onDeleted: () => void;
  showCloseButton?: boolean;
}

const STATUS_LABELS: Record<string, string> = {
  scheduled: '예정',
  in_progress: '진행 중',
  completed: '완료',
  cancelled: '취소됨',
};

function formatRange(start: string, end: string): string {
  const s = parseServerDateTime(start);
  const e = parseServerDateTime(end);
  return `${s.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })} – ${e.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}`;
}

export function MeetingDetail({
  workspaceSlug,
  meetingId,
  onClose,
  onChanged,
  onDeleted,
  showCloseButton = true,
}: MeetingDetailProps) {
  const { token, user } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const [meeting, setMeeting] = useState<MeetingDetailType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [playbackUrls, setPlaybackUrls] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await getMeeting(token, workspaceSlug, meetingId);
      setMeeting(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의를 불러올 수 없습니다.');
      setMeeting(null);
    } finally {
      setLoading(false);
    }
  }, [meetingId, token, workspaceSlug]);

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

  useRecordingPoll(token, workspaceSlug, meetingId, meeting, (updated) => {
    setMeeting(updated);
    onChanged();
  });

  const editable = canEditMeeting(user, meeting);
  const canAttach = canAttachToMeeting(user, meeting);

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
      setError(err instanceof Error ? err.message : '이슈 첨부를 해제할 수 없습니다.');
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
      setError(err instanceof Error ? err.message : '문서 첨부를 해제할 수 없습니다.');
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
      setError(err instanceof Error ? err.message : '파일을 업로드할 수 없습니다.');
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
      setError(err instanceof Error ? err.message : '파일을 삭제할 수 없습니다.');
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
        throw new Error(`다운로드 실패 (${response.status})`);
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
        err instanceof Error ? err.message : '파일 다운로드에 실패했습니다.',
      );
    }
  }

  async function handleDelete() {
    if (!token) return;
    const ok = await confirm({
      title: '회의 삭제',
      description: '이 회의를 삭제하시겠습니까?',
      confirmLabel: '삭제',
      cancelLabel: '취소',
      variant: 'danger',
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deleteMeeting(token, workspaceSlug, meetingId);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의를 삭제할 수 없습니다.');
      setBusy(false);
    }
  }

  async function handleRecordingPlayback(recordingId: string) {
    if (!token) return;
    if (playbackUrls[recordingId]) {
      return;
    }
    try {
      const playback = await getRecordingPlaybackUrl(
        token,
        workspaceSlug,
        meetingId,
        recordingId,
      );
      setPlaybackUrls((current) => ({ ...current, [recordingId]: playback.url }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '녹음 재생 링크를 가져올 수 없습니다.');
    }
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
      setError(err instanceof Error ? err.message : '녹음 재시도에 실패했습니다.');
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
              aria-label="닫기"
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
            {STATUS_LABELS[meeting.status] ?? meeting.status}
          </p>
          <h2 className="app-text-title-md text-app-ink line-clamp-2">
            {meeting.title}
          </h2>
          <p className="app-text-caption mt-1 text-app-ink/60 dark:text-app-ink/70">
            {formatRange(meeting.start_at, meeting.end_at)} · {meeting.organizer_name}
          </p>
        </div>
        <div className="ml-3 flex shrink-0 items-center gap-1">
          {editable ? (
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="rounded-md p-1.5 text-app-ink/50 hover:bg-app-surface-hover hover:text-app-ink"
              aria-label="회의 수정"
              title="수정"
            >
              <Pencil size={14} />
            </button>
          ) : null}
          {showCloseButton && onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-app-ink/50 hover:bg-app-surface-hover hover:text-app-ink"
              aria-label="닫기"
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
          title="연결된 태스크"
          count={meeting.task_links.length}
          onAdd={canAttach ? () => setTaskPickerOpen(true) : undefined}
        >
          {meeting.task_links.length === 0 ? (
            <EmptyRow text="첨부된 태스크가 없습니다." />
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
                        {link.issue_title || '제목 없음'}
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
                      aria-label="태스크 첨부 해제"
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
          title="연결된 문서"
          count={meeting.doc_links.length}
          onAdd={canAttach ? () => setDocPickerOpen(true) : undefined}
        >
          {meeting.doc_links.length === 0 ? (
            <EmptyRow text="첨부된 문서가 없습니다." />
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
                      {link.doc_title || '제목 없음'}
                    </Link>
                  </p>
                  {canRemoveAttachment(user, meeting, link) ? (
                    <button
                      type="button"
                      onClick={() => handleDetachDoc(link.doc_id)}
                      disabled={busy}
                      className="ml-2 shrink-0 text-app-ink/40 hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                      aria-label="문서 첨부 해제"
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
          icon={<Paperclip size={14} />}
          title="첨부 파일"
          count={meeting.file_attachments.length}
          onAdd={
            canAttach
              ? () => fileInputRef.current?.click()
              : undefined
          }
          addLabel={uploading ? '업로드 중...' : '추가'}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
          />
          {meeting.file_attachments.length === 0 ? (
            <EmptyRow text="첨부된 파일이 없습니다." />
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
                      title="새 탭에서 미리보기"
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
                      aria-label="파일 다운로드"
                      title="다운로드"
                    >
                      <Download size={14} />
                    </button>
                    {canRemoveAttachment(user, meeting, file) ? (
                      <button
                        type="button"
                        onClick={() => handleFileDelete(file.id)}
                        disabled={busy}
                        className="rounded-md p-1.5 text-app-ink/40 hover:bg-app-surface-hover hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                        aria-label="파일 삭제"
                        title="삭제"
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

        <Section icon={<Mic size={14} />} title="녹음" count={meeting.recordings.length}>
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
            <EmptyRow text="완료된 녹음이 없습니다." />
          ) : (
            <ul className="mt-3 space-y-2">
              {meeting.recordings.map((recording) => (
                <li
                  key={recording.id}
                  className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="app-text-body text-app-ink">
                        {recording.linked_doc_id ? (
                          <Link
                            to={buildWorkspaceAppPath(workspaceSlug, 'docs', recording.linked_doc_id)}
                            className="hover:text-app-accent hover:underline"
                          >
                            {recording.source === 'manual_upload' ? '업로드 음성' : '회의 녹음'}
                          </Link>
                        ) : (
                          recording.source === 'manual_upload' ? '업로드 음성' : '회의 녹음'
                        )}
                      </p>
                      <p className="app-text-caption text-app-ink/50">
                        {formatFileSize(recording.file_size)} · {recording.mime_type}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void handleRecordingPlayback(recording.id)}
                        className="app-text-caption text-app-accent hover:underline"
                      >
                        재생
                      </button>
                    </div>
                  </div>
                  {playbackUrls[recording.id] ? (
                    <audio controls src={playbackUrls[recording.id]} className="mt-3 w-full" />
                  ) : null}
                  {['pending', 'transcribing', 'summarizing', 'generating_doc', 'failed'].includes(
                    recording.transcription_status,
                  ) ? (
                    <div className="mt-3">
                      <RecordingProgressRail
                        recording={recording}
                        onRetry={
                          recording.transcription_status === 'failed'
                            ? () => {
                                void handleRetryRecording(recording.id);
                              }
                            : undefined
                        }
                      />
                    </div>
                  ) : null}
                  {recording.transcription_status === 'done' ? (
                    <p className="app-text-caption mt-3 text-app-ink/60">
                      회의록 생성이 완료되었습니다.
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {recovery.error ? (
            <p className="app-text-caption mt-2 text-[var(--ui-color-danger)]">{recovery.error}</p>
          ) : null}
          {recovery.loading ? (
            <p className="app-text-caption mt-2 text-app-ink/50">복구 가능한 녹음을 확인하는 중입니다.</p>
          ) : null}
        </Section>

        <Section
          icon={<Users size={14} />}
          title="참석자"
          count={meeting.attendees.length}
        >
          {meeting.attendees.length === 0 ? (
            <EmptyRow text="참석자가 없습니다." />
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
              안건
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
            회의 삭제
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
      {confirmDialog}
    </div>
  );
}

function Section({
  icon,
  title,
  count,
  onAdd,
  addLabel = '추가',
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  onAdd?: () => void;
  addLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="app-text-overline inline-flex items-center gap-1.5 text-app-ink/60 dark:text-app-ink/70">
          <span className="text-app-ink/60 dark:text-app-ink/70">{icon}</span>
          {title}
          <span className="text-app-ink/40 dark:text-app-ink/50">({count})</span>
        </h3>
        {onAdd ? (
          <button
            type="button"
            onClick={onAdd}
            className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline"
          >
            <Plus size={12} />
            {addLabel}
          </button>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <p className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-center text-app-ink/50 dark:text-app-ink/60">
      {text}
    </p>
  );
}
