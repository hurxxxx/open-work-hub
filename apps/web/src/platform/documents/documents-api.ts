import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type SearchDocumentsFilters = Omit<
  ApiSchema<'SearchDocumentsFilters'>,
  'department' | 'doc_type' | 'project'
> & {
  doc_type: string[];
  project: string[];
  department: string[];
};
export type SearchDocumentsPayload = Omit<
  ApiSchema<'SearchDocumentsRequest'>,
  'answer_mode' | 'filters' | 'top_k'
> & {
  filters: SearchDocumentsFilters;
  top_k?: number;
  answer_mode?: ApiSchema<'SearchDocumentsRequest'>['answer_mode'];
};
export type SearchDocumentHit = Omit<
  ApiSchema<'SearchDocumentsResponse'>['hits'][number],
  'next_actions'
> & {
  next_actions: string[];
};
export type GroundedAnswerCitation = ApiSchema<'GroundedAnswer'>['citations'][number];
export type GroundedAnswer = ApiSchema<'GroundedAnswer'>;
export type SearchDocumentsResponse = Omit<
  ApiSchema<'SearchDocumentsResponse'>,
  'filters_applied' | 'grounded_answer' | 'hits'
> & {
  filters_applied: SearchDocumentsFilters;
  hits: SearchDocumentHit[];
  grounded_answer: GroundedAnswer | null;
};

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
