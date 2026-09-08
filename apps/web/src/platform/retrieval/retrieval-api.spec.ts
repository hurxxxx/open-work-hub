import { afterEach, describe, expect, it, vi } from 'vitest';

import { listRetrievalSources, queryRetrieval } from './retrieval-api';

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('retrieval-api', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('queries the retrieval endpoint through the app API policy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        query: 'release plan',
        strategy: 'hybrid',
        hits: [],
        citations: [],
        methods: [],
        profile: {
          strategy: 'hybrid',
          requested_sources: ['keyword'],
          resolved_sources: ['keyword'],
          methods: [],
          backend_profiles: {},
          degraded_reasons: [],
        },
        grounded_answer: null,
        trace_id: null,
        latency_ms: 0,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await queryRetrieval(
      {
        query: 'release plan',
        sources: ['keyword'],
        top_k: 3,
      },
      'token-1',
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/retrieval/query',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          query: 'release plan',
          strategy: 'hybrid',
          sources: ['keyword'],
          source_kinds: [],
          filters: {},
          top_k: 3,
          answer_mode: 'search-only',
          include_binary_hits: false,
        }),
      }),
    );
  });

  it('lists retrieval sources through the app API policy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ sources: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await listRetrievalSources('token-1');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/retrieval/sources',
      expect.objectContaining({ method: 'GET' }),
    );
  });
});
