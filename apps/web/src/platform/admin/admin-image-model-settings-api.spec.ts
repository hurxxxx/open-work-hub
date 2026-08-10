import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getAdminImageModelSettings,
  updateAdminImageModelProfile,
  updateAdminImageModelProvider,
} from './admin-image-model-settings-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

const snapshot = {
  registry_digest: 'a'.repeat(64),
  deployment_enabled: true,
  ready: false,
  readiness_code: 'credential_required',
  providers: [],
  profile: {
    active_provider_id: null,
    brief_web_search_enabled: true,
    generation_web_search_enabled: true,
    max_iterations: 10,
    version: 0,
    updated_at: null,
  },
};

function response() {
  return new Response(JSON.stringify(snapshot), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('admin image model settings API', () => {
  it('loads the separate image settings control plane without caching', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal('fetch', fetchMock);

    await getAdminImageModelSettings('token');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/image-model-settings',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('updates provider models and credentials through the image endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal('fetch', fetchMock);

    await updateAdminImageModelProvider('token', 'plugin/image', {
      expected_registry_digest: 'a'.repeat(64),
      expected_version: 0,
      enabled: true,
      endpoint_url: 'https://images.example.test/v1',
      supervisor_model_id: 'planner-1',
      generation_model_id: 'image-1',
      api_key: 'secret',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/image-model-settings/providers/plugin%2Fimage',
      expect.objectContaining({
        method: 'PUT',
        body: expect.stringContaining('"generation_model_id":"image-1"'),
      }),
    );
  });

  it('updates the independent image execution profile', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal('fetch', fetchMock);

    await updateAdminImageModelProfile('token', {
      expected_registry_digest: 'a'.repeat(64),
      expected_version: 0,
      active_provider_id: 'openai',
      brief_web_search_enabled: false,
      generation_web_search_enabled: true,
      max_iterations: 8,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/image-model-settings/profile',
      expect.objectContaining({ method: 'PUT' }),
    );
  });
});
