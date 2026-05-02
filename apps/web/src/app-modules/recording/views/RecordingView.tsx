import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
} from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  AudioWaveform,
  CheckCircle2,
  Clock3,
  Loader2,
  Mic,
  PauseCircle,
  Play,
  RefreshCw,
  Square,
  Trash2,
  Upload,
} from 'lucide-react';
import { Button, useConfirm } from '@aidoo/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  deleteRecording,
  fetchRecordingPlaybackBlobUrl,
  getRecordingPlaybackUrl,
  importRecording,
  listRecordings,
  retryRecording,
  type Recording,
} from '../api/recording-api';

type RecorderState = 'idle' | 'requesting' | 'recording' | 'stopping' | 'uploading' | 'saved';

const RECORDER_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
] as const;

function selectRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') {
    return undefined;
  }
  return RECORDER_MIME_TYPES.find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
}

function formatElapsed(totalSec: number): string {
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value: string, timeZone: string, locale: string): string {
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date);
}

function titleFor(recording: Recording, fallback: string): string {
  return recording.title?.trim() || fallback;
}

function processingStatusKey(value: string): 'done' | 'failed' | 'creating' | 'transcribing' | 'pending' {
  if (value === 'done' || value === 'failed' || value === 'creating' || value === 'transcribing') {
    return value;
  }
  return 'pending';
}

function statusTone(key: 'done' | 'failed' | 'creating' | 'transcribing' | 'pending'): 'saved' | 'pending' | 'failed' {
  if (key === 'done') return 'saved';
  if (key === 'failed') return 'failed';
  return 'pending';
}

function statusIcon(key: 'done' | 'failed' | 'creating' | 'transcribing' | 'pending'): ReactNode {
  if (key === 'done') return <CheckCircle2 size={13} />;
  if (key === 'failed') return <AlertCircle size={13} />;
  return <PauseCircle size={13} />;
}

export function RecordingView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug } = useParams();
  const [searchParams] = useSearchParams();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const view = searchParams.get('view') === 'archived' ? 'archived' : 'mine';
  const { confirm, confirmDialog } = useConfirm();

  const [items, setItems] = useState<Recording[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [recorderState, setRecorderState] = useState<RecorderState>('idle');
  const [elapsedSec, setElapsedSec] = useState(0);
  const [recordingStartedAt, setRecordingStartedAt] = useState<Date | null>(null);
  const [playbackUrls, setPlaybackUrls] = useState<Record<string, string>>({});
  const playbackUrlsRef = useRef<Record<string, string>>({});
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef<Date | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const browserSupported = useMemo(
    () => typeof MediaRecorder !== 'undefined' && typeof navigator.mediaDevices?.getUserMedia === 'function',
    [],
  );
  const isRecording = recorderState === 'recording';
  const isWorking = ['requesting', 'stopping', 'uploading'].includes(recorderState);

  const refresh = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listRecordings(token, workspaceSlug, { view });
      setItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.loadFailed'));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [t, token, view, workspaceSlug]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!isRecording || !recordingStartedAt) {
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedSec(Math.max(0, Math.floor((Date.now() - recordingStartedAt.getTime()) / 1000)));
    }, 500);
    return () => window.clearInterval(timer);
  }, [isRecording, recordingStartedAt]);

  useEffect(
    () => () => {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== 'inactive') {
        recorder.onstop = null;
        recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      Object.values(playbackUrlsRef.current).forEach((url) => {
        if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
    },
    [],
  );

  async function saveBlob(blob: Blob | File, options: {
    title?: string | null;
    startedAt?: Date | null;
    endedAt?: Date | null;
    durationSec?: number | null;
    source?: 'quick_record' | 'manual_upload';
  }) {
    if (!token || !workspaceSlug) return;
    setRecorderState('uploading');
    setError(null);
    try {
      await importRecording(token, workspaceSlug, blob, options);
      setRecorderState('saved');
      setTitleDraft('');
      setElapsedSec(0);
      setRecordingStartedAt(null);
      await refresh();
      window.setTimeout(() => setRecorderState('idle'), 1200);
    } catch (err) {
      setRecorderState('idle');
      setError(err instanceof Error ? err.message : t('apps:recording.errors.saveFailed'));
    }
  }

  async function handleStart() {
    if (!browserSupported) {
      setError(t('apps:recording.errors.browserUnsupported'));
      return;
    }
    setRecorderState('requesting');
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = selectRecorderMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      const startedAt = new Date();
      startedAtRef.current = startedAt;
      setRecordingStartedAt(startedAt);
      setElapsedSec(0);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onerror = () => {
        setError(t('apps:recording.errors.recordingFailed'));
      };
      recorder.onstop = () => {
        const endedAt = new Date();
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        mediaRecorderRef.current = null;
        const durationSec = startedAtRef.current
          ? Math.max(0, Math.round((endedAt.getTime() - startedAtRef.current.getTime()) / 1000))
          : null;
        const type = recorder.mimeType || mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        chunksRef.current = [];
        void saveBlob(blob, {
          title: titleDraft,
          startedAt: startedAtRef.current,
          endedAt,
          durationSec,
          source: 'quick_record',
        });
      };
      mediaRecorderRef.current = recorder;
      recorder.start(1000);
      setRecorderState('recording');
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setRecorderState('idle');
      setError(err instanceof Error ? err.message : t('apps:recording.errors.startFailed'));
    }
  }

  function handleStop() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      return;
    }
    setRecorderState('stopping');
    recorder.stop();
  }

  async function handleFileSelect(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const startedAt = new Date();
    await saveBlob(file, {
      title: titleDraft || file.name,
      startedAt,
      source: 'manual_upload',
    });
  }

  async function handlePlayback(recording: Recording) {
    if (!token || !workspaceSlug || playbackUrls[recording.id]) {
      return;
    }
    setBusyId(recording.id);
    setError(null);
    try {
      const playback = await getRecordingPlaybackUrl(token, workspaceSlug, recording.id);
      const blobUrl = await fetchRecordingPlaybackBlobUrl(token, playback.url);
      setPlaybackUrls((current) => {
        const next = { ...current, [recording.id]: blobUrl };
        playbackUrlsRef.current = next;
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.playbackFailed'));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(recording: Recording) {
    if (!token || !workspaceSlug) return;
    const ok = await confirm({
      title: t('apps:recording.delete.title'),
      description: t('apps:recording.delete.description', {
        title: titleFor(recording, t('apps:recording.untitled')),
      }),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setBusyId(recording.id);
    setError(null);
    try {
      await deleteRecording(token, workspaceSlug, recording.id);
      const playbackUrl = playbackUrlsRef.current[recording.id];
      if (playbackUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(playbackUrl);
      }
      setPlaybackUrls((current) => {
        const next = { ...current };
        delete next[recording.id];
        playbackUrlsRef.current = next;
        return next;
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.deleteFailed'));
    } finally {
      setBusyId(null);
    }
  }

  async function handleRetry(recording: Recording) {
    if (!token || !workspaceSlug) return;
    setBusyId(recording.id);
    setError(null);
    try {
      await retryRecording(token, workspaceSlug, recording.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:recording.errors.retryFailed'));
    } finally {
      setBusyId(null);
    }
  }

  if (!workspaceSlug) {
    return null;
  }

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
        <div className="flex items-center gap-3">
          <Mic size={20} className="text-app-ink/60" />
          <h1 className="app-text-title-md text-app-ink">{t('apps:recording.title')}</h1>
        </div>
        <Button variant="secondary" onClick={() => void refresh()} disabled={loading || isWorking}>
          <RefreshCw size={14} className={loading ? 'mr-1 animate-spin' : 'mr-1'} />
          {t('common:actions.reload')}
        </Button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section className="border-b border-app-border bg-app-surface px-6 py-6 lg:border-b-0 lg:border-r">
          <div className="space-y-5">
            <div>
              <p className="app-text-title-sm text-app-ink">{t('apps:recording.quick.title')}</p>
              <p className="app-text-caption mt-1 text-app-ink/60">
                {browserSupported
                  ? t('apps:recording.quick.browserSupported')
                  : t('apps:recording.quick.browserUnsupported')}
              </p>
            </div>

            <label className="block">
              <span className="app-text-caption mb-1 block text-app-ink/60">
                {t('apps:recording.quick.titleLabel')}
              </span>
              <input
                value={titleDraft}
                onChange={(event) => setTitleDraft(event.target.value)}
                disabled={isRecording || isWorking}
                placeholder={t('apps:recording.quick.titlePlaceholder')}
                className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink outline-none transition-colors placeholder:text-app-ink/35 focus:border-app-accent"
              />
            </label>

            <div className="flex flex-col items-center gap-4 py-4">
              <button
                type="button"
                onClick={() => (isRecording ? handleStop() : void handleStart())}
                disabled={!browserSupported || isWorking}
                aria-label={isRecording ? t('apps:recording.quick.stop') : t('apps:recording.quick.start')}
                className="flex h-32 w-32 items-center justify-center rounded-full border border-app-accent/30 bg-app-accent text-app-accent-fg shadow-sm transition-transform hover:scale-[1.02] hover:bg-app-accent-hover disabled:scale-100 disabled:opacity-60"
              >
                {isWorking ? (
                  <Loader2 size={34} className="animate-spin" />
                ) : isRecording ? (
                  <Square size={34} />
                ) : (
                  <Mic size={38} />
                )}
              </button>

              <div className="text-center">
                <p className="app-text-title-md tabular-nums text-app-ink">
                  {formatElapsed(elapsedSec)}
                </p>
                <p className="app-text-caption text-app-ink/60">
                  {t(`apps:recording.quick.state.${recorderState}`)}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={isRecording || isWorking}
              >
                <Upload size={14} className="mr-1" />
                {t('apps:recording.quick.uploadAudio')}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>
          </div>
        </section>

        <section className="min-h-0 overflow-y-auto px-6 py-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="app-text-title-sm text-app-ink">{t('apps:recording.list.title')}</p>
              <p className="app-text-caption text-app-ink/60">
                {t('apps:recording.list.count', { count: items.length })}
              </p>
            </div>
            {loading ? <Loader2 size={18} className="animate-spin text-app-ink/40" /> : null}
          </div>

          {error ? (
            <div className="mb-4 flex items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          {items.length === 0 && !loading ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-app-ink/60">
              <AudioWaveform size={30} className="text-app-ink/30" />
              <p className="app-text-body">{t('apps:recording.list.empty')}</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {items.map((recording) => (
                <RecordingListItem
                  key={recording.id}
                  busy={busyId === recording.id}
                  locale={i18n.language}
                  playbackUrl={playbackUrls[recording.id]}
                  recording={recording}
                  timeZone={timeZone}
                  onDelete={() => void handleDelete(recording)}
                  onPlay={() => void handlePlayback(recording)}
                  onRetry={() => void handleRetry(recording)}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      {confirmDialog}
    </div>
  );
}

function RecordingListItem({
  busy,
  locale,
  playbackUrl,
  recording,
  timeZone,
  onDelete,
  onPlay,
  onRetry,
}: {
  busy: boolean;
  locale: string;
  playbackUrl: string | undefined;
  recording: Recording;
  timeZone: string;
  onDelete: () => void;
  onPlay: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const transcriptKey = processingStatusKey(recording.transcript_status);
  const rawDocKey = processingStatusKey(recording.raw_transcript_doc_status);
  const minutesDocKey = processingStatusKey(recording.minutes_doc_status);
  const retryable = transcriptKey === 'failed' || rawDocKey === 'failed' || minutesDocKey === 'failed';

  return (
    <article className="rounded-md border border-app-border bg-app-surface px-4 py-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <AudioWaveform size={16} className="shrink-0 text-app-accent" />
            <h2 className="app-text-body truncate text-app-ink">
              {titleFor(recording, t('apps:recording.untitled'))}
            </h2>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-app-ink/60">
            <span className="app-text-caption inline-flex items-center gap-1">
              <Clock3 size={13} />
              {formatDateTime(recording.started_at, timeZone, locale)}
            </span>
            {recording.duration_sec !== null && recording.duration_sec !== undefined ? (
              <span className="app-text-caption tabular-nums">
                {formatElapsed(recording.duration_sec)}
              </span>
            ) : null}
            <span className="app-text-caption">{formatBytes(recording.file_size)}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusPill icon={<CheckCircle2 size={13} />} label={t('apps:recording.status.audioSaved')} tone="saved" />
            <StatusPill
              icon={statusIcon(transcriptKey)}
              label={t(`apps:recording.status.transcript.${transcriptKey}`)}
              tone={statusTone(transcriptKey)}
            />
            <StatusPill
              icon={statusIcon(rawDocKey)}
              label={t(`apps:recording.status.rawTranscriptDoc.${rawDocKey}`)}
              tone={statusTone(rawDocKey)}
            />
            <StatusPill
              icon={statusIcon(minutesDocKey)}
              label={t(`apps:recording.status.minutesDoc.${minutesDocKey}`)}
              tone={statusTone(minutesDocKey)}
            />
          </div>
          {recording.failure_reason ? (
            <p className="app-text-caption mt-2 max-w-2xl text-[var(--ui-color-danger)]">
              {recording.failure_reason}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          {retryable ? (
            <Button variant="secondary" onClick={onRetry} disabled={busy}>
              {busy ? <Loader2 size={14} className="mr-1 animate-spin" /> : <RefreshCw size={14} className="mr-1" />}
              {t('apps:recording.actions.retry')}
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onPlay} disabled={busy || Boolean(playbackUrl)}>
            {busy && !playbackUrl ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Play size={14} className="mr-1" />}
            {t('apps:recording.actions.play')}
          </Button>
          <Button variant="secondary" onClick={onDelete} disabled={busy}>
            <Trash2 size={14} className="mr-1" />
            {t('common:actions.delete')}
          </Button>
        </div>
      </div>

      {playbackUrl ? (
        <audio controls src={playbackUrl} className="mt-3 w-full" />
      ) : null}
    </article>
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

export default RecordingView;
