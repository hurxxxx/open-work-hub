// Lightweight modal for adding attendees to an existing meeting. Available to
// any current participant (organizer or existing attendee), unlike
// MeetingEditModal which is organizer-only and edits everything.
//
// Backed by POST /meeting/meetings/{id}/attendees which is participant-permissioned.
import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { X, UserPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  addMeetingAttendees,
  listMeetingUsers,
  type MeetingAttendeeInput,
  type MeetingDetail,
  type MeetingUser,
} from '../../api/meeting-api';

interface AddAttendeesModalProps {
  isOpen: boolean;
  meeting: MeetingDetail;
  workspaceSlug: string;
  onClose: () => void;
  onAdded: (updated: MeetingDetail) => void;
}

export function AddAttendeesModal({
  isOpen,
  meeting,
  workspaceSlug,
  onClose,
  onAdded,
}: AddAttendeesModalProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const [pending, setPending] = useState<MeetingAttendeeInput[]>([]);
  const [pendingMeta, setPendingMeta] = useState<Record<string, MeetingUser>>({});
  const [query, setQuery] = useState('');
  const [queryFocused, setQueryFocused] = useState(false);
  const [results, setResults] = useState<MeetingUser[]>([]);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state whenever the modal opens (so a new meeting context starts fresh).
  useEffect(() => {
    if (!isOpen) return;
    setPending([]);
    setPendingMeta({});
    setQuery('');
    setQueryFocused(false);
    setResults([]);
    setError(null);
    setSubmitting(false);
  }, [isOpen, meeting.id]);

  // Debounced server search.
  useEffect(() => {
    if (!isOpen || !token || !queryFocused) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const handle = window.setTimeout(() => {
      listMeetingUsers(token, workspaceSlug, { q: trimmed, limit: 30 })
        .then((response) => {
          if (!cancelled) setResults(response);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 100);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [isOpen, token, query, queryFocused, workspaceSlug]);

  // Hide users who are already meeting attendees + already in the pending bucket.
  const existingIds = useMemo(() => {
    const ids = new Set<string>();
    ids.add(meeting.organizer_id);
    for (const attendee of meeting.attendees) {
      ids.add(attendee.user_id);
    }
    return ids;
  }, [meeting.attendees, meeting.organizer_id]);

  const candidates = useMemo(() => {
    const pendingIds = new Set(pending.map((item) => item.user_id));
    return results
      .filter((candidate) => !existingIds.has(candidate.id) && !pendingIds.has(candidate.id))
      .slice(0, 8);
  }, [results, existingIds, pending]);

  function addCandidate(candidate: MeetingUser) {
    setPending((prev) => [...prev, { user_id: candidate.id, role: 'required' }]);
    setPendingMeta((prev) => ({ ...prev, [candidate.id]: candidate }));
    setQuery('');
    setResults([]);
  }

  function removePending(userId: string) {
    setPending((prev) => prev.filter((item) => item.user_id !== userId));
  }

  async function handleSave() {
    if (!token || pending.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await addMeetingAttendees(
        token,
        workspaceSlug,
        meeting.id,
        pending,
      );
      onAdded(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.addAttendees.failed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t('meeting.addAttendees.title')}
      description={t('meeting.addAttendees.description')}
      maxWidth="max-w-md"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            {t('common:actions.cancel')}
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={pending.length === 0 || submitting}
          >
            {submitting
              ? t('meeting.addAttendees.adding')
              : t('meeting.addAttendees.addCount', { count: pending.length })}
          </Button>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        <div className="space-y-2">
          <label className="app-text-overline block text-app-ink/60" htmlFor="add-attendee-search">
            {t('meeting.addAttendees.searchLabel')}
          </label>
          <div className="relative">
            <input
              id="add-attendee-search"
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onFocus={() => setQueryFocused(true)}
              onBlur={() => window.setTimeout(() => setQueryFocused(false), 150)}
              placeholder={t('meeting.addAttendees.searchPlaceholder')}
              className="app-text-body w-full rounded-md border border-app-border bg-app-surface px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              autoComplete="off"
            />
            {queryFocused && query.trim() ? (
              <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-md border border-app-border bg-app-surface shadow-lg">
                {searching ? (
                  <div className="app-text-caption px-3 py-2 text-app-ink/50">
                    {t('meeting.addAttendees.searching')}
                  </div>
                ) : candidates.length === 0 ? (
                  <div className="app-text-caption px-3 py-2 text-app-ink/50">
                    {t('common:empty.noResults')}
                  </div>
                ) : (
                  <ul>
                    {candidates.map((candidate) => (
                      <li key={candidate.id}>
                        <button
                          type="button"
                          onMouseDown={(event) => {
                            // Prevent input blur from closing the dropdown
                            // before the click registers.
                            event.preventDefault();
                          }}
                          onClick={() => addCandidate(candidate)}
                          className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-app-surface-hover"
                        >
                          <div className="min-w-0">
                            <p className="app-text-body line-clamp-1 text-app-ink">
                              {candidate.full_name}
                            </p>
                            <p className="app-text-caption text-app-ink/50">
                              {candidate.email}
                            </p>
                          </div>
                          <UserPlus size={14} className="shrink-0 text-app-accent" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </div>
        </div>

        <div className="space-y-2">
          <div className="app-text-overline text-app-ink/60">
            {t('meeting.addAttendees.pendingCount', { count: pending.length })}
          </div>
          {pending.length === 0 ? (
            <div className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-center text-app-ink/40">
              {t('meeting.addAttendees.noneSelected')}
            </div>
          ) : (
            <ul className="space-y-1">
              {pending.map((item) => {
                const meta = pendingMeta[item.user_id];
                return (
                  <li
                    key={item.user_id}
                    className="flex items-center justify-between gap-2 rounded-md bg-app-surface-sidebar px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="app-text-body line-clamp-1 text-app-ink">
                        {meta?.full_name ?? item.user_id}
                      </p>
                      <p className="app-text-caption text-app-ink/50">
                        {meta?.email ?? ''}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removePending(item.user_id)}
                      aria-label={t('meeting.addAttendees.remove')}
                      className="rounded p-1 text-app-ink/40 hover:bg-app-surface-hover hover:text-app-ink"
                    >
                      <X size={14} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Dialog>
  );
}
