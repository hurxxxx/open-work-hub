import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';

import {
  listWorkspaceRetrievalSources,
  queryWorkspaceRetrieval,
  RetrievalApiError,
  type RetrievalAnswerMode,
  type RetrievalQueryPayload,
  type RetrievalQueryResponse,
  type RetrievalSource,
  type RetrievalSourceListResponse,
  type RetrievalStrategy,
} from '@/src/platform/retrieval/retrieval-api';
import {
  buildRetrievalSearchParams,
  draftValue,
  parseRetrievalSearchParams,
  sourceIdsKey,
  toggleRetrievalSourceSelection,
  type RetrievalSearchDraft,
  type RetrievalTopK,
} from './retrieval-search-view-model';

export interface RetrievalSearchControllerClient {
  listSources(
    token: string,
    workspaceSlug: string | null,
    options?: { signal?: AbortSignal },
  ): Promise<RetrievalSourceListResponse>;
  query(
    payload: RetrievalQueryPayload,
    token: string,
    workspaceSlug: string | null,
    options?: { signal?: AbortSignal },
  ): Promise<RetrievalQueryResponse>;
}

export interface RetrievalSearchControllerMessages {
  authMissing: string;
  loadFailed: string;
  queryRequired: string;
  sessionExpired: string;
  sourcesLoadFailed: string;
  workspaceMissing: string;
}

export type RetrievalSearchParamsSetter = (
  next: URLSearchParams,
  options?: { replace?: boolean },
) => void;

export interface RetrievalSearchControllerOptions {
  client?: RetrievalSearchControllerClient;
  logout: () => Promise<void> | void;
  messages: RetrievalSearchControllerMessages;
  searchParams: URLSearchParams;
  setSearchParams: RetrievalSearchParamsSetter;
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
}

export interface RetrievalSearchControllerState {
  answerMode: RetrievalAnswerMode;
  error: string | null;
  loadingSources: boolean;
  queryInput: string;
  response: RetrievalQueryResponse | null;
  searching: boolean;
  selectedSources: string[];
  sourceError: string | null;
  sources: RetrievalSource[];
  strategy: RetrievalStrategy;
  topK: RetrievalTopK;
}

export interface RetrievalSearchControllerActions {
  clearSources(): void;
  reloadSources(): void;
  setAnswerMode(answerMode: RetrievalAnswerMode): void;
  setQueryInput(value: string): void;
  setStrategy(strategy: RetrievalStrategy): void;
  setTopK(topK: RetrievalTopK): void;
  submitSearch(): void;
  toggleSource(source: string): void;
}

export interface RetrievalSearchController {
  actions: RetrievalSearchControllerActions;
  state: RetrievalSearchControllerState;
}

type RetrievalSearchState = {
  error: string | null;
  loadingSources: boolean;
  response: RetrievalQueryResponse | null;
  searching: boolean;
  sourceError: string | null;
  sources: RetrievalSource[];
};

type RetrievalSearchAction =
  | { type: 'sourcesStarted' }
  | { type: 'sourcesSucceeded'; sources: RetrievalSource[] }
  | { type: 'sourcesFailed'; error: string }
  | { type: 'searchStarted' }
  | { type: 'searchSucceeded'; response: RetrievalQueryResponse }
  | { type: 'searchFailed'; error: string };

const INITIAL_STATE: RetrievalSearchState = {
  error: null,
  loadingSources: false,
  response: null,
  searching: false,
  sourceError: null,
  sources: [],
};

const defaultClient: RetrievalSearchControllerClient = {
  listSources: listWorkspaceRetrievalSources,
  query: queryWorkspaceRetrieval,
};

export function useRetrievalSearchController({
  client = defaultClient,
  logout,
  messages,
  searchParams,
  setSearchParams,
  token,
  workspaceSlug,
}: RetrievalSearchControllerOptions): RetrievalSearchController {
  const urlSearch = useMemo(
    () => parseRetrievalSearchParams(searchParams),
    [searchParams],
  );
  const urlSourceKey = sourceIdsKey(urlSearch.selectedSources);
  const [queryDraft, setQueryDraft] = useState<RetrievalSearchDraft<string>>(
    () => ({ sourceKey: urlSearch.query, value: urlSearch.query }),
  );
  const [strategyDraft, setStrategyDraft] = useState<
    RetrievalSearchDraft<RetrievalStrategy>
  >(() => ({ sourceKey: urlSearch.strategy, value: urlSearch.strategy }));
  const [answerModeDraft, setAnswerModeDraft] = useState<
    RetrievalSearchDraft<RetrievalAnswerMode>
  >(() => ({ sourceKey: urlSearch.answerMode, value: urlSearch.answerMode }));
  const [topKDraft, setTopKDraft] = useState<
    RetrievalSearchDraft<RetrievalTopK>
  >(() => ({ sourceKey: String(urlSearch.topK), value: urlSearch.topK }));
  const [sourcesDraft, setSourcesDraft] = useState<
    RetrievalSearchDraft<string[]>
  >(() => ({ sourceKey: urlSourceKey, value: urlSearch.selectedSources }));
  const [{ error, loadingSources, response, searching, sourceError, sources }, dispatch] =
    useReducer(retrievalSearchReducer, INITIAL_STATE);
  const activeSearchAbortRef = useRef<AbortController | null>(null);
  const activeSourcesAbortRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);
  const lastSearchSignatureRef = useRef('');

  const queryInput = draftValue(queryDraft, urlSearch.query, urlSearch.query);
  const strategy = draftValue(strategyDraft, urlSearch.strategy, urlSearch.strategy);
  const answerMode = draftValue(
    answerModeDraft,
    urlSearch.answerMode,
    urlSearch.answerMode,
  );
  const topK = draftValue(topKDraft, String(urlSearch.topK), urlSearch.topK);
  const selectedSources = draftValue(
    sourcesDraft,
    urlSourceKey,
    urlSearch.selectedSources,
  );

  const queryInputRef = useRef(queryInput);
  const strategyRef = useRef(strategy);
  const answerModeRef = useRef(answerMode);
  const topKRef = useRef(topK);
  const selectedSourcesRef = useRef(selectedSources);

  queryInputRef.current = queryInput;
  strategyRef.current = strategy;
  answerModeRef.current = answerMode;
  topKRef.current = topK;
  selectedSourcesRef.current = selectedSources;

  const loadSources = useCallback(async () => {
    if (!token) {
      dispatch({ type: 'sourcesFailed', error: messages.authMissing });
      return;
    }
    if (!workspaceSlug) {
      dispatch({ type: 'sourcesFailed', error: messages.workspaceMissing });
      return;
    }
    activeSourcesAbortRef.current?.abort();
    const controller = new AbortController();
    activeSourcesAbortRef.current = controller;
    dispatch({ type: 'sourcesStarted' });
    try {
      const result = await client.listSources(token, workspaceSlug, {
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        dispatch({ type: 'sourcesSucceeded', sources: result.sources ?? [] });
      }
    } catch (caughtError: unknown) {
      if (controller.signal.aborted || isAbortError(caughtError)) {
        return;
      }
      dispatch({
        type: 'sourcesFailed',
        error:
          caughtError instanceof Error
            ? caughtError.message
            : messages.sourcesLoadFailed,
      });
    }
  }, [
    client,
    messages.authMissing,
    messages.sourcesLoadFailed,
    messages.workspaceMissing,
    token,
    workspaceSlug,
  ]);

  const runSearch = useCallback(async (options?: {
    answerMode?: RetrievalAnswerMode;
    query?: string;
    selectedSources?: string[];
    strategy?: RetrievalStrategy;
    syncUrl?: boolean;
    topK?: RetrievalTopK;
  }) => {
    if (!token) {
      dispatch({ type: 'searchFailed', error: messages.authMissing });
      return;
    }
    if (!workspaceSlug) {
      dispatch({ type: 'searchFailed', error: messages.workspaceMissing });
      return;
    }
    const nextQuery = (options?.query ?? queryInputRef.current).trim();
    if (!nextQuery) {
      dispatch({ type: 'searchFailed', error: messages.queryRequired });
      return;
    }
    const nextStrategy = options?.strategy ?? strategyRef.current;
    const nextAnswerMode = options?.answerMode ?? answerModeRef.current;
    const nextTopK = options?.topK ?? topKRef.current;
    const nextSources = options?.selectedSources ?? selectedSourcesRef.current;
    const sequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = sequence;
    activeSearchAbortRef.current?.abort();
    const controller = new AbortController();
    activeSearchAbortRef.current = controller;

    dispatch({ type: 'searchStarted' });
    try {
      const nextResponse = await client.query(
        {
          query: nextQuery,
          strategy: nextStrategy,
          answer_mode: nextAnswerMode,
          sources: nextSources,
          top_k: nextTopK,
        },
        token,
        workspaceSlug,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted && requestSequenceRef.current === sequence) {
        dispatch({ type: 'searchSucceeded', response: nextResponse });
        lastSearchSignatureRef.current = buildSearchSignature({
          answerMode: nextAnswerMode,
          query: nextQuery,
          selectedSourcesKey: sourceIdsKey(nextSources),
          strategy: nextStrategy,
          token,
          topK: nextTopK,
          workspaceSlug,
        });
        if (options?.syncUrl !== false) {
          setSearchParams(
            buildRetrievalSearchParams({
              answerMode: nextAnswerMode,
              query: nextQuery,
              selectedSources: nextSources,
              strategy: nextStrategy,
              topK: nextTopK,
              workspaceSlug,
            }),
            { replace: true },
          );
        }
      }
    } catch (caughtError: unknown) {
      if (controller.signal.aborted || isAbortError(caughtError)) {
        return;
      }
      if (caughtError instanceof RetrievalApiError && caughtError.status === 401) {
        dispatch({ type: 'searchFailed', error: messages.sessionExpired });
        void logout();
        return;
      }
      dispatch({
        type: 'searchFailed',
        error:
          caughtError instanceof Error ? caughtError.message : messages.loadFailed,
      });
    }
  }, [
    client,
    logout,
    messages.authMissing,
    messages.loadFailed,
    messages.queryRequired,
    messages.sessionExpired,
    messages.workspaceMissing,
    setSearchParams,
    token,
    workspaceSlug,
  ]);

  const searchSignature = buildSearchSignature({
    answerMode: urlSearch.answerMode,
    query: urlSearch.query,
    selectedSourcesKey: urlSourceKey,
    strategy: urlSearch.strategy,
    token,
    topK: urlSearch.topK,
    workspaceSlug,
  });

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  useEffect(() => {
    if (!token || !workspaceSlug || !urlSearch.query) {
      return;
    }
    if (lastSearchSignatureRef.current === searchSignature) {
      return;
    }
    void runSearch({
      answerMode: urlSearch.answerMode,
      query: urlSearch.query,
      selectedSources: urlSearch.selectedSources,
      strategy: urlSearch.strategy,
      syncUrl: false,
      topK: urlSearch.topK,
    });
  }, [
    runSearch,
    searchSignature,
    token,
    urlSearch.answerMode,
    urlSearch.query,
    urlSearch.selectedSources,
    urlSearch.strategy,
    urlSearch.topK,
    workspaceSlug,
  ]);

  useEffect(
    () => () => {
      activeSearchAbortRef.current?.abort();
      activeSourcesAbortRef.current?.abort();
    },
    [],
  );

  const setQueryInput = useCallback((value: string) => {
    setQueryDraft({ sourceKey: urlSearch.query, value });
  }, [urlSearch.query]);

  const actions = useMemo<RetrievalSearchControllerActions>(
    () => ({
      clearSources: () => {
        setSourcesDraft({ sourceKey: urlSourceKey, value: [] });
      },
      reloadSources: () => {
        void loadSources();
      },
      setAnswerMode: (nextAnswerMode) => {
        setAnswerModeDraft({
          sourceKey: urlSearch.answerMode,
          value: nextAnswerMode,
        });
      },
      setQueryInput,
      setStrategy: (nextStrategy) => {
        setStrategyDraft({ sourceKey: urlSearch.strategy, value: nextStrategy });
      },
      setTopK: (nextTopK) => {
        setTopKDraft({ sourceKey: String(urlSearch.topK), value: nextTopK });
      },
      submitSearch: () => {
        void runSearch({ syncUrl: true });
      },
      toggleSource: (source) => {
        setSourcesDraft({
          sourceKey: urlSourceKey,
          value: toggleRetrievalSourceSelection(selectedSources, source),
        });
      },
    }),
    [
      loadSources,
      runSearch,
      selectedSources,
      setQueryInput,
      urlSearch.answerMode,
      urlSearch.strategy,
      urlSearch.topK,
      urlSourceKey,
    ],
  );

  return {
    actions,
    state: {
      answerMode,
      error,
      loadingSources,
      queryInput,
      response,
      searching,
      selectedSources,
      sourceError,
      sources,
      strategy,
      topK,
    },
  };
}

function retrievalSearchReducer(
  state: RetrievalSearchState,
  action: RetrievalSearchAction,
): RetrievalSearchState {
  switch (action.type) {
    case 'sourcesStarted':
      return { ...state, loadingSources: true, sourceError: null };
    case 'sourcesSucceeded':
      return {
        ...state,
        loadingSources: false,
        sourceError: null,
        sources: action.sources,
      };
    case 'sourcesFailed':
      return { ...state, loadingSources: false, sourceError: action.error };
    case 'searchStarted':
      return { ...state, searching: true, error: null };
    case 'searchSucceeded':
      return {
        ...state,
        searching: false,
        error: null,
        response: action.response,
      };
    case 'searchFailed':
      return { ...state, searching: false, error: action.error };
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function buildSearchSignature(input: {
  answerMode: RetrievalAnswerMode;
  query: string;
  selectedSourcesKey: string;
  strategy: RetrievalStrategy;
  token: string | null | undefined;
  topK: RetrievalTopK;
  workspaceSlug: string | null | undefined;
}): string {
  return [
    input.token ?? '',
    input.workspaceSlug ?? '',
    input.query,
    input.strategy,
    input.answerMode,
    String(input.topK),
    input.selectedSourcesKey,
  ].join('\u0001');
}
