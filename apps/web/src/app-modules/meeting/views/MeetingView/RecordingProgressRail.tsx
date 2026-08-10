import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { MeetingRecording } from '../../api/meeting-api';

import {
  projectRecordingProgressStages,
  RECORDING_PROGRESS_STAGES,
  type RecordingProgressStageKey,
} from './recording-progress-rail-model';

const STAGE_LABEL_KEYS: Record<RecordingProgressStageKey, string> = {
  pending: 'meeting.recordingProgress.stages.pending',
  transcribing: 'meeting.recordingProgress.stages.transcribing',
  summarizing: 'meeting.recordingProgress.stages.summarizing',
  extracting_insights: 'meeting.recordingProgress.stages.extractingInsights',
  generating_doc: 'meeting.recordingProgress.stages.generatingDoc',
  done: 'meeting.recordingProgress.stages.done',
};

const STAGE_STATE_LABEL_KEYS = {
  complete: 'meeting.recordingProgress.stageStates.complete',
  current: 'meeting.recordingProgress.stageStates.current',
  upcoming: 'meeting.recordingProgress.stageStates.upcoming',
} as const;

export function RecordingProgressRail({
  recording,
  onRetry,
}: {
  recording: MeetingRecording;
  onRetry?: () => void;
}) {
  const { t } = useTranslation('apps');
  const stages = projectRecordingProgressStages(recording.transcription_status);
  return (
    <div className="space-y-2" aria-live="polite">
      <ol
        aria-label={t('meeting.recordingProgress.pipeline')}
        className="flex items-center gap-2"
      >
        {stages.map((stage, index) => {
          return (
            <li
              key={stage.key}
              aria-current={stage.current ? 'step' : undefined}
              aria-label={`${t(STAGE_LABEL_KEYS[stage.key])}: ${t(STAGE_STATE_LABEL_KEYS[stage.state])}`}
              className="flex flex-1 items-center gap-2"
            >
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] ${
                  stage.done
                    ? 'border-app-accent bg-app-accent text-app-accent-fg'
                    : stage.current
                      ? 'border-app-accent text-app-accent'
                      : 'border-app-border text-app-ink/40'
                }`}
              >
                {stage.done ? (
                  <CheckCircle2 size={12} />
                ) : stage.current ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  stage.marker
                )}
              </div>
              {index < RECORDING_PROGRESS_STAGES.length - 1 ? (
                <div
                  className={`h-px flex-1 ${stage.done ? 'bg-app-accent' : 'bg-app-border'}`}
                />
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className="flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/60">
          {recording.transcription_status === 'failed'
            ? t('meeting.recordingProgress.failed')
            : t('meeting.recordingProgress.progress', {
                progress: recording.progress_pct,
              })}
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
        <p className="app-text-caption text-[var(--ui-color-danger)]">
          {recording.failure_reason}
        </p>
      ) : null}
    </div>
  );
}
