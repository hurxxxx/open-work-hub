import type {
  DetailsPayload,
  ImageGeneration,
  ImageGenerationCreatePayload,
  LayoutPayload,
  StylePayload,
} from '../../api/image-wizard-api';
import type { AutosaveState, StepId } from './wizard-state';
import { LAYOUT_OPTIONS, type AspectId, type LayoutId } from './layout-wireframes';
import type { TemplatePreset } from './templates/template-presets';

export const DEFAULT_IMAGE_WIZARD_STYLE: StylePayload = {
  chips: [],
  palette: 'auto',
  background: 'auto',
  quality: 'high',
};

export const DEFAULT_IMAGE_WIZARD_LAYOUT: LayoutPayload = {
  layout_id: LAYOUT_OPTIONS[0] as LayoutId,
  aspect: '1024x1024' as AspectId,
};

export const DEFAULT_IMAGE_WIZARD_DETAILS: DetailsPayload = {
  audience: '',
  notes: '',
};

export const IMAGE_EDIT_NOTES_MAX = 2000;

export interface ImageWizardViewState {
  myImagesOpen: boolean;
  myImagesCount: number;
  userTemplates: TemplatePreset[];
  userTemplatesRefreshKey: number;
  removingUserTemplateIds: Set<string>;
  templateActionError: string | null;
  transitioningStep: boolean;
}

export type ImageWizardViewAction =
  | { type: 'my-images-open:set'; open: boolean }
  | { type: 'my-images-count:set'; count: number }
  | { type: 'user-templates:set'; templates: TemplatePreset[] }
  | { type: 'user-templates:remove'; templateId: string }
  | { type: 'user-templates:refresh' }
  | { type: 'template-removal:start'; templateId: string }
  | { type: 'template-removal:finish'; templateId: string }
  | { type: 'template-action-error:set'; message: string | null }
  | { type: 'transitioning-step:set'; value: boolean };

export interface ImageWizardNextDisabledArgs {
  autosave: AutosaveState;
  hasRow: boolean;
  step: StepId;
  transitioningStep: boolean;
}

export interface ImageEditGenerationPayloadArgs {
  editReferenceText: string;
  editRequestText: string;
  requiresPlan: boolean;
  source: ImageGeneration;
  trimmedInstruction: string;
}

export type ImageWizardFlowTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export const INITIAL_IMAGE_WIZARD_VIEW_STATE: ImageWizardViewState = {
  myImagesOpen: false,
  myImagesCount: 0,
  userTemplates: [],
  userTemplatesRefreshKey: 0,
  removingUserTemplateIds: new Set(),
  templateActionError: null,
  transitioningStep: false,
};

export function imageWizardViewReducer(
  state: ImageWizardViewState,
  action: ImageWizardViewAction,
): ImageWizardViewState {
  switch (action.type) {
    case 'my-images-open:set':
      return { ...state, myImagesOpen: action.open };
    case 'my-images-count:set':
      return { ...state, myImagesCount: action.count };
    case 'user-templates:set':
      return { ...state, userTemplates: action.templates };
    case 'user-templates:remove':
      return {
        ...state,
        userTemplates: state.userTemplates.filter((item) => item.id !== action.templateId),
      };
    case 'user-templates:refresh':
      return { ...state, userTemplatesRefreshKey: state.userTemplatesRefreshKey + 1 };
    case 'template-removal:start': {
      const removingUserTemplateIds = new Set(state.removingUserTemplateIds);
      removingUserTemplateIds.add(action.templateId);
      return { ...state, removingUserTemplateIds, templateActionError: null };
    }
    case 'template-removal:finish': {
      const removingUserTemplateIds = new Set(state.removingUserTemplateIds);
      removingUserTemplateIds.delete(action.templateId);
      return { ...state, removingUserTemplateIds };
    }
    case 'template-action-error:set':
      return { ...state, templateActionError: action.message };
    case 'transitioning-step:set':
      return { ...state, transitioningStep: action.value };
  }
}

export function parseImageWizardStep(stepParam: string | null): StepId {
  const parsed = parseInt(stepParam || '1', 10);
  return Math.min(Math.max(1, Number.isNaN(parsed) ? 1 : parsed), 4) as StepId;
}

export function getHighestReachableImageWizardStep(
  row: ImageGeneration | null,
  currentStep: StepId,
): StepId {
  if (!row) return 1;
  if (row.brief_versions.length > 0 || row.brief_status !== 'drafting') return 4;
  if (row.context_refs.length > 0 || row.details?.audience) {
    return Math.max(currentStep, 3) as StepId;
  }
  if (row.template_id || row.use_case) return Math.max(currentStep, 2) as StepId;
  return 1;
}

export function canJumpToImageWizardStep(next: StepId, highest: StepId): boolean {
  return next <= highest;
}

export function shouldDisableImageWizardNext({
  autosave,
  hasRow,
  step,
  transitioningStep,
}: ImageWizardNextDisabledArgs): boolean {
  return (
    (step === 1 && !hasRow)
    || transitioningStep
    || autosave === 'pending'
    || autosave === 'saving'
  );
}

export function buildTemplatePickGenerationPayload(
  template: TemplatePreset,
): ImageGenerationCreatePayload {
  return {
    template_id: template.id,
    use_case: template.preset.use_case,
    style: template.preset.style,
    layout: template.preset.layout,
  };
}

export function buildBlankGenerationPayload(): ImageGenerationCreatePayload {
  return {
    template_id: null,
    use_case: '',
    style: DEFAULT_IMAGE_WIZARD_STYLE,
    layout: DEFAULT_IMAGE_WIZARD_LAYOUT,
    details: DEFAULT_IMAGE_WIZARD_DETAILS,
  };
}

export function buildCloneGenerationPayload(
  row: ImageGeneration,
): ImageGenerationCreatePayload {
  return {
    template_id: row.template_id,
    use_case: row.use_case,
    use_case_other: row.use_case_other,
    style: row.style,
    layout: row.layout,
    details: row.details,
    context_refs: row.context_refs,
  };
}

export function buildImageEditGenerationPayload({
  editReferenceText,
  editRequestText,
  requiresPlan,
  source,
  trimmedInstruction,
}: ImageEditGenerationPayloadArgs): ImageGenerationCreatePayload {
  return {
    template_id: source.template_id,
    use_case: source.use_case,
    use_case_other: source.use_case_other,
    style: source.style,
    layout: source.layout,
    details: {
      audience: source.details?.audience || '',
      notes: buildImageEditNotes(source.details?.notes, [editRequestText, editReferenceText].join('\n')),
      source_generation_id: source.id,
      source_image_edit_instruction: trimmedInstruction,
      source_image_requires_plan: requiresPlan,
    },
    context_refs: source.context_refs,
  };
}

export function buildImageEditNotes(sourceNotes: string | undefined, editBlock: string): string {
  if (editBlock.length >= IMAGE_EDIT_NOTES_MAX) {
    return editBlock.slice(0, IMAGE_EDIT_NOTES_MAX);
  }
  const existing = (sourceNotes || '').trim();
  const roomForExisting = IMAGE_EDIT_NOTES_MAX - editBlock.length - 2;
  const trimmedExisting = existing.slice(0, Math.max(0, roomForExisting));
  return [trimmedExisting, editBlock].filter(Boolean).join('\n\n');
}

export function buildContextSummaryValue(
  row: ImageGeneration | null,
  t: ImageWizardFlowTranslator,
): string {
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
}

export function buildRefineSummaryValue(
  row: ImageGeneration | null,
  t: ImageWizardFlowTranslator,
): string | null {
  if (!row) return null;
  const styleChips = row.style.chips
    ?.slice(0, 2)
    .map((chip) => t(`ai.imageWizard.style.chips.${chip}`, { defaultValue: chip }))
    .join(' · ');
  const aspectLabel = t(`ai.imageWizard.layout.aspect.${row.layout.aspect}`, {
    defaultValue: row.layout.aspect,
  });
  return [styleChips || t('ai.imageWizard.style.empty'), aspectLabel]
    .filter(Boolean)
    .join(' · ');
}

export function buildTemplateSummaryValue(
  row: ImageGeneration | null,
  templateName: string | null,
  startBlankLabel: string,
): string | null {
  if (row?.template_id) return templateName;
  if (row) return startBlankLabel;
  return null;
}
