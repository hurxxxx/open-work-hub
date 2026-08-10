import { describe, expect, it } from 'vitest';

import {
  buildImageProfileUpdate,
  buildImageProviderUpdate,
} from './admin-image-model-settings-section';

describe('admin image model settings model', () => {
  it('does not send a blank replacement key and preserves explicit model names', () => {
    expect(
      buildImageProviderUpdate(
        {
          enabled: true,
          endpointUrl: ' https://api.openai.com/v1 ',
          supervisorModelId: ' supervisor-model ',
          generationModelId: ' image-model ',
          apiKey: ' ',
          clearApiKey: false,
        },
        {
          provider_id: 'openai',
          display_name: 'OpenAI',
          route_mode: 'external',
          credential_kind: 'api_key',
          enabled: false,
          endpoint_url: 'https://api.openai.com/v1',
          endpoint_source: 'default',
          has_api_key: true,
          supervisor_model_id: null,
          generation_model_id: null,
          ready: false,
          readiness_code: 'supervisor_model_required',
          version: 3,
          updated_at: null,
        },
        'a'.repeat(64),
      ),
    ).toEqual({
      expected_registry_digest: 'a'.repeat(64),
      expected_version: 3,
      enabled: true,
      endpoint_url: 'https://api.openai.com/v1',
      supervisor_model_id: 'supervisor-model',
      generation_model_id: 'image-model',
    });
  });

  it('keeps image agent options in the image profile contract', () => {
    expect(
      buildImageProfileUpdate(
        {
          active_provider_id: 'openai',
          brief_web_search_enabled: false,
          generation_web_search_enabled: true,
          max_iterations: 7,
          version: 2,
          updated_at: null,
        },
        'b'.repeat(64),
      ),
    ).toMatchObject({
      active_provider_id: 'openai',
      brief_web_search_enabled: false,
      generation_web_search_enabled: true,
      max_iterations: 7,
      expected_version: 2,
    });
  });
});
