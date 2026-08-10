import { useState } from 'react';
import {
  BookmarkCheck,
  BookmarkPlus,
  Copy,
  Download,
  Expand,
  Loader2,
  Send,
  Trash2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ImageLightbox } from './ImageLightbox';
import {
  buildEditedImagePreviewDescriptor,
  buildSourceImagePreviewDescriptor,
  canSubmitImageEdit,
  getImageResultMode,
  getImageTemplateToggleLabelKey,
  getNextImageTemplateState,
  getTrimmedImageEditInstruction,
  resolveImagePreviewDescriptor,
  type ResolvedImagePreviewDescriptor,
} from './image-result-turn-model';

interface ImageResultTurnProps {
  imageUrl: string | null;
  loading: boolean;
  loadError: string | null;
  failureReason: string | null;
  sourceImageUrl: string | null;
  sourceImageLoadError: string | null;
  editingImage: boolean;
  isTemplate: boolean;
  templateBusy: boolean;
  onClone: () => void;
  onDiscard: () => void;
  onEditImage: (instruction: string) => Promise<void>;
  onTemplateToggle: (nextIsTemplate: boolean) => Promise<void>;
}

export function ImageResultTurn({
  imageUrl,
  loading,
  loadError,
  failureReason,
  sourceImageUrl,
  sourceImageLoadError,
  editingImage,
  isTemplate,
  templateBusy,
  onClone,
  onDiscard,
  onEditImage,
  onTemplateToggle,
}: ImageResultTurnProps) {
  const { t } = useTranslation('apps');
  const [editText, setEditText] = useState('');
  const [preview, setPreview] = useState<ResolvedImagePreviewDescriptor | null>(null);
  const mode = getImageResultMode({
    failureReason,
    imageUrl,
    loadError,
    loading,
  });

  async function submitEdit() {
    const trimmed = getTrimmedImageEditInstruction(editText);
    if (!trimmed) return;
    await onEditImage(trimmed);
    setEditText('');
  }

  if (mode === 'failed') {
    return (
      <article className="space-y-2 rounded-lg border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 p-4 text-[var(--ui-color-danger)]">
        <p className="app-text-body font-medium">{t('ai.imageWizard.step4.failed')}</p>
        <pre className="app-text-caption whitespace-pre-wrap text-app-ink/60">
          {failureReason}
        </pre>
      </article>
    );
  }
  if (mode === 'loading') {
    return (
      <article className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface p-4 text-app-ink/65 shadow-sm">
        <Loader2 size={16} className="animate-spin text-app-accent" />
        <span className="app-text-control-sm">{t('ai.imageWizard.step4.imageLoading')}</span>
      </article>
    );
  }
  if (mode === 'loadError') {
    return (
      <article className="space-y-3 rounded-lg border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 p-4 text-[var(--ui-color-danger)]">
        <p className="app-text-body font-medium">{t('ai.imageWizard.step4.imageLoadFailed')}</p>
        <p className="app-text-caption text-app-ink/60">{loadError}</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onClone}
            className="flex items-center gap-1 rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
          >
            <Copy size={14} />
            {t('ai.imageWizard.step4.cloneAction')}
          </button>
          <button
            type="button"
            onClick={onDiscard}
            className="ml-auto flex items-center gap-1 rounded-md px-3 py-2 app-text-control-sm text-app-ink/60 hover:text-[var(--ui-color-danger)]"
          >
            <Trash2 size={14} />
            {t('ai.imageWizard.step4.discardAction')}
          </button>
        </div>
      </article>
    );
  }
  if (mode === 'empty' || !imageUrl) return null;
  const templateLabel = t(getImageTemplateToggleLabelKey(isTemplate));
  return (
    <article className="space-y-3 rounded-lg border border-app-border bg-app-surface p-4 shadow-sm">
      {preview ? (
        <ImageLightbox
          imageUrl={preview.imageUrl}
          alt={preview.alt}
          title={preview.title}
          downloadName={preview.downloadName}
          onClose={() => setPreview(null)}
        />
      ) : null}
      {sourceImageUrl ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <figure className="space-y-2">
            <figcaption className="app-text-caption font-medium text-app-ink/60">
              {t('ai.imageWizard.step4.sourceImageLabel')}
            </figcaption>
            <button
              type="button"
              onClick={() =>
                setPreview(
                  resolveImagePreviewDescriptor(
                    buildSourceImagePreviewDescriptor(sourceImageUrl),
                    t,
                  ),
                )
              }
              className="group relative block w-full"
              aria-label={t('ai.imageWizard.step4.openLargePreview')}
            >
              <img
                src={sourceImageUrl}
                alt={t('ai.imageWizard.step4.sourceImageAltText')}
                className="max-h-[420px] w-full rounded-md border border-app-border object-contain"
              />
              <span className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md bg-black/45 text-white opacity-0 transition-opacity group-hover:opacity-100">
                <Expand size={15} />
              </span>
            </button>
          </figure>
          <figure className="space-y-2">
            <figcaption className="app-text-caption font-medium text-app-ink/60">
              {t('ai.imageWizard.step4.editedImageLabel')}
            </figcaption>
            <div className="relative">
              <button
                type="button"
                onClick={() =>
                  setPreview(
                    resolveImagePreviewDescriptor(
                      buildEditedImagePreviewDescriptor(imageUrl, 'comparison'),
                      t,
                    ),
                  )
                }
                className="group block w-full"
                aria-label={t('ai.imageWizard.step4.openLargePreview')}
              >
                <img
                  src={imageUrl}
                  alt={t('ai.imageWizard.step4.altText')}
                  className="max-h-[420px] w-full rounded-md border border-app-border object-contain"
                />
                <span className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md bg-black/45 text-white opacity-0 transition-opacity group-hover:opacity-100">
                  <Expand size={15} />
                </span>
              </button>
              <TemplateToggleButton
                label={templateLabel}
                isTemplate={isTemplate}
                busy={templateBusy}
                onToggle={onTemplateToggle}
              />
            </div>
          </figure>
        </div>
      ) : (
        <div className="relative">
          <button
            type="button"
            onClick={() =>
              setPreview(
                resolveImagePreviewDescriptor(
                  buildEditedImagePreviewDescriptor(imageUrl, 'solo'),
                  t,
                ),
              )
            }
            className="group block w-full"
            aria-label={t('ai.imageWizard.step4.openLargePreview')}
          >
            <img
              src={imageUrl}
              alt={t('ai.imageWizard.step4.altText')}
              className="max-h-[480px] w-full rounded-md border border-app-border object-contain"
            />
            <span className="absolute right-2 top-2 inline-flex size-8 items-center justify-center rounded-md bg-black/45 text-white opacity-0 transition-opacity group-hover:opacity-100">
              <Expand size={15} />
            </span>
          </button>
          <TemplateToggleButton
            label={templateLabel}
            isTemplate={isTemplate}
            busy={templateBusy}
            onToggle={onTemplateToggle}
          />
        </div>
      )}
      {sourceImageLoadError ? (
        <p className="app-text-caption text-[var(--ui-color-danger)]">
          {sourceImageLoadError}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <a
          href={imageUrl}
          target="_blank"
          rel="noreferrer"
          download="generated-image.png"
          className="flex items-center gap-1 rounded-md bg-app-ink px-3 py-2 app-text-control-sm font-medium text-app-surface hover:bg-app-ink/90"
        >
          <Download size={14} />
          {t('ai.imageWizard.step4.downloadAction')}
        </a>
        <button
          type="button"
          onClick={onDiscard}
          className="ml-auto flex items-center gap-1 rounded-md px-3 py-2 app-text-control-sm text-app-ink/50 hover:text-[var(--ui-color-danger)]"
        >
          <Trash2 size={14} />
          {t('ai.imageWizard.step4.discardAction')}
        </button>
      </div>
      <div className="space-y-2 border-t border-app-border/80 pt-3">
        <label
          htmlFor="image-edit-prompt"
          className="app-text-caption font-medium text-app-ink/60"
        >
          {t('ai.imageWizard.step4.editImagePromptLabel')}
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            id="image-edit-prompt"
            value={editText}
            rows={2}
            disabled={editingImage}
            onChange={(event) => setEditText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void submitEdit();
              }
            }}
            placeholder={t('ai.imageWizard.step4.editImagePromptPlaceholder')}
            className="app-text-body min-w-0 flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none disabled:opacity-60"
          />
          <button
            type="button"
            onClick={() => void submitEdit()}
            disabled={!canSubmitImageEdit({ editText, editingImage })}
            className="flex items-center justify-center gap-1 rounded-md bg-app-ink px-3 py-2 app-text-control-sm font-medium text-app-surface transition-colors hover:bg-app-ink/90 disabled:border disabled:border-app-border disabled:bg-app-surface-sidebar disabled:text-app-ink/65 disabled:opacity-100"
          >
            {editingImage ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            {editingImage
              ? t('ai.imageWizard.step4.editImageBusy')
              : t('ai.imageWizard.step4.editImageAction')}
          </button>
        </div>
      </div>
    </article>
  );
}

interface TemplateToggleButtonProps {
  label: string;
  isTemplate: boolean;
  busy: boolean;
  onToggle: (nextIsTemplate: boolean) => Promise<void>;
}

function TemplateToggleButton({
  label,
  isTemplate,
  busy,
  onToggle,
}: TemplateToggleButtonProps) {
  return (
    <button
      type="button"
      onClick={() => void onToggle(getNextImageTemplateState(isTemplate))}
      disabled={busy}
      aria-pressed={isTemplate}
      className="absolute bottom-3 left-3 inline-flex max-w-[calc(100%-1.5rem)] items-center gap-1.5 rounded-md border border-app-border bg-app-surface/95 px-3 py-2 app-text-control-sm font-medium text-app-ink shadow-sm hover:border-app-accent hover:text-app-accent disabled:opacity-70"
    >
      {busy ? (
        <Loader2 size={14} className="shrink-0 animate-spin" />
      ) : isTemplate ? (
        <BookmarkCheck size={14} className="shrink-0" />
      ) : (
        <BookmarkPlus size={14} className="shrink-0" />
      )}
      <span className="truncate">{label}</span>
    </button>
  );
}
