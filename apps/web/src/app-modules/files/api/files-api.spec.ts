import { afterEach, describe, expect, it, vi } from 'vitest';

import { getFileDownloadUrl, searchFiles } from './files-api';

describe('Files search API', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts paged criteria through the Files workspace endpoint with cancellation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          query: 'release plan',
          strategy: 'hybrid',
          page: 2,
          page_size: 20,
          hits: [],
          has_more: false,
          max_ranked_results: 100,
          latency_ms: 3,
          trace_id: null,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();

    await searchFiles(
      'token-1',
      {
        page: 2,
        page_size: 20,
        query: 'release plan',
        strategy: 'hybrid',
      },
      { signal: controller.signal },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/files/search',
      expect.objectContaining({
        body: JSON.stringify({
          page: 2,
          page_size: 20,
          query: 'release plan',
          strategy: 'hybrid',
        }),
        method: 'POST',
        signal: controller.signal,
      }),
    );
  });

  it('gets a fresh signed URL from the existing download endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ url: '/signed/file-1' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getFileDownloadUrl('token-1', 'file 1');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/files/file%201/download',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });
});
