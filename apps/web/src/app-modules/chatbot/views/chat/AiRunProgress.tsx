import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export interface AiRunProgressValue {
  currentStage: string | null;
  progressPercent: number | null;
}

export function AiRunProgress({ value }: { value: AiRunProgressValue }) {
  const { t } = useTranslation('apps');
  const progress =
    value.progressPercent === null
      ? null
      : Math.min(100, Math.max(0, Math.round(value.progressPercent)));

  return (
    <div
      className="min-w-[min(28rem,70vw)] space-y-2"
      aria-label={t('ai.runProgress.label')}
      role="status"
    >
      <div className="flex items-center gap-2">
        <Loader2 aria-hidden="true" className="animate-spin" size={16} />
        <span className="font-medium text-app-ink">
          {t('ai.runProgress.title')}
        </span>
        {progress !== null ? (
          <span className="ml-auto tabular-nums text-app-ink/55">
            {t('ai.runProgress.percent', { progress })}
          </span>
        ) : null}
      </div>
      {value.currentStage ? (
        <p className="app-text-caption text-app-ink/60">
          {t('ai.runProgress.stage', { stage: value.currentStage })}
        </p>
      ) : null}
      {progress !== null ? (
        <div
          aria-hidden="true"
          className="h-1.5 overflow-hidden rounded-full bg-app-border"
        >
          <div
            className="h-full rounded-full bg-app-accent transition-[width] duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}
