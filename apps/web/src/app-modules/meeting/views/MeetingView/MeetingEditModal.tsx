import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  listMeetingUsers,
  parseServerDateTime,
  updateMeeting,
  type MeetingAttendeeInput,
  type MeetingDetail,
  type MeetingUser,
} from '../../api/meeting-api';

import { MeetingAvailabilityPanel } from './MeetingAvailabilityPanel';

interface MeetingEditModalProps {
  isOpen: boolean;
  meeting: MeetingDetail;
  onClose: () => void;
  onSaved: (updated: MeetingDetail) => void;
  workspaceSlug: string;
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
  workspaceSlug,
}: MeetingEditModalProps) {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
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
    knownUsers.forEach((user) => map.set(user.id, user));
    users.forEach((user) => map.set(user.id, user));
    return map;
  }, [knownUsers, users]);

  const filteredUsers = useMemo(() => {
    const selectedIds = new Set(attendees.map((item) => item.user_id));
    return users
      .filter((candidate) => {
        if (selectedIds.has(candidate.id)) return false;
        if (user?.id === meeting.organizer_id && candidate.id === meeting.organizer_id) {
          return false;
        }
        return true;
      })
      .slice(0, 8);
  }, [users, attendees, meeting.organizer_id, user?.id]);

  const visibleAttendees = useMemo(() => {
    if (user?.id !== meeting.organizer_id) {
      return attendees;
    }
    return attendees.filter((attendee) => attendee.user_id !== meeting.organizer_id);
  }, [attendees, meeting.organizer_id, user?.id]);
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
      setError(t('meeting.form.endAfterStart'));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateMeeting(token, workspaceSlug, meeting.id, {
        title: title.trim(),
        agenda: agenda,
        start_at: localInputToIso(startAt),
        end_at: localInputToIso(endAt),
        attendees,
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.editMeeting.failed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t('meeting.editMeeting.title')}
      description={t('meeting.editMeeting.description')}
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>{t('common:actions.cancel')}</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={!title.trim() || submitting}
          >
            {submitting ? t('meeting.editMeeting.saving') : t('meeting.editMeeting.saveChanges')}
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
            {t('meeting.form.title')} <span className="text-[var(--ui-color-danger)]">*</span>
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
            <label className="app-text-control-sm text-app-ink/70">
              {t('meeting.form.start')}
            </label>
            <input
              type="datetime-local"
              value={startAt}
              onChange={(e) => setStartAt(e.target.value)}
              className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
            />
          </div>
          <div className="space-y-1">
            <label className="app-text-control-sm text-app-ink/70">
              {t('meeting.form.end')}
            </label>
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
          timeZone={user?.time_zone}
        />

        <div className="space-y-2">
          <label className="app-text-control-sm text-app-ink/70">
            {t('meeting.form.attendees')}
          </label>
          {user?.id === meeting.organizer_id ? (
            <p className="app-text-caption text-app-ink/40">
              {t('meeting.form.attendeeAutoIncluded')}
            </p>
          ) : null}
          {visibleAttendees.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {visibleAttendees.map((attendee) => {
                const user = userLookup.get(attendee.user_id);
                const isOrganizer = attendee.user_id === meeting.organizer_id;
                return (
                  <span
                    key={attendee.user_id}
                    className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                  >
                    {user?.full_name ?? attendee.user_id}
                    {isOrganizer ? (
                      <span className="text-app-ink/40">· {t('meeting.form.organizer')}</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => removeAttendee(attendee.user_id)}
                        className="text-app-ink/40 hover:text-app-ink"
                        aria-label={t('meeting.form.removeItem', {
                          name: user?.full_name ?? attendee.user_id,
                        })}
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
            placeholder={t('meeting.form.searchUsersPlaceholder')}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
          {userQueryFocused ? (
            <div className="max-h-44 overflow-y-auto rounded-md border border-app-border bg-app-surface">
              {usersLoading && filteredUsers.length === 0 ? (
                <div className="app-text-caption px-3 py-2 text-app-ink/40">
                  {t('meeting.form.searchingUsers')}
                </div>
              ) : filteredUsers.length === 0 ? (
                <div className="app-text-caption px-3 py-2 text-app-ink/40">
                  {userQuery.trim()
                    ? t('meeting.form.noUserMatch')
                    : t('meeting.form.searchUsersPrompt')}
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
            {t('meeting.form.agenda')}{' '}
            <span className="text-app-ink/30">({t('meeting.form.optional')})</span>
          </label>
          <textarea
            value={agenda}
            onChange={(e) => setAgenda(e.target.value)}
            rows={4}
            placeholder={t('meeting.form.agendaPlaceholder')}
            className="app-text-body w-full resize-none rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>
      </div>
    </Dialog>
  );
}
