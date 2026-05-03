import { ApiRequestError, apiFetchJson, jsonHeaders } from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type ImageBriefStatus = 'drafting' | 'ready' | 'approved';
export type ImageGenerationStatus = 'idle' | 'queued' | 'running' | 'succeeded' | 'failed';
export type ReferenceImageRole = 'style' | 'composition' | 'content';
export type ContextRefKind = 'meeting' | 'task' | 'doc';

export interface StylePayload {
  chips: string[];
  palette: string;
  background: string;
  quality: string;
}

export interface LayoutPayload {
  layout_id: string;
  aspect: string;
}

export interface DetailsPayload {
  audience: string;
  notes: string;
}

export interface ContextRefSnapshot {
  title?: string;
  summary?: string;
  [key: string]: unknown;
}

export interface ContextRef {
  kind: ContextRefKind;
  id: string;
  snapshot?: ContextRefSnapshot;
}

export interface ReferenceImageRef {
  storage_key: string;
  role: ReferenceImageRole;
  content_type: string;
  size_bytes: number;
  original_name: string;
}

export interface BriefVersion {
  text: string;
  created_at: string;
  edit_instruction: string | null;
}

export interface ImageGeneration {
  id: string;
  workspace_id: string;
  owner_id: string;
  use_case: string;
  use_case_other: string;
  style: StylePayload;
  layout: LayoutPayload;
  details: DetailsPayload;
  context_refs: ContextRef[];
  reference_image_keys: ReferenceImageRef[];
  brief_versions: BriefVersion[];
  brief_status: ImageBriefStatus;
  image_status: ImageGenerationStatus;
  image_storage_key: string | null;
  image_model: string | null;
  agent_trace_id: string | null;
  failure_reason: string | null;
  approved_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ImageGenerationListResponse {
  items: ImageGeneration[];
  next_cursor: string | null;
}

export interface ImageGenerationCreatePayload {
  use_case?: string;
  use_case_other?: string;
  style?: Partial<StylePayload>;
  layout?: Partial<LayoutPayload>;
  details?: Partial<DetailsPayload>;
  context_refs?: ContextRef[];
}

export interface ImageGenerationPatchPayload {
  use_case?: string;
  use_case_other?: string;
  style?: Partial<StylePayload>;
  layout?: Partial<LayoutPayload>;
  details?: Partial<DetailsPayload>;
  context_refs?: ContextRef[];
}

export interface ImageDownloadResponse {
  url: string;
  expires_at: string;
}

export class ImageWizardApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJson<T>(rewriteWorkspaceApiPath(path, workspaceSlug), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new ImageWizardApiError(error.status, error.message);
    }
    throw error;
  }
}

export function createImageGeneration(
  token: string,
  workspaceSlug: string,
  payload: ImageGenerationCreatePayload,
): Promise<ImageGeneration> {
  return request<ImageGeneration>('/api/v1/images/generations', token, workspaceSlug, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function patchImageGeneration(
  token: string,
  workspaceSlug: string,
  generationId: string,
  payload: ImageGenerationPatchPayload,
): Promise<ImageGeneration> {
  return request<ImageGeneration>(
    `/api/v1/images/generations/${generationId}`,
    token,
    workspaceSlug,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function getImageGeneration(
  token: string,
  workspaceSlug: string,
  generationId: string,
): Promise<ImageGeneration> {
  return request<ImageGeneration>(
    `/api/v1/images/generations/${generationId}`,
    token,
    workspaceSlug,
  );
}

export function listImageGenerations(
  token: string,
  workspaceSlug: string,
  options: {
    limit?: number;
    image_status?: ImageGenerationStatus;
    use_case?: string;
  } = {},
): Promise<ImageGenerationListResponse> {
  const params = new URLSearchParams();
  if (options.limit) params.set('limit', String(options.limit));
  if (options.image_status) params.set('image_status', options.image_status);
  if (options.use_case) params.set('use_case', options.use_case);
  const query = params.toString();
  return request<ImageGenerationListResponse>(
    `/api/v1/images/generations${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function deleteImageGeneration(
  token: string,
  workspaceSlug: string,
  generationId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/images/generations/${generationId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export async function uploadReferenceImage(
  token: string,
  workspaceSlug: string,
  generationId: string,
  file: File,
  role: ReferenceImageRole,
): Promise<ReferenceImageRef> {
  const form = new FormData();
  form.append('file', file);
  form.append('role', role);
  const path = rewriteWorkspaceApiPath(
    `/api/v1/images/generations/${generationId}/reference-images`,
    workspaceSlug,
  );
  const response = await fetch(path, {
    method: 'POST',
    body: form,
    headers: jsonHeaders(token),
    cache: 'no-store',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message =
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Upload failed with ${response.status}.`;
    throw new ImageWizardApiError(response.status, message);
  }
  return (await response.json()) as ReferenceImageRef;
}

export function deleteReferenceImage(
  token: string,
  workspaceSlug: string,
  generationId: string,
  storageKey: string,
): Promise<void> {
  const params = new URLSearchParams({ storage_key: storageKey });
  return request<void>(
    `/api/v1/images/generations/${generationId}/reference-images?${params.toString()}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function generateBrief(
  token: string,
  workspaceSlug: string,
  generationId: string,
  options: { editInstruction?: string } = {},
): Promise<BriefVersion> {
  return request<BriefVersion>(
    `/api/v1/images/generations/${generationId}/brief`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify({
        edit_instruction: options.editInstruction || null,
      }),
    },
  );
}

export function approveImageGeneration(
  token: string,
  workspaceSlug: string,
  generationId: string,
): Promise<ImageGeneration> {
  return request<ImageGeneration>(
    `/api/v1/images/generations/${generationId}/approve`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  );
}

export function getImageDownloadUrl(
  token: string,
  workspaceSlug: string,
  generationId: string,
): Promise<ImageDownloadResponse> {
  return request<ImageDownloadResponse>(
    `/api/v1/images/generations/${generationId}/download`,
    token,
    workspaceSlug,
  );
}
