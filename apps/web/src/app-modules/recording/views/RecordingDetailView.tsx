import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  FileText,
  Link2,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Trash2,
} from 'lucide-react';
import { Button } from '@aidoo/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  attachRecordingContainer,
  detachRecordingContainer,
  fetchRecordingPlaybackBlobUrl,
  getRecording,
  getRecordingPlaybackUrl,
  retryRecording,
  updateRecording,
  type Recording,
  type RecordingContainer,
} from '../api/recording-api';

type StatusKey = 'done' | 'failed' | 'creating' | 'transcribing' | 'pending';
type ContainerApp = 'meeting' | 'pms' | 'docs';

function processingStatusKey(value: string): StatusKey {
  if (value === 'done' || value === 'failed' || value === 'creating' || value === 'transcribing') {
    return value;
  }
  return 'pending';
}

function statusTone(key: StatusKey): 'saved' | 'pending' | 'failed' {
  if (key === 'done') return 'saved';
  if (key === 'failed') return 'failed';
  return 'pending';
}

function statusIcon(key: StatusKey): ReactNode {
  if (key === 'done') return <CheckCircle2 size={13} />;
  if (key === 'failed') return <AlertCircle size={13} />;
  return <Clock3 size={13} />;
}

function formatDateTime(value: string, timeZone: string, locale: string): string {
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date);
}

function defaultContainerType(app: ContainerApp): string {
  if (app === 'meeting') return 'meeting';
  if (app === 'pms') return 'issue';
  return 'native_doc';
}

function containerHref(workspaceSlug: string, container: RecordingContainer): string | null {
  if (container.container_app === 'meeting') {
    return buildWorkspaceAppPath(workspaceSlug, 'meeting', container.container_id);
  }
  if (container.container_app === 'pms') {
    return buildWorkspaceAppPath(workspaceSlug, 'pms', container.container_id);
  }
  if (container.container_app === 'docs') {
    return buildWorkspaceAppPath(workspaceSlug, 'docs', container.container_id);
  }
  return null;
}

export function RecordingDetailView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug, recordingId } = useParams();
  const navigate = useNavigate();
  const timeZone = normalizeTimeZone(user?.time_zone);

  const [recording, setRecording] = useState<Recording | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [containerApp, setContainerApp] = useState<ContainerApp>('meeting');
  const [containerId, setContainerId] = useState('');
  const [primaryAttach, setPrimaryAttach] = useState(false);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const containerType = useMemo(() => defaultContainerType(containerApp), [containerApp]);
  const containers = recording?.containers ?? [];

  const refresh = useCallback(async () => {
    if (!token || !workspaceSlug || !recordingId) return;
    setLoading(true);
    setError(null);
    try {
      const next = await getRecording(token, workspaceSlug, recordingId);
      setRecording(next);
      setTitleDraft(next.title ?? '');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.loadDetailFailed'));
    } finally {
      setLoading(false);
    }
  }, [recordingId, t, token, workspaceSlug]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(
    () => () => {
      if (playbackUrl?.startsWith('blob:')) URL.revokeObjectURL(playbackUrl);
    },
    [playbackUrl],
  );

  async function handleSaveTitle() {
    if (!token || !workspaceSlug || !recording) return;
    setBusy('title');
    setError(null);
    try {
      const next = await updateRecording(token, workspaceSlug, recording.id, {
        title: titleDraft.trim() || null,
      });
      setRecording(next);
      setTitleDraft(next.title ?? '');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.updateFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function handlePlayback() {
    if (!token || !workspaceSlug || !recording || playbackUrl) return;
    setBusy('playback');
    setError(null);
    try {
      const playback = await getRecordingPlaybackUrl(token, workspaceSlug, recording.id);
      setPlaybackUrl(await fetchRecordingPlaybackBlobUrl(token, playback.url));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.playbackFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function handleRetry() {
    if (!token || !workspaceSlug || !recording) return;
    setBusy('retry');
    setError(null);
    try {
      const next = await retryRecording(token, workspaceSlug, recording.id);
      setRecording(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.retryFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function handleAttach() {
    if (!token || !workspaceSlug || !recording || !containerId.trim()) return;
    setBusy('attach');
    setError(null);
    try {
      const next = await attachRecordingContainer(token, workspaceSlug, recording.id, {
        container_app: containerApp,
        container_type: containerType,
        container_id: containerId.trim(),
        is_primary: primaryAttach,
      });
      setRecording(next);
      setContainerId('');
      setPrimaryAttach(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.attachFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function handleDetach(container: RecordingContainer) {
    if (!token || !workspaceSlug || !recording) return;
    setBusy(container.id);
    setError(null);
    try {
      const next = await detachRecordingContainer(token, workspaceSlug, recording.id, container.id);
      setRecording(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.detachFailed'));
    } finally {
      setBusy(null);
    }
  }

  if (!workspaceSlug) return null;

  const transcriptKey = processingStatusKey(recording?.transcript_status ?? 'pending');
  const rawDocKey = processingStatusKey(recording?.raw_transcript_doc_status ?? 'pending');
  const minutesDocKey = processingStatusKey(recording?.minutes_doc_status ?? 'pending');
  const retryable = transcriptKey === 'failed' || rawDocKey === 'failed' || minutesDocKey === 'failed';

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(buildWorkspaceAppPath(workspaceSlug, 'recording'))}
            className="inline-flex h-8 w-8 items-center justify-center rounded border border-app-border bg-app-surface-raised text-app-ink hover:bg-app-surface-subtle"
            aria-label={t('apps:recording.detail.back')}
          >
            <ArrowLeft size={16} />
          </button>
          <div className="min-w-0">
            <h1 className="app-text-title-md truncate text-app-ink">
              {recording?.title?.trim() || t('apps:recording.untitled')}
            </h1>
            {recording ? (
              <p className="app-text-caption text-app-ink/60">
                {formatDateTime(recording.started_at, timeZone, i18n.language)}
              </p>
            ) : null}
          </div>
        </div>
        <Button variant="secondary" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'mr-1 animate-spin' : 'mr-1'} />
          {t('common:actions.reload')}
        </Button>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        {error ? (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {!recording && loading ? (
          <div className="flex h-64 items-center justify-center text-app-ink/50">
            <Loader2 size={22} className="animate-spin" />
          </div>
        ) : null}

        {recording ? (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <section className="space-y-5">
              <div className="rounded-md border border-app-border bg-app-surface p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-end">
                  <label className="min-w-0 flex-1">
                    <span className="app-text-caption mb-1 block text-app-ink/60">
                      {t('apps:recording.detail.titleLabel')}
                    </span>
                    <input
                      value={titleDraft}
                      onChange={(event) => setTitleDraft(event.target.value)}
                      className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink outline-none transition-colors focus:border-app-accent"
                    />
                  </label>
                  <Button onClick={() => void handleSaveTitle()} disabled={busy === 'title'}>
                    {busy === 'title' ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />}
                    {t('common:actions.save')}
                  </Button>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <StatusPill icon={<CheckCircle2 size={13} />} label={t('apps:recording.status.audioSaved')} tone="saved" />
                  <StatusPill icon={statusIcon(transcriptKey)} label={t(`apps:recording.status.transcript.${transcriptKey}`)} tone={statusTone(transcriptKey)} />
                  <StatusPill icon={statusIcon(rawDocKey)} label={t(`apps:recording.status.rawTranscriptDoc.${rawDocKey}`)} tone={statusTone(rawDocKey)} />
                  <StatusPill icon={statusIcon(minutesDocKey)} label={t(`apps:recording.status.minutesDoc.${minutesDocKey}`)} tone={statusTone(minutesDocKey)} />
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button variant="secondary" onClick={() => void handlePlayback()} disabled={busy === 'playback' || Boolean(playbackUrl)}>
                    {busy === 'playback' ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Play size={14} className="mr-1" />}
                    {t('apps:recording.actions.play')}
                  </Button>
                  {retryable ? (
                    <Button variant="secondary" onClick={() => void handleRetry()} disabled={busy === 'retry'}>
                      {busy === 'retry' ? <Loader2 size={14} className="mr-1 animate-spin" /> : <RefreshCw size={14} className="mr-1" />}
                      {t('apps:recording.actions.retry')}
                    </Button>
                  ) : null}
                </div>

                {playbackUrl ? <audio controls src={playbackUrl} className="mt-4 w-full" /> : null}
                {recording.failure_reason ? (
                  <p className="app-text-caption mt-3 text-[var(--ui-color-danger)]">
                    {recording.failure_reason}
                  </p>
                ) : null}
              </div>

              <div className="rounded-md border border-app-border bg-app-surface p-4">
                <h2 className="app-text-title-sm text-app-ink">{t('apps:recording.detail.generatedDocs')}</h2>
                <div className="mt-3 grid gap-2">
                  <DocLink
                    docId={recording.raw_transcript_doc_id}
                    label={t('apps:recording.detail.rawTranscriptDoc')}
                    workspaceSlug={workspaceSlug}
                  />
                  <DocLink
                    docId={recording.minutes_doc_id}
                    label={t('apps:recording.detail.minutesDoc')}
                    workspaceSlug={workspaceSlug}
                  />
                </div>
              </div>
            </section>

            <aside className="space-y-5">
              <div className="rounded-md border border-app-border bg-app-surface p-4">
                <h2 className="app-text-title-sm text-app-ink">{t('apps:recording.detail.attachTitle')}</h2>
                <div className="mt-3 grid gap-3">
                  <label className="block">
                    <span className="app-text-caption mb-1 block text-app-ink/60">
                      {t('apps:recording.detail.attachApp')}
                    </span>
                    <select
                      value={containerApp}
                      onChange={(event) => setContainerApp(event.target.value as ContainerApp)}
                      className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink"
                    >
                      <option value="meeting">{t('apps:recording.detail.containerApps.meeting')}</option>
                      <option value="pms">{t('apps:recording.detail.containerApps.pms')}</option>
                      <option value="docs">{t('apps:recording.detail.containerApps.docs')}</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="app-text-caption mb-1 block text-app-ink/60">
                      {t('apps:recording.detail.attachObjectId')}
                    </span>
                    <input
                      value={containerId}
                      onChange={(event) => setContainerId(event.target.value)}
                      placeholder={t('apps:recording.detail.attachObjectIdPlaceholder')}
                      className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink outline-none transition-colors focus:border-app-accent"
                    />
                  </label>
                  <label className="app-text-caption inline-flex items-center gap-2 text-app-ink/70">
                    <input
                      type="checkbox"
                      checked={primaryAttach}
                      onChange={(event) => setPrimaryAttach(event.target.checked)}
                    />
                    {t('apps:recording.detail.primaryAttach')}
                  </label>
                  <Button onClick={() => void handleAttach()} disabled={busy === 'attach' || !containerId.trim()}>
                    {busy === 'attach' ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Link2 size={14} className="mr-1" />}
                    {t('apps:recording.detail.attach')}
                  </Button>
                </div>
              </div>

              <div className="rounded-md border border-app-border bg-app-surface p-4">
                <h2 className="app-text-title-sm text-app-ink">{t('apps:recording.detail.connectedObjects')}</h2>
                <div className="mt-3 grid gap-2">
                  {containers.length === 0 ? (
                    <p className="app-text-caption text-app-ink/60">{t('apps:recording.detail.noContainers')}</p>
                  ) : (
                    containers.map((container) => (
                      <ContainerRow
                        key={container.id}
                        busy={busy === container.id}
                        container={container}
                        href={containerHref(workspaceSlug, container)}
                        onDetach={() => void handleDetach(container)}
                      />
                    ))
                  )}
                </div>
              </div>
            </aside>
          </div>
        ) : null}
      </main>
    </div>
  );
}

function DocLink({ docId, label, workspaceSlug }: { docId: string | null; label: string; workspaceSlug: string }) {
  const { t } = useTranslation('apps');
  if (!docId) {
    return (
      <div className="flex items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink/55">
        <FileText size={14} />
        <span>{label}</span>
        <span className="ml-auto app-text-caption">{t('recording.detail.notReady')}</span>
      </div>
    );
  }
  return (
    <Link
      to={buildWorkspaceAppPath(workspaceSlug, 'docs', docId)}
      className="flex items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink hover:bg-app-surface-subtle"
    >
      <FileText size={14} />
      <span>{label}</span>
      <span className="ml-auto app-text-caption text-app-ink/55">{docId}</span>
    </Link>
  );
}

function ContainerRow({
  busy,
  container,
  href,
  onDetach,
}: {
  busy: boolean;
  container: RecordingContainer;
  href: string | null;
  onDetach: () => void;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const label = `${container.container_app}/${container.container_type}`;
  const content = (
    <>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-app-ink">{label}</p>
        <p className="app-text-caption truncate text-app-ink/55">{container.container_id}</p>
      </div>
      {container.is_primary ? (
        <span className="app-text-caption rounded border border-app-border px-1.5 py-0.5 text-app-ink/55">
          {t('apps:recording.detail.primary')}
        </span>
      ) : null}
    </>
  );
  return (
    <div className="flex items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2">
      {href ? (
        <Link to={href} className="flex min-w-0 flex-1 items-center gap-2 hover:underline">
          {content}
        </Link>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-2">{content}</div>
      )}
      <button
        type="button"
        onClick={onDetach}
        disabled={busy}
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-app-border bg-app-surface text-app-ink hover:bg-app-surface-subtle disabled:opacity-50"
        aria-label={t('apps:recording.detail.detach')}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
      </button>
    </div>
  );
}

function StatusPill({
  icon,
  label,
  tone,
}: {
  icon: ReactNode;
  label: string;
  tone: 'saved' | 'pending' | 'failed';
}) {
  const toneClass = tone === 'saved'
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
    : tone === 'failed'
      ? 'border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 text-[var(--ui-color-danger)]'
      : 'border-app-border bg-app-surface-raised text-app-ink/65';
  return (
    <span className={`app-text-caption inline-flex items-center gap-1 rounded border px-2 py-0.5 ${toneClass}`}>
      {icon}
      {label}
    </span>
  );
}

export default RecordingDetailView;
