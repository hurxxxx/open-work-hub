import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';

export type BentoHubView = 'all' | 'mine' | 'archived';
export type BentoVisibility = 'personal' | 'company';
export type BentoGenerationLanguage = 'auto' | 'ko' | 'en';

export interface BentoDocumentItem {
  id: string;

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

export type BentoAiJobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export interface BentoAiJob {
  id: string;
  kind: 'create' | 'edit';
  status: BentoAiJobStatus;
  runtime_adapter_id: string;
  stage: string | null;
  progress_percent: number;
  status_message_key: string | null;
  error_code: string | null;
  target_document_id: string | null;
  result_document_id: string | null;
  result_version: number | null;
  cancellable: boolean;
  created_at: string;
  updated_at: string;
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
): Promise<T> {
  try {
    return await apiFetchJson<T>(path, token, init);
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
): Promise<BentoHubResponse> {
  return request<BentoHubResponse>(
    withQuery(`${API_BASE}/hub`, params),
    token,
    {},
  );
}

export function createBentoDocument(
  token: string,
  payload: {
    title: string;
    company_admin_read_acknowledged?: boolean;
    visibility?: BentoVisibility;
    document_json?: string;
  },
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(`${API_BASE}/items`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateBentoDocument(
  token: string,
  payload: {
    prompt: string;
    slide_count?: number;
    language?: BentoGenerationLanguage;
    company_admin_read_acknowledged?: boolean;
    visibility?: BentoVisibility;
  },
): Promise<BentoAiJob> {
  return request<BentoAiJob>(`${API_BASE}/items/generate`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getBentoDocument(
  token: string,
  documentId: string,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}`,
    token,
    {},
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
): Promise<BentoAiJob> {
  return request<BentoAiJob>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}/ai-edit`,
    token,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function listBentoAiJobs(token: string): Promise<BentoAiJob[]> {
  return request<BentoAiJob[]>(`${API_BASE}/ai-jobs`, token, {});
}

export function getBentoAiJob(
  token: string,
  jobId: string,
): Promise<BentoAiJob> {
  return request<BentoAiJob>(
    `${API_BASE}/ai-jobs/${encodeURIComponent(jobId)}`,
    token,
    {},
  );
}

export function cancelBentoAiJob(
  token: string,
  jobId: string,
): Promise<BentoAiJob> {
  return request<BentoAiJob>(
    `${API_BASE}/ai-jobs/${encodeURIComponent(jobId)}/cancel`,
    token,
    { method: 'POST' },
  );
}

export function updateBentoDocument(
  token: string,
  documentId: string,
  payload: {
    version: number;
    title?: string;
    company_admin_read_acknowledged?: boolean;
    visibility?: BentoVisibility;
    document_json?: string;
  },
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}`,
    token,
    { method: 'PATCH', body: JSON.stringify(payload) },
  );
}

export function archiveBentoDocument(
  token: string,
  documentId: string,
): Promise<void> {
  return request<void>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}`,
    token,
    { method: 'DELETE' },
  );
}

export function restoreBentoDocument(
  token: string,
  documentId: string,
): Promise<BentoDocumentDetail> {
  return request<BentoDocumentDetail>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}/restore`,
    token,
    { method: 'POST' },
  );
}

export function permanentlyDeleteBentoDocument(
  token: string,
  documentId: string,
): Promise<void> {
  return request<void>(
    `${API_BASE}/items/${encodeURIComponent(documentId)}/permanent`,
    token,
    { method: 'DELETE' },
  );
}
