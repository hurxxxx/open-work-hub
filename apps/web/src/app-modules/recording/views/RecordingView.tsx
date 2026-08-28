import {
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type RefObject,
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
import {
  Button,
  DropdownMenu,
  InlineNotice,
  useConfirm,
} from '@open-work-hub/ui';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime as formatZonedDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import type { Recording } from '../api/recording-api';
import { RecordingRecoveryBanner } from '../recorder/RecordingRecoveryBanner';
import {
  getRecordingRecoveryAction,
  planRecordingRecoverySession,
  runRecordingRecoveryAction,
  type RecordingRecoveryAction,
} from '../recorder/recording-recovery-session-plan';
import { useRecordingRecovery } from '../recorder/useRecordingRecovery';
import { useResilientRecorder } from '../recorder/useResilientRecorder';
import { RecordingStageRail } from './RecordingStageRail';
import {
  compareRecordings,
  connectionChips,
  formatBytes,
  formatElapsed,
  hasFailedStage,
  listTitleKey,
  normalizeCategoryFilter,
  normalizeViewFilter,
  recordingMatchesCategory,
  searchableRecordingText,
  titleFor,
  type RecordingSort,
} from './recording-view-model';
import { useRecordingCollectionWorkflow } from './recording-collection-workflow';

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

export function RecordingView() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug } = useParams();
  const [searchParams] = useSearchParams();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const view = normalizeViewFilter(searchParams.get('view'));
  const category = normalizeCategoryFilter(searchParams.get('category'));
  const showQuickRecorder =
    !searchParams.has('view') && !searchParams.has('category');
  const { confirm, confirmDialog } = useConfirm();

  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<RecordingSort>('latest');
  const [titleDraft, setTitleDraft] = useState('');
  const recordingScope = useMemo(
    () => ({ kind: 'view' as const, view }),
    [view],
  );
  const recordingCollection = useRecordingCollectionWorkflow({
    token,
    workspaceSlug,
    scope: recordingScope,
    messages: {
      loadFailed: t('apps:recording.errors.loadFailed'),
      retryFailed: t('apps:recording.errors.retryFailed'),
      deleteFailed: t('apps:recording.errors.deleteFailed'),
    },
  });
  const { busyId, error, items, loading } = recordingCollection;
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const micButtonRef = useRef<HTMLButtonElement | null>(null);

  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase(i18n.language);
    const nextItems = [];
    for (const recording of items) {
      if (!recordingMatchesCategory(recording, category)) {
        continue;
      }
      const searchableText = searchableRecordingText(
        recording,
      ).toLocaleLowerCase(i18n.language);
      if (normalizedQuery && !searchableText.includes(normalizedQuery)) {
        continue;
      }
      nextItems.push(recording);
    }
    return nextItems.sort((left, right) =>
      compareRecordings(left, right, sort, i18n.language),
    );
  }, [category, i18n.language, items, query, sort]);
  const listCountLabel =
    visibleItems.length === items.length
      ? t('apps:recording.list.count', { count: items.length })
      : t('apps:recording.list.filteredCount', {
          shown: visibleItems.length,
          total: items.length,
        });

  const recovery = useRecordingRecovery({
    workspaceSlug: workspaceSlug ?? '',
    token,
  });
  const recorder = useResilientRecorder({
    workspaceSlug: workspaceSlug ?? '',
    token,
    source: 'quick_record',
    title: titleDraft,
    onRecordingSaved: async () => {
      setTitleDraft('');
      await recordingCollection.refresh();
      void recovery.refresh();
    },
  });
  const browserSupported = recorder.browserSupported;
  const isRecording = recorder.isRecording;
  const isWorking =
    recorder.isBusy ||
    ['requesting', 'stopping', 'uploading'].includes(recorder.recorderState);
  const showRecorderState =
    recorder.recorderState !== 'idle' || recorder.elapsedSec > 0;
  const visibleError = error ?? recorder.error ?? recovery.error;

  async function handleStart() {
    await recorder.startRecording({ title: titleDraft });
  }

  function handleStop() {
    recorder.stopRecording();
  }

  async function handleFileSelect(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await recorder.importAudioFile(file, {
      title: titleDraft || file.name,
      source: 'manual_upload',
    });
  }

  async function handleDelete(recording: Recording) {
    await recordingCollection.remove(recording.id, () =>
      confirm({
        title: t('apps:recording.delete.title'),
        description: t('apps:recording.delete.description', {
          title: titleFor(recording, t('apps:recording.untitled')),
        }),
        confirmLabel: t('common:actions.delete'),
        cancelLabel: t('common:actions.cancel'),
        variant: 'danger',
      }),
    );
  }

  async function handleRetry(recording: Recording) {
    await recordingCollection.retry(recording.id);
  }

  function focusRecorder() {
    micButtonRef.current?.focus();
    micButtonRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    });
  }

  if (!workspaceSlug) {
    return null;
  }

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
        <div className="flex items-center gap-3">
          <Mic size={20} className="text-app-ink/60" />
          <h1 className="app-text-title-md text-app-ink">
            {t('apps:recording.title')}
          </h1>
        </div>
        <Button
          variant="secondary"
          onClick={() => void recordingCollection.refresh()}
          disabled={loading || isWorking}
        >
          <RefreshCw
            size={14}
            className={loading ? 'mr-1 animate-spin' : 'mr-1'}
          />
          {t('common:actions.reload')}
        </Button>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto w-full max-w-5xl space-y-8">
          {showQuickRecorder ? (
            <QuickRecorderSection
              browserSupported={browserSupported}
              fileInputRef={fileInputRef}
              isRecording={isRecording}
              isWorking={isWorking}
              micButtonRef={micButtonRef}
              recorder={recorder}
              recovery={recovery}
              showRecorderState={showRecorderState}
              titleDraft={titleDraft}
              onFileSelect={handleFileSelect}
              onStart={handleStart}
              onStop={handleStop}
              onTitleDraftChange={setTitleDraft}
            />
          ) : null}

          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="app-text-title-sm text-app-ink">
                  {t(listTitleKey(view, category))}
                </p>
                <p className="app-text-caption text-app-ink/60">
                  {listCountLabel}
                </p>
              </div>
              {loading ? (
                <Loader2 size={18} className="animate-spin text-app-ink/40" />
              ) : null}
            </div>

            <div className="mb-4 flex flex-col gap-3 rounded-md border border-app-border bg-app-surface p-3 sm:flex-row sm:items-center">
              <label className="relative min-w-0 flex-1">
                <span className="sr-only">
                  {t('apps:recording.filters.searchLabel')}
                </span>
                <Search
                  size={15}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/35"
                />
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
                  onChange={(event) =>
                    setSort(event.target.value as RecordingSort)
                  }
                  className="app-field-input-sm w-auto"
                >
                  <option value="latest">
                    {t('apps:recording.filters.sort.latest')}
                  </option>
                  <option value="oldest">
                    {t('apps:recording.filters.sort.oldest')}
                  </option>
                  <option value="title">
                    {t('apps:recording.filters.sort.title')}
                  </option>
                </select>
              </label>
            </div>

            {visibleError ? (
              <div className="mb-4 flex items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <span>{visibleError}</span>
              </div>
            ) : null}

            {items.length === 0 && !loading ? (
              <div className="flex h-72 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-app-border bg-app-surface/40 px-6 text-center">
                <AudioWaveform size={40} className="text-app-ink/25" />
                <div>
                  <p className="app-text-title-sm text-app-ink">
                    {t('apps:recording.list.emptyTitle')}
                  </p>
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
                    to={buildAppHref({
                      routeId: 'recording.root',
                      workspaceSlug,
                    })}
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
                  <p className="app-text-title-sm text-app-ink">
                    {t('apps:recording.filters.emptyTitle')}
                  </p>
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
                    recording={recording}
                    detailHref={buildAppHref({
                      routeId: 'recording.detail',
                      workspaceSlug,
                      pathParams: { recordingId: recording.id },
                    })}
                    timeZone={timeZone}
                    onDelete={() => void handleDelete(recording)}
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
  recording,
  detailHref,
  timeZone,
  onDelete,
  onRetry,
}: {
  busy: boolean;
  locale: string;
  recording: Recording;
  detailHref: string;
  timeZone: string;
  onDelete: () => void;
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
    <article className="rounded-md border border-app-border bg-app-surface px-3 py-2.5 transition-colors hover:bg-app-surface-hover/60">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_15rem_auto] lg:items-center">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2.5">
            <AudioWaveform size={16} className="shrink-0 text-app-accent" />
            <h2 className="app-text-body truncate text-app-ink">
              {titleFor(recording, t('apps:recording.untitled'))}
            </h2>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-app-ink/55">
            <span className="app-text-caption inline-flex items-center gap-1">
              <Clock3 size={13} />
              {formatDateTime(recording.started_at, timeZone, locale)}
            </span>
            {recording.duration_sec !== null &&
            recording.duration_sec !== undefined ? (
              <span className="app-text-caption tabular-nums">
                {formatElapsed(recording.duration_sec)}
              </span>
            ) : null}
            <span className="app-text-caption">
              {formatBytes(recording.file_size)}
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <span
                key={chip.id}
                className="app-text-caption inline-flex max-w-full items-center rounded border border-app-border bg-app-surface-raised px-1.5 py-0.5 text-app-ink/65"
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
          {recording.failure_reason ? (
            <p className="app-text-caption mt-2 max-w-2xl text-[var(--ui-color-danger)]">
              {t('apps:recording.status.failureHelp')}
            </p>
          ) : null}
        </div>

        <div className="min-w-0">
          <RecordingStageRail recording={recording} compact />
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <Link
            to={detailHref}
            aria-label={t('apps:recording.actions.play')}
            title={t('apps:recording.actions.play')}
            className="inline-flex h-[var(--ui-density-dense)] w-8 items-center justify-center rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface-raised text-app-ink transition-colors hover:bg-app-surface-subtle"
          >
            <Play size={14} />
          </Link>
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
    </article>
  );
}

export default RecordingView;

type RecorderController = ReturnType<typeof useResilientRecorder>;
type RecoveryController = ReturnType<typeof useRecordingRecovery>;

function QuickRecorderSection({
  browserSupported,
  fileInputRef,
  isRecording,
  isWorking,
  micButtonRef,
  recorder,
  recovery,
  showRecorderState,
  titleDraft,
  onFileSelect,
  onStart,
  onStop,
  onTitleDraftChange,
}: {
  browserSupported: boolean;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isRecording: boolean;
  isWorking: boolean;
  micButtonRef: RefObject<HTMLButtonElement | null>;
  recorder: RecorderController;
  recovery: RecoveryController;
  showRecorderState: boolean;
  titleDraft: string;
  onFileSelect: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  onStart: () => Promise<void>;
  onStop: () => void;
  onTitleDraftChange: (title: string) => void;
}) {
  const { t } = useTranslation(['apps', 'common']);

  function handleRecoveryAction(action: RecordingRecoveryAction) {
    void runRecordingRecoveryAction(
      action,
      {
        resumeUpload: recorder.resumeUpload,
        continueRecording: recorder.continueRecording,
        downloadOriginal: recorder.downloadRecoveredSession,
        importOriginal: recorder.importRecoveredSession,
        finalizeUploaded: recorder.finalizeUploadedOnly,
        discard: recorder.discardSession,
      },
      recovery.refresh,
    );
  }

  return (
    <section className="border-b border-app-border pb-8">
      <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-4">
        <p className="app-text-title-sm self-start text-app-ink">
          {t('apps:recording.quick.title')}
        </p>

        <button
          ref={micButtonRef}
          type="button"
          onClick={() => (isRecording ? onStop() : void onStart())}
          disabled={!browserSupported || isWorking}
          aria-label={
            isRecording
              ? t('apps:recording.quick.stop')
              : t('apps:recording.quick.start')
          }
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
              {formatElapsed(recorder.elapsedSec)}
            </p>
            <p className="app-text-caption text-app-ink/60">
              {t(`apps:recording.quick.state.${recorder.recorderState}`)}
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
              onChange={(event) => onTitleDraftChange(event.target.value)}
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
            aria-label={t('apps:recording.quick.uploadAudio')}
            className="hidden"
            onChange={onFileSelect}
          />
        </div>

        {recorder.persistWarning ||
        recorder.wakeLockWarning ||
        recorder.inputWarning ? (
          <InlineNotice className="w-full" tone="warning">
            {recorder.persistWarning ? (
              <p className="app-text-caption">{recorder.persistWarning}</p>
            ) : null}
            {recorder.wakeLockWarning ? (
              <p className="app-text-caption">{recorder.wakeLockWarning}</p>
            ) : null}
            {recorder.inputWarning ? (
              <p className="app-text-caption">{recorder.inputWarning}</p>
            ) : null}
          </InlineNotice>
        ) : null}

        {recovery.items.length > 0 ? (
          <div className="w-full space-y-2">
            {recovery.items.map((item) => {
              const plan = planRecordingRecoverySession(item);
              const resumeAction = getRecordingRecoveryAction(
                plan,
                'resume-upload',
              );
              const continueAction = getRecordingRecoveryAction(
                plan,
                'continue-recording',
              );
              const downloadAction = getRecordingRecoveryAction(
                plan,
                'download-original',
              );
              const importAction = getRecordingRecoveryAction(
                plan,
                'import-original',
              );
              const discardAction = getRecordingRecoveryAction(plan, 'discard');
              const finalizeAction = getRecordingRecoveryAction(
                plan,
                'finalize-uploaded',
              );
              return (
                <RecordingRecoveryBanner
                  key={item.stagingId}
                  item={item}
                  plan={plan}
                  onResumeUpload={
                    resumeAction
                      ? () => handleRecoveryAction(resumeAction)
                      : undefined
                  }
                  onContinueRecording={
                    continueAction
                      ? () => handleRecoveryAction(continueAction)
                      : undefined
                  }
                  onDownload={
                    downloadAction
                      ? () => handleRecoveryAction(downloadAction)
                      : undefined
                  }
                  onImport={
                    importAction
                      ? () => handleRecoveryAction(importAction)
                      : undefined
                  }
                  onDiscard={
                    discardAction
                      ? () => handleRecoveryAction(discardAction)
                      : undefined
                  }
                  onFinalizeUploadedOnly={
                    finalizeAction
                      ? () => handleRecoveryAction(finalizeAction)
                      : undefined
                  }
                />
              );
            })}
          </div>
        ) : null}
      </div>
    </section>
  );
}
