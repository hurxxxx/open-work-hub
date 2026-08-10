import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';
import { getFileDownloadUrl, searchFiles } from './files-api';

describe('Files search API', () => {
  beforeEach(() => {
    resetWorkspaceApiRoutePolicy();
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
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
      'delivery-hub',
      {
        page: 2,
        page_size: 20,
        query: 'release plan',
        strategy: 'hybrid',
      },
      { signal: controller.signal },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/delivery-hub/files/search',
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

    await getFileDownloadUrl('token-1', 'delivery-hub', 'file 1');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/delivery-hub/files/file%201/download',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });
});
