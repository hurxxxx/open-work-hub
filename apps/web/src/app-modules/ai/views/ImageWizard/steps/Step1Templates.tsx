import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { TemplateGrid } from '../templates/TemplateGrid';
import {
  TEMPLATES_BY_CATEGORY,
  TEMPLATE_CATEGORIES,
  TEMPLATE_PRESETS,
  type TemplateCategoryId,
  type TemplatePreset,
} from '../templates/template-presets';

interface Step1TemplatesProps {
  selectedTemplateId: string | null;
  userTemplates?: TemplatePreset[];
  removingUserTemplateIds?: ReadonlySet<string>;
  templateActionError?: string | null;
  onPickTemplate: (template: TemplatePreset) => void;
  onRemoveUserTemplate?: (template: TemplatePreset) => void;
  onPickBlank: () => void;
}

export function Step1Templates({
  selectedTemplateId,
  userTemplates = [],
  removingUserTemplateIds,
  templateActionError,
  onPickTemplate,
  onRemoveUserTemplate,
  onPickBlank,
}: Step1TemplatesProps) {
  const { t } = useTranslation('apps');
  const [category, setCategory] = useState<TemplateCategoryId | 'all'>('all');

  const visibleTemplates = useMemo(() => {
    if (category === 'all') return TEMPLATE_PRESETS;
    return TEMPLATES_BY_CATEGORY[category] ?? [];
  }, [category]);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h2 className="app-text-heading-2 text-app-ink">
          {t('ai.imageWizard.steps.step1.heading')}
        </h2>
        <p className="app-text-body text-app-ink/60">
          {t('ai.imageWizard.steps.step1.description')}
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <CategoryChip
          label={t('ai.imageWizard.gallery.categories.all')}
          count={TEMPLATE_PRESETS.length}
          active={category === 'all'}
          onClick={() => setCategory('all')}
        />
        {TEMPLATE_CATEGORIES.map((id) => (
          <CategoryChip
            key={id}
            label={t(`ai.imageWizard.gallery.categories.${id}`)}
            count={TEMPLATES_BY_CATEGORY[id].length}
            active={category === id}
            onClick={() => setCategory(id)}
          />
        ))}
      </div>

      {templateActionError ? (
        <div
          role="alert"
          className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
        >
          {templateActionError}
        </div>
      ) : null}

      {category === 'all' && userTemplates.length > 0 ? (
        <section className="space-y-3">
          <h3 className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.gallery.myTemplates')}
          </h3>
          <TemplateGrid
            templates={userTemplates}
            selectedId={selectedTemplateId}
            onPick={onPickTemplate}
            onRemove={onRemoveUserTemplate}
            removingIds={removingUserTemplateIds}
            removeLabel={t('ai.imageWizard.gallery.removeTemplate')}
          />
        </section>
      ) : null}

      <section className="space-y-3">
        <h3 className="app-text-control-sm text-app-ink/70">
          {category === 'all'
            ? t('ai.imageWizard.gallery.allHeading')
            : t(`ai.imageWizard.gallery.categories.${category}`)}
        </h3>
        <TemplateGrid
          templates={visibleTemplates}
          selectedId={selectedTemplateId}
          onPick={onPickTemplate}
        />
      </section>

      <div className="border-t border-app-border pt-4 text-center">
        <button
          type="button"
          onClick={onPickBlank}
          className="app-text-control-sm text-app-ink/50 hover:text-app-ink hover:underline"
        >
          {t('ai.imageWizard.gallery.startBlank')}
        </button>
      </div>
    </div>
  );
}

interface CategoryChipProps {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}

function CategoryChip({ label, count, active, onClick }: CategoryChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border px-3 py-1 app-text-control-sm transition-colors ${
        active
          ? 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-surface-sidebar text-app-ink hover:border-app-accent/50'
      }`}
    >
      <span>{label}</span>
      <span className={`text-[10px] ${active ? 'text-app-accent/70' : 'text-app-ink/40'}`}>
        {count}
      </span>
    </button>
  );
}

export default Step1Templates;
