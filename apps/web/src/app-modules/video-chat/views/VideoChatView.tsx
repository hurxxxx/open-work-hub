import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Copy, Loader2, Plus, RefreshCw, Video, VideoOff } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime as formatZonedDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  createVideoChatSession,
  listVideoChatSessions,
  type VideoChatSession,
} from '../api/video-chat-api';

function formatDateTime(
  value: string,
  timeZone: string,
  locale: string,
): string {
  return formatZonedDateTime(value, {
    dateStyle: 'medium',
    fallback: value,
    locale,
    timeStyle: 'short',
    timeZone,
  });
}

export function VideoChatView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug } = useParams();
  const navigate = useNavigate();
  const timeZone = normalizeTimeZone(user?.time_zone);

  const [sessions, setSessions] = useState<VideoChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const openSessions = useMemo(
    () => sessions.filter((session) => session.status === 'open'),
    [sessions],
  );
  const endedSessions = useMemo(
    () => sessions.filter((session) => session.status === 'ended').slice(0, 6),
    [sessions],
  );

  const refresh = useCallback(async () => {
    if (!workspaceSlug) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listVideoChatSessions(token, workspaceSlug);
      setSessions(response.items);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : t('apps:videoChat.errors.loadFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [t, token, workspaceSlug]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!workspaceSlug) {
    return null;
  }
  const activeWorkspaceSlug = workspaceSlug;

  async function handleCreate() {
    setCreating(true);
    setError(null);
    try {
      const session = await createVideoChatSession(token, activeWorkspaceSlug, {
        title: titleDraft.trim() || null,
      });
      setTitleDraft('');
      navigate(
        buildWorkspaceAppPath(activeWorkspaceSlug, 'video-chat', session.id),
      );
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : t('apps:videoChat.errors.createFailed'),
      );
    } finally {
      setCreating(false);
    }
  }

  function roomPath(session: VideoChatSession): string {
    return buildWorkspaceAppPath(activeWorkspaceSlug, 'video-chat', session.id);
  }

  async function copyInvite(session: VideoChatSession) {
    const url = `${window.location.origin}${roomPath(session)}`;
    try {
      await window.navigator.clipboard.writeText(url);
      setCopiedId(session.id);
      window.setTimeout(() => {
        setCopiedId((current) => (current === session.id ? null : current));
      }, 1400);
    } catch {
      setError(t('apps:videoChat.errors.copyFailed'));
    }
  }

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="flex flex-col gap-3 border-b border-app-border bg-app-surface px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <Video size={20} className="text-app-ink/60" />
          <div>
            <h1 className="app-text-title-md text-app-ink">
              {t('apps:videoChat.title')}
            </h1>
            <p className="app-text-caption text-app-ink/55">
              {t('apps:videoChat.subtitle')}
            </p>
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="min-w-0">
            <span className="sr-only">
              {t('apps:videoChat.createTitleLabel')}
            </span>
            <input
              value={titleDraft}
              onChange={(event) => setTitleDraft(event.target.value)}
              maxLength={200}
              className="h-9 w-full min-w-64 rounded-md border border-app-border bg-app-surface-raised px-3 app-text-body text-app-ink outline-none transition-colors placeholder:text-app-ink/35 focus:border-app-accent"
              placeholder={t('apps:videoChat.createTitlePlaceholder')}
            />
          </label>
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-[var(--ui-radius-sm)] border border-app-accent bg-app-accent px-3 app-text-body font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {creating ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Plus size={16} />
            )}
            <span>{t('apps:videoChat.createRoom')}</span>
          </button>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            title={t('apps:videoChat.refresh')}
            className="inline-flex h-9 w-9 items-center justify-center rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface-raised text-app-ink transition-colors hover:bg-app-surface-subtle disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto px-6 py-5">
        {error ? (
          <div className="mb-4 rounded-md border border-[var(--ui-color-danger)]/25 bg-[var(--ui-color-danger)]/8 px-3 py-2 app-text-body text-[var(--ui-color-danger)]">
            {error}
          </div>
        ) : null}

        <section className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="app-text-title-sm text-app-ink">
              {t('apps:videoChat.activeRooms')}
            </h2>
            <span className="app-text-caption text-app-ink/50">
              {t('apps:videoChat.roomCount', { count: openSessions.length })}
            </span>
          </div>
          {loading ? (
            <div className="flex h-44 items-center justify-center rounded-md border border-dashed border-app-border bg-app-surface/40">
              <Loader2 size={24} className="animate-spin text-app-ink/35" />
            </div>
          ) : openSessions.length === 0 ? (
            <div className="flex h-44 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface/40 px-6 text-center">
              <VideoOff size={32} className="text-app-ink/25" />
              <p className="app-text-title-sm text-app-ink">
                {t('apps:videoChat.emptyActiveTitle')}
              </p>
              <p className="app-text-caption text-app-ink/55">
                {t('apps:videoChat.emptyActiveBody')}
              </p>
            </div>
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              {openSessions.map((session) => (
                <RoomListItem
                  key={session.id}
                  copied={copiedId === session.id}
                  onCopy={() => void copyInvite(session)}
                  onJoin={() => navigate(roomPath(session))}
                  session={session}
                  startedAt={formatDateTime(
                    session.started_at,
                    timeZone,
                    i18n.language,
                  )}
                />
              ))}
            </div>
          )}
        </section>

        {endedSessions.length > 0 ? (
          <section>
            <h2 className="app-text-title-sm mb-3 text-app-ink">
              {t('apps:videoChat.recentRooms')}
            </h2>
            <div className="grid gap-2">
              {endedSessions.map((session) => (
                <article
                  key={session.id}
                  className="flex flex-col gap-2 rounded-md border border-app-border bg-app-surface px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="app-text-body truncate text-app-ink">
                      {session.title}
                    </p>
                    <p className="app-text-caption text-app-ink/55">
                      {formatDateTime(
                        session.started_at,
                        timeZone,
                        i18n.language,
                      )}
                    </p>
                  </div>
                  <span className="app-text-caption rounded border border-app-border bg-app-surface-raised px-2 py-1 text-app-ink/55">
                    {t('apps:videoChat.statusEnded')}
                  </span>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}

function RoomListItem({
  copied,
  onCopy,
  onJoin,
  session,
  startedAt,
}: {
  copied: boolean;
  onCopy: () => void;
  onJoin: () => void;
  session: VideoChatSession;
  startedAt: string;
}) {
  const { t } = useTranslation(['apps', 'common']);

  return (
    <article className="rounded-md border border-app-border bg-app-surface px-3 py-3 transition-colors hover:bg-app-surface-hover/60">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface-raised text-app-accent">
          <Video size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <h3 className="app-text-body truncate font-semibold text-app-ink">
              {session.title}
            </h3>
            <span className="app-text-caption shrink-0 rounded border border-app-success-border bg-app-success/10 px-1.5 py-0.5 text-app-success-text">
              {t('apps:videoChat.statusOpen')}
            </span>
          </div>
          <p className="app-text-caption mt-1 text-app-ink/55">
            {t('apps:videoChat.startedBy', {
              name: session.started_by_name,
              time: startedAt,
            })}
          </p>
          <p className="app-text-caption mt-1 truncate text-app-ink/40">
            {session.room_name}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCopy}
          title={t('apps:videoChat.copyInvite')}
          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface-raised px-2.5 text-[0.82rem] font-medium text-app-ink transition-colors hover:bg-app-surface-subtle"
        >
          <Copy size={14} />
          <span>
            {copied
              ? t('apps:videoChat.copied')
              : t('apps:videoChat.copyInvite')}
          </span>
        </button>
        <button
          type="button"
          onClick={onJoin}
          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-[var(--ui-radius-sm)] border border-app-accent bg-app-accent px-2.5 text-[0.82rem] font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover"
        >
          <Video size={14} />
          <span>{t('apps:videoChat.joinRoom')}</span>
        </button>
      </div>
    </article>
  );
}
