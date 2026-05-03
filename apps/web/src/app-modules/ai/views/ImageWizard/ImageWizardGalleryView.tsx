import { useEffect, useState } from 'react';
import { ImageIcon, Loader2, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useConfirm } from '@aidoo/ui/feedback/confirm-dialog';
import {
  deleteImageGeneration,
  listImageGenerations,
  type ImageGeneration,
} from '../../api/image-wizard-api';

interface ImageWizardGalleryViewProps {
  workspaceSlug: string;
  newWizardHref: string;
  buildDetailHref: (generationId: string) => string;
  onChanged: () => void;
}

const STATUS_TONE: Record<string, string> = {
  succeeded: 'text-[var(--ui-color-success,green)]',
  failed: 'text-[var(--ui-color-danger)]',
  running: 'text-app-accent',
  queued: 'text-app-ink/60',
  idle: 'text-app-ink/40',
};

export function ImageWizardGalleryView({
  workspaceSlug,
  newWizardHref,
  buildDetailHref,
  onChanged,
}: ImageWizardGalleryViewProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const [items, setItems] = useState<ImageGeneration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    listImageGenerations(token, workspaceSlug, { limit: 50 })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
        setError(null);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug]);

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
      setItems((current) => current.filter((item) => item.id !== generationId));
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'delete failed');
    }
  }

  return (
    <div className="space-y-4">
      {confirmDialog}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="app-text-heading-2 text-app-ink">
            {t('ai.imageWizard.gallery.title')}
          </h1>
          <p className="app-text-caption text-app-ink/60">
            {t('ai.imageWizard.gallery.subtitle')}
          </p>
        </div>
        <Link
          to={newWizardHref}
          className="flex items-center gap-2 rounded-md bg-app-accent px-3 py-2 app-text-control-sm font-medium text-white transition-colors hover:opacity-90"
        >
          <Plus size={14} />
          {t('ai.imageWizard.gallery.newAction')}
        </Link>
      </div>

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
        <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface-sidebar p-10 text-app-ink/50">
          <ImageIcon size={20} />
          <p className="app-text-body">{t('ai.imageWizard.gallery.empty')}</p>
        </div>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => {
            const latestBrief = item.brief_versions[item.brief_versions.length - 1];
            const tone = STATUS_TONE[item.image_status] ?? 'text-app-ink/40';
            return (
              <li
                key={item.id}
                className="space-y-2 rounded-md border border-app-border bg-app-surface p-3 text-app-ink"
              >
                <div className="flex items-center justify-between">
                  <Link
                    to={buildDetailHref(item.id)}
                    className="app-text-body line-clamp-1 font-medium text-app-ink hover:text-app-accent"
                  >
                    {item.use_case
                      ? t(`ai.imageWizard.usecase.${item.use_case}.label`, {
                          defaultValue: item.use_case,
                        })
                      : t('ai.imageWizard.gallery.untitled')}
                  </Link>
                  <button
                    type="button"
                    onClick={() => handleDelete(item.id)}
                    className="text-app-ink/40 hover:text-[var(--ui-color-danger)]"
                    aria-label={t('common:actions.delete')}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className={`app-text-caption ${tone}`}>
                  {t(`ai.imageWizard.gallery.status.${item.image_status}`, {
                    defaultValue: item.image_status,
                  })}
                </p>
                <p className="app-text-caption line-clamp-2 text-app-ink/50">
                  {latestBrief?.text || t('ai.imageWizard.gallery.noBrief')}
                </p>
                <p className="app-text-caption text-app-ink/30">
                  {new Date(item.created_at).toLocaleString()}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default ImageWizardGalleryView;
