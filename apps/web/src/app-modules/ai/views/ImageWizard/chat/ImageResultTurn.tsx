import { Copy, Download, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ImageResultTurnProps {
  imageUrl: string | null;
  loading: boolean;
  loadError: string | null;
  failureReason: string | null;
  onClone: () => void;
  onDiscard: () => void;
}

export function ImageResultTurn({
  imageUrl,
  loading,
  loadError,
  failureReason,
  onClone,
  onDiscard,
}: ImageResultTurnProps) {
  const { t } = useTranslation('apps');
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
      <img
        src={imageUrl}
        alt={t('ai.imageWizard.step4.altText')}
        className="max-h-[480px] w-full rounded-md border border-app-border object-contain"
      />
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
          onClick={onClone}
          className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent"
        >
          <Copy size={14} />
          {t('ai.imageWizard.step4.cloneAction')}
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
    </article>
  );
}

export default ImageResultTurn;
