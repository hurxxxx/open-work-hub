import { Download, ImageIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export interface ImageRevisionGalleryItem {
  id: string;
  imageUrl: string | null;
  loadError: string | null;
  createdAt: string;
  isCurrent: boolean;
}

interface ImageRevisionGalleryProps {
  items: ImageRevisionGalleryItem[];
  loadError: string | null;
}

export function ImageRevisionGallery({ items, loadError }: ImageRevisionGalleryProps) {
  const { t } = useTranslation('apps');

  if (items.length === 0 && !loadError) return null;

  return (
    <section className="space-y-3 rounded-lg border border-app-border bg-app-surface p-4 shadow-sm">
      <div className="space-y-1">
        <h3 className="app-text-heading-3 text-app-ink">
          {t('ai.imageWizard.step4.revisionGalleryTitle')}
        </h3>
        <p className="app-text-caption text-app-ink/60">
          {t('ai.imageWizard.step4.revisionGalleryDescription')}
        </p>
      </div>
      {loadError ? (
        <p className="app-text-caption text-[var(--ui-color-danger)]">{loadError}</p>
      ) : null}
      {items.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item, index) => (
            <figure
              key={item.id}
              className="overflow-hidden rounded-md border border-app-border bg-app-surface-sidebar"
            >
              {item.imageUrl ? (
                <a href={item.imageUrl} target="_blank" rel="noreferrer" className="block">
                  <img
                    src={item.imageUrl}
                    alt={t('ai.imageWizard.step4.revisionImageAlt', { index: index + 1 })}
                    className="h-40 w-full object-contain"
                  />
                </a>
              ) : (
                <div className="flex h-40 items-center justify-center text-app-ink/30">
                  <ImageIcon size={22} />
                </div>
              )}
              <figcaption className="space-y-2 border-t border-app-border px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="app-text-control-sm font-medium text-app-ink">
                      {t('ai.imageWizard.step4.revisionLabel', { index: index + 1 })}
                      {item.isCurrent ? (
                        <span className="ml-2 rounded-sm bg-app-accent/10 px-1.5 py-0.5 app-text-caption text-app-accent">
                          {t('ai.imageWizard.step4.currentRevisionBadge')}
                        </span>
                      ) : null}
                    </p>
                    <p className="app-text-caption text-app-ink/45">
                      {new Date(item.createdAt).toLocaleString()}
                    </p>
                  </div>
                  {item.imageUrl ? (
                    <a
                      href={item.imageUrl}
                      download={`generated-image-${index + 1}.png`}
                      className="inline-flex shrink-0 items-center justify-center rounded-md border border-app-border p-2 text-app-ink/65 hover:border-app-accent hover:text-app-accent"
                      aria-label={t('ai.imageWizard.step4.downloadRevision')}
                    >
                      <Download size={14} />
                    </a>
                  ) : null}
                </div>
                {item.loadError ? (
                  <p className="app-text-caption text-[var(--ui-color-danger)]">
                    {item.loadError}
                  </p>
                ) : null}
              </figcaption>
            </figure>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default ImageRevisionGallery;
