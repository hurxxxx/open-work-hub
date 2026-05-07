import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ArrowLeft,
  CalendarDays,
  CheckSquare,
  Database,
  FileText,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { Button, useConfirm } from '@ai-do/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { DocsViewerModal } from '@/src/app-modules/docs/public-api';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import type { MeetingListItem } from '@/src/app-modules/meeting/public-api';
import type { PmsIssue } from '@/src/app-modules/pms/public-api';
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
import { MeetingPickerModal } from './MeetingPickerModal';
import { RecordingStageRail } from './RecordingStageRail';
import { TaskPickerModal } from './TaskPickerModal';

function formatDateTime(value: string, timeZone: string, locale: string): string {
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date);
}

function containerHref(workspaceSlug: string, container: RecordingContainer): string | null {
  if (container.container_app === 'meeting') {
    return buildWorkspaceAppPath(workspaceSlug, 'meeting', container.container_id);
  }
  if (container.container_app === 'pms') {
    return buildWorkspaceAppPath(workspaceSlug, 'pms', `?issue=${encodeURIComponent(container.container_id)}`);
  }
  if (container.container_app === 'docs') {
    return buildWorkspaceAppPath(workspaceSlug, 'docs', container.container_id);
  }
  return null;
}

type DocPreviewTarget = {
  docId: string;
  label: string;
};

export function RecordingDetailView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug, recordingId } = useParams();
  const navigate = useNavigate();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const { confirm, confirmDialog } = useConfirm();

  const [recording, setRecording] = useState<Recording | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [savedTitle, setSavedTitle] = useState('');
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [titleStatus, setTitleStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [meetingPickerOpen, setMeetingPickerOpen] = useState(false);
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [docPreview, setDocPreview] = useState<DocPreviewTarget | null>(null);

  const containers = useMemo(() => recording?.containers ?? [], [recording?.containers]);
  const meetingContainers = useMemo(
    () => containers.filter((container) => container.container_app === 'meeting'),
    [containers],
  );
  const taskContainers = useMemo(
    () => containers.filter((container) => container.container_app === 'pms'),
    [containers],
  );
  const otherContainers = useMemo(
    () => containers.filter((container) => container.container_app !== 'meeting' && container.container_app !== 'pms'),
    [containers],
  );

  const refresh = useCallback(async () => {
    if (!token || !workspaceSlug || !recordingId) return;
    setLoading(true);
    setError(null);
    try {
      const next = await getRecording(token, workspaceSlug, recordingId);
      setRecording(next);
      setTitleDraft(next.title ?? '');
      setSavedTitle(next.title ?? '');
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
    const trimmed = titleDraft.trim();
    if (trimmed === savedTitle.trim()) return;
    setTitleStatus('saving');
    setError(null);
    try {
      const next = await updateRecording(token, workspaceSlug, recording.id, {
        title: trimmed || null,
      });
      setRecording(next);
      setSavedTitle(next.title ?? '');
      setTitleDraft(next.title ?? '');
      setTitleStatus('saved');
      window.setTimeout(() => setTitleStatus('idle'), 1500);
    } catch (err) {
      setTitleStatus('idle');
      setError(err instanceof Error ? err.message : t('apps:recording.errors.updateFailed'));
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

  async function handleAttachMeeting(meeting: MeetingListItem) {
    if (!token || !workspaceSlug || !recording) return;
    const next = await attachRecordingContainer(token, workspaceSlug, recording.id, {
      container_app: 'meeting',
      container_type: 'meeting',
      container_id: meeting.id,
    });
    setRecording(next);
  }

  async function handleAttachTask(issue: PmsIssue) {
    if (!token || !workspaceSlug || !recording) return;
    const next = await attachRecordingContainer(token, workspaceSlug, recording.id, {
      container_app: 'pms',
      container_type: 'issue',
      container_id: issue.id,
    });
    setRecording(next);
  }

  async function handleDetach(container: RecordingContainer) {
    if (!token || !workspaceSlug || !recording) return;
    const ok = await confirm({
      title: t('apps:recording.detail.detachConfirmTitle'),
      description: t('apps:recording.detail.detachConfirmDescription'),
      confirmLabel: t('apps:recording.detail.detach'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
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

  const failureStatuses = recording
    ? [recording.transcript_status, recording.raw_transcript_doc_status, recording.minutes_doc_status]
    : [];
  const retryable = failureStatuses.some((status) => status === 'failed');

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
        <div className="mx-auto w-full max-w-3xl space-y-5">
          {error ? (
            <div className="flex items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
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
            <>
              <section className="rounded-md border border-app-border bg-app-surface p-4">
                <label className="block">
                  <span className="app-text-caption mb-1 flex items-center justify-between text-app-ink/60">
                    <span>{t('apps:recording.detail.titleLabel')}</span>
                    {titleStatus === 'saving' ? (
                      <span className="inline-flex items-center gap-1 text-app-ink/45">
                        <Loader2 size={11} className="animate-spin" />
                        {t('common:actions.saving')}
                      </span>
                    ) : titleStatus === 'saved' ? (
                      <span className="text-emerald-600 dark:text-emerald-400">
                        {t('apps:recording.detail.titleSaved')}
                      </span>
                    ) : null}
                  </span>
                  <input
                    value={titleDraft}
                    onChange={(event) => setTitleDraft(event.target.value)}
                    onBlur={() => void handleSaveTitle()}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        (event.currentTarget as HTMLInputElement).blur();
                      }
                    }}
                    className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink outline-none transition-colors focus:border-app-accent"
                  />
                </label>

                <div className="mt-4">
                  <RecordingStageRail
                    recording={recording}
                    onRetry={retryable ? () => void handleRetry() : undefined}
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => void handlePlayback()}
                    disabled={busy === 'playback' || Boolean(playbackUrl)}
                  >
                    {busy === 'playback' ? (
                      <Loader2 size={14} className="mr-1 animate-spin" />
                    ) : (
                      <Play size={14} className="mr-1" />
                    )}
                    {t('apps:recording.actions.play')}
                  </Button>
                  {retryable ? (
                    <Button
                      variant="secondary"
                      onClick={() => void handleRetry()}
                      disabled={busy === 'retry'}
                    >
                      {busy === 'retry' ? (
                        <Loader2 size={14} className="mr-1 animate-spin" />
                      ) : (
                        <RefreshCw size={14} className="mr-1" />
                      )}
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
              </section>

              <section className="rounded-md border border-app-border bg-app-surface p-4">
                <h2 className="app-text-title-sm text-app-ink">
                  {t('apps:recording.detail.generatedDocsTitle')}
                </h2>
                <div className="mt-3 grid gap-2">
                  <DocLink
                    docId={recording.raw_transcript_doc_id}
                    label={t('apps:recording.detail.rawTranscriptDoc')}
                    notReadyLabel={t('apps:recording.detail.notReady')}
                    onOpen={(docId, label) => setDocPreview({ docId, label })}
                  />
                  <DocLink
                    docId={recording.minutes_doc_id}
                    label={t('apps:recording.detail.minutesDoc')}
                    notReadyLabel={t('apps:recording.detail.notReady')}
                    onOpen={(docId, label) => setDocPreview({ docId, label })}
                  />
                </div>
              </section>

              <section className="rounded-md border border-app-border bg-app-surface p-4">
                <h2 className="app-text-title-sm text-app-ink">
                  {t('apps:recording.detail.linkedItems')}
                </h2>

                <div className="mt-4 space-y-5">
                  <LinkedSubsection
                    icon={<CalendarDays size={14} />}
                    title={t('apps:recording.detail.linkedMeetings')}
                    count={meetingContainers.length}
                    onAdd={() => setMeetingPickerOpen(true)}
                    addLabel={t('apps:recording.detail.addMeeting')}
                    emptyLabel={t('apps:recording.detail.noLinkedMeetings')}
                    items={meetingContainers}
                    busyId={busy}
                    workspaceSlug={workspaceSlug}
                    onDetach={handleDetach}
                    detachLabel={t('apps:recording.detail.detach')}
                  />

                  <LinkedSubsection
                    icon={<CheckSquare size={14} />}
                    title={t('apps:recording.detail.linkedTasks')}
                    count={taskContainers.length}
                    onAdd={() => setTaskPickerOpen(true)}
                    addLabel={t('apps:recording.detail.addTask')}
                    emptyLabel={t('apps:recording.detail.noLinkedTasks')}
                    items={taskContainers}
                    busyId={busy}
                    workspaceSlug={workspaceSlug}
                    onDetach={handleDetach}
                    detachLabel={t('apps:recording.detail.detach')}
                  />

                  <LinkedSubsection
                    icon={<Database size={14} />}
                    title={t('apps:recording.detail.otherConnections')}
                    count={otherContainers.length}
                    emptyLabel={t('apps:recording.detail.noOtherConnections')}
                    items={otherContainers}
                    busyId={busy}
                    workspaceSlug={workspaceSlug}
                    onDetach={handleDetach}
                    detachLabel={t('apps:recording.detail.detach')}
                  />
                </div>
              </section>
            </>
          ) : null}
        </div>
      </main>

      {recording ? (
        <>
          <MeetingPickerModal
            isOpen={meetingPickerOpen}
            onClose={() => setMeetingPickerOpen(false)}
            workspaceSlug={workspaceSlug}
            excludeMeetingIds={meetingContainers.map((container) => container.container_id)}
            onPick={handleAttachMeeting}
          />
          <TaskPickerModal
            isOpen={taskPickerOpen}
            onClose={() => setTaskPickerOpen(false)}
            workspaceSlug={workspaceSlug}
            excludeIssueIds={taskContainers.map((container) => container.container_id)}
            onPick={handleAttachTask}
          />
          <DocsViewerModal
            open={docPreview !== null}
            itemId={docPreview?.docId}
            fallbackTitle={docPreview?.label}
            workspaceSlug={workspaceSlug}
            onOpenChange={(nextOpen) => {
              if (!nextOpen) setDocPreview(null);
            }}
          />
        </>
      ) : null}

      {confirmDialog}
    </div>
  );
}

function LinkedSubsection({
  icon,
  title,
  count,
  onAdd,
  addLabel,
  emptyLabel,
  items,
  busyId,
  workspaceSlug,
  onDetach,
  detachLabel,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  onAdd?: () => void;
  addLabel?: string;
  emptyLabel: string;
  items: RecordingContainer[];
  busyId: string | null;
  workspaceSlug: string;
  onDetach: (container: RecordingContainer) => void;
  detachLabel: string;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-app-ink">
          <span className="text-app-ink/50">{icon}</span>
          <span className="app-text-body font-medium">{title}</span>
          <span className="app-text-caption text-app-ink/45">{count}</span>
        </div>
        {onAdd && addLabel ? (
          <button
            type="button"
            onClick={onAdd}
            className="app-text-caption inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface-raised px-2 py-1 text-app-ink hover:bg-app-surface-subtle"
          >
            <Plus size={12} />
            {addLabel}
          </button>
        ) : null}
      </div>
      {items.length === 0 ? (
        <p className="app-text-caption text-app-ink/50">{emptyLabel}</p>
      ) : (
        <ul className="space-y-1">
          {items.map((container) => (
            <ContainerRow
              key={container.id}
              busy={busyId === container.id}
              container={container}
              href={containerHref(workspaceSlug, container)}
              onDetach={() => onDetach(container)}
              detachLabel={detachLabel}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function DocLink({
  docId,
  label,
  notReadyLabel,
  onOpen,
}: {
  docId: string | null | undefined;
  label: string;
  notReadyLabel: string;
  onOpen: (docId: string, label: string) => void;
}) {
  if (!docId) {
    return (
      <div className="flex w-full items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink/55">
        <FileText size={14} />
        <span>{label}</span>
        <span className="ml-auto app-text-caption">{notReadyLabel}</span>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(docId, label)}
      aria-haspopup="dialog"
      className="flex w-full items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2 text-left text-sm text-app-ink hover:bg-app-surface-subtle"
    >
      <FileText size={14} />
      <span>{label}</span>
    </button>
  );
}

function ContainerRow({
  busy,
  container,
  href,
  onDetach,
  detachLabel,
}: {
  busy: boolean;
  container: RecordingContainer;
  href: string | null;
  onDetach: () => void;
  detachLabel: string;
}) {
  const { t } = useTranslation('apps');
  const appLabel = t(`recording.detail.containerApps.${container.container_app}`, {
    defaultValue: container.container_app,
  });
  const typeLabel = t(`recording.detail.containerTypes.${container.container_type}`, {
    defaultValue: container.container_type,
  });
  const shortId = container.container_id.length > 12
    ? `${container.container_id.slice(0, 8)}...${container.container_id.slice(-4)}`
    : container.container_id;
  const displayTitle =
    container.container_title?.trim() || `${appLabel} · ${shortId}`;
  const detachAriaLabel = t('recording.detail.detachItemLabel', {
    item: displayTitle,
  });
  const content = (
    <div className="min-w-0">
      <p className="app-text-body line-clamp-1 text-app-ink" title={container.container_id}>
        {displayTitle}
      </p>
      <p className="app-text-caption line-clamp-1 text-app-ink/45">{typeLabel}</p>
    </div>
  );
  return (
    <li className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-raised px-3 py-2">
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
        className="ml-2 shrink-0 rounded p-1 text-app-ink/40 hover:text-[var(--ui-color-danger)] disabled:opacity-40"
        aria-label={detachAriaLabel || detachLabel}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
      </button>
    </li>
  );
}

export default RecordingDetailView;
