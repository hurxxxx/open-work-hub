import { Loader2, Megaphone, Pencil, Pin, Plus, Trash2, X } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import {
  createAnnouncement,
  deleteAnnouncement,
  listAnnouncements,
  updateAnnouncement,
  type Announcement,
  type AnnouncementScope,
} from '@/src/app-modules/announcements/public-api';
import { hasAnySystemRole } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

function AnnouncementRow({
  announcement,
  timeZone,
  locale,
  onSelect,
}: {
  announcement: Announcement;
  timeZone: string;
  locale: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="-mx-2 flex w-full items-center gap-3 border-b border-app-border px-2 py-3 text-left transition-colors last:border-b-0 hover:bg-app-surface-hover"
    >
      {announcement.isPinned ? (
        <Pin size={15} className="shrink-0 text-app-accent" />
      ) : (
        <Megaphone size={15} className="shrink-0 text-app-ink/45" />
      )}
      <span className="app-text-body min-w-0 flex-1 truncate text-app-ink">
        {announcement.title}
      </span>
      <span className="app-text-caption shrink-0 text-app-ink/55">
        {announcement.authorName}
      </span>
      <span className="app-text-caption shrink-0 text-app-ink/45">
        {formatDateTime(announcement.createdAt, {
          locale,
          month: 'short',
          day: 'numeric',
          timeZone,
        })}
      </span>
    </button>
  );
}

function AnnouncementEditorModal({
  scope,
  title,
  announcement,
  onClose,
  onSaved,
}: {
  scope: AnnouncementScope;
  title: string;
  announcement: Announcement | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();

  const isEdit = announcement !== null;
  const [draftTitle, setDraftTitle] = useState(announcement?.title ?? '');
  const [body, setBody] = useState(announcement?.body ?? '');
  const [pinned, setPinned] = useState(announcement?.isPinned ?? false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || !draftTitle.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (isEdit) {
        await updateAnnouncement(token, announcement.id, {
          title: draftTitle.trim(),
          body: body.trim(),
          isPinned: pinned,
        });
      } else {
        await createAnnouncement(token, {
          title: draftTitle.trim(),
          body: body.trim(),
          scope,
          isPinned: pinned,
        });
      }
      onSaved();
    } catch {
      setError(
        isEdit
          ? t('home.announcementUpdateError')
          : t('home.announcementSubmitError'),
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl border border-app-border bg-app-surface p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="app-text-title-md text-app-ink">
            {isEdit
              ? t('home.announcementEditTitle')
              : t('home.announcementCreate')}{' '}
            · {title}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-app-ink/45 transition-colors hover:text-app-ink"
            aria-label={t('home.announcementCancel')}
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <input
            type="text"
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            placeholder={t('home.announcementTitlePlaceholder')}
            maxLength={200}
            autoFocus
            className="app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none focus:border-app-accent"
          />
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder={t('home.announcementBodyPlaceholder')}
            rows={5}
            className="app-text-body w-full resize-none rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none focus:border-app-accent"
          />
          <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
            <input
              type="checkbox"
              checked={pinned}
              onChange={(event) => setPinned(event.target.checked)}
            />
            {t('home.announcementPin')}
          </label>
          {error ? (
            <p className="app-text-caption text-app-danger">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="app-text-body-sm rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              {t('home.announcementCancel')}
            </button>
            <button
              type="submit"
              disabled={!draftTitle.trim() || submitting}
              className="app-text-body-sm flex items-center gap-1.5 rounded-md bg-app-accent px-3 py-2 text-app-accent-fg transition-opacity disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : null}
              {t('home.announcementSubmit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AnnouncementDetailModal({
  announcement,
  timeZone,
  locale,
  canManage,
  onClose,
  onEdit,
  onDeleted,
}: {
  announcement: Announcement;
  timeZone: string;
  locale: string;
  canManage: boolean;
  onClose: () => void;
  onEdit: () => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();

  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    if (!token || deleting) return;
    if (!window.confirm(t('home.announcementDeleteConfirm'))) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteAnnouncement(token, announcement.id);
      onDeleted();
    } catch {
      setError(t('home.announcementDeleteError'));
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[80vh] w-full max-w-md flex-col rounded-xl border border-app-border bg-app-surface p-5 shadow-xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2">
            {announcement.isPinned ? (
              <Pin size={16} className="mt-0.5 shrink-0 text-app-accent" />
            ) : (
              <Megaphone
                size={16}
                className="mt-0.5 shrink-0 text-app-ink/45"
              />
            )}
            <h3 className="app-text-title-md break-words text-app-ink">
              {announcement.title}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-app-ink/45 transition-colors hover:text-app-ink"
            aria-label={t('home.announcementClose')}
          >
            <X size={18} />
          </button>
        </div>
        <div className="app-text-caption mb-3 flex items-center gap-2 text-app-ink/55">
          <span>{announcement.authorName}</span>
          <span>·</span>
          <span>
            {formatDateTime(announcement.createdAt, {
              locale,
              year: 'numeric',
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              timeZone,
            })}
          </span>
        </div>
        <div className="app-text-body min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap break-words text-app-ink">
          {announcement.body.trim() ? (
            announcement.body
          ) : (
            <span className="text-app-ink/55">
              {t('home.announcementNoBody')}
            </span>
          )}
        </div>
        {error ? (
          <p className="app-text-caption mt-3 text-app-danger">{error}</p>
        ) : null}
        {canManage ? (
          <div className="mt-4 flex justify-end gap-2 border-t border-app-border pt-3">
            <button
              type="button"
              onClick={remove}
              disabled={deleting}
              className="app-text-body-sm flex items-center gap-1.5 rounded-md border border-app-border px-3 py-2 text-app-danger transition-colors hover:bg-app-surface-hover disabled:opacity-50"
            >
              {deleting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Trash2 size={14} />
              )}
              {t('home.announcementDelete')}
            </button>
            <button
              type="button"
              onClick={onEdit}
              className="app-text-body-sm flex items-center gap-1.5 rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <Pencil size={14} className="text-app-ink/55" />
              {t('home.announcementEdit')}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function AnnouncementsBoard({
  scope,
  title,
}: {
  scope: AnnouncementScope;
  title: string;
}) {
  const { t, i18n } = useTranslation('apps');
  const { token, user } = useAuth();

  const timeZone = normalizeTimeZone(user?.time_zone);
  const canManage = hasAnySystemRole(user, ['platform_admin']);

  const [items, setItems] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Announcement | null>(null);
  const [editing, setEditing] = useState<Announcement | null>(null);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    setLoading(true);
    listAnnouncements(token, { scope, limit: 8 })
      .then((response) => {
        if (!cancelled) setItems(response.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, scope, reloadKey]);

  const reload = () => setReloadKey((key) => key + 1);

  return (
    <section className="flex h-full flex-col rounded-lg border border-app-border bg-app-surface p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Megaphone size={16} className="shrink-0 text-app-accent" />
          <h2 className="app-text-title-md truncate text-app-ink">{title}</h2>
        </div>
        {canManage ? (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="app-text-caption flex shrink-0 items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink transition-colors hover:border-app-accent/40 hover:bg-app-surface-hover"
          >
            <Plus size={12} className="text-app-ink/55" />
            {t('home.announcementCreate')}
          </button>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex justify-center py-6">
            <Loader2 size={16} className="animate-spin text-app-ink/45" />
          </div>
        ) : items.length === 0 ? (
          <p className="app-text-body py-6 text-center text-app-ink/55">
            {t('home.announcementsEmpty')}
          </p>
        ) : (
          items.map((announcement) => (
            <AnnouncementRow
              key={announcement.id}
              announcement={announcement}
              timeZone={timeZone}
              locale={i18n.language}
              onSelect={() => setSelected(announcement)}
            />
          ))
        )}
      </div>
      {creating ? (
        <AnnouncementEditorModal
          scope={scope}
          title={title}
          announcement={null}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            reload();
          }}
        />
      ) : null}
      {editing ? (
        <AnnouncementEditorModal
          scope={scope}
          title={title}
          announcement={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setSelected(null);
            reload();
          }}
        />
      ) : null}
      {selected && !editing ? (
        <AnnouncementDetailModal
          announcement={selected}
          timeZone={timeZone}
          locale={i18n.language}
          canManage={canManage}
          onClose={() => setSelected(null)}
          onEdit={() => setEditing(selected)}
          onDeleted={() => {
            setSelected(null);
            reload();
          }}
        />
      ) : null}
    </section>
  );
}
