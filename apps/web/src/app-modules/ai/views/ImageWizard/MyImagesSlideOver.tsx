import { useEffect, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { useConfirm } from '@aidoo/ui/feedback/confirm-dialog';
import { Download, ImageIcon, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  deleteImageGeneration,
  downloadGeneratedImageBlob,
  listImageGenerations,
  type ImageGeneration,
} from '../../api/image-wizard-api';
import { getUserTemplateSourceId } from './templates/template-presets';

const STATUS_TONE: Record<string, string> = {
  succeeded: 'text-[var(--ui-color-success,green)]',
  failed: 'text-[var(--ui-color-danger)]',
  running: 'text-app-accent',
  queued: 'text-app-ink/60',
  idle: 'text-app-ink/40',
};

function getGallerySummary(item: ImageGeneration): string {
  const editInstruction =
    typeof item.details?.source_image_edit_instruction === 'string'
      ? item.details.source_image_edit_instruction.trim()
      : '';
  if (editInstruction) return editInstruction;
  const latestBrief = item.brief_versions[item.brief_versions.length - 1];
  if (!latestBrief || latestBrief.internal) return '';
  return latestBrief.text;
}

function getGalleryTitle(
  item: ImageGeneration,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (getUserTemplateSourceId(item.template_id)) {
    return t('ai.imageWizard.gallery.userTemplateBasedTitle');
  }
  if (item.template_id) {
    return t(`ai.imageWizard.templates.${item.template_id}.name`, {
      defaultValue: item.template_id,
    });
  }
  return t('ai.imageWizard.gallery.untitled');
}

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
  const [items, setItems] = useState<ImageGeneration[]>([]);
  const [thumbnailUrls, setThumbnailUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    setLoading(true);
    listImageGenerations(token, workspaceSlug, { limit: 100, has_image_activity: true })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
        onCountChange?.(response.items.length);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, token, workspaceSlug, onCountChange]);

  useEffect(() => {
    if (!open || !token || items.length === 0) {
      setThumbnailUrls({});
      return;
    }
    let cancelled = false;
    const objectUrls: string[] = [];
    const succeeded = items.filter(
      (item) => item.image_status === 'succeeded' && item.image_storage_key,
    );
    Promise.all(
      succeeded.map(async (item) => {
        try {
          const blob = await downloadGeneratedImageBlob(token, workspaceSlug, item.id);
          if (cancelled) return null;
          const objectUrl = URL.createObjectURL(blob);
          objectUrls.push(objectUrl);
          return [item.id, objectUrl] as const;
        } catch {
          return null;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      const loadedEntries = entries.filter(
        (entry): entry is readonly [string, string] => entry !== null,
      );
      setThumbnailUrls(Object.fromEntries(loadedEntries));
    });
    return () => {
      cancelled = true;
      for (const objectUrl of objectUrls) URL.revokeObjectURL(objectUrl);
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
      setItems(next);
      onCountChange?.(next.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.deleteFailed'));
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
              const summary = getGallerySummary(item);
              const thumbnailUrl = thumbnailUrls[item.id];
              const tone = STATUS_TONE[item.image_status] ?? 'text-app-ink/40';
              return (
                <li
                  key={item.id}
                  className="flex items-start justify-between gap-3 px-3 py-3 hover:bg-app-surface-hover"
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
                      {getGalleryTitle(item, t)}
                    </p>
                    <p className={`app-text-caption ${tone}`}>
                      {t(`ai.imageWizard.gallery.status.${item.image_status}`, {
                        defaultValue: item.image_status,
                      })}{' '}
                      · {new Date(item.created_at).toLocaleString()}
                    </p>
                    {summary ? (
                      <p className="app-text-caption mt-1 line-clamp-2 text-app-ink/50">
                        {summary}
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

export default MyImagesSlideOver;
