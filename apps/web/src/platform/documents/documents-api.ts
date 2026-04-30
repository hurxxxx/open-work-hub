import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export interface SearchDocumentsFilters {
  doc_type: string[];
  project: string[];
  department: string[];
}

export interface SearchDocumentsPayload {
  query: string;
  filters: SearchDocumentsFilters;
  top_k?: number;
  answer_mode?: 'search-only' | 'grounded-answer';
}

export interface SearchDocumentHit {
  document_id: string;
  title: string;
  summary: string;
  source_type: string;
  score: number;
  updated: string;
  project: string;
  department: string;
  acl: string;
  owner: string;
  page_reference: string;
  citation: string;
  next_actions: string[];
}

export interface GroundedAnswerCitation {
  document_id: string;
  title: string;
  page_reference: string;
  quote: string;
}

export interface GroundedAnswer {
  summary: string;
  key_points: string[];
  citations: GroundedAnswerCitation[];
  next_actions: string[];
}

export interface SearchDocumentsResponse {
  scenario_id: string;
  query_profile: string;
  filters_applied: SearchDocumentsFilters;
  hits: SearchDocumentHit[];
  next_actions: string[];
  grounded_answer: GroundedAnswer | null;
}

class DocumentsApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function searchDocuments(
  payload: SearchDocumentsPayload,
  token: string,
): Promise<SearchDocumentsResponse> {
  const response = await fetch(rewriteWorkspaceApiPath('/api/v1/search/documents'), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    cache: 'no-store',
  });

  const result = await response.json().catch(() => null);
  if (!response.ok) {
    throw new DocumentsApiError(
      response.status,
      result?.detail ?? `Request failed with ${response.status}.`,
    );
  }

  return result as SearchDocumentsResponse;
}
