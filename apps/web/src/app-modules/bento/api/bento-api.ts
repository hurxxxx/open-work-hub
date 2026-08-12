import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type BentoHubView = 'all' | 'mine' | 'archived';
export type BentoVisibility = 'personal' | 'workspace';
export type BentoGenerationLanguage = 'auto' | 'ko' | 'en';

export interface BentoDocumentItem {
  id: string;
  workspace_id: string;
  title: string;
  visibility: BentoVisibility;
  version: number;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  can_edit: boolean;
  can_manage: boolean;
}

export interface BentoDocumentDetail extends BentoDocumentItem {
  document_json: string;
}

export interface BentoHubResponse {
  items: BentoDocumentItem[];
  view: BentoHubView;
  page: number;
  page_size: number;
  total: number;
}

export class BentoApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const API_BASE = '/api/v1/bento';

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  try {
    return await apiFetchJson<T>(
      rewriteWorkspaceApiPath(path, workspaceSlug),
      token,
      init,
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new BentoApiError(error.status, error.message);
    }
    throw error;
  }
}

function withQuery(
  path: string,
  params: { view?: BentoHubView; q?: string },
): string {
  const search = new URLSearchParams();
  if (params.view) search.set('view', params.view);
  if (params.q?.trim()) search.set('q', params.q.trim());
  search.set('page_size', '200');
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function listBentoDocuments(
  token: string,
  params: { view?: BentoHubView; q?: string },
  workspaceSlug?: string | null,
): Promise<BentoHubResponse> {
  return request<BentoHubResponse>(
    withQuery(`${API_BASE}/hub`, params),
    token,
    {},
    workspaceSlug,
  );
}

export function createBentoDocument(
  token: string,
  payload: {
    title: string;
    visibility?: BentoVisibility;
    document_json?: string;
  },
  workspaceSlug?: string | null,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items`,
    token,
    { method: 'POST', body: JSON.stringify(payload) },
    workspaceSlug,
  );
}

export function generateBentoDocument(
  token: string,
  payload: {
    prompt: string;
    slide_count?: number;
    language?: BentoGenerationLanguage;
    visibility?: BentoVisibility;
  },
  workspaceSlug?: string | null,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/generate`,
    token,
    { method: 'POST', body: JSON.stringify(payload) },
    workspaceSlug,
  );
}

export function getBentoDocument(
  token: string,
  documentId: string,
  workspaceSlug?: string | null,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}`,
    token,
    {},
    workspaceSlug,
  );
}

export function editBentoDocumentWithAi(
  token: string,
  documentId: string,
  payload: {
    version: number;
    prompt: string;
    language?: BentoGenerationLanguage;
  },
  workspaceSlug?: string | null,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}/ai-edit`,
    token,
    { method: 'POST', body: JSON.stringify(payload) },
    workspaceSlug,
  );
}

export function updateBentoDocument(
  token: string,
  documentId: string,
  payload: {
    version: number;
    title?: string;
    visibility?: BentoVisibility;
    document_json?: string;
  },
  workspaceSlug?: string | null,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify(payload) },
    workspaceSlug,
  );
}

export function archiveBentoDocument(
  token: string,
  documentId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function restoreBentoDocument(
  token: string,
  documentId: string,
  workspaceSlug?: string | null,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}/restore`,
    token,
    { method: 'POST' },
    workspaceSlug,
  );
}

export function permanentlyDeleteBentoDocument(
  token: string,
  documentId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}/permanent`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}
