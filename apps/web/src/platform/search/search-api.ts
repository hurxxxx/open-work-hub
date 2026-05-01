import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type KeywordSearchEntityType = ApiSchema<'SearchEntityType'>;
export type KeywordSearchHighlight = ApiSchema<'SearchHighlight'>;
export type KeywordSearchSnippet = Omit<ApiSchema<'SearchSnippet'>, 'highlights'> & {
  highlights: KeywordSearchHighlight[];
};
export type KeywordSearchPerson = ApiSchema<'SearchPerson'>;
export type KeywordSearchContainer = ApiSchema<'SearchContainerRef'>;
type KeywordSearchHitContract = ApiSchema<'KeywordSearchResponse'>['hits'][number];
export type KeywordSearchHit = Omit<
  KeywordSearchHitContract,
  'containers' | 'date_markers' | 'metadata' | 'people' | 'snippet'
> & {
  snippet: KeywordSearchSnippet;
  people: KeywordSearchPerson[];
  containers: KeywordSearchContainer[];
  date_markers: Record<string, unknown>;
  metadata: Record<string, unknown>;
};
export type KeywordSearchFacetValue = ApiSchema<'EntityTypeFacet'>;
export type KeywordSearchStatusFacetValue = ApiSchema<'StatusFacet'>;
export type KeywordSearchContainerFacetValue = ApiSchema<'ContainerFacet'>;
export type KeywordSearchFacets = Omit<ApiSchema<'SearchFacets'>, 'containers' | 'entity_types' | 'status'> & {
  entity_types: KeywordSearchFacetValue[];
  status: KeywordSearchStatusFacetValue[];
  containers: KeywordSearchContainerFacetValue[];
};
export type KeywordSearchResponse = Omit<
  ApiSchema<'KeywordSearchResponse'>,
  'facets' | 'hits' | 'next_offset' | 'trace_id'
> & {
  hits: KeywordSearchHit[];
  facets: KeywordSearchFacets;
  next_offset: number | null;
  trace_id: string | null;
};
export type KeywordSearchPayload = Partial<Omit<ApiSchema<'KeywordSearchRequest'>, 'query'>> & {
  query: string;
};

export class SearchApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function queryWorkspaceKeywordSearch(
  payload: KeywordSearchPayload,
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<KeywordSearchResponse> {
  try {
    return await apiFetchJson<KeywordSearchResponse>(
      rewriteWorkspaceApiPath('/api/v1/search/query', workspaceSlug),
      token,
      {
        method: 'POST',
        body: JSON.stringify({
          query: payload.query,
          workspace_id: payload.workspace_id ?? null,
          entity_types: payload.entity_types ?? [],
          people: payload.people ?? { role: 'any', user_ids: [] },
          status_by_type: payload.status_by_type ?? {},
          date_filters: payload.date_filters ?? [],
          container_refs: payload.container_refs ?? [],
          sort: payload.sort ?? { field: 'relevance', direction: 'desc' },
          limit: payload.limit ?? 20,
          offset: payload.offset ?? 0,
        }),
        signal: options?.signal,
      },
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new SearchApiError(error.status, extractErrorMessage(error.payload, error.status));
    }
    throw error;
  }
}

function extractErrorMessage(payload: unknown, status: number): string {
  if (status === 401) {
    return '세션이 만료되었습니다. 다시 로그인해주세요.';
  }
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return `검색 결과를 불러오지 못했습니다. (${status})`;
}
