import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';

import type { Recording } from '../api/recording-api';

type StageState = 'done' | 'inProgress' | 'pending' | 'failed';

type StageKey = 'audio' | 'transcript' | 'rawDoc' | 'minutesDoc';

interface Stage {
  key: StageKey;
  state: StageState;
}

function pipelineState(value: string): StageState {
  if (value === 'done') return 'done';
  if (value === 'failed') return 'failed';
  if (value === 'creating' || value === 'transcribing') return 'inProgress';
  return 'pending';
}

function deriveStages(recording: Recording): Stage[] {
  return [
    { key: 'audio', state: 'done' },
    { key: 'transcript', state: pipelineState(recording.transcript_status) },
    { key: 'rawDoc', state: pipelineState(recording.raw_transcript_doc_status) },
    { key: 'minutesDoc', state: pipelineState(recording.minutes_doc_status) },
  ];
}

export function RecordingStageRail({
  recording,
  compact = false,
  onRetry,
}: {
  recording: Recording;
  compact?: boolean;
  onRetry?: () => void;
}) {
  const { t } = useTranslation('apps');
  const stages = deriveStages(recording);
  const failedStage = stages.find((stage) => stage.state === 'failed');
  const activeStage = !failedStage ? stages.find((stage) => stage.state === 'inProgress') : undefined;
  const allDone = stages.every((stage) => stage.state === 'done');
  const statusLabel = failedStage
    ? t('recording.status.failedLabel', { stage: t(`recording.status.stages.${failedStage.key}`) })
    : activeStage
      ? t('recording.status.progressLabel', { stage: t(`recording.status.stages.${activeStage.key}`) })
      : allDone
        ? t('recording.status.allDone')
        : t('recording.status.pendingLabel');

  const circleSize = compact ? 'h-5 w-5 text-[10px]' : 'h-6 w-6 text-[11px]';
  const iconSize = compact ? 10 : 12;

  return (
    <div className="space-y-2" aria-live="polite">
      <div className="flex items-center gap-2">
        {stages.map((stage, index) => {
          const isLast = index === stages.length - 1;
          const tone =
            stage.state === 'done'
              ? 'border-app-accent bg-app-accent text-app-accent-fg'
              : stage.state === 'inProgress'
                ? 'border-app-accent text-app-accent'
                : stage.state === 'failed'
                  ? 'border-[var(--ui-color-danger)] text-[var(--ui-color-danger)]'
                  : 'border-app-border text-app-ink/40';
          const stageLabel = t(`recording.status.stages.${stage.key}`);
          const stateLabel = t(`recording.status.state.${stage.state}`);
          return (
            <div key={stage.key} className="flex flex-1 items-center gap-2">
              <div
                className={`flex shrink-0 items-center justify-center rounded-full border ${circleSize} ${tone}`}
                title={`${stageLabel}: ${stateLabel}`}
                aria-label={`${stageLabel}: ${stateLabel}`}
              >
                {stage.state === 'done' ? (
                  <CheckCircle2 size={iconSize} />
                ) : stage.state === 'inProgress' ? (
                  <Loader2 size={iconSize} className="animate-spin" />
                ) : stage.state === 'failed' ? (
                  <AlertTriangle size={iconSize} />
                ) : (
                  <span>{index + 1}</span>
                )}
              </div>
              {!isLast ? (
                <div
                  className={`h-px flex-1 ${
                    stage.state === 'done' ? 'bg-app-accent' : 'bg-app-border'
                  }`}
                />
              ) : null}
            </div>
          );
        })}
      </div>

      {compact ? (
        <p className="app-text-caption text-app-ink/55">{statusLabel}</p>
      ) : (
        <div className="flex items-center justify-between gap-3">
          <p className="app-text-caption text-app-ink/60">{statusLabel}</p>
          {failedStage && onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="app-text-caption inline-flex items-center gap-1 text-[var(--ui-color-danger)] hover:underline"
            >
              <RefreshCw size={12} />
              {t('recording.actions.retry')}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default RecordingStageRail;
