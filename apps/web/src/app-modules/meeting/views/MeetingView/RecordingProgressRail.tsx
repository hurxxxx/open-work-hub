import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  MeetingRecording,
  MeetingRecordingStatus,
} from '../../api/meeting-api';

const STAGES = [
  { key: 'pending' },
  { key: 'transcribing' },
  { key: 'summarizing' },
  { key: 'extracting_insights' },
  { key: 'generating_doc' },
  { key: 'done' },
] as const satisfies ReadonlyArray<{ key: MeetingRecordingStatus }>;

// Failure rail should freeze at the "generating_doc" marker (final
// pipeline stage before completion). Deriving from STAGES keeps this
// correct when stages are inserted — hard-coding the index would drift.
const FAILED_STAGE_INDEX = STAGES.findIndex((stage) => stage.key === 'generating_doc');

function stageIndex(status: MeetingRecordingStatus): number {
  const index = STAGES.findIndex((stage) => stage.key === status);
  if (index >= 0) return index;
  if (status === 'failed') return FAILED_STAGE_INDEX;
  return 0;
}

export function RecordingProgressRail({
  recording,
  onRetry,
}: {
  recording: MeetingRecording;
  onRetry?: () => void;
}) {
  const { t } = useTranslation('apps');
  const currentIndex = stageIndex(recording.transcription_status);
  const active = recording.transcription_status !== 'failed' && recording.transcription_status !== 'done';
  return (
    <div className="space-y-2" aria-live="polite">
      <div className="flex items-center gap-2">
        {STAGES.map((stage, index) => {
          const done = index < currentIndex || recording.transcription_status === 'done';
          const current = index === currentIndex && active;
          return (
            <div key={stage.key} className="flex flex-1 items-center gap-2">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] ${
                  done
                    ? 'border-app-accent bg-app-accent text-app-accent-fg'
                    : current
                      ? 'border-app-accent text-app-accent'
                      : 'border-app-border text-app-ink/40'
                }`}
              >
                {done ? <CheckCircle2 size={12} /> : current ? <Loader2 size={12} className="animate-spin" /> : index + 1}
              </div>
              {index < STAGES.length - 1 ? (
                <div className={`h-px flex-1 ${done ? 'bg-app-accent' : 'bg-app-border'}`} />
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/60">
          {recording.transcription_status === 'failed'
            ? t('meeting.recordingProgress.failed')
            : t('meeting.recordingProgress.progress', { progress: recording.progress_pct })}
        </p>
        {recording.transcription_status === 'failed' && onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="app-text-caption inline-flex items-center gap-1 text-[var(--ui-color-danger)] hover:underline"
          >
            <AlertTriangle size={12} />
            {t('meeting.recordingProgress.retry')}
          </button>
        ) : null}
      </div>
      {recording.failure_reason ? (
        <p className="app-text-caption text-[var(--ui-color-danger)]">{recording.failure_reason}</p>
      ) : null}
    </div>
  );
}
