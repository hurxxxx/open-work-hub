import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  AudioWaveform,
  Clock3,
  Loader2,
  Mic,
  MoreHorizontal,
  Play,
  RefreshCw,
  Search,
  Square,
  Upload,
} from 'lucide-react';
import { Button, DropdownMenu, useConfirm } from '@aidoo/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  deleteRecording,
  fetchRecordingPlaybackBlobUrl,
  getRecordingPlaybackUrl,
  importRecording,
  listRecordings,
  retryRecording,
  type Recording,
  type RecordingContainer,
  type RecordingViewFilter,
} from '../api/recording-api';
import { RecordingStageRail } from './RecordingStageRail';

type RecorderState = 'idle' | 'requesting' | 'recording' | 'stopping' | 'uploading' | 'saved';
type RecordingCategoryFilter = 'all' | 'meeting' | 'task' | 'unlinked';
type RecordingSort = 'latest' | 'oldest' | 'title';

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

function hasFailedStage(recording: Recording): boolean {
  return [
    recording.audio_status,
    recording.transcript_status,
    recording.raw_transcript_doc_status,
    recording.minutes_doc_status,
    recording.meeting_insight_status,
  ].some((status) => status === 'failed');
}

function normalizeViewFilter(value: string | null): RecordingViewFilter {
  if (
    value === 'needs_review'
    || value === 'processing'
    || value === 'failed'
    || value === 'archived'
  ) {
    return value;
  }
  return 'mine';
}

function normalizeCategoryFilter(value: string | null): RecordingCategoryFilter {
  return value === 'meeting' || value === 'task' || value === 'unlinked' ? value : 'all';
}

function listTitleKey(view: RecordingViewFilter, category: RecordingCategoryFilter): string {
  if (view === 'processing') return 'apps:recording.views.processing';
  if (view === 'failed') return 'apps:recording.views.failed';
  if (view === 'archived') return 'apps:recording.views.archived';
  if (category === 'meeting') return 'apps:recording.views.meeting';
  if (category === 'task') return 'apps:recording.views.task';
  if (category === 'unlinked') return 'apps:recording.views.unlinked';
  return 'apps:recording.views.mine';
}

function recordingContainers(recording: Recording): RecordingContainer[] {
  return recording.containers ?? [];
}

function isMeetingContainer(container: RecordingContainer): boolean {
  return container.container_app === 'meeting' && container.container_type === 'meeting';
}

function isTaskContainer(container: RecordingContainer): boolean {
  return container.container_app === 'pms' && ['issue', 'task'].includes(container.container_type);
}

function recordingMatchesCategory(recording: Recording, category: RecordingCategoryFilter): boolean {
  if (category === 'all') return true;
  const containers = recordingContainers(recording);
  if (category === 'meeting') return containers.some(isMeetingContainer);
  if (category === 'task') return containers.some(isTaskContainer);
  return !containers.some((container) => isMeetingContainer(container) || isTaskContainer(container));
}

function searchableRecordingText(recording: Recording): string {
  return [
    recording.title,
    recording.mime_type,
    ...recordingContainers(recording).flatMap((container) => [
      container.container_title ?? '',
      container.container_app,
      container.container_type,
    ]),
  ].join(' ');
}

function compareRecordings(
  left: Recording,
  right: Recording,
  sort: RecordingSort,
  locale: string,
): number {
  if (sort === 'title') {
    return titleFor(left, '').localeCompare(titleFor(right, ''), locale, { sensitivity: 'base' });
  }
  const leftTime = new Date(left.started_at).getTime();
  const rightTime = new Date(right.started_at).getTime();
  return sort === 'oldest' ? leftTime - rightTime : rightTime - leftTime;
}

function connectionChips(recording: Recording): Array<{
  id: string;
  labelKey: string;
  title: string | null;
}> {
  const chips = recordingContainers(recording)
    .filter((container) => isMeetingContainer(container) || isTaskContainer(container))
    .map((container) => ({
      id: container.id,
      labelKey: isMeetingContainer(container)
        ? 'apps:recording.filters.categories.meeting'
        : 'apps:recording.filters.categories.task',
      title: container.container_title ?? null,
    }));

  return chips.length > 0
    ? chips
    : [{ id: 'unlinked', labelKey: 'apps:recording.filters.categories.unlinked', title: null }];
}

export function RecordingView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug } = useParams();
  const [searchParams] = useSearchParams();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const view = normalizeViewFilter(searchParams.get('view'));
  const category = normalizeCategoryFilter(searchParams.get('category'));
  const showQuickRecorder = !searchParams.has('view') && !searchParams.has('category');
  const { confirm, confirmDialog } = useConfirm();

  const [items, setItems] = useState<Recording[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<RecordingSort>('latest');
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
  const micButtonRef = useRef<HTMLButtonElement | null>(null);

  const browserSupported = useMemo(
    () => typeof MediaRecorder !== 'undefined' && typeof navigator.mediaDevices?.getUserMedia === 'function',
    [],
  );
  const isRecording = recorderState === 'recording';
  const isWorking = ['requesting', 'stopping', 'uploading'].includes(recorderState);
  const showRecorderState = recorderState !== 'idle' || elapsedSec > 0;
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase(i18n.language);
    return [...items]
      .filter((recording) => recordingMatchesCategory(recording, category))
      .filter((recording) => (
        normalizedQuery
          ? searchableRecordingText(recording).toLocaleLowerCase(i18n.language).includes(normalizedQuery)
          : true
      ))
      .sort((left, right) => compareRecordings(left, right, sort, i18n.language));
  }, [category, i18n.language, items, query, sort]);
  const listCountLabel = visibleItems.length === items.length
    ? t('apps:recording.list.count', { count: items.length })
    : t('apps:recording.list.filteredCount', { shown: visibleItems.length, total: items.length });

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

  function focusRecorder() {
    micButtonRef.current?.focus();
    micButtonRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

      <main className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto w-full max-w-5xl space-y-8">
          {showQuickRecorder ? (
            <section className="border-b border-app-border pb-8">
              <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-4">
                <p className="app-text-title-sm self-start text-app-ink">{t('apps:recording.quick.title')}</p>

                <button
                  ref={micButtonRef}
                  type="button"
                  onClick={() => (isRecording ? handleStop() : void handleStart())}
                  disabled={!browserSupported || isWorking}
                  aria-label={isRecording ? t('apps:recording.quick.stop') : t('apps:recording.quick.start')}
                  className={`flex h-32 w-32 shrink-0 items-center justify-center rounded-full border shadow-sm transition-all hover:scale-[1.02] disabled:scale-100 disabled:opacity-60 ${
                    isRecording
                      ? 'border-[var(--ui-color-danger)]/40 bg-[var(--ui-color-danger)]/10 text-[var(--ui-color-danger)]'
                      : 'border-app-accent/30 bg-app-accent text-app-accent-fg hover:bg-app-accent-hover'
                  }`}
                >
                  {isWorking ? (
                    <Loader2 size={36} className="animate-spin" />
                  ) : isRecording ? (
                    <Square size={36} />
                  ) : (
                    <Mic size={42} />
                  )}
                </button>

                {showRecorderState ? (
                  <div className="text-center">
                    <p className="app-text-title-md tabular-nums text-app-ink">
                      {formatElapsed(elapsedSec)}
                    </p>
                    <p className="app-text-caption text-app-ink/60">
                      {t(`apps:recording.quick.state.${recorderState}`)}
                    </p>
                  </div>
                ) : (
                  <p className="app-text-caption text-center text-app-ink/55">
                    {browserSupported
                      ? t('apps:recording.quick.browserSupported')
                      : t('apps:recording.quick.browserUnsupported')}
                  </p>
                )}

                <div className="mt-2 w-full border-t border-app-border pt-4">
                  <label className="block">
                    <span className="app-text-caption mb-1 block text-app-ink/60">
                      {t('apps:recording.quick.titleLabel')}
                    </span>
                    <input
                      value={titleDraft}
                      onChange={(event) => setTitleDraft(event.target.value)}
                      disabled={isRecording || isWorking}
                      placeholder={t('apps:recording.quick.titlePlaceholder')}
                      className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink outline-none transition-colors placeholder:text-app-ink/35 focus:border-app-accent disabled:opacity-60"
                    />
                  </label>
                </div>

                <div className="self-start">
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
          ) : null}

          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="app-text-title-sm text-app-ink">{t(listTitleKey(view, category))}</p>
                <p className="app-text-caption text-app-ink/60">
                  {listCountLabel}
                </p>
              </div>
              {loading ? <Loader2 size={18} className="animate-spin text-app-ink/40" /> : null}
            </div>

            <div className="mb-4 flex flex-col gap-3 rounded-md border border-app-border bg-app-surface px-3 py-3 sm:flex-row sm:items-center">
              <label className="relative min-w-0 flex-1">
                <span className="sr-only">{t('apps:recording.filters.searchLabel')}</span>
                <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/35" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t('apps:recording.filters.searchPlaceholder')}
                  className="h-9 w-full rounded-md border border-app-border bg-app-surface-raised py-2 pl-9 pr-3 text-sm text-app-ink outline-none transition-colors placeholder:text-app-ink/35 focus:border-app-accent"
                />
              </label>
              <label className="flex shrink-0 items-center gap-2">
                <span className="app-text-caption text-app-ink/55">
                  {t('apps:recording.filters.sortLabel')}
                </span>
                <select
                  value={sort}
                  onChange={(event) => setSort(event.target.value as RecordingSort)}
                  className="h-9 rounded-md border border-app-border bg-app-surface-raised px-2 text-sm text-app-ink outline-none transition-colors focus:border-app-accent"
                >
                  <option value="latest">{t('apps:recording.filters.sort.latest')}</option>
                  <option value="oldest">{t('apps:recording.filters.sort.oldest')}</option>
                  <option value="title">{t('apps:recording.filters.sort.title')}</option>
                </select>
              </label>
            </div>

            {error ? (
              <div className="mb-4 flex items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}

            {items.length === 0 && !loading ? (
              <div className="flex h-72 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-app-border bg-app-surface/40 px-6 text-center">
                <AudioWaveform size={40} className="text-app-ink/25" />
                <div>
                  <p className="app-text-title-sm text-app-ink">{t('apps:recording.list.emptyTitle')}</p>
                  <p className="app-text-caption mt-1 text-app-ink/55">
                    {t('apps:recording.list.emptyBody')}
                  </p>
                </div>
                {showQuickRecorder ? (
                  <Button variant="secondary" onClick={focusRecorder}>
                    <Mic size={14} className="mr-1" />
                    {t('apps:recording.quick.start')}
                  </Button>
                ) : (
                  <Link
                    to={buildWorkspaceAppPath(workspaceSlug, 'recording')}
                    className="inline-flex h-[var(--ui-density-dense)] items-center justify-center rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface-raised px-2.5 text-[0.84rem] font-semibold text-app-ink transition-colors hover:bg-app-surface-subtle"
                  >
                    <Mic size={14} className="mr-1" />
                    {t('apps:recording.quick.start')}
                  </Link>
                )}
              </div>
            ) : visibleItems.length === 0 && !loading ? (
              <div className="flex h-56 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-app-border bg-app-surface/40 px-6 text-center">
                <Search size={34} className="text-app-ink/25" />
                <div>
                  <p className="app-text-title-sm text-app-ink">{t('apps:recording.filters.emptyTitle')}</p>
                  <p className="app-text-caption mt-1 text-app-ink/55">
                    {t('apps:recording.filters.emptyBody')}
                  </p>
                </div>
                {query ? (
                  <Button variant="secondary" onClick={() => setQuery('')}>
                    {t('apps:recording.filters.clearSearch')}
                  </Button>
                ) : null}
              </div>
            ) : (
              <div className="grid gap-3">
                {visibleItems.map((recording) => (
                  <RecordingListItem
                    key={recording.id}
                    busy={busyId === recording.id}
                    locale={i18n.language}
                    playbackUrl={playbackUrls[recording.id]}
                    recording={recording}
                    detailHref={buildWorkspaceAppPath(workspaceSlug, 'recording', recording.id)}
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
      </main>

      {confirmDialog}
    </div>
  );
}

function RecordingListItem({
  busy,
  locale,
  playbackUrl,
  recording,
  detailHref,
  timeZone,
  onDelete,
  onPlay,
  onRetry,
}: {
  busy: boolean;
  locale: string;
  playbackUrl: string | undefined;
  recording: Recording;
  detailHref: string;
  timeZone: string;
  onDelete: () => void;
  onPlay: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const retryable = hasFailedStage(recording);
  const chips = connectionChips(recording);

  const overflowItems = [
    ...(retryable
      ? [
          {
            id: 'retry',
            label: (
              <span className="inline-flex items-center gap-2">
                <RefreshCw size={14} />
                {t('apps:recording.actions.retry')}
              </span>
            ),
            onSelect: onRetry,
            disabled: busy,
          },
        ]
      : []),
    {
      id: 'delete',
      label: t('common:actions.delete'),
      onSelect: onDelete,
      disabled: busy,
      tone: 'danger' as const,
      separatorBefore: retryable,
    },
  ];

  return (
    <article className="rounded-md border border-app-border bg-app-surface px-4 py-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <AudioWaveform size={16} className="shrink-0 text-app-accent" />
            <h2 className="app-text-body truncate text-app-ink">
              {titleFor(recording, t('apps:recording.untitled'))}
            </h2>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-app-ink/55">
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
          <div className="mt-2 flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <span
                key={chip.id}
                className="app-text-caption inline-flex max-w-full items-center rounded-full border border-app-border bg-app-surface-raised px-2 py-0.5 text-app-ink/65"
                title={chip.title ?? undefined}
              >
                <span className="shrink-0">{t(chip.labelKey)}</span>
                {chip.title ? (
                  <span className="ml-1 min-w-0 truncate text-app-ink">
                    {chip.title}
                  </span>
                ) : null}
              </span>
            ))}
          </div>
          <div className="mt-3">
            <RecordingStageRail recording={recording} compact />
          </div>
          {recording.failure_reason ? (
            <p className="app-text-caption mt-2 max-w-2xl text-[var(--ui-color-danger)]">
              {t('apps:recording.status.failureHelp')}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button variant="secondary" onClick={onPlay} disabled={busy || Boolean(playbackUrl)}>
            {busy && !playbackUrl ? (
              <Loader2 size={14} className="mr-1 animate-spin" />
            ) : (
              <Play size={14} className="mr-1" />
            )}
            {t('apps:recording.actions.play')}
          </Button>
          <Link
            to={detailHref}
            className="inline-flex h-[var(--ui-density-dense)] items-center justify-center rounded-[var(--ui-radius-sm)] border border-app-accent bg-app-accent px-2.5 text-[0.84rem] font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover"
          >
            {t('apps:recording.actions.openDetail')}
          </Link>
          <DropdownMenu
            trigger={
              <button
                type="button"
                className="inline-flex h-[var(--ui-density-dense)] w-8 items-center justify-center rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface-raised text-app-ink hover:bg-app-surface-subtle disabled:opacity-50"
                disabled={busy}
                aria-label={t('common:actions.open')}
              >
                <MoreHorizontal size={14} />
              </button>
            }
            items={overflowItems}
          />
        </div>
      </div>

      {playbackUrl ? <audio controls src={playbackUrl} className="mt-3 w-full" /> : null}
    </article>
  );
}

export default RecordingView;
