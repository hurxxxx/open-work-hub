import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { CheckSquare, FileText, Paperclip, Plus, X } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createMeeting,
  listMeetingUsers,
  uploadMeetingFile,
  type MeetingAttendeeInput,
  type MeetingUser,
} from '../../api/meeting-api';

import { MeetingAvailabilityPanel } from './MeetingAvailabilityPanel';
import { TaskPickerModal } from './TaskPickerModal';
import { DocPickerModal } from './DocPickerModal';

interface MeetingCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (meetingId: string) => void;
  workspaceSlug: string;
  /** Pre-fill start/end when opened from a calendar slot selection. */
  initialRange?: { start: Date; end: Date; allDay: boolean } | null;
}

interface PickedTask {
  id: string;
  title: string;
  reference: string;
}

interface PickedDoc {
  id: string;
  title: string;
}

function defaultStart(): string {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  now.setHours(now.getHours() + 1);
  return toLocalInputValue(now);
}

function defaultEnd(): string {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  now.setHours(now.getHours() + 2);
  return toLocalInputValue(now);
}

/** Derive (startAt, endAt) inputs from a calendar slot selection.
 *  Month-view cells arrive as all-day ranges — convert to a 1-hour 09:00 slot
 *  on the selected day since meetings aren't stored as all-day. */
function rangeToInputs(range: { start: Date; end: Date; allDay: boolean }): {
  start: string;
  end: string;
} {
  if (range.allDay) {
    const start = new Date(
      range.start.getFullYear(),
      range.start.getMonth(),
      range.start.getDate(),
      9,
      0,
      0,
      0,
    );
    const end = new Date(start.getTime());
    end.setHours(end.getHours() + 1);
    return { start: toLocalInputValue(start), end: toLocalInputValue(end) };
  }
  return {
    start: toLocalInputValue(range.start),
    end: toLocalInputValue(range.end),
  };
}

function toLocalInputValue(date: Date): string {
  // datetime-local expects YYYY-MM-DDTHH:mm in local time, no timezone suffix.
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function localInputToIso(value: string): string {
  // The API expects a naive ISO datetime; the backend stores naive UTC and we
  // pass the local-clock value through. Treat user input as local-wall time
  // and serialize without a timezone marker.
  return new Date(value).toISOString();
}

export function MeetingCreateModal({
  isOpen,
  onClose,
  onCreated,
  workspaceSlug,
  initialRange,
}: MeetingCreateModalProps) {
  const { token, user } = useAuth();
  const [title, setTitle] = useState('');
  const [agenda, setAgenda] = useState('');
  const [startAt, setStartAt] = useState(defaultStart());
  const [endAt, setEndAt] = useState(defaultEnd());
  const [attendees, setAttendees] = useState<MeetingAttendeeInput[]>([]);
  const [pickedAttendeeUsers, setPickedAttendeeUsers] = useState<MeetingUser[]>([]);
  const [users, setUsers] = useState<MeetingUser[]>([]);
  const [userQuery, setUserQuery] = useState('');
  const [userQueryFocused, setUserQueryFocused] = useState(false);
  const [usersLoading, setUsersLoading] = useState(false);
  const [pickedTasks, setPickedTasks] = useState<PickedTask[]>([]);
  const [pickedDocs, setPickedDocs] = useState<PickedDoc[]>([]);
  const [pickedFiles, setPickedFiles] = useState<File[]>([]);
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdMeetingId, setCreatedMeetingId] = useState<string | null>(null);
  const [partialFailures, setPartialFailures] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setTitle('');
    setAgenda('');
    if (initialRange) {
      const inputs = rangeToInputs(initialRange);
      setStartAt(inputs.start);
      setEndAt(inputs.end);
    } else {
      setStartAt(defaultStart());
      setEndAt(defaultEnd());
    }
    setAttendees(
      user
        ? [{ user_id: user.id, role: 'required' as const }]
        : [],
    );
    setPickedAttendeeUsers([]);
    setUsers([]);
    setUserQuery('');
    setUserQueryFocused(false);
    setPickedTasks([]);
    setPickedDocs([]);
    setPickedFiles([]);
    setTaskPickerOpen(false);
    setDocPickerOpen(false);
    setError(null);
    setSubmitting(false);
    setCreatedMeetingId(null);
    setPartialFailures([]);
  }, [isOpen, initialRange, user]);

  // Server-side user search. Only fires when there's an actual query so an
  // empty focus doesn't surface a misleading "first 8 alphabetical users"
  // dropdown — that was the original confusion behind "왜 delivery-hub-member 가
  // 검색이 안되지?".
  useEffect(() => {
    if (!isOpen || !token || !userQueryFocused) return;
    const trimmed = userQuery.trim();
    if (!trimmed) {
      setUsers([]);
      setUsersLoading(false);
      return;
    }
    let cancelled = false;
    setUsersLoading(true);
    const handle = window.setTimeout(() => {
      listMeetingUsers(token, workspaceSlug, { q: trimmed, limit: 30 })
        .then((response) => {
          if (!cancelled) setUsers(response);
        })
        .catch(() => {
          if (!cancelled) setUsers([]);
        })
        .finally(() => {
          if (!cancelled) setUsersLoading(false);
        });
    }, 100);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [isOpen, token, userQuery, userQueryFocused, workspaceSlug]);

  const userLookup = useMemo(() => {
    const map = new Map<string, MeetingUser>();
    pickedAttendeeUsers.forEach((user) => map.set(user.id, user));
    users.forEach((user) => map.set(user.id, user));
    return map;
  }, [users, pickedAttendeeUsers]);

  const filteredUsers = useMemo(() => {
    const selectedIds = new Set(attendees.map((item) => item.user_id));
    return users
      .filter((candidate) => candidate.id !== user?.id && !selectedIds.has(candidate.id))
      .slice(0, 8);
  }, [users, attendees, user?.id]);

  const visibleAttendees = useMemo(
    () => attendees.filter((attendee) => attendee.user_id !== user?.id),
    [attendees, user?.id],
  );
  const availabilityUsers = useMemo(
    () => visibleAttendees.map((attendee) => {
      const candidate = userLookup.get(attendee.user_id);
      return {
        id: attendee.user_id,
        email: candidate?.email ?? '',
        full_name: candidate?.full_name ?? attendee.user_id,
      };
    }),
    [userLookup, visibleAttendees],
  );

  function addAttendee(user: MeetingUser) {
    setAttendees((prev) => [
      ...prev,
      { user_id: user.id, role: 'required' },
    ]);
    setPickedAttendeeUsers((prev) =>
      prev.some((item) => item.id === user.id) ? prev : [...prev, user],
    );
    setUserQuery('');
  }

  function removeAttendee(userId: string) {
    if (userId === user?.id) {
      return;
    }
    setAttendees((prev) => prev.filter((item) => item.user_id !== userId));
  }

  function removePickedTask(taskId: string) {
    setPickedTasks((prev) => prev.filter((item) => item.id !== taskId));
  }

  function removePickedDoc(docId: string) {
    setPickedDocs((prev) => prev.filter((item) => item.id !== docId));
  }

  function handleFileInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    // Allow the same file to be re-picked later by resetting the input.
    event.target.value = '';
    if (files.length === 0) return;
    setPickedFiles((prev) => [...prev, ...files]);
  }

  function removePickedFile(index: number) {
    setPickedFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function handleCreate() {
    if (!token || !title.trim()) return;
    if (new Date(endAt) <= new Date(startAt)) {
      setError('종료 시각은 시작 시각보다 늦어야 합니다.');
      return;
    }
    setSubmitting(true);
    setError(null);
    setPartialFailures([]);
    try {
      const meeting = await createMeeting(token, workspaceSlug, {
        title: title.trim(),
        agenda: agenda.trim(),
        start_at: localInputToIso(startAt),
        end_at: localInputToIso(endAt),
        attendees,
        task_ids: pickedTasks.map((task) => task.id),
        doc_ids: pickedDocs.map((doc) => doc.id),
      });

      const failures: string[] = [];
      const succeededFileNames = new Set<string>();
      for (const file of pickedFiles) {
        try {
          await uploadMeetingFile(token, workspaceSlug, meeting.id, file);
          succeededFileNames.add(file.name);
        } catch (err) {
          failures.push(
            `파일 "${file.name}": ${err instanceof Error ? err.message : '실패'}`,
          );
        }
      }

      if (failures.length > 0) {
        // Drop successfully attached items so the remaining chips are the
        // ones the user still needs to address, and keep the modal open so
        // the error panel is visible. Task/doc attachment is now part of the
        // meeting create transaction, so only file uploads can partially fail.
        setPickedFiles((prev) =>
          prev.filter((f) => !succeededFileNames.has(f.name)),
        );
        setCreatedMeetingId(meeting.id);
        setPartialFailures(failures);
        setError(
          `회의는 만들어졌지만 일부 첨부에 실패했습니다. 남은 항목을 확인하세요.`,
        );
        return;
      }

      onCreated(meeting.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의 생성에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  function handleOpenCreatedMeeting() {
    if (!createdMeetingId) return;
    onCreated(createdMeetingId);
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="New Meeting"
      description="참석자와 연결된 업무를 포함해 새 회의를 만듭니다."
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            {createdMeetingId ? '닫기' : '취소'}
          </Button>
          {createdMeetingId ? (
            <Button variant="primary" onClick={handleOpenCreatedMeeting}>
              회의 보러 가기
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={!title.trim() || submitting}
            >
              {submitting ? '만드는 중...' : '회의 만들기'}
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-warning)]/40 bg-[var(--ui-color-warning)]/10 px-3 py-2 text-[var(--ui-color-warning)]"
          >
            <p>{error}</p>
            {partialFailures.length > 0 ? (
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[var(--ui-color-warning)]/90">
                {partialFailures.map((line, idx) => (
                  <li key={idx}>{line}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            제목 <span className="text-[var(--ui-color-danger)]">*</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예: Q2 로드맵 검토"
            maxLength={200}
            autoFocus
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>

        <div className="space-y-2">
          <label className="app-text-control-sm text-app-ink/70">연결된 업무</label>
          <p className="app-text-caption text-app-ink/40">
            이 회의에서 다룰 PMS 태스크, 문서, 첨부 파일을 미리 연결합니다.
          </p>
          {pickedTasks.length > 0 ||
          pickedDocs.length > 0 ||
          pickedFiles.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {pickedTasks.map((task) => (
                <span
                  key={`task-${task.id}`}
                  className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                >
                  <CheckSquare size={11} className="text-app-ink/40" />
                  <span className="max-w-[14rem] truncate">
                    {task.reference ? `${task.reference} · ` : ''}
                    {task.title}
                  </span>
                  <button
                    type="button"
                    onClick={() => removePickedTask(task.id)}
                    className="text-app-ink/40 hover:text-app-ink"
                    aria-label={`${task.title} 제거`}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
              {pickedDocs.map((doc) => (
                <span
                  key={`doc-${doc.id}`}
                  className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                >
                  <FileText size={11} className="text-app-ink/40" />
                  <span className="max-w-[14rem] truncate">{doc.title}</span>
                  <button
                    type="button"
                    onClick={() => removePickedDoc(doc.id)}
                    className="text-app-ink/40 hover:text-app-ink"
                    aria-label={`${doc.title} 제거`}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
              {pickedFiles.map((file, index) => (
                <span
                  key={`file-${index}-${file.name}`}
                  className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                >
                  <Paperclip size={11} className="text-app-ink/40" />
                  <span className="max-w-[14rem] truncate">
                    {file.name}
                  </span>
                  <span className="text-app-ink/40">
                    ({formatFileSize(file.size)})
                  </span>
                  <button
                    type="button"
                    onClick={() => removePickedFile(index)}
                    className="text-app-ink/40 hover:text-app-ink"
                    aria-label={`${file.name} 제거`}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          ) : null}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setTaskPickerOpen(true)}
              className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
            >
              <Plus size={12} />
              <CheckSquare size={12} />
              태스크
            </button>
            <button
              type="button"
              onClick={() => setDocPickerOpen(true)}
              className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
            >
              <Plus size={12} />
              <FileText size={12} />
              문서
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
            >
              <Plus size={12} />
              <Paperclip size={12} />
              파일
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleFileInputChange}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="app-text-control-sm text-app-ink/70">시작</label>
            <input
              type="datetime-local"
              value={startAt}
              onChange={(e) => setStartAt(e.target.value)}
              className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
            />
          </div>
          <div className="space-y-1">
            <label className="app-text-control-sm text-app-ink/70">종료</label>
            <input
              type="datetime-local"
              value={endAt}
              onChange={(e) => setEndAt(e.target.value)}
              className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
            />
          </div>
        </div>

        <MeetingAvailabilityPanel
          workspaceSlug={workspaceSlug}
          attendeeUsers={availabilityUsers}
          meetingStart={startAt ? new Date(startAt) : null}
          meetingEnd={endAt ? new Date(endAt) : null}
        />

        <div className="space-y-2">
          <label className="app-text-control-sm text-app-ink/70">참석자</label>
          <p className="app-text-caption text-app-ink/40">
            본인은 자동 참석자로 포함됩니다.
          </p>
          {visibleAttendees.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {visibleAttendees.map((attendee) => {
                const user = userLookup.get(attendee.user_id);
                return (
                  <span
                    key={attendee.user_id}
                    className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                  >
                    {user?.full_name ?? attendee.user_id}
                    <button
                      type="button"
                      onClick={() => removeAttendee(attendee.user_id)}
                      className="text-app-ink/40 hover:text-app-ink"
                      aria-label={`${user?.full_name ?? attendee.user_id} 제거`}
                    >
                      <X size={12} />
                    </button>
                  </span>
                );
              })}
            </div>
          ) : null}
          <input
            type="text"
            value={userQuery}
            onChange={(e) => setUserQuery(e.target.value)}
            onFocus={() => setUserQueryFocused(true)}
            onBlur={() => {
              // Delay so a click on the suggestion list still registers.
              window.setTimeout(() => setUserQueryFocused(false), 150);
            }}
            placeholder="이름 또는 이메일로 검색"
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
          {userQueryFocused ? (
            <div className="max-h-44 overflow-y-auto rounded-md border border-app-border bg-app-surface">
              {usersLoading && filteredUsers.length === 0 ? (
                <div className="app-text-caption px-3 py-2 text-app-ink/40">
                  검색 중...
                </div>
              ) : filteredUsers.length === 0 ? (
                <div className="app-text-caption px-3 py-2 text-app-ink/40">
                  {userQuery.trim()
                    ? '일치하는 사용자가 없습니다.'
                    : '이름 또는 이메일을 입력하세요.'}
                </div>
              ) : (
                <ul>
                  {filteredUsers.map((user) => (
                    <li key={user.id}>
                      <button
                        type="button"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => addAttendee(user)}
                        className="app-text-body flex w-full items-center justify-between px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <span>{user.full_name}</span>
                        <span className="app-text-caption text-app-ink/40">
                          {user.email}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            안건 <span className="text-app-ink/30">(선택)</span>
          </label>
          <textarea
            value={agenda}
            onChange={(e) => setAgenda(e.target.value)}
            rows={4}
            placeholder="회의에서 다룰 안건을 적어주세요."
            className="app-text-body w-full resize-none rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>
      </div>

      <TaskPickerModal
        isOpen={taskPickerOpen}
        onClose={() => setTaskPickerOpen(false)}
        workspaceSlug={workspaceSlug}
        excludeIssueIds={pickedTasks.map((task) => task.id)}
        onPick={(issue) => {
          setPickedTasks((prev) => [
            ...prev,
            {
              id: issue.id,
              title: issue.title,
              reference: issue.reference,
            },
          ]);
        }}
      />
      <DocPickerModal
        isOpen={docPickerOpen}
        onClose={() => setDocPickerOpen(false)}
        workspaceSlug={workspaceSlug}
        excludeDocIds={pickedDocs.map((doc) => doc.id)}
        onPick={(doc) => {
          setPickedDocs((prev) => [
            ...prev,
            { id: doc.source_id, title: doc.title },
          ]);
        }}
      />
    </Dialog>
  );
}
