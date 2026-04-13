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
  const hasLocal = item.localSession != null;
  const hasRemote = item.remoteStaging != null;
  return (
    <div className="rounded-md border border-amber-300/50 bg-amber-50 px-3 py-3 text-amber-900">
      <p className="app-text-body font-medium">미완료 녹음이 발견되었습니다.</p>
      <p className="app-text-caption mt-1 text-amber-900/80">
        {hasLocal
          ? `이 기기에 ${formatBytes(item.localBytes)} 분량의 복구본이 남아 있습니다.`
          : '이 기기에는 복구본이 없지만 서버에 업로드된 분량이 남아 있습니다.'}
        {hasRemote ? ` 서버 업로드 분량은 ${formatBytes(item.remoteStaging?.bytes_received ?? 0)} 입니다.` : ''}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {hasLocal && hasRemote && onResumeUpload ? (
          <ActionButton label="업로드 이어서 하기" onClick={onResumeUpload} />
        ) : null}
        {hasLocal && hasRemote && onContinueRecording ? (
          <ActionButton label="복구 후 추가 녹음" onClick={onContinueRecording} />
        ) : null}
        {hasLocal && item.previewUrl ? (
          <audio controls src={item.previewUrl} className="h-8 max-w-full" />
        ) : null}
        {hasLocal && onDownload ? <ActionButton label="원본 다운로드" onClick={onDownload} /> : null}
        {hasLocal && !hasRemote && onImport ? (
          <ActionButton label="원본 파일로 다시 업로드" onClick={onImport} />
        ) : null}
        {!hasLocal && hasRemote && onFinalizeUploadedOnly ? (
          <ActionButton label="업로드된 분량으로 확정" onClick={onFinalizeUploadedOnly} />
        ) : null}
        {onDiscard ? <ActionButton label="폐기" onClick={onDiscard} danger /> : null}
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
