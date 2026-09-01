import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getAdminHermesInventory,
  getAdminHermesResearchSettings,
  updateAdminHermesResearchSource,
} from './admin-hermes-tools-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('admin Hermes tools API', () => {
  it('reads profile tool status and the persisted research policy', async () => {
    const inventory = {
      profile: { id: 'binding-id' },
      capabilities: {},
      toolsets: [],
      mcp_servers: [],
      skills: [],
    };
    const settings = { revision: 1, sources: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(inventory), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(settings), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      getAdminHermesInventory('token', 'binding/id'),
    ).resolves.toEqual(inventory);
    await expect(getAdminHermesResearchSettings('token')).resolves.toEqual(
      settings,
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/admin/hermes/profiles/binding%2Fid/inventory',
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer token' }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/admin/hermes/research-sources',
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer token' }),
      }),
    );
  });

  it('writes one source with optimistic revision control', async () => {
    const settings = { revision: 4, sources: [] };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(settings), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      updateAdminHermesResearchSource('token', 'semantic_scholar', false, 3),
    ).resolves.toEqual(settings);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/hermes/research-sources/semantic_scholar',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({
          Authorization: 'Bearer token',
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify({ enabled: false, expected_revision: 3 }),
      }),
    );
  });
});
