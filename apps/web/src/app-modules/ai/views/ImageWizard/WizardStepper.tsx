import { useTranslation } from 'react-i18next';

import type { StepId } from './wizard-state';

export const STEP_IDS: StepId[] = [1, 2, 3, 4];

interface WizardStepperProps {
  current: StepId;
  highest: StepId;
  onJump: (step: StepId) => void;
}

export function WizardStepper({ current, highest, onJump }: WizardStepperProps) {
  const { t } = useTranslation('apps');
  return (
    <ol className="flex items-center gap-2 app-text-control-sm text-app-ink/60">
      {STEP_IDS.map((step, idx) => {
        const isCurrent = step === current;
        const isCompleted = step < current || step <= highest;
        const isClickable = step <= highest;
        return (
          <li key={step} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => isClickable && onJump(step)}
              disabled={!isClickable}
              aria-current={isCurrent ? 'step' : undefined}
              className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 transition-colors ${
                isCurrent
                  ? 'bg-app-accent/15 text-app-accent'
                  : isCompleted
                    ? 'text-app-ink hover:bg-app-surface-hover'
                    : 'cursor-not-allowed text-app-ink/30'
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold ${
                  isCurrent
                    ? 'bg-app-ink text-app-surface'
                    : isCompleted
                      ? 'bg-app-accent/30 text-app-accent'
                      : 'bg-app-surface-hover text-app-ink/40'
                }`}
              >
                {step}
              </span>
              <span className="hidden sm:inline">
                {t(`ai.imageWizard.steps.step${step}.title`, { defaultValue: `Step ${step}` })}
              </span>
            </button>
            {idx < STEP_IDS.length - 1 ? (
              <span className="hidden h-px w-6 bg-app-border sm:block" aria-hidden />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export default WizardStepper;
