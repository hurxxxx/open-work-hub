import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { FileSearchResponse } from '../api/files-api';
import {
  useFileSearchController,
  type FileSearchControllerClient,
  type FileSearchControllerMessages,
  type FileSearchParamsSetter,
} from './useFileSearchController';

function messages(): FileSearchControllerMessages {
  return {
    authMissing: 'auth missing',
    downloadFailed: 'download failed',
    loadFailed: 'load failed',
    queryRequired: 'query required',
    sessionExpired: 'session expired',
  };
}

function response(
  page: number,
  hasMore: boolean,
  query = 'release plan',
): FileSearchResponse {
  return {
    query,
    strategy: 'semantic',
    page,
    page_size: 20,
    hits: [],
    has_more: hasMore,
    max_ranked_results: 100,
    latency_ms: 8,
    trace_id: null,
  };
}

function createClient(): FileSearchControllerClient {
  return {
    download: vi.fn().mockResolvedValue({ url: '/download/file-1' }),
    search: vi
      .fn<FileSearchControllerClient['search']>()
      .mockImplementation((_token, payload) =>
        Promise.resolve(response(payload.page, payload.page === 1)),
      ),
  };
}

function renderController(
  client = createClient(),
  searchParams = 'view=search',
) {
  const setSearchParams = vi.fn<FileSearchParamsSetter>();
  const openDownload = vi.fn();
  const logout = vi.fn();
  const rendered = renderHook(() =>
    useFileSearchController({
      client,
      logout,
      messages: messages(),
      openDownload,
      searchParams: new URLSearchParams(searchParams),
      setSearchParams,
      token: 'token-1',
    }),
  );
  return { ...rendered, client, logout, openDownload, setSearchParams };
}

describe('useFileSearchController', () => {
  it('submits criteria at page one and navigates the bounded result window', async () => {
    const { client, result, setSearchParams } = renderController();

    act(() => {
      result.current.actions.setQueryInput('  release plan  ');
      result.current.actions.setStrategy('semantic');
      result.current.actions.submitSearch();
    });

    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(1));
    expect(client.search).toHaveBeenLastCalledWith(
      'token-1',
      {
        page: 1,
        page_size: 20,
        query: 'release plan',
        strategy: 'semantic',
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await waitFor(() => expect(result.current.state.response?.page).toBe(1));
    expect(setSearchParams.mock.calls[0]?.[0].toString()).toBe(
      'view=search&q=release+plan&strategy=semantic',
    );

    act(() => result.current.actions.nextPage());

    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(2));
    expect(client.search).toHaveBeenLastCalledWith(
      'token-1',
      expect.objectContaining({ page: 2 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await waitFor(() => expect(result.current.state.response?.page).toBe(2));
    expect(setSearchParams.mock.calls[1]?.[0].toString()).toBe(
      'view=search&q=release+plan&strategy=semantic&page=2',
    );
  });

  it('aborts the previous search and ignores its stale response', async () => {
    const pending = new Map<
      string,
      { resolve: (value: FileSearchResponse) => void; signal?: AbortSignal }
    >();
    const client = createClient();
    vi.mocked(client.search).mockImplementation(
      (_token, payload, options) =>
        new Promise((resolve) => {
          pending.set(payload.query, { resolve, signal: options?.signal });
        }),
    );
    const { result } = renderController(client);

    act(() => {
      result.current.actions.setQueryInput('first');
      result.current.actions.submitSearch();
    });
    await waitFor(() => expect(pending.has('first')).toBe(true));

    act(() => {
      result.current.actions.setQueryInput('second');
      result.current.actions.submitSearch();
    });
    await waitFor(() => expect(pending.has('second')).toBe(true));
    expect(pending.get('first')?.signal?.aborted).toBe(true);

    await act(async () => {
      pending.get('second')?.resolve(response(1, false, 'second'));
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(result.current.state.response?.query).toBe('second'),
    );

    await act(async () => {
      pending.get('first')?.resolve(response(1, false, 'first'));
      await Promise.resolve();
    });
    expect(result.current.state.response?.query).toBe('second');
  });

  it('requests a fresh download URL only after the user clicks download', async () => {
    const { client, openDownload, result } = renderController();

    expect(client.download).not.toHaveBeenCalled();
    act(() => result.current.actions.download('file-1'));

    await waitFor(() =>
      expect(client.download).toHaveBeenCalledWith('token-1', 'file-1'),
    );
    await waitFor(() =>
      expect(openDownload).toHaveBeenCalledWith('/download/file-1', 'token-1'),
    );
    expect(result.current.state.busyDownloadId).toBeNull();
  });

  it('runs deep-linked search criteria without rewriting the URL', async () => {
    const client = createClient();
    const { setSearchParams } = renderController(
      client,
      'view=search&q=roadmap&strategy=keyword&page=3',
    );

    await waitFor(() => expect(client.search).toHaveBeenCalledTimes(1));
    expect(client.search).toHaveBeenCalledWith(
      'token-1',
      {
        page: 3,
        page_size: 20,
        query: 'roadmap',
        strategy: 'keyword',
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(setSearchParams).not.toHaveBeenCalled();
  });

  it('does not expose results from the previous account during navigation', async () => {
    const client = createClient();
    vi.mocked(client.search).mockImplementation((token, payload) =>
      Promise.resolve(response(payload.page, false, `${token}:result`)),
    );
    const setSearchParams = vi.fn<FileSearchParamsSetter>();
    const rendered = renderHook(
      ({ searchParams, token }) =>
        useFileSearchController({
          client,
          logout: vi.fn(),
          messages: messages(),
          openDownload: vi.fn(),
          searchParams: new URLSearchParams(searchParams),
          setSearchParams,
          token,
        }),
      {
        initialProps: {
          searchParams: 'view=search&q=roadmap',
          token: 'account-a',
        },
      },
    );

    await waitFor(() =>
      expect(rendered.result.current.state.response?.query).toBe(
        'account-a:result',
      ),
    );

    rendered.rerender({
      searchParams: 'view=search',
      token: 'account-b',
    });

    expect(rendered.result.current.state.response).toBeNull();
  });
});
