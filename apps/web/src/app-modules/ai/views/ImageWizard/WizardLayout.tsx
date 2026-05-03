import { useTranslation } from 'react-i18next';
import { AlertTriangle, Check, ImageIcon, Loader2, Plus } from 'lucide-react';

import type { AutosaveState, StepId } from './wizard-state';
import { WizardStepper } from './WizardStepper';

interface WizardLayoutProps {
  step: StepId;
  highest: StepId;
  autosave: AutosaveState;
  myImagesCount: number;
  onJumpStep: (step: StepId) => void;
  onNewImage: () => void;
  onOpenMyImages: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
}

export function WizardLayout({
  step,
  highest,
  autosave,
  myImagesCount,
  onJumpStep,
  onNewImage,
  onOpenMyImages,
  children,
  footer,
}: WizardLayoutProps) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex min-h-full flex-col bg-app-surface">
      <header className="sticky top-0 z-10 flex flex-col gap-2 border-b border-app-border bg-app-surface/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="app-text-heading-3 text-app-ink">{t('ai.imageWizard.title')}</h1>
            <button
              type="button"
              onClick={onNewImage}
              className="inline-flex items-center gap-1.5 rounded-md bg-app-accent px-3 py-1.5 app-text-control-sm text-app-accent-fg transition-colors hover:bg-app-accent-hover"
            >
              <Plus size={14} />
              {t('ai.imageWizard.step4.newImageAction')}
            </button>
          </div>
          <div className="flex items-center gap-3">
            <AutosaveIndicator state={autosave} />
            <button
              type="button"
              onClick={onOpenMyImages}
              className="flex items-center gap-1.5 rounded-full border border-app-border px-3 py-1 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
            >
              <ImageIcon size={13} />
              {t('ai.imageWizard.wizard.myImages')}
              {myImagesCount > 0 ? (
                <span className="rounded-full bg-app-accent/15 px-1.5 text-app-accent">
                  {myImagesCount}
                </span>
              ) : null}
            </button>
          </div>
        </div>
        <WizardStepper current={step} highest={highest} onJump={onJumpStep} />
      </header>
      <main className="flex-1 px-6 py-5">
        <div className="mx-auto w-full max-w-6xl">{children}</div>
      </main>
      {footer}
    </div>
  );
}

interface AutosaveIndicatorProps {
  state: AutosaveState;
}

function AutosaveIndicator({ state }: AutosaveIndicatorProps) {
  const { t } = useTranslation('apps');
  if (state === 'idle') return null;
  if (state === 'saving' || state === 'pending') {
    return (
      <span className="flex items-center gap-1 app-text-caption text-app-ink/50">
        <Loader2 size={11} className="animate-spin" />
        {t('ai.imageWizard.wizard.saving')}
      </span>
    );
  }
  if (state === 'saved') {
    return (
      <span className="flex items-center gap-1 app-text-caption text-app-ink/50">
        <Check size={11} />
        {t('ai.imageWizard.wizard.saved')}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 app-text-caption text-[var(--ui-color-danger)]">
      <AlertTriangle size={11} />
      {t('ai.imageWizard.wizard.saveError')}
    </span>
  );
}

export default WizardLayout;
