import type { ImageGeneration } from '../../api/image-wizard-api';
import { getUserTemplateSourceId } from './templates/template-presets';

export const MY_IMAGES_STATUS_TONE: Record<string, string> = {
  succeeded: 'text-[var(--ui-color-success,green)]',
  failed: 'text-[var(--ui-color-danger)]',
  running: 'text-app-accent',
  queued: 'text-app-ink/60',
  idle: 'text-app-ink/40',
};

export interface MyImageGalleryProjection {
  statusTone: string;
  summary: string;
  title: {
    defaultValue?: string;
    key: string;
  };
}

export type MyImagesState = {
  items: ImageGeneration[];
  thumbnailUrls: Record<string, string>;
  loading: boolean;
  error: string | null;
};

export type MyImagesAction =
  | {
    type: 'load';
  }
  | {
    type: 'loaded';
    items: ImageGeneration[];
  }
  | {
    type: 'failed';
    message: string;
  }
  | {
    type: 'thumbnails-loaded';
    thumbnailUrls: Record<string, string>;
  }
  | {
    type: 'clear-thumbnails';
  }
  | {
    type: 'delete-succeeded';
    generationId: string;
  };

export const MY_IMAGES_INITIAL_STATE: MyImagesState = {
  items: [],
  thumbnailUrls: {},
  loading: false,
  error: null,
};

export function getMyImageGallerySummary(item: ImageGeneration): string {
  const editInstruction =
    typeof item.details?.source_image_edit_instruction === 'string'
      ? item.details.source_image_edit_instruction.trim()
      : '';
  if (editInstruction) return editInstruction;
  const latestBrief = item.brief_versions[item.brief_versions.length - 1];
  if (!latestBrief || latestBrief.internal) return '';
  return latestBrief.text;
}

export function getMyImageGalleryTitle(item: ImageGeneration): MyImageGalleryProjection['title'] {
  if (getUserTemplateSourceId(item.template_id)) {
    return { key: 'ai.imageWizard.gallery.userTemplateBasedTitle' };
  }
  if (item.template_id) {
    return {
      key: `ai.imageWizard.templates.${item.template_id}.name`,
      defaultValue: item.template_id,
    };
  }
  return { key: 'ai.imageWizard.gallery.untitled' };
}

export function shouldLoadGalleryThumbnail(item: ImageGeneration): boolean {
  return item.image_status === 'succeeded' && Boolean(item.image_storage_key);
}

export function projectMyImageGalleryItem(
  item: ImageGeneration,
): MyImageGalleryProjection {
  return {
    statusTone: MY_IMAGES_STATUS_TONE[item.image_status] ?? 'text-app-ink/40',
    summary: getMyImageGallerySummary(item),
    title: getMyImageGalleryTitle(item),
  };
}

export function myImagesReducer(
  state: MyImagesState,
  action: MyImagesAction,
): MyImagesState {
  switch (action.type) {
    case 'load':
      return {
        ...state,
        loading: true,
        error: null,
      };
    case 'loaded':
      return {
        ...state,
        items: action.items,
        loading: false,
      };
    case 'failed':
      return {
        ...state,
        loading: false,
        error: action.message,
      };
    case 'thumbnails-loaded':
      return {
        ...state,
        thumbnailUrls: action.thumbnailUrls,
      };
    case 'clear-thumbnails':
      return {
        ...state,
        thumbnailUrls: {},
      };
    case 'delete-succeeded':
      return {
        ...state,
        items: state.items.filter((item) => item.id !== action.generationId),
      };
  }
}
