import { useEffect, useReducer } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { useConfirm } from '@ai-do/ui/feedback/confirm-dialog';
import { Download, ImageIcon, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  deleteImageGeneration,
  downloadGeneratedImageBlob,
  listImageGenerations,
} from '../../api/image-wizard-api';
import {
  MY_IMAGES_INITIAL_STATE,
  myImagesReducer,
  projectMyImageGalleryItem,
  shouldLoadGalleryThumbnail,
} from './my-images-gallery-model';
import { loadGeneratedImageAssets } from './generated-image-assets';

interface MyImagesSlideOverProps {
  open: boolean;
  onClose: () => void;
  workspaceSlug: string;
  onPickGeneration: (generationId: string) => void;
  onCountChange?: (count: number) => void;
}

export function MyImagesSlideOver({
  open,
  onClose,
  workspaceSlug,
  onPickGeneration,
  onCountChange,
}: MyImagesSlideOverProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const [{ error, items, loading, thumbnailUrls }, dispatch] = useReducer(
    myImagesReducer,
    MY_IMAGES_INITIAL_STATE,
  );

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    dispatch({ type: 'load' });
    listImageGenerations(token, workspaceSlug, { limit: 100, has_image_activity: true })
      .then((response) => {
        if (cancelled) return;
        dispatch({
          type: 'loaded',
          items: response.items,
        });
        onCountChange?.(response.items.length);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'failed',
          message: err.message,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [open, token, workspaceSlug, onCountChange]);

  useEffect(() => {
    if (!open || !token || items.length === 0) {
      dispatch({ type: 'clear-thumbnails' });
      return;
    }
    let cancelled = false;
    let disposeAssets: (() => void) | null = null;
    const succeeded = items.filter(shouldLoadGalleryThumbnail);
    loadGeneratedImageAssets(
      succeeded.map((item) => item.id),
      {
        downloadBlob: (generationId) =>
          downloadGeneratedImageBlob(token, workspaceSlug, generationId),
        createObjectUrl: (blob) => URL.createObjectURL(blob),
        revokeObjectUrl: (objectUrl) => URL.revokeObjectURL(objectUrl),
      },
    ).then((assets) => {
      disposeAssets = assets.dispose;
      if (cancelled) {
        assets.dispose();
        return;
      }
      const loadedEntries = assets.results
        .filter((item): item is typeof item & { url: string } => item.url !== null)
        .map((item) => [item.generationId, item.url] as const);
      if (cancelled) return;
      dispatch({
        type: 'thumbnails-loaded',
        thumbnailUrls: Object.fromEntries(loadedEntries),
      });
    });
    return () => {
      cancelled = true;
      disposeAssets?.();
    };
  }, [open, token, workspaceSlug, items]);

  async function handleDelete(generationId: string) {
    if (!token) return;
    const confirmed = await confirm({
      title: t('ai.imageWizard.gallery.deleteTitle'),
      description: t('ai.imageWizard.gallery.deleteDescription'),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!confirmed) return;
    try {
      await deleteImageGeneration(token, workspaceSlug, generationId);
      const next = items.filter((item) => item.id !== generationId);
      dispatch({
        type: 'delete-succeeded',
        generationId,
      });
      onCountChange?.(next.length);
    } catch (err) {
      dispatch({
        type: 'failed',
        message: err instanceof Error ? err.message : t('ai.imageWizard.errors.deleteFailed'),
      });
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      closeLabel={t('common:actions.close')}
      title={t('ai.imageWizard.gallery.title')}
      description={t('ai.imageWizard.gallery.subtitle')}
      maxWidth="max-w-2xl"
      actions={
        <div className="flex w-full items-center justify-end">
          <Button onClick={onClose}>{t('common:actions.close')}</Button>
        </div>
      }
    >
      {confirmDialog}
      <div className="space-y-3">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}
        {loading ? (
          <div className="flex h-32 items-center justify-center text-app-ink/40">
            <Loader2 size={16} className="animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface-sidebar p-8 text-app-ink/50">
            <ImageIcon size={20} />
            <p className="app-text-body">{t('ai.imageWizard.gallery.empty')}</p>
          </div>
        ) : (
          <ul className="divide-y divide-app-border rounded-md border border-app-border">
            {items.map((item) => {
              const projection = projectMyImageGalleryItem(item);
              const thumbnailUrl = thumbnailUrls[item.id];
              const title =
                projection.title.defaultValue === undefined
                  ? t(projection.title.key)
                  : t(projection.title.key, { defaultValue: projection.title.defaultValue });
              return (
                <li
                  key={item.id}
                  className="flex items-start justify-between gap-3 p-3 hover:bg-app-surface-hover"
                >
                  <button
                    type="button"
                    onClick={() => onPickGeneration(item.id)}
                    className="flex h-20 w-24 shrink-0 items-center justify-center overflow-hidden rounded-md border border-app-border bg-app-surface-sidebar text-app-ink/30"
                    aria-label={t('ai.imageWizard.gallery.openImage')}
                  >
                    {thumbnailUrl ? (
                      <img
                        src={thumbnailUrl}
                        alt={t('ai.imageWizard.gallery.thumbnailAlt')}
                        className="h-full w-full object-contain"
                      />
                    ) : (
                      <ImageIcon size={18} />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => onPickGeneration(item.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="app-text-body line-clamp-1 font-medium text-app-ink">
                      {title}
                    </p>
                    <p className={`app-text-caption ${projection.statusTone}`}>
                      {t(`ai.imageWizard.gallery.status.${item.image_status}`, {
                        defaultValue: item.image_status,
                      })}{' '}
                      · <UserDateTime value={item.created_at} />
                    </p>
                    {projection.summary ? (
                      <p className="app-text-caption mt-1 line-clamp-2 text-app-ink/50">
                        {projection.summary}
                      </p>
                    ) : null}
                  </button>
                  {thumbnailUrl ? (
                    <a
                      href={thumbnailUrl}
                      download={`generated-image-${item.id}.png`}
                      className="shrink-0 rounded-md border border-app-border p-2 text-app-ink/50 hover:border-app-accent hover:text-app-accent"
                      aria-label={t('ai.imageWizard.gallery.downloadImage')}
                    >
                      <Download size={14} />
                    </a>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => handleDelete(item.id)}
                    className="shrink-0 text-app-ink/40 hover:text-[var(--ui-color-danger)]"
                    aria-label={t('common:actions.delete')}
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
