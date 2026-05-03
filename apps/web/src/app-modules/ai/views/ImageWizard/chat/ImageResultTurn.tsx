import { useState } from 'react';
import { Copy, Download, Loader2, Plus, Send, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ImageResultTurnProps {
  imageUrl: string | null;
  loading: boolean;
  loadError: string | null;
  failureReason: string | null;
  sourceImageUrl: string | null;
  sourceImageLoadError: string | null;
  editingImage: boolean;
  onClone: () => void;
  onDiscard: () => void;
  onEditImage: (instruction: string) => Promise<void>;
  onNewImage: () => void;
}

export function ImageResultTurn({
  imageUrl,
  loading,
  loadError,
  failureReason,
  sourceImageUrl,
  sourceImageLoadError,
  editingImage,
  onClone,
  onDiscard,
  onEditImage,
  onNewImage,
}: ImageResultTurnProps) {
  const { t } = useTranslation('apps');
  const [editText, setEditText] = useState('');

  async function submitEdit() {
    const trimmed = editText.trim();
    if (!trimmed) return;
    await onEditImage(trimmed);
    setEditText('');
  }

  if (failureReason) {
    return (
      <article className="space-y-2 rounded-lg border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 p-4 text-[var(--ui-color-danger)]">
        <p className="app-text-body font-medium">{t('ai.imageWizard.step4.failed')}</p>
        <pre className="app-text-caption whitespace-pre-wrap text-app-ink/60">
          {failureReason}
        </pre>
      </article>
    );
  }
  if (loading) {
    return (
      <article className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface p-4 text-app-ink/65 shadow-sm">
        <Loader2 size={16} className="animate-spin text-app-accent" />
        <span className="app-text-control-sm">{t('ai.imageWizard.step4.imageLoading')}</span>
      </article>
    );
  }
  if (loadError) {
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
  if (!imageUrl) return null;
  return (
    <article className="space-y-3 rounded-lg border border-app-border bg-app-surface p-4 shadow-sm">
      {sourceImageUrl ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <figure className="space-y-2">
            <figcaption className="app-text-caption font-medium text-app-ink/60">
              {t('ai.imageWizard.step4.sourceImageLabel')}
            </figcaption>
            <img
              src={sourceImageUrl}
              alt={t('ai.imageWizard.step4.sourceImageAltText')}
              className="max-h-[420px] w-full rounded-md border border-app-border object-contain"
            />
          </figure>
          <figure className="space-y-2">
            <figcaption className="app-text-caption font-medium text-app-ink/60">
              {t('ai.imageWizard.step4.editedImageLabel')}
            </figcaption>
            <img
              src={imageUrl}
              alt={t('ai.imageWizard.step4.altText')}
              className="max-h-[420px] w-full rounded-md border border-app-border object-contain"
            />
          </figure>
        </div>
      ) : (
        <img
          src={imageUrl}
          alt={t('ai.imageWizard.step4.altText')}
          className="max-h-[480px] w-full rounded-md border border-app-border object-contain"
        />
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
          onClick={onNewImage}
          className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
        >
          <Plus size={14} />
          {t('ai.imageWizard.step4.newImageAction')}
        </button>
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
            disabled={editingImage || !editText.trim()}
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

export default ImageResultTurn;
