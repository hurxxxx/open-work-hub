import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';

import {
  listWorkspaceRetrievalSources,
  queryWorkspaceRetrieval,
} from './retrieval-api';

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('retrieval-api', () => {
  beforeEach(() => {
    resetWorkspaceApiRoutePolicy();
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
    vi.unstubAllGlobals();
  });

  it('queries the workspace retrieval endpoint through the workspace path policy', async () => {
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

    await queryWorkspaceRetrieval(
      {
        query: 'release plan',
        sources: ['keyword'],
        top_k: 3,
      },
      'token-1',
      'delivery-hub',
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/delivery-hub/retrieval/query',
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

  it('lists retrieval sources through the workspace path policy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ sources: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await listWorkspaceRetrievalSources('token-1', 'delivery-hub');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/delivery-hub/retrieval/sources',
      expect.objectContaining({ method: 'GET' }),
    );
  });
});
