import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { X } from 'lucide-react';

import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listMeetingUsers,
  parseServerDateTime,
  updateMeeting,
  type MeetingAttendeeInput,
  type MeetingDetail,
  type MeetingUser,
} from '@/src/domains/meeting/meeting-api';

interface MeetingEditModalProps {
  isOpen: boolean;
  meeting: MeetingDetail;
  onClose: () => void;
  onSaved: (updated: MeetingDetail) => void;
}

function toLocalInputValue(iso: string): string {
  // Convert an ISO datetime back into a YYYY-MM-DDTHH:mm value the
  // <input type="datetime-local"> control accepts. We render in local time
  // so the user edits in their wall clock.
  const date = parseServerDateTime(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

export function MeetingEditModal({
  isOpen,
  meeting,
  onClose,
  onSaved,
}: MeetingEditModalProps) {
  const { token } = useAuth();
  const [title, setTitle] = useState(meeting.title);
  const [agenda, setAgenda] = useState(meeting.agenda);
  const [startAt, setStartAt] = useState(toLocalInputValue(meeting.start_at));
  const [endAt, setEndAt] = useState(toLocalInputValue(meeting.end_at));
  const [attendees, setAttendees] = useState<MeetingAttendeeInput[]>(
    meeting.attendees.map((attendee) => ({
      user_id: attendee.user_id,
      role: attendee.role,
    })),
  );
  const [knownUsers, setKnownUsers] = useState<MeetingUser[]>(
    meeting.attendees.map((attendee) => ({
      id: attendee.user_id,
      email: attendee.email,
      full_name: attendee.full_name,
    })),
  );
  const [users, setUsers] = useState<MeetingUser[]>([]);
  const [userQuery, setUserQuery] = useState('');
  const [userQueryFocused, setUserQueryFocused] = useState(false);
  const [usersLoading, setUsersLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset all form state when the modal opens or the underlying meeting
  // changes — guards against stale values when the user edits a different
  // meeting in the same session.
  useEffect(() => {
    if (!isOpen) return;
    setTitle(meeting.title);
    setAgenda(meeting.agenda);
    setStartAt(toLocalInputValue(meeting.start_at));
    setEndAt(toLocalInputValue(meeting.end_at));
    setAttendees(
      meeting.attendees.map((attendee) => ({
        user_id: attendee.user_id,
        role: attendee.role,
      })),
    );
    setKnownUsers(
      meeting.attendees.map((attendee) => ({
        id: attendee.user_id,
        email: attendee.email,
        full_name: attendee.full_name,
      })),
    );
    setUsers([]);
    setUserQuery('');
    setUserQueryFocused(false);
    setError(null);
    setSubmitting(false);
  }, [isOpen, meeting]);

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
      listMeetingUsers(token, { q: trimmed, limit: 30 })
        .then((response) => {
          if (!cancelled) setUsers(response);
        })
        .catch(() => {
          if (!cancelled) setUsers([]);
        })
        .finally(() => {
          if (!cancelled) setUsersLoading(false);
        });
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [isOpen, token, userQuery, userQueryFocused]);

  const userLookup = useMemo(() => {
    const map = new Map<string, MeetingUser>();
    knownUsers.forEach((user) => map.set(user.id, user));
    users.forEach((user) => map.set(user.id, user));
    return map;
  }, [knownUsers, users]);

  const filteredUsers = useMemo(() => {
    const selectedIds = new Set(attendees.map((item) => item.user_id));
    return users.filter((user) => !selectedIds.has(user.id)).slice(0, 8);
  }, [users, attendees]);

  function addAttendee(user: MeetingUser) {
    setAttendees((prev) => [
      ...prev,
      { user_id: user.id, role: 'required' },
    ]);
    setKnownUsers((prev) =>
      prev.some((item) => item.id === user.id) ? prev : [...prev, user],
    );
    setUserQuery('');
  }

  function removeAttendee(userId: string) {
    if (userId === meeting.organizer_id) {
      // The organizer is always reinjected by the backend; surfacing this as
      // a UI rule keeps the form honest.
      return;
    }
    setAttendees((prev) => prev.filter((item) => item.user_id !== userId));
  }

  async function handleSave() {
    if (!token || !title.trim()) return;
    if (new Date(endAt) <= new Date(startAt)) {
      setError('종료 시각은 시작 시각보다 늦어야 합니다.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateMeeting(token, meeting.id, {
        title: title.trim(),
        agenda: agenda,
        start_at: localInputToIso(startAt),
        end_at: localInputToIso(endAt),
        attendees,
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의를 수정할 수 없습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Edit Meeting"
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>취소</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={!title.trim() || submitting}
          >
            {submitting ? '저장 중...' : '변경 저장'}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-warning)]/40 bg-[var(--ui-color-warning)]/10 px-3 py-2 text-[var(--ui-color-warning)]"
          >
            {error}
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
            maxLength={200}
            autoFocus
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
          />
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

        <div className="space-y-2">
          <label className="app-text-control-sm text-app-ink/70">참석자</label>
          {attendees.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {attendees.map((attendee) => {
                const user = userLookup.get(attendee.user_id);
                const isOrganizer = attendee.user_id === meeting.organizer_id;
                return (
                  <span
                    key={attendee.user_id}
                    className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                  >
                    {user?.full_name ?? attendee.user_id}
                    {isOrganizer ? (
                      <span className="text-app-ink/40">· 주최자</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => removeAttendee(attendee.user_id)}
                        className="text-app-ink/40 hover:text-app-ink"
                        aria-label={`${user?.full_name ?? attendee.user_id} 제거`}
                      >
                        <X size={12} />
                      </button>
                    )}
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
    </Dialog>
  );
}
