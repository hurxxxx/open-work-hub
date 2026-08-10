import { afterEach, describe, expect, it, vi } from 'vitest';

import { getAdminModelRuntimeStatus } from './admin-model-runtime-status-api';

describe('admin model runtime status API', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('requests a fresh platform-admin snapshot', async () => {
    const snapshot = {
      checked_at: '2026-07-13T02:00:00Z',
      status: 'online' as const,
      targets: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getAdminModelRuntimeStatus('token')).resolves.toEqual(
      snapshot,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/model-runtime-status',
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer token' }),
      }),
    );
  });
});
