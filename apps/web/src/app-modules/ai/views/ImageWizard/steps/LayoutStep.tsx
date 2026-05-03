import { useTranslation } from 'react-i18next';

import type { LayoutPayload } from '../../../api/image-wizard-api';
import {
  ASPECT_OPTIONS,
  LAYOUT_OPTIONS,
  type AspectId,
  type LayoutId,
} from '../wizard-options';

interface LayoutStepProps {
  layout: LayoutPayload;
  disabled?: boolean;
  onChange: (next: LayoutPayload) => void;
}

const ASPECT_BOX: Record<AspectId, string> = {
  '1024x1024': 'h-12 w-12',
  '1536x1024': 'h-9 w-14',
  '1024x1536': 'h-14 w-9',
};

export function LayoutStep({ layout, disabled = false, onChange }: LayoutStepProps) {
  const { t } = useTranslation('apps');

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="app-text-control-sm text-app-ink/70">
          {t('ai.imageWizard.layout.layoutLabel')}
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {LAYOUT_OPTIONS.map((id: LayoutId) => {
            const isSelected = layout.layout_id === id;
            return (
              <button
                key={id}
                type="button"
                aria-pressed={isSelected}
                disabled={disabled}
                onClick={() => onChange({ ...layout, layout_id: id })}
                className={`rounded-md border px-3 py-3 text-left transition-colors ${
                  isSelected
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
                } disabled:cursor-not-allowed disabled:opacity-60`}
              >
                <p className="app-text-body font-medium">
                  {t(`ai.imageWizard.layout.layouts.${id}.label`)}
                </p>
                <p className="app-text-caption text-app-ink/50">
                  {t(`ai.imageWizard.layout.layouts.${id}.hint`)}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <p className="app-text-control-sm text-app-ink/70">
          {t('ai.imageWizard.layout.aspectLabel')}
        </p>
        <div className="flex flex-wrap gap-3">
          {ASPECT_OPTIONS.map((aspect: AspectId) => {
            const isSelected = layout.aspect === aspect;
            return (
              <button
                key={aspect}
                type="button"
                aria-pressed={isSelected}
                disabled={disabled}
                onClick={() => onChange({ ...layout, aspect })}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 transition-colors ${
                  isSelected
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
                } disabled:cursor-not-allowed disabled:opacity-60`}
              >
                <span
                  className={`block rounded border ${
                    isSelected ? 'border-app-accent' : 'border-app-ink/30'
                  } ${ASPECT_BOX[aspect]}`}
                />
                <span className="app-text-control-sm">
                  {t(`ai.imageWizard.layout.aspect.${aspect}`)}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default LayoutStep;
