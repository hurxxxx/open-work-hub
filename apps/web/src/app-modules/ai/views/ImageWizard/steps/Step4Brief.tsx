import { useEffect, useRef, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  approveImageGeneration,
  cancelImageGeneration,
  downloadGeneratedImageBlob,
  generateBrief,
  getImageGeneration,
  listImageGenerations,
  setImageGenerationTemplate,
  type ImageGeneration,
} from '../../../api/image-wizard-api';
import { BriefTurn } from '../chat/BriefTurn';
import { ImageResultTurn } from '../chat/ImageResultTurn';
import {
  ImageRevisionGallery,
  type ImageRevisionGalleryItem,
} from '../chat/ImageRevisionGallery';
import { PendingTurn } from '../chat/PendingTurn';

const POLL_INTERVAL_MS = 2000;

function getSourceGenerationId(item: ImageGeneration): string {
  return typeof item.details?.source_generation_id === 'string'
    ? item.details.source_generation_id
    : '';
}

function getRootGenerationId(item: ImageGeneration, byId: Map<string, ImageGeneration>): string {
  let currentId = item.id;
  const seen = new Set<string>();
  while (currentId && !seen.has(currentId)) {
    seen.add(currentId);
    const current = byId.get(currentId);
    if (!current) return currentId;
    const sourceId = getSourceGenerationId(current);
    if (!sourceId) return currentId;
    if (!byId.has(sourceId)) return sourceId;
    currentId = sourceId;
  }
  return item.id;
}

function collectRevisionRows(
  current: ImageGeneration,
  candidates: ImageGeneration[],
): ImageGeneration[] {
  const byId = new Map(candidates.map((item) => [item.id, item]));
  byId.set(current.id, current);
  const rootId = getRootGenerationId(current, byId);
  return Array.from(byId.values())
    .filter((item) => getRootGenerationId(item, byId) === rootId)
    .filter((item) => item.image_status === 'succeeded' && Boolean(item.image_storage_key))
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
}

interface Step4BriefProps {
  workspaceSlug: string;
  row: ImageGeneration;
  onRowReplaced: (next: ImageGeneration) => void;
  onClone: () => void;
  onDiscard: () => void;
  onImageEdit: (instruction: string) => Promise<void>;
  onTemplateChanged?: (next: ImageGeneration) => void;
}

export function Step4Brief({
  workspaceSlug,
  row,
  onRowReplaced,
  onClone,
  onDiscard,
  onImageEdit,
  onTemplateChanged,
}: Step4BriefProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const [busy, setBusy] = useState<'brief' | 'approve' | 'cancel' | 'image-edit' | null>(null);
  const [templateBusy, setTemplateBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [imageLoadError, setImageLoadError] = useState<string | null>(null);
  const [sourceImageUrl, setSourceImageUrl] = useState<string | null>(null);
  const [sourceImageLoadError, setSourceImageLoadError] = useState<string | null>(null);
  const [revisionItems, setRevisionItems] = useState<ImageRevisionGalleryItem[]>([]);
  const [revisionGalleryError, setRevisionGalleryError] = useState<string | null>(null);
  const requestedInitialBriefFor = useRef<string | null>(null);
  const requestedDirectEditFor = useRef<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sourceGenerationId =
    typeof row.details?.source_generation_id === 'string'
      ? row.details.source_generation_id
      : '';
  const sourceImageEditInstruction =
    typeof row.details?.source_image_edit_instruction === 'string'
      ? row.details.source_image_edit_instruction
      : '';
  const imageEditRequiresPlan = row.details?.source_image_requires_plan === true;
  const isImageEdit = Boolean(sourceGenerationId && sourceImageEditInstruction);
  const shouldSkipPlanForImageEdit = isImageEdit && !imageEditRequiresPlan;

  // Auto-request the initial image plan on entering step 4 if there are none yet.
  useEffect(() => {
    if (!token) return;
    if (shouldSkipPlanForImageEdit) return;
    if (requestedInitialBriefFor.current === row.id) return;
    if (row.brief_versions.length > 0) {
      requestedInitialBriefFor.current = row.id;
      return;
    }
    if (row.brief_status === 'approved') return;
    requestedInitialBriefFor.current = row.id;
    void runGenerateBrief();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, row.id, shouldSkipPlanForImageEdit]);

  // Most image edits are concrete enough to run immediately. If a user lands
  // on an unqueued direct edit draft, approve and dispatch it without showing
  // the internal execution prompt as a human plan.
  useEffect(() => {
    if (!token || !shouldSkipPlanForImageEdit) return;
    if (requestedDirectEditFor.current === row.id) return;
    if (row.image_status !== 'idle' || row.brief_status === 'approved') return;
    requestedDirectEditFor.current = row.id;
    void runApprove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, row.id, row.image_status, row.brief_status, shouldSkipPlanForImageEdit]);

  // Poll while generating.
  useEffect(() => {
    if (!token || !row.id) return;
    if (row.image_status !== 'queued' && row.image_status !== 'running') return;
    function tick() {
      if (!token) return;
      getImageGeneration(token, workspaceSlug, row.id)
        .then((fetched) => {
          onRowReplaced(fetched);
        })
        .catch(() => {
          // ignore; next tick retries
        })
        .finally(() => {
          pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
        });
    }
    pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      pollTimer.current = null;
    };
  }, [token, workspaceSlug, row.id, row.image_status, onRowReplaced]);

  // Fetch the generated image through the authenticated API. The MinIO URL is
  // internal to the VM and cannot be used directly from the public HTTPS page.
  useEffect(() => {
    if (!token || row.image_status !== 'succeeded' || !row.id) {
      setDownloadUrl(null);
      setImageLoadError(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setImageLoadError(null);
    downloadGeneratedImageBlob(token, workspaceSlug, row.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setDownloadUrl(objectUrl);
      })
      .catch((err) => {
        if (cancelled) return;
        setDownloadUrl(null);
        setImageLoadError(
          err instanceof Error ? err.message : t('ai.imageWizard.step4.imageLoadFailed'),
        );
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, workspaceSlug, row.id, row.image_status, t]);

  // If this generation is an edit, load the source result so the current view
  // reads as one comparison flow instead of a disconnected new job.
  useEffect(() => {
    if (!token || !sourceGenerationId) {
      setSourceImageUrl(null);
      setSourceImageLoadError(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setSourceImageLoadError(null);
    downloadGeneratedImageBlob(token, workspaceSlug, sourceGenerationId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSourceImageUrl(objectUrl);
      })
      .catch((err) => {
        if (cancelled) return;
        setSourceImageUrl(null);
        setSourceImageLoadError(
          err instanceof Error ? err.message : t('ai.imageWizard.step4.sourceImageLoadFailed'),
        );
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, workspaceSlug, sourceGenerationId, t]);

  useEffect(() => {
    if (!token || !isImageEdit) {
      setRevisionItems([]);
      setRevisionGalleryError(null);
      return;
    }
    let cancelled = false;
    const objectUrls: string[] = [];
    setRevisionGalleryError(null);
    listImageGenerations(token, workspaceSlug, { limit: 100 })
      .then(async (response) => {
        const revisions = collectRevisionRows(row, response.items);
        const loaded = await Promise.all(
          revisions.map(async (item): Promise<ImageRevisionGalleryItem> => {
            try {
              const blob = await downloadGeneratedImageBlob(token, workspaceSlug, item.id);
              if (cancelled) {
                return {
                  id: item.id,
                  imageUrl: null,
                  loadError: null,
                  createdAt: item.created_at,
                  isCurrent: item.id === row.id,
                };
              }
              const objectUrl = URL.createObjectURL(blob);
              objectUrls.push(objectUrl);
              return {
                id: item.id,
                imageUrl: objectUrl,
                loadError: null,
                createdAt: item.created_at,
                isCurrent: item.id === row.id,
              };
            } catch (err) {
              return {
                id: item.id,
                imageUrl: null,
                loadError:
                  err instanceof Error
                    ? err.message
                    : t('ai.imageWizard.step4.revisionImageLoadFailed'),
                createdAt: item.created_at,
                isCurrent: item.id === row.id,
              };
            }
          }),
        );
        if (!cancelled) setRevisionItems(loaded);
      })
      .catch((err) => {
        if (cancelled) return;
        setRevisionItems([]);
        setRevisionGalleryError(
          err instanceof Error ? err.message : t('ai.imageWizard.step4.revisionGalleryLoadFailed'),
        );
      });
    return () => {
      cancelled = true;
      for (const objectUrl of objectUrls) URL.revokeObjectURL(objectUrl);
    };
  }, [token, workspaceSlug, row, row.id, row.updated_at, row.image_status, isImageEdit, t]);

  async function runGenerateBrief(editInstruction?: string) {
    if (!token) return;
    setBusy('brief');
    setError(null);
    try {
      await generateBrief(token, workspaceSlug, row.id, { editInstruction });
      const refreshed = await getImageGeneration(token, workspaceSlug, row.id);
      onRowReplaced(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.briefFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function runApprove() {
    if (!token) return;
    setBusy('approve');
    setError(null);
    try {
      const approved = await approveImageGeneration(token, workspaceSlug, row.id);
      onRowReplaced(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.approveFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function runCancel() {
    if (!token) return;
    setBusy('cancel');
    setError(null);
    try {
      const cancelled = await cancelImageGeneration(token, workspaceSlug, row.id);
      onRowReplaced(cancelled);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.cancelFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function runImageEdit(instruction: string) {
    setBusy('image-edit');
    setError(null);
    try {
      await onImageEdit(instruction);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.editImageFailed'));
    } finally {
      setBusy(null);
    }
  }

  async function runTemplateToggle(nextIsTemplate: boolean) {
    if (!token) return;
    setTemplateBusy(true);
    setError(null);
    try {
      const updated = await setImageGenerationTemplate(
        token,
        workspaceSlug,
        row.id,
        nextIsTemplate,
      );
      onRowReplaced(updated);
      onTemplateChanged?.(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('ai.imageWizard.errors.saveFailed'));
    } finally {
      setTemplateBusy(false);
    }
  }

  const isGeneratingImage = row.image_status === 'queued' || row.image_status === 'running';
  const isFinished =
    row.image_status === 'succeeded'
    || row.image_status === 'failed'
    || row.image_status === 'cancelled';
  const showBriefPlan = !shouldSkipPlanForImageEdit;
  const composerDisabled = row.brief_status === 'approved' || isGeneratingImage || isFinished;
  const latestBrief = row.brief_versions.at(-1);
  const latestBriefIndex = Math.max(0, row.brief_versions.length - 1);

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h2 className="app-text-heading-2 text-app-ink">
            {isImageEdit
              ? t('ai.imageWizard.steps.step4.editHeading')
              : t('ai.imageWizard.steps.step4.heading')}
          </h2>
          <p className="app-text-body text-app-ink/60">
            {isImageEdit
              ? t('ai.imageWizard.steps.step4.editDescription')
              : t('ai.imageWizard.steps.step4.description')}
          </p>
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
        >
          {error}
        </div>
      ) : null}

      {row.brief_versions.length === 0 && busy === 'brief' ? (
        <div className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar p-4 text-app-ink/60">
          <Loader2 size={16} className="animate-spin text-app-accent" />
          <span className="app-text-control-sm">
            {t('ai.imageWizard.step4.generatingFirstBrief')}
          </span>
        </div>
      ) : null}

      {shouldSkipPlanForImageEdit && !isGeneratingImage && !isFinished && !error ? (
        <div className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar p-4 text-app-ink/60">
          <Loader2 size={16} className="animate-spin text-app-accent" />
          <span className="app-text-control-sm">
            {t('ai.imageWizard.step4.startingImageEdit')}
          </span>
        </div>
      ) : null}

      {showBriefPlan ? (
        <div className="space-y-3">
          {latestBrief ? (
            <BriefTurn
              key={`${latestBrief.created_at}-${latestBriefIndex}`}
              version={latestBrief}
              index={latestBriefIndex}
              isLatest
              approving={busy === 'approve'}
              approveDisabled={composerDisabled}
              onApprove={runApprove}
            />
          ) : null}
        </div>
      ) : null}

      {showBriefPlan && row.brief_versions.length > 0 && !isGeneratingImage && !isFinished ? (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => runGenerateBrief()}
            disabled={busy === 'brief'}
            className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink hover:border-app-accent hover:text-app-accent disabled:opacity-50"
          >
            {busy === 'brief' ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Sparkles size={13} />
            )}
            {t('ai.imageWizard.step4.regenerate')}
          </button>
        </div>
      ) : null}

      {sourceImageUrl && !isFinished ? (
        <article className="space-y-2 rounded-lg border border-app-border bg-app-surface p-4 shadow-sm">
          <h3 className="app-text-caption font-medium text-app-ink/60">
            {t('ai.imageWizard.step4.sourceImageLabel')}
          </h3>
          <img
            src={sourceImageUrl}
            alt={t('ai.imageWizard.step4.sourceImageAltText')}
            className="max-h-[360px] w-full rounded-md border border-app-border object-contain"
          />
        </article>
      ) : null}

      {sourceImageLoadError && !isFinished ? (
        <div
          role="alert"
          className="app-text-caption rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
        >
          {sourceImageLoadError}
        </div>
      ) : null}

      {isGeneratingImage ? (
        <PendingTurn
          status={row.image_status as 'queued' | 'running'}
          cancelling={busy === 'cancel'}
          onCancel={runCancel}
        />
      ) : null}

      {row.image_status === 'cancelled' ? (
        <article className="rounded-lg border border-app-border bg-app-surface-sidebar p-4 text-app-ink/65">
          <p className="app-text-body font-medium text-app-ink">
            {t('ai.imageWizard.step4.cancelled')}
          </p>
          <p className="app-text-caption mt-1">
            {t('ai.imageWizard.step4.cancelledDescription')}
          </p>
        </article>
      ) : null}

      {row.image_status === 'succeeded' || row.image_status === 'failed' ? (
        <ImageResultTurn
          imageUrl={downloadUrl}
          loading={!downloadUrl && !imageLoadError && row.image_status === 'succeeded'}
          loadError={imageLoadError}
          failureReason={row.image_status === 'failed' ? row.failure_reason : null}
          sourceImageUrl={sourceImageUrl}
          sourceImageLoadError={sourceImageLoadError}
          editingImage={busy === 'image-edit'}
          isTemplate={row.is_template}
          templateBusy={templateBusy}
          onClone={onClone}
          onDiscard={onDiscard}
          onEditImage={runImageEdit}
          onTemplateToggle={runTemplateToggle}
        />
      ) : null}

      <ImageRevisionGallery items={revisionItems} loadError={revisionGalleryError} />
    </div>
  );
}

export default Step4Brief;
