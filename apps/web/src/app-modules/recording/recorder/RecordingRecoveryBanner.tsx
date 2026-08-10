import { useTranslation } from 'react-i18next';

import { formatByteSize } from '@/src/platform/format/byte-size';
import {
  getRecordingRecoveryAction,
  planRecordingRecoverySession,
  type RecordingRecoveryPlan,
} from './recording-recovery-session-plan';
import type { RecoverySessionItem } from './useRecordingRecovery';

export function RecordingRecoveryBanner({
  item,
  onResumeUpload,
  onContinueRecording,
  onDownload,
  onImport,
  onDiscard,
  onFinalizeUploadedOnly,
  plan: providedPlan,
}: {
  item: RecoverySessionItem;
  onResumeUpload?: () => void;
  onContinueRecording?: () => void;
  onDownload?: () => void;
  onImport?: () => void;
  onDiscard?: () => void;
  onFinalizeUploadedOnly?: () => void;
  plan?: RecordingRecoveryPlan;
}) {
  const { t, i18n } = useTranslation('apps');
  const plan = providedPlan ?? planRecordingRecoverySession(item);
  return (
    <div className="rounded-md border border-app-warning-border bg-app-warning-bg p-3 text-app-warning-text">
      <p className="app-text-body font-medium">
        {t('recording.recovery.title')}
      </p>
      <p className="app-text-caption mt-1 text-app-warning-text/80">
        {plan.hasLocal
          ? t('recording.recovery.localCopy', {
              bytes: formatByteSize(plan.localBytes),
            })
          : t('recording.recovery.remoteOnly')}
        {plan.hasRemote
          ? ` ${t('recording.recovery.remoteBytes', {
              bytes: formatByteSize(plan.remoteBytes),
            })}`
          : ''}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {getRecordingRecoveryAction(plan, 'resume-upload') && onResumeUpload ? (
          <ActionButton
            label={t('recording.recovery.resumeUpload')}
            onClick={onResumeUpload}
          />
        ) : null}
        {getRecordingRecoveryAction(plan, 'continue-recording') &&
        onContinueRecording ? (
          <ActionButton
            label={t('recording.recovery.continueRecording')}
            onClick={onContinueRecording}
          />
        ) : null}
        {plan.hasLocal && plan.previewUrl ? (
          <audio
            aria-label={t('recording.recovery.previewAudio')}
            controls
            src={plan.previewUrl}
            className="h-8 max-w-full"
          >
            <track
              kind="captions"
              src="data:text/vtt,WEBVTT%0A"
              srcLang={i18n.language}
              label={t('recording.recovery.previewCaptions')}
              default
            />
          </audio>
        ) : null}
        {getRecordingRecoveryAction(plan, 'download-original') && onDownload ? (
          <ActionButton
            label={t('recording.recovery.downloadOriginal')}
            onClick={onDownload}
          />
        ) : null}
        {getRecordingRecoveryAction(plan, 'import-original') && onImport ? (
          <ActionButton
            label={t('recording.recovery.importOriginal')}
            onClick={onImport}
          />
        ) : null}
        {getRecordingRecoveryAction(plan, 'finalize-uploaded') &&
        onFinalizeUploadedOnly ? (
          <ActionButton
            label={t('recording.recovery.finalizeUploaded')}
            onClick={onFinalizeUploadedOnly}
          />
        ) : null}
        {getRecordingRecoveryAction(plan, 'discard') && onDiscard ? (
          <ActionButton
            label={t('recording.recovery.discard')}
            onClick={onDiscard}
            danger
          />
        ) : null}
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
          : 'bg-white text-app-warning-text ring-1 ring-amber-300/60'
      }`}
    >
      {label}
    </button>
  );
}
