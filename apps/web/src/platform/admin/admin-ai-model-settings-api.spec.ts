import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AdminAiModelSettingsApiError,
  discoverAdminAiModelProviderModels,
  getAdminAiModelSettings,
  groupAiModelWorkloadsByApp,
  isAiModelProviderReady,
  isConfigurableModelRoutingWorkload,
  modelSupportsCapabilities,
  resetAdminAiModelWorkloadRoute,
  updateAdminAiModelWorkloadRoute,
  type AiModelCatalogEntry,
  type AiModelProviderConfig,
  type AdminAiModelSettings,
  type AiModelWorkload,
} from './admin-ai-model-settings-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

function workload(
  workloadId: string,
  appIds: string[],
  overrides: Partial<AiModelWorkload> = {},
): AiModelWorkload {
  return {
    workload_id: workloadId,
    task_kind: workloadId,
    owner_domain: 'ai',
    app_ids: appIds,
    description: '',
    label_key: '',
    description_key: '',
    execution_kind: 'chat',
    default_runtime_adapter: 'chat_completion',
    effective_runtime_adapter: 'chat_completion',
    allowed_runtime_adapters: ['chat_completion'],
    runtime_adapters: [],
    default_route: 'local',
    effective_route: 'local',
    allowed_routes: ['local', 'external'],
    allowed_providers: ['local', 'anthropic'],
    required_capabilities: ['chat'],
    model_roles: ['primary'],
    external_data: false,
    local_max_output_tokens: 32768,
    external_max_output_tokens: 65536,
    ready: true,
    readiness_code: null,
    resolved_routes: [],
    override: null,
    management_surface: 'llm_routing',
    ...overrides,
  };
}

function settings(
  providers: AiModelProviderConfig[],
  workloads: AiModelWorkload[] = [],
): AdminAiModelSettings {
  return {
    registry_digest: 'a'.repeat(64),
    providers,
    models: [],
    workloads,
    orphaned_overrides: [],
  };
}

function provider(
  providerId: string,
  overrides: Partial<AiModelProviderConfig> = {},
): AiModelProviderConfig {
  return {
    provider_id: providerId,
    display_name: providerId,
    route_mode: providerId === 'local' ? 'local' : 'external',
    credential_kind: providerId === 'local' ? 'none' : 'api_key',
    enabled: false,
    endpoint_url: null,
    endpoint_source: 'default',
    has_api_key: false,
    default_model_id: null,
    version: 1,
    updated_at: null,
    ...overrides,
  };
}

describe('admin AI model settings model', () => {
  it('groups registered workloads by every owning app and keeps stable ordering', () => {
    const groups = groupAiModelWorkloadsByApp([
      workload('mail.summarize', ['mail']),
      workload('shared.answer', ['docs', 'mail']),
      workload('platform.health', []),
    ]);

    expect(groups.map((group) => group.appId)).toEqual([
      'docs',
      'mail',
      'platform',
    ]);
    expect(groups[1]?.workloads.map((item) => item.workload_id)).toEqual([
      'mail.summarize',
      'shared.answer',
    ]);
  });

  it('requires every workload capability when filtering models', () => {
    const model: AiModelCatalogEntry = {
      id: 'model-1',
      provider_id: 'local',
      model_key: 'local-model',
      display_name: 'Local model',
      capabilities: ['chat', 'tool_calling'],
      enabled: true,
      source: 'manual',
      discovery_status: 'active',
      last_seen_at: null,
      version: 1,
      updated_at: null,
    };

    expect(modelSupportsCapabilities(model, ['chat'])).toBe(true);
    expect(modelSupportsCapabilities(model, ['chat', 'vision'])).toBe(false);
  });

  it('keeps generative Vision workloads configurable in model routing', () => {
    expect(
      isConfigurableModelRoutingWorkload(workload('chatbot', ['ai'])),
    ).toBe(true);
    expect(
      isConfigurableModelRoutingWorkload(
        workload('docs.attachment_vision', ['docs'], {
          management_surface: 'document_processing',
          required_capabilities: ['vision'],
        }),
      ),
    ).toBe(true);
    expect(
      isConfigurableModelRoutingWorkload(
        workload('document.embedding', ['documents'], {
          management_surface: 'document_processing',
          required_capabilities: ['embedding'],
        }),
      ),
    ).toBe(false);
  });

  it('treats a ready runtime route as authoritative for provider readiness', () => {
    const localProvider = provider('local');
    const data = settings(
      [localProvider],
      [
        workload('docs.answer', ['docs'], {
          resolved_routes: [
            {
              model_role: 'primary',
              provider_id: 'local',
              model_key: 'legacy-local-model',
              route_source: 'default',
              config_source: 'legacy_env',
              max_output_tokens: 32768,
            },
          ],
        }),
      ],
    );

    expect(isAiModelProviderReady(data, localProvider)).toBe(true);
  });

  it('falls back to persisted provider configuration without a runtime route', () => {
    const localProvider = provider('local', {
      enabled: true,
      endpoint_url: 'http://local-llm.test',
    });
    const externalProvider = provider('anthropic', {
      enabled: true,
      endpoint_url: 'https://api.anthropic.com',
      has_api_key: true,
    });
    const disabledProvider = provider('openai');
    const data = settings([localProvider, externalProvider, disabledProvider]);

    expect(isAiModelProviderReady(data, localProvider)).toBe(true);
    expect(isAiModelProviderReady(data, externalProvider)).toBe(true);
    expect(isAiModelProviderReady(data, disabledProvider)).toBe(false);
    expect(isAiModelProviderReady(data, undefined)).toBe(false);
  });

  it('keeps the backend error code so only stale registry conflicts reload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Refresh the settings.' }), {
          status: 409,
          headers: {
            'Content-Type': 'application/json',
            'X-Open-Work-Hub-Error-Code': 'admin.ai_model_registry_changed',
          },
        }),
      ),
    );

    const caught = await getAdminAiModelSettings('token').catch(
      (error: unknown) => error,
    );

    expect(caught).toBeInstanceOf(AdminAiModelSettingsApiError);
    expect(caught).toMatchObject({
      status: 409,
      code: 'admin.ai_model_registry_changed',
    });
  });

  it('sends digest and row version when resetting an override', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          registry_digest: 'a'.repeat(64),
          providers: [],
          models: [],
          workloads: [],
          orphaned_overrides: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await resetAdminAiModelWorkloadRoute('token', 'mail.summarize', {
      expected_registry_digest: 'a'.repeat(64),
      expected_version: 7,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        'expected_registry_digest=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&expected_version=7',
      ),
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('requests provider model discovery with the registry digest', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          registry_digest: 'a'.repeat(64),
          providers: [],
          models: [],
          workloads: [],
          orphaned_overrides: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await discoverAdminAiModelProviderModels(
      'token',
      'anthropic',
      'a'.repeat(64),
    );

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/ai-model-settings/providers/anthropic/discover-models',
      expect.objectContaining({ method: 'POST' }),
    );
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      expected_registry_digest: 'a'.repeat(64),
    });
  });

  it('sends route and output caps as token integers', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          registry_digest: 'a'.repeat(64),
          providers: [],
          models: [],
          workloads: [],
          orphaned_overrides: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await updateAdminAiModelWorkloadRoute('token', 'web-search.answer', {
      expected_registry_digest: 'a'.repeat(64),
      expected_version: null,
      route_mode: 'external',
      provider_id: 'anthropic',
      model_ids: { default: 'model-1' },
      local_max_output_tokens: 32768,
      external_max_output_tokens: 65536,
    });

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      local_max_output_tokens: 32768,
      external_max_output_tokens: 65536,
    });
  });
});
