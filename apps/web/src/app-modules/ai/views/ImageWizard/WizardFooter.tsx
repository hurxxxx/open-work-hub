import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface WizardFooterProps {
  onPrev?: () => void;
  onNext?: () => void;
  onSkip?: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
  hidden?: boolean;
}

export function WizardFooter({
  onPrev,
  onNext,
  onSkip,
  nextDisabled,
  nextLabel,
  hidden,
}: WizardFooterProps) {
  const { t } = useTranslation('apps');
  if (hidden) return null;
  return (
    <div className="sticky bottom-0 left-0 right-0 z-10 flex items-center justify-between border-t border-app-border bg-app-surface/95 px-6 py-3 backdrop-blur">
      <div>
        {onPrev ? (
          <button
            type="button"
            onClick={onPrev}
            className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
          >
            <ArrowLeft size={14} />
            {t('ai.imageWizard.wizard.prev')}
          </button>
        ) : <span />}
      </div>
      <div className="flex items-center gap-2">
        {onSkip ? (
          <button
            type="button"
            onClick={onSkip}
            className="rounded-md px-3 py-2 app-text-control-sm text-app-ink/60 hover:text-app-ink"
          >
            {t('ai.imageWizard.wizard.skip')}
          </button>
        ) : null}
        {onNext ? (
          <button
            type="button"
            onClick={onNext}
            disabled={nextDisabled}
            className="flex items-center gap-1 rounded-md bg-app-accent px-4 py-2 app-text-control-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-40"
          >
            {nextLabel ?? t('ai.imageWizard.wizard.next')}
            <ArrowRight size={14} />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default WizardFooter;
