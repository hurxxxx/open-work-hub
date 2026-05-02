import { useTranslation } from 'react-i18next';

import type { RecoverySessionItem } from './useRecordingRecovery';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function RecordingRecoveryBanner({
  item,
  onResumeUpload,
  onContinueRecording,
  onDownload,
  onImport,
  onDiscard,
  onFinalizeUploadedOnly,
}: {
  item: RecoverySessionItem;
  onResumeUpload?: () => void;
  onContinueRecording?: () => void;
  onDownload?: () => void;
  onImport?: () => void;
  onDiscard?: () => void;
  onFinalizeUploadedOnly?: () => void;
}) {
  const { t } = useTranslation('apps');
  const hasLocal = item.localSession != null;
  const hasRemote = item.remoteStaging != null;
  return (
    <div className="rounded-md border border-amber-300/50 bg-amber-50 px-3 py-3 text-amber-900">
      <p className="app-text-body font-medium">{t('meeting.recordingRecovery.title')}</p>
      <p className="app-text-caption mt-1 text-amber-900/80">
        {hasLocal
          ? t('meeting.recordingRecovery.localCopy', { bytes: formatBytes(item.localBytes) })
          : t('meeting.recordingRecovery.remoteOnly')}
        {hasRemote
          ? ` ${t('meeting.recordingRecovery.remoteBytes', {
              bytes: formatBytes(item.remoteStaging?.bytes_received ?? 0),
            })}`
          : ''}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {hasLocal && hasRemote && onResumeUpload ? (
          <ActionButton label={t('meeting.recordingRecovery.resumeUpload')} onClick={onResumeUpload} />
        ) : null}
        {hasLocal && hasRemote && onContinueRecording ? (
          <ActionButton label={t('meeting.recordingRecovery.continueRecording')} onClick={onContinueRecording} />
        ) : null}
        {hasLocal && item.previewUrl ? (
          <audio controls src={item.previewUrl} className="h-8 max-w-full" />
        ) : null}
        {hasLocal && onDownload ? <ActionButton label={t('meeting.recordingRecovery.downloadOriginal')} onClick={onDownload} /> : null}
        {hasLocal && !hasRemote && onImport ? (
          <ActionButton label={t('meeting.recordingRecovery.importOriginal')} onClick={onImport} />
        ) : null}
        {!hasLocal && hasRemote && onFinalizeUploadedOnly ? (
          <ActionButton label={t('meeting.recordingRecovery.finalizeUploaded')} onClick={onFinalizeUploadedOnly} />
        ) : null}
        {onDiscard ? <ActionButton label={t('meeting.recordingRecovery.discard')} onClick={onDiscard} danger /> : null}
      </div>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  danger = false,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1.5 text-xs font-medium ${
        danger
          ? 'bg-white text-[var(--ui-color-danger)] ring-1 ring-[var(--ui-color-danger)]/20'
          : 'bg-white text-amber-900 ring-1 ring-amber-300/60'
      }`}
    >
      {label}
    </button>
  );
}
