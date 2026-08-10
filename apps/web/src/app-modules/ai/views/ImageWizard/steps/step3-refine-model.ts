import type {
  LayoutPayload,
  ReferenceImageRef,
  ReferenceImageRole,
  StylePayload,
} from '../../../api/image-wizard-api';

export const ROLE_OPTIONS: ReferenceImageRole[] = ['style', 'composition', 'content'];
export const PALETTE_OPTIONS = ['auto', 'brand', 'warm', 'cool', 'monochrome', 'vivid'] as const;
export const BACKGROUND_OPTIONS = ['auto', 'transparent', 'white', 'dark'] as const;
export const QUALITY_OPTIONS = ['auto', 'low', 'medium', 'high'] as const;
export const MAX_REFS = 4;

export type Step3Panel = 'style' | 'layout' | 'refs' | 'advanced';

export interface SelectOption {
  value: string;
  label: string;
}

export interface Step3RefineState {
  openPanel: Step3Panel | null;
  styleSheetOpen: boolean;
  uploading: boolean;
  uploadError: string | null;
  pendingRole: ReferenceImageRole;
}

export type Step3RefineAction =
  | { type: 'panel:toggle'; panel: Step3Panel }
  | { type: 'style-sheet:set'; open: boolean }
  | { type: 'upload:start' }
  | { type: 'upload:finish' }
  | { type: 'upload:fail'; message: string }
  | { type: 'role:set'; role: ReferenceImageRole };

export const INITIAL_STEP3_REFINE_STATE: Step3RefineState = {
  openPanel: 'style',
  styleSheetOpen: false,
  uploading: false,
  uploadError: null,
  pendingRole: 'style',
};

export interface Step3RefineProjection {
  advancedSummary: string;
  backgroundOptions: SelectOption[];
  layoutSummary: string;
  paletteOptions: SelectOption[];
  qualityOptions: SelectOption[];
  referenceLimitReached: boolean;
  refsSummary: string;
  roleOptions: SelectOption[];
  styleSummary: string;
}

export interface BuildStep3RefineProjectionArgs {
  layout: LayoutPayload;
  referenceCount: number;
  style: StylePayload;
  t: Step3RefineTranslator;
}

export interface CanUploadReferenceImageArgs {
  maxRefs?: number;
  referenceCount: number;
  tokenPresent: boolean;
}

export type Step3RefineTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function step3RefineReducer(
  state: Step3RefineState,
  action: Step3RefineAction,
): Step3RefineState {
  switch (action.type) {
    case 'panel:toggle':
      return {
        ...state,
        openPanel: state.openPanel === action.panel ? null : action.panel,
      };
    case 'style-sheet:set':
      return { ...state, styleSheetOpen: action.open };
    case 'upload:start':
      return { ...state, uploading: true, uploadError: null };
    case 'upload:finish':
      return { ...state, uploading: false };
    case 'upload:fail':
      return { ...state, uploading: false, uploadError: action.message };
    case 'role:set':
      return { ...state, pendingRole: action.role };
  }
}

export function buildStep3RefineProjection({
  layout,
  referenceCount,
  style,
  t,
}: BuildStep3RefineProjectionArgs): Step3RefineProjection {
  const referenceLimitReached = isReferenceImageLimitReached(referenceCount);
  return {
    advancedSummary: buildAdvancedSummary(style, t),
    backgroundOptions: buildSelectOptions(BACKGROUND_OPTIONS, 'ai.imageWizard.style.background', t),
    layoutSummary: buildLayoutSummary(layout, t),
    paletteOptions: buildSelectOptions(PALETTE_OPTIONS, 'ai.imageWizard.style.palette', t),
    qualityOptions: buildSelectOptions(QUALITY_OPTIONS, 'ai.imageWizard.style.quality', t),
    referenceLimitReached,
    refsSummary: t('ai.imageWizard.referenceImages.countSummary', {
      count: referenceCount,
      max: MAX_REFS,
    }),
    roleOptions: ROLE_OPTIONS.map((role) => ({
      value: role,
      label: t(`ai.imageWizard.referenceImages.roles.${role}`),
    })),
    styleSummary: buildStyleSummary(style, t),
  };
}

export function buildStyleSummary(
  style: StylePayload,
  t: Step3RefineTranslator,
): string {
  if (style.chips.length === 0) return t('ai.imageWizard.style.empty');
  return (
    style.chips
      .slice(0, 3)
      .map((chip) => t(`ai.imageWizard.style.chips.${chip}`, { defaultValue: chip }))
      .join(' · ') + (style.chips.length > 3 ? ` +${style.chips.length - 3}` : '')
  );
}

export function buildLayoutSummary(
  layout: LayoutPayload,
  t: Step3RefineTranslator,
): string {
  const layoutLabel = layout.layout_id
    ? t(`ai.imageWizard.layout.layouts.${layout.layout_id}.label`, {
        defaultValue: layout.layout_id,
      })
    : t('ai.imageWizard.layout.unset');
  const aspectLabel = t(`ai.imageWizard.layout.aspect.${layout.aspect}`, {
    defaultValue: layout.aspect,
  });
  return `${layoutLabel} · ${aspectLabel}`;
}

export function buildAdvancedSummary(
  style: StylePayload,
  t: Step3RefineTranslator,
): string {
  return `${t(`ai.imageWizard.style.background.${style.background || 'auto'}`)} · ${t(
    `ai.imageWizard.style.quality.${style.quality || 'auto'}`,
  )}`;
}

export function canUploadReferenceImage({
  maxRefs = MAX_REFS,
  referenceCount,
  tokenPresent,
}: CanUploadReferenceImageArgs): boolean {
  return tokenPresent && !isReferenceImageLimitReached(referenceCount, maxRefs);
}

export function isReferenceImageLimitReached(
  referenceCount: number,
  maxRefs = MAX_REFS,
): boolean {
  return referenceCount >= maxRefs;
}

export function removeReferenceImage(
  references: readonly ReferenceImageRef[],
  storageKey: string,
): ReferenceImageRef[] {
  return references.filter((ref) => ref.storage_key !== storageKey);
}

export function getReferenceImageDisplayName(ref: ReferenceImageRef): string | undefined {
  return ref.original_name || ref.storage_key.split('/').pop();
}

function buildSelectOptions(
  values: readonly string[],
  keyPrefix: string,
  t: Step3RefineTranslator,
): SelectOption[] {
  return values.map((value) => ({
    value,
    label: t(`${keyPrefix}.${value}`, { defaultValue: value }),
  }));
}
