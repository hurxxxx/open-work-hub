import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type RetrievalQueryPayload = Partial<
  Omit<ApiSchema<'RetrievalQueryRequest'>, 'query'>
> & {
  query: string;
};
export type RetrievalQueryResponse = ApiSchema<'RetrievalQueryResponse'>;
export type RetrievalHit = ApiSchema<'RetrievalHit'>;
export type RetrievalSource = ApiSchema<'RetrievalSourceDescriptor'>;
export type RetrievalSourceListResponse =
  ApiSchema<'RetrievalSourceListResponse'>;
export type RetrievalStrategy = ApiSchema<'RetrievalQueryRequest'>['strategy'];
export type RetrievalAnswerMode =
  ApiSchema<'RetrievalQueryRequest'>['answer_mode'];

export class RetrievalApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function queryWorkspaceRetrieval(
  payload: RetrievalQueryPayload,
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<RetrievalQueryResponse> {
  return apiFetchJsonWithMappedError<RetrievalQueryResponse>(
    rewriteWorkspaceApiPath('/api/v1/retrieval/query', workspaceSlug),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        query: payload.query,
        strategy: payload.strategy ?? 'hybrid',
        sources: payload.sources ?? [],
        source_kinds: payload.source_kinds ?? [],
        filters: payload.filters ?? {},
        top_k: payload.top_k ?? 8,
        answer_mode: payload.answer_mode ?? 'search-only',
        include_binary_hits: payload.include_binary_hits ?? false,
      }),
      signal: options?.signal,
    },
    (error) =>
      new RetrievalApiError(
        error.status,
        extractErrorMessage(error.payload, error.status),
      ),
  );
}

export async function listWorkspaceRetrievalSources(
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<RetrievalSourceListResponse> {
  return apiFetchJsonWithMappedError<RetrievalSourceListResponse>(
    rewriteWorkspaceApiPath('/api/v1/retrieval/sources', workspaceSlug),
    token,
    {
      method: 'GET',
      signal: options?.signal,
    },
    (error) =>
      new RetrievalApiError(
        error.status,
        extractErrorMessage(error.payload, error.status),
      ),
  );
}

function extractErrorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return `Request failed with ${status}.`;
}
