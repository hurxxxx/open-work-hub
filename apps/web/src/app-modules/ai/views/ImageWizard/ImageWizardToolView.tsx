import { useCallback, useEffect, useMemo, useReducer } from 'react';
import { Loader2 } from 'lucide-react';
import { Navigate, useSearchParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
  resolveShellWorkspaceSlug,
} from '@/src/platform/workspaces/workspace-utils';
import {
  approveImageGeneration,
  createImageGeneration,
  deleteImageGeneration,
  downloadGeneratedImageBlob,
  getImageGeneration,
  listImageGenerations,
  setImageGenerationTemplate,
  uploadReferenceImage,
} from '../../api/image-wizard-api';
import { MyImagesSlideOver } from './MyImagesSlideOver';
import { Step1Templates } from './steps/Step1Templates';
import { Step2Context } from './steps/Step2Context';
import { Step3Refine } from './steps/Step3Refine';
import { Step4Brief } from './steps/Step4Brief';
import { StepSummary } from './StepSummary';
import { WizardFooter } from './WizardFooter';
import { WizardLayout } from './WizardLayout';
import { useWizardState, type StepId } from './wizard-state';
import type { TemplatePreset } from './templates/template-presets';
import { useTranslation } from 'react-i18next';
import {
  loadUserTemplatePresets,
  resolveTemplateDisplayName,
  resolveUserTemplateSourceId,
} from './image-wizard-user-templates';
import {
  DEFAULT_IMAGE_WIZARD_DETAILS,
  DEFAULT_IMAGE_WIZARD_LAYOUT,
  DEFAULT_IMAGE_WIZARD_STYLE,
  INITIAL_IMAGE_WIZARD_VIEW_STATE,
  buildContextSummaryValue,
  buildRefineSummaryValue,
  buildTemplateSummaryValue,
  canJumpToImageWizardStep,
  getHighestReachableImageWizardStep,
  imageWizardViewReducer,
  parseImageWizardStep,
  shouldDisableImageWizardNext,
} from './image-wizard-flow-model';
import {
  createImageWizardGenerationWorkflow,
  type ImageWizardRouteTarget,
} from './image-wizard-generation-workflow';

function useImageWizardToolElement() {
  const { i18n, t } = useTranslation('apps');
  const { user, token } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [searchParams, setSearchParams] = useSearchParams();

  const workspaceSlug = useMemo(
    () =>
      searchParams.get('workspace') ||
      resolveShellWorkspaceSlug(user, null) ||
      '',
    [searchParams, user],
  );
  const generationId = searchParams.get('gen');
  const step = parseImageWizardStep(searchParams.get('step'));

  const [viewState, dispatchViewState] = useReducer(
    imageWizardViewReducer,
    INITIAL_IMAGE_WIZARD_VIEW_STATE,
  );
  const {
    myImagesOpen,
    myImagesCount,
    userTemplates,
    userTemplatesRefreshKey,
    removingUserTemplateIds,
    templateActionError,
    transitioningStep,
  } = viewState;

  const updateUrl = useCallback(
    (next: { gen?: string | null; step?: StepId }) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          if ('gen' in next) {
            if (next.gen) params.set('gen', next.gen);
            else params.delete('gen');
          }
          if (next.step) params.set('step', String(next.step));
          return params;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  const pushUrl = useCallback(
    (next: ImageWizardRouteTarget) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          if ('gen' in next) {
            if (next.gen) params.set('gen', next.gen);
            else params.delete('gen');
          }
          if (next.step) params.set('step', String(next.step));
          return params;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );

  const handleGenerationCreated = useCallback(
    (id: string) => updateUrl({ gen: id }),
    [updateUrl],
  );

  const wizard = useWizardState({
    workspaceSlug,
    generationId,
    onIdChange: handleGenerationCreated,
  });
  const flushWizard = wizard.flush;

  // Light count refresh for the My-Images pill.
  useEffect(() => {
    if (!token || !workspaceSlug) return;
    let cancelled = false;
    listImageGenerations(token, workspaceSlug, {
      limit: 50,
      has_image_activity: true,
    })
      .then((response) => {
        if (cancelled) return;
        dispatchViewState({
          type: 'my-images-count:set',
          count: response.items.length,
        });
      })
      .catch(() => {
        // ignore
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, generationId, wizard.row?.image_status]);

  useEffect(() => {
    if (!token || !workspaceSlug) {
      dispatchViewState({ type: 'user-templates:set', templates: [] });
      return;
    }
    let cancelled = false;
    const disposers: Array<() => void> = [];
    listImageGenerations(token, workspaceSlug, {
      limit: 100,
      image_status: 'succeeded',
      is_template: true,
    })
      .then(async (response) => {
        const loaded = await loadUserTemplatePresets({
          token,
          workspaceSlug,
          items: response.items,
          formatDate: (createdAt) =>
            formatDateTime(createdAt, {
              dateStyle: 'medium',
              fallback: createdAt,
              locale: i18n.language,
              timeZone,
            }),
          formatDisplayName: (createdAtDisplay) =>
            t('ai.imageWizard.gallery.userTemplateName', {
              date: createdAtDisplay,
            }),
          userTemplateHint: t('ai.imageWizard.gallery.userTemplateHint'),
          assetPort: {
            downloadBlob: (generationId) =>
              downloadGeneratedImageBlob(token, workspaceSlug, generationId),
            createObjectUrl: (blob) => URL.createObjectURL(blob),
            revokeObjectUrl: (objectUrl) => URL.revokeObjectURL(objectUrl),
          },
        });
        disposers.push(loaded.dispose);
        if (!cancelled) {
          dispatchViewState({
            type: 'user-templates:set',
            templates: loaded.presets,
          });
        } else {
          loaded.dispose();
        }
      })
      .catch(() => {
        if (!cancelled)
          dispatchViewState({ type: 'user-templates:set', templates: [] });
      });
    return () => {
      cancelled = true;
      for (const dispose of disposers) dispose();
    };
  }, [
    i18n.language,
    timeZone,
    token,
    workspaceSlug,
    userTemplatesRefreshKey,
    t,
  ]);

  // After the wizard creates a row mid-flow, advance step 1 → 2 once row exists.
  // For Step1's pick handlers, advancement is explicit.

  const highest = useMemo<StepId>(
    () => getHighestReachableImageWizardStep(wizard.row, step),
    [wizard.row, step],
  );

  const goToStep = useCallback(
    async (next: StepId) => {
      if (next === 4) {
        dispatchViewState({ type: 'transitioning-step:set', value: true });
        try {
          await flushWizard();
        } finally {
          dispatchViewState({ type: 'transitioning-step:set', value: false });
        }
      }
      updateUrl({ step: next });
    },
    [flushWizard, updateUrl],
  );

  const handleJumpStep = useCallback(
    (next: StepId) => {
      if (!canJumpToImageWizardStep(next, highest)) return;
      void goToStep(next);
    },
    [goToStep, highest],
  );

  const generationWorkflow = useMemo(
    () =>
      createImageWizardGenerationWorkflow({
        api: token
          ? {
              approve: (generationId) =>
                approveImageGeneration(token, workspaceSlug, generationId),
              create: (payload) =>
                createImageGeneration(token, workspaceSlug, payload),
              delete: (generationId) =>
                deleteImageGeneration(token, workspaceSlug, generationId),
              downloadBlob: (generationId) =>
                downloadGeneratedImageBlob(token, workspaceSlug, generationId),
              get: (generationId) =>
                getImageGeneration(token, workspaceSlug, generationId),
              uploadReference: (generationId, file, role) =>
                uploadReferenceImage(
                  token,
                  workspaceSlug,
                  generationId,
                  file,
                  role,
                ),
            }
          : null,
        canDeleteIdleRows: Boolean(token),
        draft: {
          applyServer: wizard.applyServer,
          flush: wizard.flush,
          get row() {
            return wizard.row;
          },
          startNew: wizard.startNew,
          update: wizard.update,
        },
        imageEditCopy: {
          referenceText: t('ai.imageWizard.step4.editImageNotesReference'),
          requestText: (instruction) =>
            t('ai.imageWizard.step4.editImageNotesRequest', { instruction }),
        },
        route: {
          push: pushUrl,
          replace: updateUrl,
        },
      }),
    [
      pushUrl,
      t,
      token,
      updateUrl,
      wizard.applyServer,
      wizard.flush,
      wizard.row,
      wizard.startNew,
      wizard.update,
      workspaceSlug,
    ],
  );

  async function handleRemoveUserTemplate(template: TemplatePreset) {
    if (!token) return;
    const sourceId = resolveUserTemplateSourceId(template);
    if (!sourceId) return;
    dispatchViewState({
      type: 'template-removal:start',
      templateId: template.id,
    });
    try {
      const updated = await setImageGenerationTemplate(
        token,
        workspaceSlug,
        sourceId,
        false,
      );
      if (wizard.row?.id === sourceId) {
        wizard.applyServer(updated);
      }
      dispatchViewState({
        type: 'user-templates:remove',
        templateId: template.id,
      });
      dispatchViewState({ type: 'user-templates:refresh' });
    } catch (error) {
      dispatchViewState({
        type: 'template-action-error:set',
        message:
          error instanceof Error
            ? error.message
            : t('ai.imageWizard.errors.saveFailed'),
      });
    } finally {
      dispatchViewState({
        type: 'template-removal:finish',
        templateId: template.id,
      });
    }
  }

  if (!workspaceSlug) {
    const fallback =
      resolveDefaultWorkspaceAppPath(user, 'image-wizard') ||
      buildWorkspaceAppPath(
        resolveShellWorkspaceSlug(user, null) ?? '',
        'image-wizard',
      );
    return fallback ? <Navigate to={fallback} replace /> : null;
  }

  if (wizard.loading) {
    return (
      <div className="flex h-32 items-center justify-center text-app-ink/40">
        <Loader2 size={16} className="animate-spin" />
      </div>
    );
  }

  const row = wizard.row;
  const templateName = resolveTemplateDisplayName(
    row?.template_id,
    userTemplates,
    {
      userTemplateFallback: t('ai.imageWizard.gallery.userTemplateFallback'),
      getBuiltinTemplateName: (templateId) =>
        t(`ai.imageWizard.templates.${templateId}.name`, {
          defaultValue: templateId,
        }),
    },
  );

  const summaries = (
    <div className="space-y-2 mb-4">
      {step > 1 ? (
        <StepSummary
          stepNumber={1}
          title={t('ai.imageWizard.steps.step1.title')}
          value={buildTemplateSummaryValue(
            row,
            templateName,
            t('ai.imageWizard.gallery.startBlank'),
          )}
          onEdit={() => handleJumpStep(1)}
        />
      ) : null}
      {step > 2 ? (
        <StepSummary
          stepNumber={2}
          title={t('ai.imageWizard.steps.step2.title')}
          value={buildContextSummaryValue(row, t)}
          onEdit={() => handleJumpStep(2)}
        />
      ) : null}
      {step > 3 ? (
        <StepSummary
          stepNumber={3}
          title={t('ai.imageWizard.steps.step3.title')}
          value={buildRefineSummaryValue(row, t)}
          onEdit={() => handleJumpStep(3)}
        />
      ) : null}
    </div>
  );

  const stepBody = (() => {
    if (step === 1) {
      return (
        <Step1Templates
          selectedTemplateId={row?.template_id ?? null}
          userTemplates={userTemplates}
          removingUserTemplateIds={removingUserTemplateIds}
          templateActionError={templateActionError}
          onPickTemplate={(template) =>
            void generationWorkflow.pickTemplate(template)
          }
          onRemoveUserTemplate={(template) =>
            void handleRemoveUserTemplate(template)
          }
          onPickBlank={() => void generationWorkflow.pickBlank()}
        />
      );
    }
    if (step === 2 && row) {
      return (
        <Step2Context
          workspaceSlug={workspaceSlug}
          details={row.details ?? DEFAULT_IMAGE_WIZARD_DETAILS}
          contextRefs={row.context_refs ?? []}
          onChangeDetails={(details) => wizard.update({ details })}
          onChangeContextRefs={(context_refs) =>
            wizard.update({ context_refs })
          }
        />
      );
    }
    if (step === 3 && row) {
      return (
        <Step3Refine
          workspaceSlug={workspaceSlug}
          generationId={row.id}
          style={row.style ?? DEFAULT_IMAGE_WIZARD_STYLE}
          layout={row.layout ?? DEFAULT_IMAGE_WIZARD_LAYOUT}
          references={row.reference_image_keys ?? []}
          onChangeStyle={(style) => wizard.update({ style })}
          onChangeLayout={(layout) => wizard.update({ layout })}
          onReferencesChange={(refs) =>
            wizard.applyServer({ ...row, reference_image_keys: refs })
          }
        />
      );
    }
    if (step === 4 && row) {
      return (
        <Step4Brief
          workspaceSlug={workspaceSlug}
          row={row}
          onRowReplaced={wizard.applyServer}
          onClone={() => void generationWorkflow.cloneCurrent()}
          onDiscard={generationWorkflow.discardCurrent}
          onImageEdit={generationWorkflow.editCurrentImage}
          onTemplateChanged={() =>
            dispatchViewState({ type: 'user-templates:refresh' })
          }
        />
      );
    }
    return null;
  })();

  const footer = (
    <WizardFooter
      onPrev={step > 1 ? () => void goToStep((step - 1) as StepId) : undefined}
      onNext={step < 4 ? () => void goToStep((step + 1) as StepId) : undefined}
      onSkip={step === 2 || step === 3 ? () => void goToStep(4) : undefined}
      nextDisabled={shouldDisableImageWizardNext({
        step,
        hasRow: Boolean(row),
        transitioningStep,
        autosave: wizard.autosave,
      })}
      hidden={false}
    />
  );

  return (
    <>
      <WizardLayout
        step={step}
        highest={highest}
        autosave={wizard.autosave}
        myImagesCount={myImagesCount}
        onJumpStep={handleJumpStep}
        onNewImage={() => void generationWorkflow.startNewImage()}
        onOpenMyImages={() =>
          dispatchViewState({ type: 'my-images-open:set', open: true })
        }
        footer={footer}
      >
        {step > 1 ? summaries : null}
        {wizard.error ? (
          <div
            role="alert"
            className="mb-3 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 app-text-body text-[var(--ui-color-danger)]"
          >
            {wizard.error}
          </div>
        ) : null}
        {stepBody}
      </WizardLayout>
      <MyImagesSlideOver
        open={myImagesOpen}
        onClose={() =>
          dispatchViewState({ type: 'my-images-open:set', open: false })
        }
        workspaceSlug={workspaceSlug}
        onPickGeneration={(id) => {
          dispatchViewState({ type: 'my-images-open:set', open: false });
          updateUrl({ gen: id, step: 4 });
        }}
        onCountChange={(count) =>
          dispatchViewState({ type: 'my-images-count:set', count })
        }
      />
    </>
  );
}

export function ImageWizardToolView() {
  return useImageWizardToolElement();
}
