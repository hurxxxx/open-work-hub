import { useEffect, useReducer, useRef } from 'react';
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
import { ImageRevisionGallery } from '../chat/ImageRevisionGallery';
import { PendingTurn } from '../chat/PendingTurn';
import {
  createStep4BrowserGeneratedImageAssetApi,
  loadStep4GeneratedImageAsset,
  loadStep4RevisionGallery,
  type LoadedGeneratedImageAsset,
  type LoadedStep4RevisionGallery,
  step4AssetLoadErrorMessage,
} from './step4-brief-assets';
import {
  INITIAL_STEP4_BRIEF_STATE,
  getInitialStep4BriefIntent,
  projectStep4Brief,
  step4BriefReducer,
  shouldAutoApproveDirectImageEdit,
  shouldPollStep4ImageGeneration,
} from './step4-brief-model';
import { createStep4BriefOperations } from './step4-brief-operations';

const POLL_INTERVAL_MS = 2000;
const generatedImageAssetApi = createStep4BrowserGeneratedImageAssetApi(
  downloadGeneratedImageBlob,
);

function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
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

type AppsTranslator = ReturnType<typeof useTranslation>['t'];

interface UseStep4BriefControllerArgs {
  workspaceSlug: string;
  row: ImageGeneration;
  token: string | null | undefined;
  t: AppsTranslator;
  onRowReplaced: (next: ImageGeneration) => void;
  onImageEdit: (instruction: string) => Promise<void>;
  onTemplateChanged?: (next: ImageGeneration) => void;
}

function useStep4BriefController({
  workspaceSlug,
  row,
  onRowReplaced,
  onImageEdit,
  onTemplateChanged,
  token,
  t,
}: UseStep4BriefControllerArgs) {
  const [state, dispatch] = useReducer(step4BriefReducer, INITIAL_STEP4_BRIEF_STATE);
  const requestedInitialBriefFor = useRef<string | null>(null);
  const requestedDirectEditFor = useRef<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const {
    sourceGenerationId,
    isImageEdit,
    shouldSkipPlanForImageEdit,
    isGeneratingImage,
    isFinished,
    showBriefPlan,
    composerDisabled,
    latestBrief,
    latestBriefIndex,
  } = projectStep4Brief(row);
  const {
    runGenerateBrief,
    runApprove,
    runCancel,
    runImageEdit,
    runTemplateToggle,
  } = createStep4BriefOperations({
    api: {
      generateBrief,
      getGeneration: getImageGeneration,
      approveGeneration: approveImageGeneration,
      cancelGeneration: cancelImageGeneration,
      setTemplate: setImageGenerationTemplate,
    },
    dispatch,
    onImageEdit,
    onRowReplaced,
    onTemplateChanged,
    row,
    t,
    token,
    workspaceSlug,
  });
  const runGenerateBriefRef = useLatestRef(runGenerateBrief);
  const runApproveRef = useLatestRef(runApprove);

  // Auto-request the initial image plan on entering step 4 if there are none yet.
  useEffect(() => {
    const intent = getInitialStep4BriefIntent({
      briefStatus: row.brief_status,
      briefVersionCount: row.brief_versions.length,
      generationId: row.id,
      requestedGenerationId: requestedInitialBriefFor.current,
      shouldSkipPlanForImageEdit,
      token,
    });
    if (intent === 'idle') return;
    requestedInitialBriefFor.current = row.id;
    if (intent === 'mark-handled') return;
    void runGenerateBriefRef.current();
  }, [
    token,
    row.brief_status,
    row.brief_versions.length,
    row.id,
    runGenerateBriefRef,
    shouldSkipPlanForImageEdit,
  ]);

  // Most image edits are concrete enough to run immediately. If a user lands
  // on an unqueued direct edit draft, approve and dispatch it without showing
  // the internal execution prompt as a human plan.
  useEffect(() => {
    const shouldApprove = shouldAutoApproveDirectImageEdit({
      briefStatus: row.brief_status,
      generationId: row.id,
      imageStatus: row.image_status,
      requestedGenerationId: requestedDirectEditFor.current,
      shouldSkipPlanForImageEdit,
      token,
    });
    if (!shouldApprove) return;
    requestedDirectEditFor.current = row.id;
    void runApproveRef.current();
  }, [
    token,
    row.id,
    row.image_status,
    row.brief_status,
    runApproveRef,
    shouldSkipPlanForImageEdit,
  ]);

  // Poll while generating.
  useEffect(() => {
    if (!token || !row.id) return;
    if (!shouldPollStep4ImageGeneration(row.image_status)) return;
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
      dispatch({ type: 'image:reset' });
      return;
    }
    let cancelled = false;
    let asset: LoadedGeneratedImageAsset | null = null;
    dispatch({ type: 'image:loading' });
    loadStep4GeneratedImageAsset({
      api: generatedImageAssetApi,
      generationId: row.id,
      token,
      workspaceSlug,
    })
      .then((loaded) => {
        if (cancelled) {
          loaded.dispose();
          return;
        }
        asset = loaded;
        dispatch({ type: 'image:loaded', url: loaded.url });
      })
      .catch((err) => {
        if (cancelled) return;
        dispatch({
          type: 'image:fail',
          message: step4AssetLoadErrorMessage(err, t('ai.imageWizard.step4.imageLoadFailed')),
        });
      });
    return () => {
      cancelled = true;
      asset?.dispose();
    };
  }, [token, workspaceSlug, row.id, row.image_status, t]);

  // If this generation is an edit, load the source result so the current view
  // reads as one comparison flow instead of a disconnected new job.
  useEffect(() => {
    if (!token || !sourceGenerationId) {
      dispatch({ type: 'source:reset' });
      return;
    }
    let cancelled = false;
    let asset: LoadedGeneratedImageAsset | null = null;
    dispatch({ type: 'source:loading' });
    loadStep4GeneratedImageAsset({
      api: generatedImageAssetApi,
      generationId: sourceGenerationId,
      token,
      workspaceSlug,
    })
      .then((loaded) => {
        if (cancelled) {
          loaded.dispose();
          return;
        }
        asset = loaded;
        dispatch({ type: 'source:loaded', url: loaded.url });
      })
      .catch((err) => {
        if (cancelled) return;
        dispatch({
          type: 'source:fail',
          message: step4AssetLoadErrorMessage(
            err,
            t('ai.imageWizard.step4.sourceImageLoadFailed'),
          ),
        });
      });
    return () => {
      cancelled = true;
      asset?.dispose();
    };
  }, [token, workspaceSlug, sourceGenerationId, t]);

  useEffect(() => {
    if (!token || !isImageEdit) {
      dispatch({ type: 'revisions:reset' });
      return;
    }
    let cancelled = false;
    let gallery: LoadedStep4RevisionGallery | null = null;
    dispatch({ type: 'revisions:loading' });
    listImageGenerations(token, workspaceSlug, { limit: 100 })
      .then(async (response) => {
        const loadedGallery = await loadStep4RevisionGallery({
          api: generatedImageAssetApi,
          candidates: response.items,
          current: row,
          revisionImageLoadFailed: t('ai.imageWizard.step4.revisionImageLoadFailed'),
          token,
          workspaceSlug,
        });
        if (cancelled) {
          loadedGallery.dispose();
          return;
        }
        gallery = loadedGallery;
        dispatch({ type: 'revisions:loaded', items: loadedGallery.items });
      })
      .catch((err) => {
        if (cancelled) return;
        dispatch({
          type: 'revisions:fail',
          message:
            err instanceof Error
              ? err.message
              : t('ai.imageWizard.step4.revisionGalleryLoadFailed'),
        });
      });
    return () => {
      cancelled = true;
      gallery?.dispose();
    };
  }, [token, workspaceSlug, row, row.id, row.updated_at, row.image_status, isImageEdit, t]);

  return {
    ...state,
    isImageEdit,
    shouldSkipPlanForImageEdit,
    isGeneratingImage,
    isFinished,
    showBriefPlan,
    composerDisabled,
    latestBrief,
    latestBriefIndex,
    runGenerateBrief,
    runApprove,
    runCancel,
    runImageEdit,
    runTemplateToggle,
  };
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
  const {
    busy,
    templateBusy,
    error,
    downloadUrl,
    imageLoadError,
    sourceImageUrl,
    sourceImageLoadError,
    revisionItems,
    revisionGalleryError,
    isImageEdit,
    shouldSkipPlanForImageEdit,
    isGeneratingImage,
    isFinished,
    showBriefPlan,
    composerDisabled,
    latestBrief,
    latestBriefIndex,
    runGenerateBrief,
    runApprove,
    runCancel,
    runImageEdit,
    runTemplateToggle,
  } = useStep4BriefController({
    workspaceSlug,
    row,
    token,
    t,
    onRowReplaced,
    onImageEdit,
    onTemplateChanged,
  });

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
