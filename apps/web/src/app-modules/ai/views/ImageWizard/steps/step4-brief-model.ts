import type {
  BriefVersion,
  ImageGeneration,
} from '../../../api/image-wizard-api';

export interface ImageRevisionGalleryItem {
  id: string;
  imageUrl: string | null;
  loadError: string | null;
  createdAt: string;
  isCurrent: boolean;
}

export type Step4Busy = 'brief' | 'approve' | 'cancel' | 'image-edit' | null;

export interface Step4BriefState {
  busy: Step4Busy;
  templateBusy: boolean;
  error: string | null;
  downloadUrl: string | null;
  imageLoadError: string | null;
  sourceImageUrl: string | null;
  sourceImageLoadError: string | null;
  revisionItems: ImageRevisionGalleryItem[];
  revisionGalleryError: string | null;
}

export type Step4BriefAction =
  | { type: 'operation:start'; busy: Exclude<Step4Busy, null> }
  | { type: 'operation:finish' }
  | { type: 'operation:fail'; message: string }
  | { type: 'template:start' }
  | { type: 'template:finish' }
  | { type: 'template:fail'; message: string }
  | { type: 'image:reset' }
  | { type: 'image:loading' }
  | { type: 'image:loaded'; url: string }
  | { type: 'image:fail'; message: string }
  | { type: 'source:reset' }
  | { type: 'source:loading' }
  | { type: 'source:loaded'; url: string }
  | { type: 'source:fail'; message: string }
  | { type: 'revisions:reset' }
  | { type: 'revisions:loading' }
  | { type: 'revisions:loaded'; items: ImageRevisionGalleryItem[] }
  | { type: 'revisions:fail'; message: string };

export const INITIAL_STEP4_BRIEF_STATE: Step4BriefState = {
  busy: null,
  templateBusy: false,
  error: null,
  downloadUrl: null,
  imageLoadError: null,
  sourceImageUrl: null,
  sourceImageLoadError: null,
  revisionItems: [],
  revisionGalleryError: null,
};

export interface Step4BriefProjection {
  composerDisabled: boolean;
  imageEditRequiresPlan: boolean;
  isFinished: boolean;
  isGeneratingImage: boolean;
  isImageEdit: boolean;
  latestBrief: BriefVersion | undefined;
  latestBriefIndex: number;
  shouldSkipPlanForImageEdit: boolean;
  showBriefPlan: boolean;
  sourceGenerationId: string;
  sourceImageEditInstruction: string;
}

export type Step4InitialBriefIntent = 'idle' | 'mark-handled' | 'request';

export interface Step4InitialBriefIntentInput {
  briefStatus: ImageGeneration['brief_status'];
  briefVersionCount: number;
  generationId: string;
  requestedGenerationId: string | null;
  shouldSkipPlanForImageEdit: boolean;
  token: string | null | undefined;
}

export interface Step4DirectImageEditAutoApproveInput {
  briefStatus: ImageGeneration['brief_status'];
  generationId: string;
  imageStatus: ImageGeneration['image_status'];
  requestedGenerationId: string | null;
  shouldSkipPlanForImageEdit: boolean;
  token: string | null | undefined;
}

export function step4BriefReducer(
  state: Step4BriefState,
  action: Step4BriefAction,
): Step4BriefState {
  switch (action.type) {
    case 'operation:start':
      return { ...state, busy: action.busy, error: null };
    case 'operation:finish':
      return { ...state, busy: null };
    case 'operation:fail':
      return { ...state, busy: null, error: action.message };
    case 'template:start':
      return { ...state, templateBusy: true, error: null };
    case 'template:finish':
      return { ...state, templateBusy: false };
    case 'template:fail':
      return { ...state, templateBusy: false, error: action.message };
    case 'image:reset':
      return { ...state, downloadUrl: null, imageLoadError: null };
    case 'image:loading':
      return { ...state, downloadUrl: null, imageLoadError: null };
    case 'image:loaded':
      return { ...state, downloadUrl: action.url, imageLoadError: null };
    case 'image:fail':
      return { ...state, downloadUrl: null, imageLoadError: action.message };
    case 'source:reset':
      return { ...state, sourceImageUrl: null, sourceImageLoadError: null };
    case 'source:loading':
      return { ...state, sourceImageUrl: null, sourceImageLoadError: null };
    case 'source:loaded':
      return { ...state, sourceImageUrl: action.url, sourceImageLoadError: null };
    case 'source:fail':
      return { ...state, sourceImageUrl: null, sourceImageLoadError: action.message };
    case 'revisions:reset':
      return { ...state, revisionItems: [], revisionGalleryError: null };
    case 'revisions:loading':
      return { ...state, revisionGalleryError: null };
    case 'revisions:loaded':
      return { ...state, revisionItems: action.items, revisionGalleryError: null };
    case 'revisions:fail':
      return { ...state, revisionItems: [], revisionGalleryError: action.message };
  }
}

export function getSourceGenerationId(item: ImageGeneration): string {
  return typeof item.details?.source_generation_id === 'string'
    ? item.details.source_generation_id
    : '';
}

function getRootGenerationId(
  item: ImageGeneration,
  byId: Map<string, ImageGeneration>,
): string {
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

export function collectImageRevisionRows(
  current: ImageGeneration,
  candidates: readonly ImageGeneration[],
): ImageGeneration[] {
  const byId = new Map(candidates.map((item) => [item.id, item]));
  byId.set(current.id, current);
  const rootId = getRootGenerationId(current, byId);
  const rows: ImageGeneration[] = [];
  for (const item of byId.values()) {
    const isSameRevisionTree = getRootGenerationId(item, byId) === rootId;
    if (isSameRevisionTree && item.image_status === 'succeeded' && item.image_storage_key) {
      rows.push(item);
    }
  }
  return rows.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
}

export function projectStep4Brief(row: ImageGeneration): Step4BriefProjection {
  const sourceGenerationId = getSourceGenerationId(row);
  const sourceImageEditInstruction =
    typeof row.details?.source_image_edit_instruction === 'string'
      ? row.details.source_image_edit_instruction
      : '';
  const imageEditRequiresPlan = row.details?.source_image_requires_plan === true;
  const isImageEdit = Boolean(sourceGenerationId && sourceImageEditInstruction);
  const shouldSkipPlanForImageEdit = isImageEdit && !imageEditRequiresPlan;
  const isGeneratingImage = row.image_status === 'queued' || row.image_status === 'running';
  const isFinished =
    row.image_status === 'succeeded'
    || row.image_status === 'failed'
    || row.image_status === 'cancelled';
  const latestBrief = row.brief_versions.at(-1);
  return {
    composerDisabled: row.brief_status === 'approved' || isGeneratingImage || isFinished,
    imageEditRequiresPlan,
    isFinished,
    isGeneratingImage,
    isImageEdit,
    latestBrief,
    latestBriefIndex: Math.max(0, row.brief_versions.length - 1),
    shouldSkipPlanForImageEdit,
    showBriefPlan: !shouldSkipPlanForImageEdit,
    sourceGenerationId,
    sourceImageEditInstruction,
  };
}

export function getInitialStep4BriefIntent({
  briefStatus,
  briefVersionCount,
  generationId,
  requestedGenerationId,
  shouldSkipPlanForImageEdit,
  token,
}: Step4InitialBriefIntentInput): Step4InitialBriefIntent {
  if (!token) return 'idle';
  if (shouldSkipPlanForImageEdit) return 'idle';
  if (requestedGenerationId === generationId) return 'idle';
  if (briefStatus === 'approved') return 'idle';
  return briefVersionCount > 0 ? 'mark-handled' : 'request';
}

export function shouldAutoApproveDirectImageEdit({
  briefStatus,
  generationId,
  imageStatus,
  requestedGenerationId,
  shouldSkipPlanForImageEdit,
  token,
}: Step4DirectImageEditAutoApproveInput): boolean {
  if (!token || !shouldSkipPlanForImageEdit) return false;
  if (requestedGenerationId === generationId) return false;
  if (imageStatus !== 'idle') return false;
  return briefStatus !== 'approved';
}

export function shouldPollStep4ImageGeneration(
  imageStatus: ImageGeneration['image_status'],
): boolean {
  return imageStatus === 'queued' || imageStatus === 'running';
}
