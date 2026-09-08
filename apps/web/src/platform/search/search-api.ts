import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';

export type KeywordSearchEntityType = string;
export type KeywordSearchHighlight = ApiSchema<'SearchHighlight'>;
export type KeywordSearchSnippet = Omit<
  ApiSchema<'SearchSnippet'>,
  'highlights'
> & {
  highlights: KeywordSearchHighlight[];
};
export type KeywordSearchPerson = ApiSchema<'SearchPerson'>;
export type KeywordSearchTarget = ApiSchema<'SearchTargetRef'>;
type KeywordSearchHitContract =
  ApiSchema<'KeywordSearchResponse'>['hits'][number];
export type KeywordSearchHit = Omit<
  KeywordSearchHitContract,
  'targets' | 'date_markers' | 'metadata' | 'people' | 'snippet'
> & {
  snippet: KeywordSearchSnippet;
  people: KeywordSearchPerson[];
  targets: KeywordSearchTarget[];
  date_markers: Record<string, unknown>;
  metadata: Record<string, unknown>;
};
export type KeywordSearchFacetValue = ApiSchema<'EntityTypeFacet'>;
export type KeywordSearchStatusFacetValue = ApiSchema<'StatusFacet'>;
export type KeywordSearchTargetFacetValue = ApiSchema<'TargetFacet'>;
export type KeywordSearchFacets = Omit<
  ApiSchema<'SearchFacets'>,
  'targets' | 'entity_types' | 'status'
> & {
  entity_types: KeywordSearchFacetValue[];
  status: KeywordSearchStatusFacetValue[];
  targets: KeywordSearchTargetFacetValue[];
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
export type KeywordSearchPayload = Partial<
  Omit<ApiSchema<'KeywordSearchRequest'>, 'query'>
> & {
  query: string;
};

export class SearchApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function queryKeywordSearch(
  payload: KeywordSearchPayload,
  token: string,
  options?: { signal?: AbortSignal },
): Promise<KeywordSearchResponse> {
  return apiFetchJsonWithMappedError<KeywordSearchResponse>(
    '/api/v1/search/query',
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        query: payload.query,
        entity_types: payload.entity_types ?? [],
        people: payload.people ?? { role: 'any', user_ids: [] },
        status_by_type: payload.status_by_type ?? {},
        date_filters: payload.date_filters ?? [],
        target_refs: payload.target_refs ?? [],
        sort: payload.sort ?? { field: 'relevance', direction: 'desc' },
        limit: payload.limit ?? 20,
        offset: payload.offset ?? 0,
      }),
      signal: options?.signal,
    },
    (error) =>
      new SearchApiError(
        error.status,
        extractErrorMessage(error.payload, error.status),
      ),
  );
}

function extractErrorMessage(payload: unknown, status: number): string {
  if (status === 401) {
    return i18n.t('apps:ai.search.sessionExpired');
  }
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return i18n.t('apps:ai.search.loadFailedWithStatus', { status });
}
