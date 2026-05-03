import { useTranslation } from 'react-i18next';

import type { TemplatePreset } from './template-presets';
import { TEMPLATE_MOCKUPS } from './mockups';

interface TemplateCardProps {
  template: TemplatePreset;
  selected?: boolean;
  onPick: () => void;
}

export function TemplateCard({ template, selected, onPick }: TemplateCardProps) {
  const { t } = useTranslation('apps');
  const Mockup = TEMPLATE_MOCKUPS[template.mockupId];
  const name = t(`ai.imageWizard.templates.${template.id}.name`, { defaultValue: template.id });
  const hint = t(`ai.imageWizard.templates.${template.id}.hint`, { defaultValue: '' });
  const categoryLabel = t(`ai.imageWizard.gallery.categories.${template.category}`, {
    defaultValue: template.category,
  });

  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={selected}
      className={`group flex flex-col overflow-hidden rounded-lg border bg-app-surface text-left text-app-accent transition-all ${
        selected
          ? 'border-app-accent ring-2 ring-app-accent/40'
          : 'border-app-border hover:-translate-y-0.5 hover:border-app-accent/50 hover:shadow-md'
      }`}
    >
      <span className="block aspect-[16/10] w-full overflow-hidden border-b border-app-border bg-app-surface-sidebar">
        <Mockup />
      </span>
      <span className="flex flex-col gap-1 p-3">
        <span className="app-text-body font-medium text-app-ink">{name}</span>
        <span className="flex items-center gap-1.5 app-text-caption text-app-ink/50">
          <span className="rounded bg-app-surface-hover px-1.5 py-0.5">{categoryLabel}</span>
          {hint ? <span className="line-clamp-1">· {hint}</span> : null}
        </span>
      </span>
    </button>
  );
}

export default TemplateCard;
