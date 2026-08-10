import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  KeywordSearchResponse,
} from '@/src/platform/search/search-api';
import {
  useRagSearchController,
  type RagSearchControllerClient,
  type RagSearchControllerMessages,
  type RagSearchParamsSetter,
} from './useRagSearchController';

function emptySearchResponse(query = ''): KeywordSearchResponse {
  return {
    query,
    hits: [],
    facets: {
      entity_types: [],
      status: [],
      targets: [],
    },
    total: 0,
    has_more: false,
    next_offset: null,
    trace_id: 'trace-1',
  };
}

function messages(): RagSearchControllerMessages {
  return {
    authMissing: 'auth missing',
    loadFailed: 'load failed',
    sessionExpired: 'session expired',
    workspaceMissing: 'workspace missing',
  };
}

function createClient(): RagSearchControllerClient {
  return {
    search: vi.fn<RagSearchControllerClient['search']>().mockImplementation((payload) =>
      Promise.resolve(emptySearchResponse(payload.query)),
    ),
  };
}

function renderController(options: {
  availableEntityTypes?: string[];
  client?: RagSearchControllerClient;
  searchParams?: string;
} = {}) {
  const client = options.client ?? createClient();
  const logout = vi.fn();
  const searchParams = new URLSearchParams(options.searchParams ?? 'workspace=hq');
  const setSearchParams = vi.fn<RagSearchParamsSetter>();
  const rendered = renderHook(() =>
    useRagSearchController({
      availableEntityTypes: options.availableEntityTypes ?? [
        'doc',
        'meeting',
        'pms_task',
      ],
      client,
      logout,
      messages: messages(),
      searchParams,
      setSearchParams,
      token: 'token-1',
      workspaceId: 'workspace-1',
      workspaceSlug: 'hq',
    }),
  );
  return { ...rendered, client, logout, setSearchParams };
}

describe('useRagSearchController', () => {
  it('does not run an initial search for a workspace-only tool search URL', async () => {
    const { client, result } = renderController();

    await act(async () => {
      await Promise.resolve();
    });

    expect(client.search).not.toHaveBeenCalled();
    expect(result.current.state.response).toBeNull();
    expect(result.current.state.searching).toBe(false);
  });

  it('runs URL search criteria for deep-linked searches', async () => {
    const { client, setSearchParams } = renderController({
      searchParams: 'workspace=hq&q=roadmap',
    });

    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(1));

    expect(client.search).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'roadmap',
        entity_types: [],
        sort: { field: 'relevance', direction: 'desc' },
        limit: 20,
        offset: 0,
        workspace_id: 'workspace-1',
      }),
      'token-1',
      'hq',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(setSearchParams).not.toHaveBeenCalled();
  });

  it('drops stale URL entity filters that are absent from workspace bootstrap', async () => {
    const { client } = renderController({
      availableEntityTypes: ['doc'],
      searchParams:
        'workspace=hq&q=roadmap&type=planner_event&type=doc&type=unknown',
    });

    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(1));

    expect(client.search).toHaveBeenCalledWith(
      expect.objectContaining({ entity_types: ['doc'] }),
      'token-1',
      'hq',
      expect.any(Object),
    );
  });

  it('runs a search after explicit submit from an empty initial URL', async () => {
    const { client, result, setSearchParams } = renderController();

    await act(async () => {
      await Promise.resolve();
    });
    expect(client.search).not.toHaveBeenCalled();

    act(() => {
      result.current.actions.setQueryInput('  roadmap  ');
    });
    await act(async () => {
      result.current.actions.submitSearch();
    });

    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(1));
    expect(client.search).toHaveBeenCalledWith(
      expect.objectContaining({ query: 'roadmap' }),
      'token-1',
      'hq',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await waitFor(() => expect(setSearchParams).toHaveBeenCalledTimes(1));
    const [nextSearchParams, options] = setSearchParams.mock.calls[0];
    expect(nextSearchParams.toString()).toBe('workspace=hq&q=roadmap');
    expect(options).toEqual({ replace: true });
  });
});
