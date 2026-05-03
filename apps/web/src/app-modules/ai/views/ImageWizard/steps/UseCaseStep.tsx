import { useTranslation } from 'react-i18next';

import { USE_CASE_OPTIONS, type UseCaseId } from '../wizard-options';

interface UseCaseStepProps {
  useCase: string;
  useCaseOther: string;
  disabled?: boolean;
  onChange: (next: { useCase?: string; useCaseOther?: string }) => void;
}

export function UseCaseStep({
  useCase,
  useCaseOther,
  disabled = false,
  onChange,
}: UseCaseStepProps) {
  const { t } = useTranslation('apps');
  return (
    <div className="space-y-3">
      <p className="app-text-caption text-app-ink/60">
        {t('ai.imageWizard.steps.useCase.description')}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {USE_CASE_OPTIONS.map((id: UseCaseId) => {
          const isSelected = useCase === id;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={isSelected}
              disabled={disabled}
              onClick={() => onChange({ useCase: id })}
              className={`rounded-md border px-3 py-3 text-left transition-colors ${
                isSelected
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              <p className="app-text-body font-medium">
                {t(`ai.imageWizard.usecase.${id}.label`)}
              </p>
              <p className="app-text-caption text-app-ink/50">
                {t(`ai.imageWizard.usecase.${id}.hint`)}
              </p>
            </button>
          );
        })}
      </div>
      {useCase === 'other' ? (
        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.usecase.otherLabel')}
          </label>
          <input
            type="text"
            value={useCaseOther}
            maxLength={200}
            disabled={disabled}
            onChange={(event) => onChange({ useCaseOther: event.target.value })}
            placeholder={t('ai.imageWizard.usecase.otherPlaceholder')}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>
      ) : null}
    </div>
  );
}

export default UseCaseStep;
