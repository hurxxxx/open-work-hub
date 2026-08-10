import { useState } from 'react';
import { Expand, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { getBuiltinTemplatePreviewUrl, type TemplatePreset } from './template-presets';
import { TEMPLATE_MOCKUPS } from './mockups';
import { ImageLightbox } from '../chat/ImageLightbox';

interface TemplateCardProps {
  template: TemplatePreset;
  selected?: boolean;
  onPick: () => void;
  onRemove?: () => void;
  removeLabel?: string;
  removeBusy?: boolean;
}

export function TemplateCard({
  template,
  selected,
  onPick,
  onRemove,
  removeLabel,
  removeBusy = false,
}: TemplateCardProps) {
  const { t } = useTranslation('apps');
  const Mockup = TEMPLATE_MOCKUPS[template.mockupId];
  const [previewFailed, setPreviewFailed] = useState(false);
  const [largePreviewOpen, setLargePreviewOpen] = useState(false);
  const previewUrl = template.previewUrl ?? getBuiltinTemplatePreviewUrl(template.id);
  const name =
    template.name ?? t(`ai.imageWizard.templates.${template.id}.name`, { defaultValue: template.id });
  const hint = template.hint ?? t(`ai.imageWizard.templates.${template.id}.hint`, { defaultValue: '' });
  const categoryLabel = t(`ai.imageWizard.gallery.categories.${template.category}`, {
    defaultValue: template.category,
  });
  const canOpenPreview = Boolean(previewUrl && !previewFailed);
  const previewLabel = t('ai.imageWizard.gallery.previewTemplate', { name });
  const downloadName = `template-${template.id.replace(/[^a-z0-9_-]+/gi, '-')}.png`;

  return (
    <article
      className={`group relative flex flex-col overflow-hidden rounded-lg border bg-app-surface text-left text-app-accent transition-all ${
        selected
          ? 'border-app-accent ring-2 ring-app-accent/40'
          : 'border-app-border hover:-translate-y-0.5 hover:border-app-accent/50 hover:shadow-md'
      }`}
    >
      <button
        type="button"
        onClick={onPick}
        aria-pressed={selected}
        className="flex min-h-full flex-1 flex-col text-left"
      >
        <span className="relative block aspect-[16/10] w-full overflow-hidden border-b border-app-border bg-app-surface-sidebar">
          {previewUrl && !previewFailed ? (
            <img
              src={previewUrl}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
              onError={() => setPreviewFailed(true)}
            />
          ) : (
            <Mockup />
          )}
        </span>
        <span className="flex flex-col gap-1 p-3">
          <span className="app-text-body font-medium text-app-ink">{name}</span>
          <span className="flex items-center gap-1.5 app-text-caption text-app-ink/50">
            <span className="rounded bg-app-surface-hover px-1.5 py-0.5">{categoryLabel}</span>
            {hint ? <span className="line-clamp-1">· {hint}</span> : null}
          </span>
        </span>
      </button>
      {largePreviewOpen && canOpenPreview ? (
        <ImageLightbox
          imageUrl={previewUrl}
          alt={previewLabel}
          title={name}
          downloadName={downloadName}
          onClose={() => setLargePreviewOpen(false)}
        />
      ) : null}
      {canOpenPreview ? (
        <button
          type="button"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setLargePreviewOpen(true);
          }}
          className="absolute left-2 top-2 inline-flex size-8 items-center justify-center rounded-md border border-app-border bg-app-surface/95 text-app-ink/60 shadow-sm opacity-0 transition-opacity hover:border-app-accent hover:text-app-accent group-hover:opacity-100 focus:opacity-100"
          aria-label={previewLabel}
          title={previewLabel}
        >
          <Expand size={14} />
        </button>
      ) : null}
      {onRemove ? (
        <button
          type="button"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onRemove();
          }}
          disabled={removeBusy}
          className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md border border-app-border bg-app-surface/95 text-app-ink/60 shadow-sm hover:border-[var(--ui-color-danger)] hover:text-[var(--ui-color-danger)] disabled:opacity-60"
          aria-label={removeLabel}
          title={removeLabel}
        >
          {removeBusy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
        </button>
      ) : null}
    </article>
  );
}
