import { useTranslation } from 'react-i18next';

import type { StylePayload } from '../../../api/image-wizard-api';
import {
  BACKGROUND_OPTIONS,
  PALETTE_OPTIONS,
  QUALITY_OPTIONS,
  STYLE_CHIPS,
  type BackgroundId,
  type PaletteId,
  type QualityId,
  type StyleChipId,
} from '../wizard-options';

interface StyleStepProps {
  style: StylePayload;
  disabled?: boolean;
  onChange: (next: StylePayload) => void;
}

export function StyleStep({ style, disabled = false, onChange }: StyleStepProps) {
  const { t } = useTranslation('apps');

  function toggleChip(chip: StyleChipId) {
    const exists = style.chips.includes(chip);
    onChange({
      ...style,
      chips: exists ? style.chips.filter((c) => c !== chip) : [...style.chips, chip],
    });
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="app-text-control-sm text-app-ink/70">
          {t('ai.imageWizard.style.chipsLabel')}
        </p>
        <div className="flex flex-wrap gap-2">
          {STYLE_CHIPS.map((chip: StyleChipId) => {
            const isSelected = style.chips.includes(chip);
            return (
              <button
                key={chip}
                type="button"
                aria-pressed={isSelected}
                disabled={disabled}
                onClick={() => toggleChip(chip)}
                className={`app-text-control-sm rounded-full border px-3 py-1 transition-colors ${
                  isSelected
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
                } disabled:cursor-not-allowed disabled:opacity-60`}
              >
                {t(`ai.imageWizard.style.chips.${chip}`)}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.style.paletteLabel')}
          </label>
          <select
            value={style.palette || 'auto'}
            disabled={disabled}
            onChange={(event) =>
              onChange({ ...style, palette: event.target.value })
            }
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
          >
            {PALETTE_OPTIONS.map((value: PaletteId) => (
              <option key={value} value={value}>
                {t(`ai.imageWizard.style.palette.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.style.backgroundLabel')}
          </label>
          <select
            value={style.background || 'auto'}
            disabled={disabled}
            onChange={(event) =>
              onChange({ ...style, background: event.target.value })
            }
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
          >
            {BACKGROUND_OPTIONS.map((value: BackgroundId) => (
              <option key={value} value={value}>
                {t(`ai.imageWizard.style.background.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.style.qualityLabel')}
          </label>
          <select
            value={style.quality || 'high'}
            disabled={disabled}
            onChange={(event) =>
              onChange({ ...style, quality: event.target.value })
            }
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
          >
            {QUALITY_OPTIONS.map((value: QualityId) => (
              <option key={value} value={value}>
                {t(`ai.imageWizard.style.quality.${value}`)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

export default StyleStep;
