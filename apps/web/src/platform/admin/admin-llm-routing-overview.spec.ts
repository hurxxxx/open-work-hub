import { describe, expect, it } from 'vitest';
import {
  buildLlmWorkloadUpdate,
  selectedModelId,
  type WorkloadDraft,
} from './admin-llm-routing-overview';
import type {
  AdminAiModelSettings,
  AiModelWorkload,
} from './admin-ai-model-settings-api';

const data = { registry_digest: 'digest' } as AdminAiModelSettings;
const workload = {
  app_id: 'chatbot',
  workload_id: 'chatbot',
  effective_route: 'external',
  effective_runtime_adapter: 'hermes',
  local_max_output_tokens: 32768,
  external_max_output_tokens: 65536,
  override: null,
  resolved_routes: [{ provider_id: 'connection-a', model_key: 'model-a' }],
} as AiModelWorkload;
const draft: WorkloadDraft = {
  routeMode: 'external',
  providerId: 'connection-a',
  providerExplicit: false,
  modelIds: {},
  localMaxOutputK: '32',
  externalMaxOutputK: '8',
  runtimeAdapterId: 'hermes',
};

describe('workload inheritance mutations', () => {
  it('previews current inheritance without selecting the first model or using stale resolved metadata', () => {
    const policyData: AdminAiModelSettings = {
      registry_digest: 'digest',
      providers: [
        {
          provider_id: 'connection-a',
          provider_kind: 'openrouter',
          display_name: 'Connection',
          route_mode: 'external',
          credential_kind: 'api_key',
          enabled: true,
          endpoint_url: 'https://openrouter.ai/api/v1',
          endpoint_source: 'custom',
          has_api_key: true,
          default_model_id: 'model-b',
          version: 1,
          updated_at: null,
          preset: '',
          verified: false,
        },
      ],
      provider_kinds: ['openrouter'],
      models: ['model-a', 'model-b'].map((id) => ({
        id,
        provider_id: 'connection-a',
        model_key: id,
        display_name: id,
        capabilities: ['chat'],
        enabled: true,
        source: 'manual',
        discovery_status: 'active',
        last_seen_at: null,
        version: 1,
        updated_at: null,
      })),
      defaults: [
        {
          app_id: 'chatbot',
          route_mode: 'external',
          provider_id: 'connection-a',
          model_id: 'model-a',
          max_output_tokens: null,
          version: 1,
        },
      ],
      workloads: [],
      orphaned_overrides: [],
    };
    const scopedWorkload = { ...workload, required_capabilities: ['chat'] };
    expect(selectedModelId(policyData, scopedWorkload, draft, 'default')).toBe(
      'model-a',
    );
    expect(
      selectedModelId(
        policyData,
        scopedWorkload,
        { ...draft, providerExplicit: true },
        'default',
      ),
    ).toBe('model-b');
    policyData.defaults = [];
    policyData.providers = policyData.providers.map((provider) => ({
      ...provider,
      default_model_id: null,
    }));
    expect(selectedModelId(policyData, scopedWorkload, draft, 'default')).toBe(
      '',
    );
  });
  it('changing only the cap does not freeze inherited connection, model, route or runtime', () => {
    expect(buildLlmWorkloadUpdate(data, workload, draft)).toEqual({
      expected_registry_digest: 'digest',
      expected_version: null,
      route_mode: null,
      provider_id: null,
      model_ids: {},
      local_max_output_tokens: null,
      external_max_output_tokens: 8192,
      runtime_adapter_id: null,
    });
  });
  it('stores an explicitly selected model with its connection', () => {
    expect(
      buildLlmWorkloadUpdate(data, workload, {
        ...draft,
        modelIds: { default: 'selected-model' },
      }),
    ).toMatchObject({
      provider_id: 'connection-a',
      model_ids: { default: 'selected-model' },
    });
  });
  it('preserves existing overrides when saving an unrelated cap', () => {
    const overridden = {
      ...workload,
      override: {
        route_mode: 'external',
        provider_id: 'connection-a',
        model_ids: {},
        version: 3,
        local_max_output_tokens: null,
        external_max_output_tokens: null,
        runtime_adapter_id: null,
        updated_at: null,
      },
    } as AiModelWorkload;
    expect(
      buildLlmWorkloadUpdate(data, overridden, {
        ...draft,
        providerExplicit: true,
      }),
    ).toMatchObject({
      expected_version: 3,
      route_mode: 'external',
      provider_id: 'connection-a',
      model_ids: {},
    });
  });
});
