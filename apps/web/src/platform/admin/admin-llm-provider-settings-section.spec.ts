import { describe, expect, it } from 'vitest';

import type { AiModelProviderConfig } from './admin-ai-model-settings-api';
import {
  buildLlmProviderUpdate,
  type LlmProviderDraft,
} from './admin-llm-provider-settings-section';

const provider: AiModelProviderConfig = {
  provider_id: 'anthropic',
  display_name: 'Anthropic',
  route_mode: 'external',
  credential_kind: 'api_key',
  enabled: true,
  endpoint_url: 'https://api.anthropic.com',
  endpoint_source: 'default',
  has_api_key: true,
  default_model_id: 'anthropic-claude-sonnet-4-6',
  version: 3,
  updated_at: null,
};

const draft: LlmProviderDraft = {
  enabled: true,
  endpointUrl: 'https://api.anthropic.com',
  defaultModelId: 'anthropic-claude-sonnet-4-6',
  apiKey: '',
  clearApiKey: false,
};

describe('buildLlmProviderUpdate', () => {
  it('omits an empty key so the stored secret is preserved', () => {
    expect(buildLlmProviderUpdate(draft, provider, 'digest')).toEqual({
      expected_registry_digest: 'digest',
      expected_version: 3,
      enabled: true,
      endpoint_url: 'https://api.anthropic.com',
      default_model_id: 'anthropic-claude-sonnet-4-6',
    });
  });

  it('sends only an explicit replacement or clear action', () => {
    expect(
      buildLlmProviderUpdate(
        { ...draft, apiKey: '  replacement-key  ' },
        provider,
        'digest',
      ),
    ).toMatchObject({ api_key: 'replacement-key' });
    expect(
      buildLlmProviderUpdate(
        { ...draft, clearApiKey: true },
        provider,
        'digest',
      ),
    ).toMatchObject({ clear_api_key: true });
  });
});
