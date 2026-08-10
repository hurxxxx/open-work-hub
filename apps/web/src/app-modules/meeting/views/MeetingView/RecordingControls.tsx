import { Loader2, Lock, Mic, Square, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { formatByteSize } from '@/src/platform/format/byte-size';
import type {
  ActiveRecordingLock,
  MeetingTaskLink,
} from '../../api/meeting-api';

function formatElapsed(totalSec: number): string {
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, '0'))
    .join(':');
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
  wakeLockWarning,
  inputWarning,
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
  wakeLockWarning: string | null;
  inputWarning: string | null;
  /**
   * Non-null when another participant currently holds the recording lock.
   * Disables the local start affordances and renders an inline notice so the
   * user understands why they can't record. Null when nobody else is recording
   * (or when the viewer themselves is the active recorder).
   */
  lockedByOther: ActiveRecordingLock | null;
  onStart: (linkedTaskId: string | null) => Promise<void> | void;
  onStop: () => void;
  onImportFile: (
    file: File,
    linkedTaskId: string | null,
  ) => Promise<void> | void;
}) {
  const { t } = useTranslation('apps');
  const [linkedTaskId, setLinkedTaskId] = useState<string | null>(
    taskLinks[0]?.task_id ?? null,
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function handleImportFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await onImportFile(file, linkedTaskId);
  }

  return (
    <div className="space-y-3 rounded-md border border-app-border bg-app-surface-sidebar p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="app-text-body text-app-ink">
            {t('meeting.recordingControls.title')}
          </p>
          <p className="app-text-caption text-app-ink/60">
            {browserSupported
              ? t('meeting.recordingControls.browserSupported')
              : t('meeting.recordingControls.browserUnsupported')}
          </p>
        </div>
        {isBusy ? (
          <Loader2 size={16} className="animate-spin text-app-ink/40" />
        ) : null}
      </div>

      {taskLinks.length > 0 ? (
        <label className="block">
          <span className="app-text-caption mb-1 block text-app-ink/60">
            {t('meeting.recordingControls.linkedTask')}
          </span>
          <select
            className="app-field-input"
            value={linkedTaskId ?? ''}
            onChange={(event) => setLinkedTaskId(event.target.value || null)}
          >
            <option value="">
              {t('meeting.recordingControls.noSelection')}
            </option>
            {taskLinks.map((link) => (
              <option key={link.id} value={link.task_id}>
                {link.list_key
                  ? `${link.list_key}-${link.task_number}`
                  : link.task_title}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {persistWarning ? (
        <p className="app-text-caption text-app-warning-text">
          {persistWarning}
        </p>
      ) : null}

      {wakeLockWarning ? (
        <p className="app-text-caption text-app-warning-text">
          {wakeLockWarning}
        </p>
      ) : null}

      {inputWarning ? (
        <p className="app-text-caption text-app-warning-text">{inputWarning}</p>
      ) : null}

      {lockedByOther ? (
        <output className="flex items-start gap-2 rounded-md border border-app-border bg-app-surface px-3 py-2">
          <Lock size={14} className="mt-0.5 shrink-0 text-app-ink/50" />
          <div className="min-w-0">
            <p className="app-text-caption font-medium text-app-ink">
              {t('meeting.recordingControls.lockedByUser', {
                name: lockedByOther.user_name,
              })}
            </p>
            <p className="app-text-caption text-app-ink/60">
              {t('meeting.recordingControls.lockedDescription')}
            </p>
          </div>
        </output>
      ) : null}

      {isRecording ? (
        <div className="rounded-md border border-app-accent/20 bg-app-accent/5 px-3 py-2">
          <div className="flex items-center gap-2 text-app-accent">
            <span className="size-2 rounded-full bg-[var(--ui-color-danger)]" />
            <span className="app-text-caption font-medium">
              {t('meeting.recordingControls.recording')}
            </span>
          </div>
          <p className="app-text-body mt-1 text-app-ink">
            {formatElapsed(elapsedSec)}
          </p>
          <p className="app-text-caption text-app-ink/60">
            {t('meeting.recordingControls.localUploadProgress', {
              queued: formatByteSize(queuedBytes),
              uploaded: formatByteSize(uploadedBytes),
            })}
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
            {isRecording
              ? t('meeting.recordingControls.stop')
              : t('meeting.recordingControls.start')}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isBusy || Boolean(lockedByOther)}
          className="inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink transition-colors hover:bg-app-surface-hover disabled:opacity-60"
        >
          <Upload size={14} />
          {t('meeting.recordingControls.uploadAudio')}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*"
          aria-label={t('meeting.recordingControls.uploadAudio')}
          className="hidden"
          onChange={handleImportFile}
        />
      </div>
    </div>
  );
}
