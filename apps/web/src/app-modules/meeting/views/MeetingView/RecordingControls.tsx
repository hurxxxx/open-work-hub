import { Loader2, Lock, Mic, Square, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

import type { ActiveRecordingLock, MeetingTaskLink } from '../../api/meeting-api';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatElapsed(totalSec: number): string {
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

export function RecordingControls({
  browserSupported,
  taskLinks,
  isRecording,
  isBusy,
  elapsedSec,
  queuedBytes,
  uploadedBytes,
  persistWarning,
  lockedByOther,
  onStart,
  onStop,
  onImportFile,
}: {
  browserSupported: boolean;
  taskLinks: MeetingTaskLink[];
  isRecording: boolean;
  isBusy: boolean;
  elapsedSec: number;
  queuedBytes: number;
  uploadedBytes: number;
  persistWarning: string | null;
  /**
   * Non-null when another participant currently holds the recording lock.
   * Disables the local start affordances and renders an inline notice so the
   * user understands why they can't record. Null when nobody else is recording
   * (or when the viewer themselves is the active recorder).
   */
  lockedByOther: ActiveRecordingLock | null;
  onStart: (linkedTaskId: string | null) => Promise<void> | void;
  onStop: () => void;
  onImportFile: (file: File, linkedTaskId: string | null) => Promise<void> | void;
}) {
  const [linkedTaskId, setLinkedTaskId] = useState<string | null>(taskLinks[0]?.issue_id ?? null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function handleImportFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await onImportFile(file, linkedTaskId);
  }

  return (
    <div className="space-y-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="app-text-body text-app-ink">회의 녹음</p>
          <p className="app-text-caption text-app-ink/60">
            {browserSupported
              ? '브라우저에 먼저 저장한 뒤 안전하게 업로드합니다.'
              : '이 브라우저에서는 라이브 녹음을 지원하지 않습니다. 음성 파일 업로드를 사용하세요.'}
          </p>
        </div>
        {isBusy ? <Loader2 size={16} className="animate-spin text-app-ink/40" /> : null}
      </div>

      {taskLinks.length > 0 ? (
        <label className="block">
          <span className="app-text-caption mb-1 block text-app-ink/60">연결할 태스크</span>
          <select
            className="w-full rounded-md border border-app-border bg-white px-2 py-2 text-sm text-app-ink"
            value={linkedTaskId ?? ''}
            onChange={(event) => setLinkedTaskId(event.target.value || null)}
          >
            <option value="">선택 안 함</option>
            {taskLinks.map((link) => (
              <option key={link.id} value={link.issue_id}>
                {link.list_key ? `${link.list_key}-${link.issue_number}` : link.issue_title}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {persistWarning ? (
        <p className="app-text-caption text-amber-700">{persistWarning}</p>
      ) : null}

      {lockedByOther ? (
        <div
          role="status"
          className="flex items-start gap-2 rounded-md border border-app-border bg-app-surface px-3 py-2"
        >
          <Lock size={14} className="mt-0.5 shrink-0 text-app-ink/50" />
          <div className="min-w-0">
            <p className="app-text-caption font-medium text-app-ink">
              {lockedByOther.user_name} 님이 녹음 중입니다.
            </p>
            <p className="app-text-caption text-app-ink/60">
              녹음이 끝나면 자동으로 다시 시작할 수 있게 됩니다. (응답 없는 녹음은 약 1분 후 자동 해제됩니다.)
            </p>
          </div>
        </div>
      ) : null}

      {isRecording ? (
        <div className="rounded-md border border-app-accent/20 bg-app-accent/5 px-3 py-2">
          <div className="flex items-center gap-2 text-app-accent">
            <span className="h-2 w-2 rounded-full bg-[var(--ui-color-danger)]" />
            <span className="app-text-caption font-medium">녹음 중</span>
          </div>
          <p className="app-text-body mt-1 text-app-ink">{formatElapsed(elapsedSec)}</p>
          <p className="app-text-caption text-app-ink/60">
            로컬 {formatBytes(queuedBytes)} · 업로드 완료 {formatBytes(uploadedBytes)}
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {browserSupported ? (
          <button
            type="button"
            onClick={() => (isRecording ? onStop() : onStart(linkedTaskId))}
            disabled={isBusy || (Boolean(lockedByOther) && !isRecording)}
            className="inline-flex items-center gap-1 rounded-md bg-app-accent px-3 py-2 text-sm font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {isRecording ? <Square size={14} /> : <Mic size={14} />}
            {isRecording ? '녹음 중지' : '녹음 시작'}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isBusy || Boolean(lockedByOther)}
          className="inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink transition-colors hover:bg-app-surface-hover disabled:opacity-60"
        >
          <Upload size={14} />
          음성 파일 업로드
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={handleImportFile}
        />
      </div>
    </div>
  );
}
