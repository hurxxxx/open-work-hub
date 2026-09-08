import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  RetrievalQueryResponse,
  RetrievalSourceListResponse,
} from '@/src/platform/retrieval/retrieval-api';
import {
  useRetrievalSearchController,
  type RetrievalSearchControllerClient,
  type RetrievalSearchControllerMessages,
  type RetrievalSearchParamsSetter,
} from './useRetrievalSearchController';

function messages(): RetrievalSearchControllerMessages {
  return {
    authMissing: 'auth missing',
    loadFailed: 'load failed',
    queryRequired: 'query required',
    sessionExpired: 'session expired',
    sourcesLoadFailed: 'sources failed',
    workspaceMissing: 'workspace missing',
  };
}

function sourcesResponse(): RetrievalSourceListResponse {
  return {
    sources: [
      {
        source: 'keyword',
        label: 'Keyword',
        scope: 'workspace',
        backend: 'keyword_search',
        required_app_ids: [],
        active: true,
        available: true,
        description: '',
      },
      {
        source: 'generic_rag',
        label: 'Workspace RAG',
        scope: 'workspace',
        backend: 'qdrant',
        required_app_ids: ['docs'],
        active: true,
        available: true,
        description: '',
      },
    ],
  };
}

function retrievalResponse(query = ''): RetrievalQueryResponse {
  return {
    query,
    strategy: 'hybrid',
    hits: [],
    citations: [],
    methods: [],
    profile: {
      strategy: 'hybrid',
      requested_sources: [],
      resolved_sources: ['keyword', 'generic_rag'],
      methods: ['keyword', 'rag'],
      backend_profiles: {},
      degraded_reasons: [],
    },
    grounded_answer: null,
    trace_id: 'trace-1',
    latency_ms: 7,
  };
}

function createClient(): RetrievalSearchControllerClient {
  return {
    listSources: vi
      .fn<RetrievalSearchControllerClient['listSources']>()
      .mockResolvedValue(sourcesResponse()),
    query: vi
      .fn<RetrievalSearchControllerClient['query']>()
      .mockImplementation((payload) =>
        Promise.resolve(retrievalResponse(payload.query)),
      ),
  };
}

function renderController(
  options: {
    client?: RetrievalSearchControllerClient;
    reactStrictMode?: boolean;
    searchParams?: string;
  } = {},
) {
  const client = options.client ?? createClient();
  const logout = vi.fn();
  const searchParams = new URLSearchParams(
    options.searchParams ?? 'workspace=hq',
  );
  const setSearchParams = vi.fn<RetrievalSearchParamsSetter>();
  const rendered = renderHook(
    () =>
      useRetrievalSearchController({
        client,
        logout,
        messages: messages(),
        searchParams,
        setSearchParams,
        token: 'token-1',
      }),
    { reactStrictMode: options.reactStrictMode },
  );
  return { ...rendered, client, logout, setSearchParams };
}

describe('useRetrievalSearchController', () => {
  it('loads source catalog without running a query for workspace-only URLs', async () => {
    const { client, result } = renderController();

    await waitFor(() => expect(client.listSources).toHaveBeenCalledTimes(1));

    expect(client.query).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.state.sources).toHaveLength(2));
    expect(result.current.state.response).toBeNull();
  });

  it('runs deep-linked retrieval criteria without rewriting the URL', async () => {
    const { client, setSearchParams } = renderController({
      searchParams: 'q=release&strategy=semantic&source=generic_rag&top_k=12',
    });

    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(1));

    expect(client.query).toHaveBeenCalledWith(
      expect.objectContaining({
        answer_mode: 'search-only',
        query: 'release',
        sources: ['generic_rag'],
        strategy: 'semantic',
        top_k: 12,
      }),
      'token-1',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(setSearchParams).not.toHaveBeenCalled();
  });

  it('retries a deep-linked search after StrictMode aborts the first effect pass', async () => {
    let queryCalls = 0;
    const client = createClient();
    vi.mocked(client.query).mockImplementation((payload, _token, options) => {
      queryCalls += 1;
      if (queryCalls === 1) {
        return new Promise((_, reject) => {
          options?.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          );
        });
      }
      return Promise.resolve(retrievalResponse(payload.query));
    });
    const { result } = renderController({
      client,
      reactStrictMode: true,
      searchParams: 'q=release',
    });

    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.state.searching).toBe(false));
    expect(result.current.state.response?.query).toBe('release');
  });

  it('submits explicit search criteria and syncs URL params', async () => {
    const { client, result, setSearchParams } = renderController();

    await waitFor(() => expect(client.listSources).toHaveBeenCalledTimes(1));
    act(() => {
      result.current.actions.setQueryInput('  release plan  ');
      result.current.actions.setStrategy('graph_hybrid');
      result.current.actions.setAnswerMode('grounded-answer');
      result.current.actions.setTopK(20);
      result.current.actions.toggleSource('keyword');
    });

    await act(async () => {
      result.current.actions.submitSearch();
    });

    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(1));
    expect(client.query).toHaveBeenCalledWith(
      expect.objectContaining({
        answer_mode: 'grounded-answer',
        query: 'release plan',
        sources: ['keyword'],
        strategy: 'graph_hybrid',
        top_k: 20,
      }),
      'token-1',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await waitFor(() => expect(setSearchParams).toHaveBeenCalledTimes(1));
    const [nextSearchParams, options] = setSearchParams.mock.calls[0];
    expect(nextSearchParams.toString()).toBe(
      'q=release+plan&strategy=graph_hybrid&answer_mode=grounded-answer&top_k=20&source=keyword',
    );
    expect(options).toEqual({ replace: true });
  });
});
