import { useCallback, useEffect, useState } from 'react';
import {
  CheckSquare,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { Button } from '@aidoo/ui';

import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  attachDocToMeeting,
  attachTaskToMeeting,
  deleteMeeting,
  detachDocFromMeeting,
  detachTaskFromMeeting,
  getMeeting,
  type MeetingDetail as MeetingDetailType,
} from '@/src/domains/meeting/meeting-api';
import { canEditMeeting } from '@/src/domains/meeting/meeting-permissions';

import { MeetingEditModal } from './MeetingEditModal';
import { TaskPickerModal } from './TaskPickerModal';
import { DocPickerModal } from './DocPickerModal';

interface MeetingDetailProps {
  meetingId: string;
  onClose: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  scheduled: '예정',
  in_progress: '진행 중',
  completed: '완료',
  cancelled: '취소됨',
};

function formatRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  return `${s.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })} – ${e.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}`;
}

export function MeetingDetail({
  meetingId,
  onClose,
  onChanged,
  onDeleted,
}: MeetingDetailProps) {
  const { token, user } = useAuth();
  const [meeting, setMeeting] = useState<MeetingDetailType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await getMeeting(token, meetingId);
      setMeeting(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의를 불러올 수 없습니다.');
      setMeeting(null);
    } finally {
      setLoading(false);
    }
  }, [token, meetingId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const editable = canEditMeeting(user, meeting);

  async function handleAttachTask(issue: { id: string }) {
    if (!token) return;
    const updated = await attachTaskToMeeting(token, meetingId, issue.id);
    setMeeting(updated);
    onChanged();
  }

  async function handleDetachTask(issueId: string) {
    if (!token) return;
    setBusy(true);
    try {
      const updated = await detachTaskFromMeeting(token, meetingId, issueId);
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
    const updated = await attachDocToMeeting(token, meetingId, doc.source_id);
    setMeeting(updated);
    onChanged();
  }

  async function handleDetachDoc(docId: string) {
    if (!token) return;
    setBusy(true);
    try {
      const updated = await detachDocFromMeeting(token, meetingId, docId);
      setMeeting(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : '문서 첨부를 해제할 수 없습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!token) return;
    if (!window.confirm('이 회의를 삭제하시겠습니까?')) return;
    setBusy(true);
    try {
      await deleteMeeting(token, meetingId);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의를 삭제할 수 없습니다.');
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
          <button
            type="button"
            onClick={onClose}
            className="text-app-ink/50 hover:text-app-ink"
            aria-label="닫기"
          >
            <X size={16} />
          </button>
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
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-app-ink/50 hover:bg-app-surface-hover hover:text-app-ink"
            aria-label="패널 닫기"
          >
            <X size={16} />
          </button>
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
          onAdd={editable ? () => setTaskPickerOpen(true) : undefined}
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
                      {link.issue_title || '제목 없음'}
                    </p>
                    <p className="app-text-caption text-app-ink/40">
                      {link.project_key
                        ? `${link.project_key}-${link.issue_number}`
                        : '#'}
                    </p>
                  </div>
                  {editable ? (
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
          onAdd={editable ? () => setDocPickerOpen(true) : undefined}
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
                    {link.doc_title || '제목 없음'}
                  </p>
                  {editable ? (
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
      />
      <DocPickerModal
        isOpen={docPickerOpen}
        onClose={() => setDocPickerOpen(false)}
        onPick={handleAttachDoc}
        excludeDocIds={meeting.doc_links.map((link) => link.doc_id)}
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
      />
    </div>
  );
}

function Section({
  icon,
  title,
  count,
  onAdd,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  onAdd?: () => void;
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
            추가
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
