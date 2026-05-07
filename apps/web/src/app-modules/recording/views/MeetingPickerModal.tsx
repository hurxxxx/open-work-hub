import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { formatDateTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
import { listMeetings, type MeetingListItem } from '@/src/app-modules/meeting/public-api';

// NOTE: listMeetings has no `q` param at the API layer, so search is
// client-side over the returned list. If a workspace accumulates more than a
// few hundred meetings this should switch to a server-side search endpoint.
interface MeetingPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (meeting: MeetingListItem) => Promise<void> | void;
  excludeMeetingIds?: string[];
  workspaceSlug: string;
}

export function MeetingPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeMeetingIds = [],
  workspaceSlug,
}: MeetingPickerModalProps) {
  const { t, i18n } = useTranslation('apps');
  const { token, user } = useAuth();
  const canAccess = hasWorkspaceMembership(user, workspaceSlug);
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [items, setItems] = useState<MeetingListItem[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !token || !canAccess) return;
    setQuery('');
    setError(null);
    setSubmittingId(null);
    let cancelled = false;
    setLoading(true);
    listMeetings(token, workspaceSlug, { scope: 'all' })
      .then((response) => {
        if (cancelled) return;
        const sorted = [...response.items].sort((a, b) => (a.start_at < b.start_at ? 1 : -1));
        setItems(sorted);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? t('recording.detail.meetingPicker.loadFailed'));
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token, canAccess, workspaceSlug, t]);

  const excludeSet = useMemo(() => new Set(excludeMeetingIds), [excludeMeetingIds]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((item) => !excludeSet.has(item.id))
      .filter((item) => (q ? item.title.toLowerCase().includes(q) : true))
      .slice(0, 50);
  }, [items, query, excludeSet]);

  async function handlePick(meeting: MeetingListItem) {
    setSubmittingId(meeting.id);
    setError(null);
    try {
      await onPick(meeting);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('recording.errors.attachFailed'));
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t('recording.detail.meetingPicker.title')}
      description={t('recording.detail.meetingPicker.description')}
      maxWidth="max-w-xl"
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>
            {t('common:actions.close')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        {!canAccess ? (
          <NoAccessNotice
            workspaceLabel={t('recording.title')}
            action={t('recording.detail.addMeeting')}
          />
        ) : null}

        {canAccess && error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        {canAccess ? (
          <>
            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">
                {t('common:actions.search')}
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('recording.detail.meetingPicker.searchPlaceholder')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
            </div>

            <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
              {loading ? (
                <div className="flex h-24 items-center justify-center text-app-ink/40">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              ) : filteredItems.length === 0 ? (
                <div className="px-4 py-6 text-center app-text-caption text-app-ink/50">
                  {t('recording.detail.meetingPicker.empty')}
                </div>
              ) : (
                <ul className="divide-y divide-app-border">
                  {filteredItems.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => handlePick(item)}
                        disabled={submittingId !== null}
                        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                      >
                        <div className="min-w-0">
                          <p className="app-text-body line-clamp-1 text-app-ink">
                            {item.title || t('recording.untitled')}
                          </p>
                          <p className="app-text-caption text-app-ink/40">
                            {formatDateTime(item.start_at, {
                              day: 'numeric',
                              hour: '2-digit',
                              locale: i18n.language,
                              minute: '2-digit',
                              month: 'short',
                              timeZone,
                            })}
                            {item.organizer_name ? ` · ${item.organizer_name}` : ''}
                          </p>
                        </div>
                        {submittingId === item.id ? (
                          <Loader2 size={14} className="animate-spin text-app-ink/40" />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}

export default MeetingPickerModal;
