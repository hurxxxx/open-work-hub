import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface StepSummaryProps {
  stepNumber: number;
  title: string;
  value: string | null;
  onEdit?: () => void;
}

export function StepSummary({ stepNumber, title, value, onEdit }: StepSummaryProps) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex items-center justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <div className="flex items-center gap-2 min-w-0">
        <span className="flex size-5 items-center justify-center rounded-full bg-app-accent/15 text-app-accent">
          <Check size={11} />
        </span>
        <span className="app-text-control-sm text-app-ink/60 shrink-0">
          {stepNumber}. {title}
        </span>
        {value ? (
          <span className="app-text-control-sm font-medium text-app-ink truncate">
            : {value}
          </span>
        ) : null}
      </div>
      {onEdit ? (
        <button
          type="button"
          onClick={onEdit}
          className="app-text-control-sm text-app-accent hover:underline shrink-0"
        >
          {t('ai.imageWizard.wizard.editAction')}
        </button>
      ) : null}
    </div>
  );
}
