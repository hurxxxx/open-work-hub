import { useEffect, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { useConfirm } from '@aidoo/ui/feedback/confirm-dialog';
import { ImageIcon, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  deleteImageGeneration,
  listImageGenerations,
  type ImageGeneration,
} from '../../api/image-wizard-api';

const STATUS_TONE: Record<string, string> = {
  succeeded: 'text-[var(--ui-color-success,green)]',
  failed: 'text-[var(--ui-color-danger)]',
  running: 'text-app-accent',
  queued: 'text-app-ink/60',
  idle: 'text-app-ink/40',
};

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    setLoading(true);
    listImageGenerations(token, workspaceSlug, { limit: 50 })
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
              const latestBrief = item.brief_versions[item.brief_versions.length - 1];
              const tone = STATUS_TONE[item.image_status] ?? 'text-app-ink/40';
              return (
                <li
                  key={item.id}
                  className="flex items-start justify-between gap-3 px-3 py-3 hover:bg-app-surface-hover"
                >
                  <button
                    type="button"
                    onClick={() => onPickGeneration(item.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="app-text-body line-clamp-1 font-medium text-app-ink">
                      {item.template_id
                        ? t(`ai.imageWizard.templates.${item.template_id}.name`, {
                            defaultValue: item.template_id,
                          })
                        : t('ai.imageWizard.gallery.untitled')}
                    </p>
                    <p className={`app-text-caption ${tone}`}>
                      {t(`ai.imageWizard.gallery.status.${item.image_status}`, {
                        defaultValue: item.image_status,
                      })}{' '}
                      · {new Date(item.created_at).toLocaleString()}
                    </p>
                    {latestBrief ? (
                      <p className="app-text-caption mt-1 line-clamp-2 text-app-ink/50">
                        {latestBrief.text}
                      </p>
                    ) : null}
                  </button>
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
