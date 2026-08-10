import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';

import {
  queryWorkspaceKeywordSearch,
  SearchApiError,
  type KeywordSearchEntityType,
  type KeywordSearchHit,
  type KeywordSearchPayload,
  type KeywordSearchResponse,
} from '@/src/platform/search/search-api';
import {
  RAG_SEARCH_INITIAL_STATE,
  buildHitKey,
  buildSearchParams,
  draftValue,
  entityTypesKey,
  filterAvailableEntityTypes,
  isEntityType,
  parseSearchParams,
  ragSearchReducer,
  requestedSelectedHitKey,
  selectedHitFromResponse,
  toggleEntityTypeSelection,
  type SearchDraft,
  type SearchSortField,
  type UrlSearchState,
} from './rag-search-view-model';

export interface RagSearchControllerClient {
  search(
    payload: KeywordSearchPayload,
    token: string,
    workspaceSlug: string | null,
    options?: { signal?: AbortSignal },
  ): Promise<KeywordSearchResponse>;
}

export interface RagSearchControllerMessages {
  authMissing: string;
  loadFailed: string;
  sessionExpired: string;
  workspaceMissing: string;
}

export type RagSearchParamsSetter = (
  next: URLSearchParams,
  options?: { replace?: boolean },
) => void;

export interface RagSearchControllerOptions {
  availableEntityTypes: readonly KeywordSearchEntityType[];
  client?: RagSearchControllerClient;
  logout: () => Promise<void> | void;
  messages: RagSearchControllerMessages;
  searchParams: URLSearchParams;
  setSearchParams: RagSearchParamsSetter;
  token: string | null | undefined;
  workspaceId: string | null;
  workspaceSlug: string | null | undefined;
}

export interface RagSearchControllerState {
  error: string | null;
  queryInput: string;
  response: KeywordSearchResponse | null;
  searching: boolean;
  selectedEntityTypes: KeywordSearchEntityType[];
  selectedHit: KeywordSearchHit | null;
  selectedHitKey: string | null;
  sortField: SearchSortField;
  urlSearch: UrlSearchState;
}

export interface RagSearchControllerActions {
  changeSort(nextSort: SearchSortField): void;
  loadMore(): void;
  selectHit(hit: KeywordSearchHit): void;
  setQueryInput(value: string): void;
  submitSearch(): void;
  toggleEntityType(entityType: KeywordSearchEntityType | null): void;
}

export interface RagSearchController {
  actions: RagSearchControllerActions;
  state: RagSearchControllerState;
}

const defaultClient: RagSearchControllerClient = {
  search: queryWorkspaceKeywordSearch,
};

export function useRagSearchController({
  availableEntityTypes,
  client = defaultClient,
  logout,
  messages,
  searchParams,
  setSearchParams,
  token,
  workspaceId,
  workspaceSlug,
}: RagSearchControllerOptions): RagSearchController {
  const urlSearch = useMemo(
    () => parseSearchParams(searchParams),
    [searchParams],
  );
  const urlEntityTypesKey = entityTypesKey(
    filterAvailableEntityTypes(urlSearch.entityTypes, availableEntityTypes),
  );
  const urlEntityTypes = useMemo(
    () => urlEntityTypesKey.split('\u0000').filter(isEntityType),
    [urlEntityTypesKey],
  );
  const urlSortKey = urlSearch.sort;
  const [queryDraft, setQueryDraft] = useState<SearchDraft<string>>(() => ({
    sourceKey: urlSearch.query,
    value: urlSearch.query,
  }));
  const [entityTypesDraft, setEntityTypesDraft] = useState<
    SearchDraft<KeywordSearchEntityType[]>
  >(() => ({
    sourceKey: urlEntityTypesKey,
    value: urlEntityTypes,
  }));
  const [sortDraft, setSortDraft] = useState<SearchDraft<SearchSortField>>(
    () => ({
      sourceKey: urlSortKey,
      value: urlSearch.sort,
    }),
  );
  const [{ response, searching, error }, dispatch] = useReducer(
    ragSearchReducer,
    RAG_SEARCH_INITIAL_STATE,
  );
  const queryInput = draftValue(queryDraft, urlSearch.query, urlSearch.query);
  const selectedEntityTypes = draftValue(
    entityTypesDraft,
    urlEntityTypesKey,
    urlEntityTypes,
  );
  const sortField = draftValue(sortDraft, urlSortKey, urlSearch.sort);
  const activeAbortRef = useRef<AbortController | null>(null);
  const lastSearchSignatureRef = useRef('');
  const requestSequenceRef = useRef(0);
  const queryInputRef = useRef(queryInput);
  const selectedEntityTypesRef = useRef(selectedEntityTypes);
  const sortFieldRef = useRef(sortField);

  queryInputRef.current = queryInput;
  selectedEntityTypesRef.current = selectedEntityTypes;
  sortFieldRef.current = sortField;

  const runSearch = useCallback(
    async (options?: {
      append?: boolean;
      entityTypes?: KeywordSearchEntityType[];
      offset?: number;
      query?: string;
      sort?: SearchSortField;
      syncUrl?: boolean;
    }) => {
      if (!token) {
        dispatch({ type: 'searchFailed', error: messages.authMissing });
        return;
      }
      if (!workspaceSlug) {
        dispatch({ type: 'searchFailed', error: messages.workspaceMissing });
        return;
      }
      const nextQuery = options?.query ?? queryInputRef.current;
      const nextEntityTypes = filterAvailableEntityTypes(
        options?.entityTypes ?? selectedEntityTypesRef.current,
        availableEntityTypes,
      );
      const nextSort = options?.sort ?? sortFieldRef.current;
      const nextOffset = options?.offset ?? 0;
      const sequence = requestSequenceRef.current + 1;
      requestSequenceRef.current = sequence;
      activeAbortRef.current?.abort();
      const controller = new AbortController();
      activeAbortRef.current = controller;

      dispatch({ type: 'searchStarted' });
      try {
        const nextResponse = await client.search(
          {
            workspace_id: workspaceId,
            query: nextQuery.trim(),
            entity_types: nextEntityTypes,
            sort: { field: nextSort, direction: 'desc' },
            limit: 20,
            offset: nextOffset,
          },
          token,
          workspaceSlug,
          { signal: controller.signal },
        );
        if (
          !controller.signal.aborted &&
          requestSequenceRef.current === sequence
        ) {
          dispatch({
            type: 'searchSucceeded',
            response: nextResponse,
            append: Boolean(options?.append),
          });
          if (options?.syncUrl !== false) {
            lastSearchSignatureRef.current = buildSearchSignature({
              token,
              workspaceSlug,
              query: nextQuery.trim(),
              entityTypesKey: entityTypesKey(nextEntityTypes),
              sort: nextSort,
            });
            setSearchParams(
              buildSearchParams({
                workspaceSlug,
                query: nextQuery.trim(),
                entityTypes: nextEntityTypes,
                sort: nextSort,
              }),
              { replace: true },
            );
          }
        }
      } catch (caughtError: unknown) {
        if (controller.signal.aborted || isAbortError(caughtError)) {
          return;
        }
        if (
          caughtError instanceof SearchApiError &&
          caughtError.status === 401
        ) {
          dispatch({ type: 'searchFailed', error: messages.sessionExpired });
          void logout();
          return;
        }
        dispatch({
          type: 'searchFailed',
          error:
            caughtError instanceof Error
              ? caughtError.message
              : messages.loadFailed,
        });
      }
    },
    [
      availableEntityTypes,
      client,
      logout,
      messages.authMissing,
      messages.loadFailed,
      messages.sessionExpired,
      messages.workspaceMissing,
      setSearchParams,
      token,
      workspaceId,
      workspaceSlug,
    ],
  );

  const searchSignature = buildSearchSignature({
    token,
    workspaceSlug,
    query: urlSearch.query,
    entityTypesKey: urlEntityTypesKey,
    sort: urlSearch.sort,
  });
  const hasUrlSearchCriteria =
    Boolean(urlSearch.query) || urlEntityTypes.length > 0;

  useEffect(() => {
    if (!token || !workspaceSlug) {
      return;
    }
    if (lastSearchSignatureRef.current === searchSignature) {
      return;
    }
    lastSearchSignatureRef.current = searchSignature;
    if (!hasUrlSearchCriteria) {
      return;
    }
    void runSearch({
      query: urlSearch.query,
      entityTypes: urlEntityTypes,
      sort: urlSearch.sort,
      syncUrl: false,
    });
  }, [
    hasUrlSearchCriteria,
    runSearch,
    searchSignature,
    token,
    urlEntityTypes,
    urlSearch.query,
    urlSearch.sort,
    workspaceSlug,
  ]);

  useEffect(
    () => () => {
      activeAbortRef.current?.abort();
    },
    [],
  );

  const requestedSelectedKey = requestedSelectedHitKey(urlSearch);
  const selectedHit = useMemo(
    () => selectedHitFromResponse(response, requestedSelectedKey),
    [requestedSelectedKey, response],
  );
  const selectedHitKey = selectedHit ? buildHitKey(selectedHit) : null;

  const setQueryInput = useCallback(
    (value: string) => {
      setQueryDraft({ sourceKey: urlSearch.query, value });
    },
    [urlSearch.query],
  );

  const actions = useMemo<RagSearchControllerActions>(
    () => ({
      changeSort: (nextSort) => {
        setSortDraft({ sourceKey: urlSortKey, value: nextSort });
        void runSearch({ sort: nextSort, syncUrl: true });
      },
      loadMore: () => {
        if (!response) return;
        void runSearch({
          offset: response.next_offset ?? response.hits.length,
          append: true,
          syncUrl: false,
        });
      },
      selectHit: (hit) => {
        const next = new URLSearchParams(searchParams);
        next.set('selected_type', hit.entity_type);
        next.set('selected_id', hit.entity_id);
        setSearchParams(next, { replace: true });
      },
      setQueryInput,
      submitSearch: () => {
        void runSearch({ syncUrl: true });
      },
      toggleEntityType: (entityType) => {
        const nextTypes = toggleEntityTypeSelection(
          selectedEntityTypes,
          entityType,
        );
        setEntityTypesDraft({ sourceKey: urlEntityTypesKey, value: nextTypes });
        void runSearch({ entityTypes: nextTypes, syncUrl: true });
      },
    }),
    [
      response,
      runSearch,
      searchParams,
      selectedEntityTypes,
      setQueryInput,
      setSearchParams,
      urlEntityTypesKey,
      urlSortKey,
    ],
  );

  return {
    actions,
    state: {
      error,
      queryInput,
      response,
      searching,
      selectedEntityTypes,
      selectedHit,
      selectedHitKey,
      sortField,
      urlSearch,
    },
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function buildSearchSignature(input: {
  entityTypesKey: string;
  query: string;
  sort: SearchSortField;
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
}): string {
  return [
    input.token ?? '',
    input.workspaceSlug ?? '',
    input.query,
    input.entityTypesKey,
    input.sort,
  ].join('\u0001');
}
