import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import {
  AudioWaveform,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  ScrollText,
  Trash2,
} from 'lucide-react';
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { DocsViewerModal } from '@/src/app-modules/docs/public-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { RecordingStageRail } from './RecordingStageRail';
import { useRecordingCollectionWorkflow } from './recording-collection-workflow';
import { formatBytes, hasFailedStage, titleFor } from './recording-view-model';

export interface LinkedRecordingListItem {
  id: string;
  title: string;
  subtitle?: string | null;
  statusLine?: string | null;
  rawTranscriptDocId?: string | null;
  minutesDocId?: string | null;
  detailHref?: string | null;
  canDelete?: boolean;
  canRetry?: boolean;
  progress?: ReactNode;
  doneLabel?: ReactNode;
}

export interface LinkedRecordingListProps {
  items: LinkedRecordingListItem[];

  emptyText: string;
  loading?: boolean;
  errorText?: string | null;
  disabled?: boolean;
  onRetry?: (recordingId: string) => Promise<void> | void;
  onDelete?: (recordingId: string) => Promise<void> | void;
  onError?: (error: unknown) => void;
}

export interface LinkedRecordingsForTargetProps {
  targetApp: string;
  targetType: string;
  targetId: string;
  title?: string;
  emptyText?: string;
  showHeader?: boolean;
}

type RecordingDocViewerTarget = {
  docId: string;
  title: string;
};

function iconButtonClass(tone: 'default' | 'danger' = 'default'): string {
  return [
    'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors',
    tone === 'danger'
      ? 'border-[var(--ui-color-danger)]/35 text-[var(--ui-color-danger)] hover:bg-[var(--ui-color-danger)]/10 disabled:opacity-50'
      : 'border-app-border bg-app-surface text-app-ink/70 hover:border-app-ink/30 hover:bg-app-surface-hover hover:text-app-ink disabled:opacity-50',
  ].join(' ');
}

export function LinkedRecordingList({
  items,
  emptyText,
  loading = false,
  errorText = null,
  disabled = false,
  onRetry,
  onDelete,
  onError,
}: LinkedRecordingListProps) {
  const { t } = useTranslation(['apps', 'common']);
  const [docViewer, setDocViewer] = useState<RecordingDocViewerTarget | null>(
    null,
  );
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);

  const handleRetry = useCallback(
    async (recordingId: string) => {
      if (!onRetry) return;
      setActionBusyId(recordingId);
      try {
        await onRetry(recordingId);
      } catch (error) {
        onError?.(error);
      } finally {
        setActionBusyId(null);
      }
    },
    [onError, onRetry],
  );

  const handleDelete = useCallback(
    async (recordingId: string) => {
      if (!onDelete) return;
      setActionBusyId(recordingId);
      try {
        await onDelete(recordingId);
      } catch (error) {
        onError?.(error);
      } finally {
        setActionBusyId(null);
      }
    },
    [onDelete, onError],
  );

  if (loading) {
    return (
      <div className="flex min-h-20 items-center justify-center rounded-md border border-app-border bg-app-surface-sidebar text-app-ink/45">
        <Loader2 size={18} className="animate-spin" />
      </div>
    );
  }

  if (errorText) {
    return (
      <div className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-[var(--ui-color-danger)]">
        {errorText}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-center text-app-ink/45">
        {emptyText}
      </div>
    );
  }

  return (
    <>
      <ul className="space-y-2">
        {items.map((item) => {
          const actionBusy = actionBusyId === item.id;
          const isBusy = disabled || actionBusy;
          const detailHref =
            item.detailHref ??
            buildAppHref({
              routeId: 'recording.detail',
              pathParams: { recordingId: item.id },
            });
          return (
            <li
              key={item.id}
              className="rounded-md border border-app-border bg-app-surface-sidebar px-2.5 py-2 transition-colors hover:bg-app-surface-hover/60"
            >
              <div className="grid min-w-0 gap-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <AudioWaveform
                      size={15}
                      className="shrink-0 text-app-accent"
                    />
                    <p className="app-text-body min-w-0 truncate text-app-ink">
                      {item.title}
                    </p>
                  </div>
                  {item.subtitle ? (
                    <p className="app-text-caption mt-1 break-words text-app-ink/50">
                      {item.subtitle}
                    </p>
                  ) : null}
                  {item.statusLine ? (
                    <p className="app-text-caption mt-1 break-words text-app-ink/60">
                      {item.statusLine}
                    </p>
                  ) : null}
                  {item.doneLabel ? (
                    <p className="app-text-caption mt-1 text-app-ink/60">
                      {item.doneLabel}
                    </p>
                  ) : null}
                </div>

                <div className="flex shrink-0 flex-wrap items-center gap-1">
                  <Link
                    to={detailHref}
                    aria-label={t('apps:recording.actions.play')}
                    title={t('apps:recording.actions.play')}
                    className={iconButtonClass()}
                  >
                    <Play size={15} />
                  </Link>
                  {item.rawTranscriptDocId ? (
                    <button
                      type="button"
                      onClick={() =>
                        setDocViewer({
                          docId: item.rawTranscriptDocId as string,
                          title: t('apps:recording.detail.rawTranscriptDoc'),
                        })
                      }
                      aria-haspopup="dialog"
                      aria-label={t('apps:recording.detail.rawTranscriptDoc')}
                      title={t('apps:recording.detail.rawTranscriptDoc')}
                      className={iconButtonClass()}
                      disabled={isBusy}
                    >
                      <FileText size={15} />
                    </button>
                  ) : null}
                  {item.minutesDocId ? (
                    <button
                      type="button"
                      onClick={() =>
                        setDocViewer({
                          docId: item.minutesDocId as string,
                          title: t('apps:recording.detail.minutesDoc'),
                        })
                      }
                      aria-haspopup="dialog"
                      aria-label={t('apps:recording.detail.minutesDoc')}
                      title={t('apps:recording.detail.minutesDoc')}
                      className={iconButtonClass()}
                      disabled={isBusy}
                    >
                      <ScrollText size={15} />
                    </button>
                  ) : null}
                  {item.canRetry && onRetry ? (
                    <button
                      type="button"
                      onClick={() => void handleRetry(item.id)}
                      aria-label={t('apps:recording.actions.retry')}
                      title={t('apps:recording.actions.retry')}
                      className={iconButtonClass('danger')}
                      disabled={isBusy}
                    >
                      {actionBusy ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <RefreshCw size={15} />
                      )}
                    </button>
                  ) : null}
                  {item.canDelete && onDelete ? (
                    <button
                      type="button"
                      onClick={() => void handleDelete(item.id)}
                      aria-label={t('common:actions.delete')}
                      title={t('common:actions.delete')}
                      className={iconButtonClass('danger')}
                      disabled={isBusy}
                    >
                      {actionBusy ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Trash2 size={15} />
                      )}
                    </button>
                  ) : null}
                </div>
              </div>

              {item.progress ? (
                <div className="mt-2">{item.progress}</div>
              ) : null}
            </li>
          );
        })}
      </ul>
      <DocsViewerModal
        open={docViewer !== null}
        itemId={docViewer?.docId}
        fallbackTitle={docViewer?.title}
        onOpenChange={(open) => {
          if (!open) setDocViewer(null);
        }}
      />
    </>
  );
}

export function LinkedRecordingsForTarget({
  targetApp,
  targetType,
  targetId,
  title,
  emptyText,
  showHeader = true,
}: LinkedRecordingsForTargetProps) {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const recordingScope = useMemo(
    () => ({
      kind: 'target' as const,
      targetApp,
      targetType,
      targetId,
    }),
    [targetApp, targetId, targetType],
  );
  const recordingCollection = useRecordingCollectionWorkflow({
    token,
    scope: recordingScope,
    messages: {
      loadFailed: t('recording.errors.loadFailed'),
      retryFailed: t('recording.errors.retryFailed'),
      deleteFailed: t('recording.errors.loadFailed'),
    },
  });
  const { error: errorText, items: recordings, loading } = recordingCollection;

  const retryLinkedRecording = useCallback(
    async (recordingId: string) => {
      await recordingCollection.retry(recordingId);
    },
    [recordingCollection],
  );

  const linkedItems = useMemo<LinkedRecordingListItem[]>(
    () =>
      recordings.map((recording) => {
        const isOwner = user?.id === recording.owner_id;
        return {
          id: recording.id,
          title: titleFor(recording, t('recording.untitled')),
          subtitle: `${formatBytes(recording.file_size)} · ${recording.mime_type}`,
          detailHref: buildAppHref({
            routeId: 'recording.detail',
            pathParams: { recordingId: recording.id },
          }),
          canRetry: isOwner && hasFailedStage(recording),
          progress: <RecordingStageRail recording={recording} compact />,
        };
      }),
    [recordings, t, user?.id],
  );

  return (
    <div className="space-y-2">
      {showHeader ? (
        <div className="flex items-center gap-2">
          <AudioWaveform size={14} className="text-app-ink/50" />
          <h3 className="app-text-title-md text-app-ink">
            {title ?? t('recording.linked.title')}
          </h3>
          <span className="app-text-caption text-app-ink/40">
            {recordings.length}
          </span>
        </div>
      ) : null}
      <LinkedRecordingList
        items={linkedItems}
        emptyText={emptyText ?? t('recording.linked.empty')}
        loading={loading}
        errorText={errorText}
        onRetry={retryLinkedRecording}
        onError={(error) => recordingCollection.setError(error)}
      />
    </div>
  );
}
