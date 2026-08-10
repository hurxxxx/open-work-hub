import { afterEach, describe, expect, it, vi } from 'vitest';

import { getAdminDocumentProcessingSnapshot } from './admin-document-processing-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('admin document processing API', () => {
  it('loads the read-only snapshot without a request body', async () => {
    const snapshot = {
      configuration_scope: 'api_environment',
      health_scope: 'api_process',
      worker_health_available: false,
      enabled: false,
      ready: true,
      query_timeout_ms: 210000,
      providers: [],
      ocr: {},
      vision: { workloads: [] },
      embedding: {},
      rerank: {},
      vector_index: {},
      keyword_index: {},
      chunking: {},
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAdminDocumentProcessingSnapshot('token');

    expect(result).toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/document-processing',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(fetchMock.mock.calls[0]?.[1]).not.toHaveProperty('body');
  });
});
