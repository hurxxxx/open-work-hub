import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';

import type { ImageGeneration } from '../../api/image-wizard-api';
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
  type TemplatePreset,
} from './templates/template-presets';
import {
  loadGeneratedImageAsset,
  type GeneratedImageAssetPort,
} from './generated-image-assets';

const USER_TEMPLATE_FALLBACK_CATEGORY = 'card';
const USER_TEMPLATE_FALLBACK_MOCKUP = 'blank_canvas';
const USER_TEMPLATE_ASSET_LOAD_CONCURRENCY = 4;

export interface LoadUserTemplatePresetsOptions {
  token: string;
  workspaceSlug: string;
  items: ImageGeneration[];
  formatDate: (createdAt: string) => string;
  formatDisplayName: (createdAtDisplay: string) => string;
  userTemplateHint: string;
  assetPort: GeneratedImageAssetPort;
}

export interface LoadedUserTemplatePresets {
  presets: TemplatePreset[];
  dispose: () => void;
}

export function normalizeUserTemplateStyle(
  style: ImageGeneration['style'],
): TemplatePreset['preset']['style'] {
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

export function normalizeUserTemplateLayout(
  layout: ImageGeneration['layout'],
): TemplatePreset['preset']['layout'] {
  const layoutId = LAYOUT_OPTIONS.includes(layout.layout_id as LayoutId)
    ? (layout.layout_id as LayoutId)
    : (LAYOUT_OPTIONS[0] as LayoutId);
  const aspect = ASPECT_OPTIONS.includes(layout.aspect as AspectId)
    ? (layout.aspect as AspectId)
    : '1024x1024';
  return { layout_id: layoutId, aspect };
}

export function resolveUserTemplateSourceId(
  template: TemplatePreset,
): string | null {
  const direct = template.sourceGenerationId?.trim() || null;
  return (
    getUserTemplateSourceId(direct) ??
    direct ??
    getUserTemplateSourceId(template.id)
  );
}

export function resolveTemplateDisplayName(
  templateId: string | null | undefined,
  userTemplates: TemplatePreset[],
  options: {
    userTemplateFallback: string;
    getBuiltinTemplateName: (templateId: string) => string;
  },
): string | null {
  if (!templateId) return null;
  return (
    userTemplates.find((template) => template.id === templateId)?.name ??
    (getUserTemplateSourceId(templateId)
      ? options.userTemplateFallback
      : options.getBuiltinTemplateName(templateId))
  );
}

async function loadUserTemplatePreset(
  options: LoadUserTemplatePresetsOptions,
  item: ImageGeneration,
  disposers: Array<() => void>,
): Promise<TemplatePreset | null> {
  if (!item.image_storage_key) return null;

  let previewUrl: string | undefined;
  try {
    const asset = await loadGeneratedImageAsset(item.id, options.assetPort);
    previewUrl = asset.url;
    disposers.push(asset.dispose);
  } catch {
    previewUrl = undefined;
  }

  const sourcePreset = getTemplate(item.template_id);
  const createdAtDisplay = options.formatDate(item.created_at);
  return {
    id: makeUserTemplateId(item.id),
    category: sourcePreset?.category ?? USER_TEMPLATE_FALLBACK_CATEGORY,
    mockupId: sourcePreset?.mockupId ?? USER_TEMPLATE_FALLBACK_MOCKUP,
    name: options.formatDisplayName(createdAtDisplay),
    hint: options.userTemplateHint,
    previewUrl,
    sourceGenerationId: item.id,
    preset: {
      use_case: item.use_case,
      style: normalizeUserTemplateStyle(item.style),
      layout: normalizeUserTemplateLayout(item.layout),
    },
  };
}

export async function loadUserTemplatePresets(
  options: LoadUserTemplatePresetsOptions,
): Promise<LoadedUserTemplatePresets> {
  const disposers: Array<() => void> = [];
  const loaded = await runRequestsWithConcurrency(
    options.items,
    USER_TEMPLATE_ASSET_LOAD_CONCURRENCY,
    (item) => loadUserTemplatePreset(options, item, disposers),
  );

  return {
    presets: loaded.filter(
      (template): template is TemplatePreset => template !== null,
    ),
    dispose: () => {
      for (const dispose of disposers) dispose();
    },
  };
}
