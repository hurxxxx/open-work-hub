import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
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
  try {
    return await apiFetchJson<SearchDocumentsResponse>(
      rewriteWorkspaceApiPath('/api/v1/search/documents'),
      token,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new DocumentsApiError(error.status, error.message);
    }
    throw error;
  }
}
