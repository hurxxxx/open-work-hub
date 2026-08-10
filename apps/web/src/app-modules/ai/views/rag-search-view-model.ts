import type {
  KeywordSearchEntityType,
  KeywordSearchHit,
  KeywordSearchResponse,
} from '@/src/platform/search/search-api';

export type SearchSortField = 'relevance' | 'updated_at';

export type UrlSearchState = {
  workspaceSlug: string | null;
  query: string;
  entityTypes: KeywordSearchEntityType[];
  sort: SearchSortField;
  selectedType: KeywordSearchEntityType | null;
  selectedId: string | null;
};

export type SearchDraft<TValue> = {
  sourceKey: string;
  value: TValue;
};

export type RagSearchState = {
  response: KeywordSearchResponse | null;
  searching: boolean;
  error: string | null;
};

export type RagSearchAction =
  | { type: 'searchStarted' }
  | {
      type: 'searchSucceeded';
      response: KeywordSearchResponse;
      append: boolean;
    }
  | { type: 'searchFailed'; error: string };

export const RAG_SEARCH_INITIAL_STATE: RagSearchState = {
  response: null,
  searching: false,
  error: null,
};

export function ragSearchReducer(
  state: RagSearchState,
  action: RagSearchAction,
): RagSearchState {
  switch (action.type) {
    case 'searchStarted':
      return {
        ...state,
        searching: true,
        error: null,
      };
    case 'searchSucceeded':
      return {
        ...state,
        response:
          action.append && state.response
            ? {
                ...action.response,
                hits: [...state.response.hits, ...action.response.hits],
              }
            : action.response,
        searching: false,
        error: null,
      };
    case 'searchFailed':
      return {
        ...state,
        searching: false,
        error: action.error,
      };
  }
}

export function parseSearchParams(
  searchParams: URLSearchParams,
): UrlSearchState {
  const selectedType = searchParams.get('selected_type');
  return {
    workspaceSlug: searchParams.get('workspace')?.trim() || null,
    query: searchParams.get('q')?.trim() || '',
    entityTypes: searchParams.getAll('type').filter(isEntityType),
    sort:
      searchParams.get('sort') === 'updated_at' ? 'updated_at' : 'relevance',
    selectedType:
      selectedType && isEntityType(selectedType) ? selectedType : null,
    selectedId: searchParams.get('selected_id')?.trim() || null,
  };
}

export function buildSearchParams(input: {
  workspaceSlug: string;
  query: string;
  entityTypes: KeywordSearchEntityType[];
  sort: SearchSortField;
}): URLSearchParams {
  const params = new URLSearchParams();
  params.set('workspace', input.workspaceSlug);
  if (input.query) {
    params.set('q', input.query);
  }
  for (const entityType of input.entityTypes) {
    params.append('type', entityType);
  }
  if (input.sort !== 'relevance') {
    params.set('sort', input.sort);
  }
  return params;
}

export function entityTypesKey(
  entityTypes: readonly KeywordSearchEntityType[],
): string {
  return entityTypes.join('\u0000');
}

export function filterAvailableEntityTypes(
  entityTypes: readonly KeywordSearchEntityType[],
  availableEntityTypes: readonly KeywordSearchEntityType[],
): KeywordSearchEntityType[] {
  const available = new Set(availableEntityTypes);
  return [...new Set(entityTypes)].filter((entityType) =>
    available.has(entityType),
  );
}

export function draftValue<TValue>(
  draft: SearchDraft<TValue>,
  sourceKey: string,
  fallback: TValue,
): TValue {
  return draft.sourceKey === sourceKey ? draft.value : fallback;
}

export function toggleEntityTypeSelection(
  selectedEntityTypes: readonly KeywordSearchEntityType[],
  entityType: KeywordSearchEntityType | null,
): KeywordSearchEntityType[] {
  if (entityType === null) {
    return [];
  }
  return selectedEntityTypes.includes(entityType)
    ? selectedEntityTypes.filter((item) => item !== entityType)
    : [...selectedEntityTypes, entityType];
}

export function requestedSelectedHitKey(
  urlSearch: Pick<UrlSearchState, 'selectedId' | 'selectedType'>,
): string | null {
  return urlSearch.selectedType && urlSearch.selectedId
    ? buildHitKeyFromParts(urlSearch.selectedType, urlSearch.selectedId)
    : null;
}

export function selectedHitFromResponse(
  response: KeywordSearchResponse | null,
  requestedSelectedKey: string | null,
): KeywordSearchHit | null {
  if (!response?.hits.length) {
    return null;
  }
  if (requestedSelectedKey) {
    return (
      response.hits.find((hit) => buildHitKey(hit) === requestedSelectedKey) ??
      response.hits[0] ??
      null
    );
  }
  return response.hits[0] ?? null;
}

export function buildHitKey(hit: KeywordSearchHit): string {
  return buildHitKeyFromParts(hit.entity_type, hit.entity_id);
}

export function buildHitKeyFromParts(
  entityType: KeywordSearchEntityType,
  entityId: string,
): string {
  return `${entityType}:${entityId}`;
}

export function isEntityType(value: string): value is KeywordSearchEntityType {
  return /^[A-Za-z0-9_.:-]{1,64}$/.test(value);
}
