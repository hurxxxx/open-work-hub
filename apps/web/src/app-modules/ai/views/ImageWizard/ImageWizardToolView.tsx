import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Navigate, useSearchParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
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
  type ImageGeneration,
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
import {
  ASPECT_OPTIONS,
  LAYOUT_OPTIONS,
  type AspectId,
  type LayoutId,
} from './layout-wireframes';
import { STYLE_IDS, type StyleShape } from './style-presets';
import {
  getTemplate,
  getUserTemplateSourceId,
  makeUserTemplateId,
  TEMPLATE_PRESETS,
  type TemplatePreset,
} from './templates/template-presets';
import { useTranslation } from 'react-i18next';

const DEFAULT_STYLE = {
  chips: [] as string[],
  palette: 'auto',
  background: 'auto',
  quality: 'high',
};
const DEFAULT_LAYOUT = {
  layout_id: LAYOUT_OPTIONS[0] as LayoutId,
  aspect: '1024x1024' as AspectId,
};
const DEFAULT_DETAILS = { audience: '', notes: '' };
const IMAGE_EDIT_NOTES_MAX = 2000;
const AMBIGUOUS_EDIT_TERMS = [
  '\uC88B\uAC8C',
  '\uC608\uC058\uAC8C',
  '\uACE0\uAE09\uC2A4\uB7FD',
  '\uC790\uC5F0\uC2A4\uB7FD',
  '\uC138\uB828',
  '\uD604\uB300\uC801',
  '\uAC1C\uC120',
  '\uBA4B\uC9C0\uAC8C',
  '\uAE54\uB054\uD558\uAC8C',
  '\uC54C\uC544\uC11C',
];
const CONCRETE_EDIT_TERMS = [
  '\uBC30\uACBD',
  '\uC0C9',
  '\uD14D\uC2A4\uD2B8',
  '\uBB38\uAD6C',
  '\uC81C\uBAA9',
  '\uB85C\uACE0',
  '\uC81C\uAC70',
  '\uC0AD\uC81C',
  '\uCD94\uAC00',
  '\uBC1D',
  '\uC5B4\uB461',
  '\uAC15\uC870',
  '\uC67C\uCABD',
  '\uC624\uB978\uCABD',
  '\uC704',
  '\uC544\uB798',
  '\uD06C\uAC8C',
  '\uC791\uAC8C',
  '\uD45C\uC815',
];
const LARGE_EDIT_PATTERNS = [
  /\uC644\uC804\uD788/,
  /\uC804\uBD80/,
  /\uCC98\uC74C\uBD80\uD130/,
  /\uAC08\uC544\uC5CE/,
  /\uC0C8 \uC774\uBBF8\uC9C0\uCC98\uB7FC/,
  /\uC544\uC608/,
  /\uC804\uCCB4\s*(\uC2A4\uD0C0\uC77C|\uAD6C\uB3C4|\uB808\uC774\uC544\uC6C3|\uCEE8\uC149)/,
];

function normalizeUserTemplateStyle(style: ImageGeneration['style']): TemplatePreset['preset']['style'] {
  const chips = (style.chips ?? []).filter((chip): chip is StyleShape =>
    STYLE_IDS.includes(chip as StyleShape),
  );
  return {
    chips,
    palette: style.palette || 'auto',
    background: style.background || 'auto',
    quality: style.quality || 'high',
  };
}

function normalizeUserTemplateLayout(layout: ImageGeneration['layout']): TemplatePreset['preset']['layout'] {
  const layoutId = LAYOUT_OPTIONS.includes(layout.layout_id as LayoutId)
    ? (layout.layout_id as LayoutId)
    : (LAYOUT_OPTIONS[0] as LayoutId);
  const aspect = ASPECT_OPTIONS.includes(layout.aspect as AspectId)
    ? (layout.aspect as AspectId)
    : '1024x1024';
  return { layout_id: layoutId, aspect };
}

function resolveUserTemplateSourceId(template: TemplatePreset): string | null {
  const direct = template.sourceGenerationId?.trim() || null;
  return getUserTemplateSourceId(direct) ?? direct ?? getUserTemplateSourceId(template.id);
}

function buildImageEditNotes(sourceNotes: string | undefined, editBlock: string): string {
  if (editBlock.length >= IMAGE_EDIT_NOTES_MAX) {
    return editBlock.slice(0, IMAGE_EDIT_NOTES_MAX);
  }
  const existing = (sourceNotes || '').trim();
  const roomForExisting = IMAGE_EDIT_NOTES_MAX - editBlock.length - 2;
  const trimmedExisting = existing.slice(0, Math.max(0, roomForExisting));
  return [trimmedExisting, editBlock].filter(Boolean).join('\n\n');
}

export function shouldReviewImageEditInstruction(instruction: string): boolean {
  const normalized = instruction.trim().toLowerCase();
  if (!normalized) return false;
  if (LARGE_EDIT_PATTERNS.some((pattern) => pattern.test(normalized))) return true;
  const hasAmbiguousTerm = AMBIGUOUS_EDIT_TERMS.some((term) => normalized.includes(term));
  if (!hasAmbiguousTerm) return false;
  return !CONCRETE_EDIT_TERMS.some((term) => normalized.includes(term));
}

export function shouldStartNewGenerationForTemplatePick(
  row: Pick<ImageGeneration, 'brief_status'> | null,
): boolean {
  return row?.brief_status === 'approved';
}

export function ImageWizardToolView() {
  const { t } = useTranslation('apps');
  const { user, token } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const workspaceSlug = useMemo(
    () => searchParams.get('workspace') || resolveShellWorkspaceSlug(user, null) || '',
    [searchParams, user],
  );
  const generationId = searchParams.get('gen');
  const stepParam = parseInt(searchParams.get('step') || '1', 10);
  const step = (Math.min(Math.max(1, isNaN(stepParam) ? 1 : stepParam), 4) as StepId);

  const [myImagesOpen, setMyImagesOpen] = useState(false);
  const [myImagesCount, setMyImagesCount] = useState(0);
  const [userTemplates, setUserTemplates] = useState<TemplatePreset[]>([]);
  const [userTemplatesRefreshKey, setUserTemplatesRefreshKey] = useState(0);
  const [removingUserTemplateIds, setRemovingUserTemplateIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [templateActionError, setTemplateActionError] = useState<string | null>(null);
  const [transitioningStep, setTransitioningStep] = useState(false);

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
    listImageGenerations(token, workspaceSlug, { limit: 50, has_image_activity: true })
      .then((response) => {
        if (cancelled) return;
        setMyImagesCount(response.items.length);
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
      setUserTemplates([]);
      return;
    }
    let cancelled = false;
    const objectUrls: string[] = [];
    listImageGenerations(token, workspaceSlug, {
      limit: 100,
      image_status: 'succeeded',
      is_template: true,
    })
      .then(async (response) => {
        const templates = await Promise.all(
          response.items
            .filter((item) => Boolean(item.image_storage_key))
            .map(async (item): Promise<TemplatePreset | null> => {
              let previewUrl: string | undefined;
              try {
                const blob = await downloadGeneratedImageBlob(token, workspaceSlug, item.id);
                if (cancelled) return null;
                previewUrl = URL.createObjectURL(blob);
                objectUrls.push(previewUrl);
              } catch {
                previewUrl = undefined;
              }
              const sourcePreset = getTemplate(item.template_id);
              const createdAt = new Date(item.created_at).toLocaleDateString();
              return {
                id: makeUserTemplateId(item.id),
                category: sourcePreset?.category ?? 'card',
                mockupId: sourcePreset?.mockupId ?? 'blank_canvas',
                name: t('ai.imageWizard.gallery.userTemplateName', { date: createdAt }),
                hint: t('ai.imageWizard.gallery.userTemplateHint'),
                previewUrl,
                sourceGenerationId: item.id,
                preset: {
                  use_case: item.use_case,
                  style: normalizeUserTemplateStyle(item.style),
                  layout: normalizeUserTemplateLayout(item.layout),
                },
              };
            }),
        );
        if (!cancelled) {
          setUserTemplates(
            templates.filter((template): template is TemplatePreset => template !== null),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setUserTemplates([]);
      });
    return () => {
      cancelled = true;
      for (const objectUrl of objectUrls) URL.revokeObjectURL(objectUrl);
    };
  }, [token, workspaceSlug, userTemplatesRefreshKey, t]);

  // After the wizard creates a row mid-flow, advance step 1 → 2 once row exists.
  // For Step1's pick handlers, advancement is explicit.

  const highest = useMemo<StepId>(() => {
    if (!wizard.row) return 1;
    if (wizard.row.brief_versions.length > 0 || wizard.row.brief_status !== 'drafting') return 4;
    if (
      wizard.row.context_refs.length > 0
      || wizard.row.details?.audience
    ) {
      return Math.max(step, 3) as StepId;
    }
    if (wizard.row.template_id || wizard.row.use_case) return Math.max(step, 2) as StepId;
    return 1;
  }, [wizard.row, step]);

  const goToStep = useCallback(
    async (next: StepId) => {
      if (next === 4) {
        setTransitioningStep(true);
        try {
          await flushWizard();
        } finally {
          setTransitioningStep(false);
        }
      }
      updateUrl({ step: next });
    },
    [flushWizard, updateUrl],
  );

  const handleJumpStep = useCallback(
    (next: StepId) => {
      if (next > highest) return;
      void goToStep(next);
    },
    [goToStep, highest],
  );

  async function handleTemplatePick(template: TemplatePreset) {
    const payload = {
      template_id: template.id,
      use_case: template.preset.use_case,
      style: template.preset.style,
      layout: template.preset.layout,
    };
    if (!wizard.row || shouldStartNewGenerationForTemplatePick(wizard.row)) {
      const created = await wizard.startNew(payload);
      updateUrl({ gen: created.id, step: 2 });
      return;
    }
    wizard.update(payload);
    updateUrl({ step: 2 });
  }

  async function handleBlankPick() {
    if (!wizard.row) {
      const created = await wizard.startNew({
        template_id: null,
        use_case: '',
        style: DEFAULT_STYLE,
        layout: DEFAULT_LAYOUT,
        details: DEFAULT_DETAILS,
      });
      updateUrl({ gen: created.id, step: 2 });
      return;
    }
    updateUrl({ step: 2 });
  }

  async function handleRemoveUserTemplate(template: TemplatePreset) {
    if (!token) return;
    const sourceId = resolveUserTemplateSourceId(template);
    if (!sourceId) return;
    setTemplateActionError(null);
    setRemovingUserTemplateIds((prev) => {
      const next = new Set(prev);
      next.add(template.id);
      return next;
    });
    try {
      const updated = await setImageGenerationTemplate(token, workspaceSlug, sourceId, false);
      if (wizard.row?.id === sourceId) {
        wizard.applyServer(updated);
      }
      setUserTemplates((prev) => prev.filter((item) => item.id !== template.id));
      setUserTemplatesRefreshKey((value) => value + 1);
    } catch (error) {
      setTemplateActionError(
        error instanceof Error ? error.message : t('ai.imageWizard.errors.saveFailed'),
      );
    } finally {
      setRemovingUserTemplateIds((prev) => {
        const next = new Set(prev);
        next.delete(template.id);
        return next;
      });
    }
  }

  async function handleClone() {
    if (!wizard.row) return;
    const created = await wizard.startNew({
      template_id: wizard.row.template_id,
      use_case: wizard.row.use_case,
      use_case_other: wizard.row.use_case_other,
      style: wizard.row.style,
      layout: wizard.row.layout,
      details: wizard.row.details,
      context_refs: wizard.row.context_refs,
    });
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        params.set('gen', created.id);
        params.set('step', '4');
        return params;
      },
      { replace: false },
    );
  }

  async function handleImageEdit(instruction: string) {
    if (!token || !wizard.row) return;
    const source = wizard.row;
    const trimmedInstruction = instruction.trim();
    const requiresPlan = shouldReviewImageEditInstruction(trimmedInstruction);
    const sourceBlob = await downloadGeneratedImageBlob(token, workspaceSlug, source.id);
    let created: ImageGeneration | null = null;
    try {
      created = await createImageGeneration(token, workspaceSlug, {
        template_id: source.template_id,
        use_case: source.use_case,
        use_case_other: source.use_case_other,
        style: source.style,
        layout: source.layout,
        details: {
          audience: source.details?.audience || '',
          notes: buildImageEditNotes(
            source.details?.notes,
            [
              t('ai.imageWizard.step4.editImageNotesRequest', {
                instruction: trimmedInstruction,
              }),
              t('ai.imageWizard.step4.editImageNotesReference'),
            ].join('\n'),
          ),
          source_generation_id: source.id,
          source_image_edit_instruction: trimmedInstruction,
          source_image_requires_plan: requiresPlan,
        },
        context_refs: source.context_refs,
      });
      const sourceFile = new File([sourceBlob], `image-edit-source-${source.id}.png`, {
        type: sourceBlob.type || 'image/png',
      });
      const createdId = created.id;
      await uploadReferenceImage(token, workspaceSlug, createdId, sourceFile, 'composition');
      const next = requiresPlan
        ? await getImageGeneration(token, workspaceSlug, createdId)
        : await approveImageGeneration(token, workspaceSlug, createdId);
      wizard.applyServer(next);
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          params.set('gen', createdId);
          params.set('step', '4');
          return params;
        },
        { replace: false },
      );
    } catch (error) {
      if (created) {
        await deleteImageGeneration(token, workspaceSlug, created.id).catch(() => undefined);
      }
      throw error;
    }
  }

  async function handleNewImage() {
    if (token && wizard.row?.image_status === 'idle') {
      await deleteImageGeneration(token, workspaceSlug, wizard.row.id).catch(() => undefined);
    } else {
      await flushWizard();
    }
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        params.delete('gen');
        params.set('step', '1');
        return params;
      },
      { replace: false },
    );
  }

  function handleDiscard() {
    if (token && wizard.row?.image_status === 'idle') {
      void deleteImageGeneration(token, workspaceSlug, wizard.row.id).catch(() => undefined);
    }
    updateUrl({ gen: null, step: 1 });
  }

  if (!workspaceSlug) {
    const fallback =
      resolveDefaultWorkspaceAppPath(user, 'ai')
      || buildWorkspaceAppPath(resolveShellWorkspaceSlug(user, null) ?? '', 'ai');
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
  const templateName = row?.template_id
    ? userTemplates.find((template) => template.id === row.template_id)?.name
      ?? (getUserTemplateSourceId(row.template_id)
        ? t('ai.imageWizard.gallery.userTemplateFallback')
        : null)
      ?? t(`ai.imageWizard.templates.${row.template_id}.name`, { defaultValue: row.template_id })
    : null;

  const summaries = (
    <div className="space-y-2 mb-4">
      {step > 1 ? (
        <StepSummary
          stepNumber={1}
          title={t('ai.imageWizard.steps.step1.title')}
          value={
            row?.template_id
              ? templateName
              : row
                ? t('ai.imageWizard.gallery.startBlank')
                : null
          }
          onEdit={() => handleJumpStep(1)}
        />
      ) : null}
      {step > 2 ? (
        <StepSummary
          stepNumber={2}
          title={t('ai.imageWizard.steps.step2.title')}
          value={(() => {
            const audience = row?.details?.audience?.trim();
            const refsCount = row?.context_refs?.length ?? 0;
            if (!audience && refsCount === 0) {
              return t('ai.imageWizard.wizard.noneSelected');
            }
            const parts: string[] = [];
            if (audience) parts.push(audience);
            if (refsCount > 0) {
              parts.push(t('ai.imageWizard.context.attachedCount', { count: refsCount }));
            }
            return parts.join(' · ');
          })()}
          onEdit={() => handleJumpStep(2)}
        />
      ) : null}
      {step > 3 ? (
        <StepSummary
          stepNumber={3}
          title={t('ai.imageWizard.steps.step3.title')}
          value={(() => {
            if (!row) return null;
            const styleChips = row.style.chips
              ?.slice(0, 2)
              .map((chip) =>
                t(`ai.imageWizard.style.chips.${chip}`, { defaultValue: chip }),
              )
              .join(' · ');
            const aspectLabel = t(`ai.imageWizard.layout.aspect.${row.layout.aspect}`, {
              defaultValue: row.layout.aspect,
            });
            return [styleChips || t('ai.imageWizard.style.empty'), aspectLabel]
              .filter(Boolean)
              .join(' · ');
          })()}
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
          onPickTemplate={(template) => void handleTemplatePick(template)}
          onRemoveUserTemplate={(template) => void handleRemoveUserTemplate(template)}
          onPickBlank={() => void handleBlankPick()}
        />
      );
    }
    if (step === 2 && row) {
      return (
        <Step2Context
          workspaceSlug={workspaceSlug}
          details={row.details ?? DEFAULT_DETAILS}
          contextRefs={row.context_refs ?? []}
          onChangeDetails={(details) => wizard.update({ details })}
          onChangeContextRefs={(context_refs) => wizard.update({ context_refs })}
        />
      );
    }
    if (step === 3 && row) {
      return (
        <Step3Refine
          workspaceSlug={workspaceSlug}
          generationId={row.id}
          style={row.style ?? DEFAULT_STYLE}
          layout={row.layout ?? DEFAULT_LAYOUT}
          references={row.reference_image_keys ?? []}
          onChangeStyle={(style) => wizard.update({ style })}
          onChangeLayout={(layout) => wizard.update({ layout })}
          onReferencesChange={(refs) => wizard.applyServer({ ...row, reference_image_keys: refs })}
        />
      );
    }
    if (step === 4 && row) {
      return (
        <Step4Brief
          workspaceSlug={workspaceSlug}
          row={row}
          onRowReplaced={wizard.applyServer}
          onClone={() => void handleClone()}
          onDiscard={handleDiscard}
          onImageEdit={handleImageEdit}
          onTemplateChanged={() => setUserTemplatesRefreshKey((value) => value + 1)}
        />
      );
    }
    return null;
  })();

  const footer = (
    <WizardFooter
      onPrev={step > 1 ? () => void goToStep((step - 1) as StepId) : undefined}
      onNext={
        step < 4
          ? () => void goToStep((step + 1) as StepId)
          : undefined
      }
      onSkip={step === 2 || step === 3 ? () => void goToStep(4) : undefined}
      nextDisabled={
        (step === 1 && !row)
        || transitioningStep
        || wizard.autosave === 'pending'
        || wizard.autosave === 'saving'
      }
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
        onNewImage={() => void handleNewImage()}
        onOpenMyImages={() => setMyImagesOpen(true)}
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
        onClose={() => setMyImagesOpen(false)}
        workspaceSlug={workspaceSlug}
        onPickGeneration={(id) => {
          setMyImagesOpen(false);
          updateUrl({ gen: id, step: 4 });
        }}
        onCountChange={setMyImagesCount}
      />
    </>
  );
}

// Re-export presets so other modules (and tests) can introspect.
export { TEMPLATE_PRESETS, getTemplate };
export default ImageWizardToolView;
