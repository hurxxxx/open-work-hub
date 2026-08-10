import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createAdminPlatformApiKey,
  listAdminPlatformApiKeys,
  revealAdminPlatformApiKey,
  revokeAdminPlatformApiKey,
} from './admin-platform-api-keys-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

function response(payload: unknown = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('admin platform API keys API', () => {
  it('lists keys without caching', async () => {
    const payload = { available_scopes: ['hr:read'], items: [] };
    const fetchMock = vi.fn().mockResolvedValue(response(payload));
    vi.stubGlobal('fetch', fetchMock);

    await expect(listAdminPlatformApiKeys('token')).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/api-keys',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('creates a key with its name and selected scopes', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal('fetch', fetchMock);

    await createAdminPlatformApiKey('token', {
      name: 'Health screening',
      scopes: ['hr:read'],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/api-keys',
      expect.objectContaining({
        body: JSON.stringify({
          name: 'Health screening',
          scopes: ['hr:read'],
        }),
        method: 'POST',
      }),
    );
  });

  it('reveals and revokes a key without sending a request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal('fetch', fetchMock);

    await revealAdminPlatformApiKey('token', 'key/1');
    await revokeAdminPlatformApiKey('token', 'key/1');

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/admin/api-keys/key%2F1/reveal',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/admin/api-keys/key%2F1/revoke',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock.mock.calls[0]?.[1]).not.toHaveProperty('body');
    expect(fetchMock.mock.calls[1]?.[1]).not.toHaveProperty('body');
  });
});
