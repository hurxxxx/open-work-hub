import { expect, test } from '@playwright/test';
import type { ApiSchema } from '@open-work-hub/contracts/api';

import { FAKE_PLATFORM_ADMIN_USER, stubShellBackend } from './helpers';

const MODEL_SETTINGS_FIXTURE = {
  registry_digest: 'e2e-routing-layout',
  providers: [
    {
      provider_id: 'anthropic',
      display_name: 'Anthropic',
      route_mode: 'external',
      credential_kind: 'api_key',
      enabled: true,
      endpoint_url: null,
      endpoint_source: 'default',
      has_api_key: true,
      default_model_id: 'model-anthropic',
      version: 1,
      updated_at: null,
    },
  ],
  models: [
    {
      id: 'model-anthropic',
      provider_id: 'anthropic',
      model_key: 'claude-sonnet-4-6',
      display_name: 'Claude Sonnet 4.6',
      capabilities: ['chat'],
      enabled: true,
      source: 'manual',
      discovery_status: 'active',
      last_seen_at: null,
      version: 1,
      updated_at: null,
    },
  ],
  workloads: [
    {
      workload_id: 'e2e_external_workload',
      task_kind: 'e2e_external_workload',
      owner_domain: 'platform',
      app_ids: ['platform'],
      description: 'E2E external workload',
      label_key: '',
      description_key: '',
      execution_kind: 'chat',
      default_runtime_adapter: 'chat_completion',
      effective_runtime_adapter: 'chat_completion',
      allowed_runtime_adapters: ['chat_completion'],
      runtime_adapters: [
        {
          adapter_id: 'chat_completion',
          display_name: 'Chat completion',
          allowed_routes: ['external'],
          allowed_providers: ['anthropic'],
        },
      ],
      default_route: 'external',
      effective_route: 'external',
      allowed_routes: ['external'],
      allowed_providers: ['anthropic'],
      required_capabilities: ['chat'],
      model_roles: ['default'],
      external_data: true,
      local_max_output_tokens: 32 * 1024,
      external_max_output_tokens: 64 * 1024,
      ready: true,
      readiness_code: null,
      resolved_routes: [
        {
          model_role: 'default',
          provider_id: 'anthropic',
          model_key: 'claude-sonnet-4-6',
          route_source: 'default',
          config_source: 'database',
          max_output_tokens: 64 * 1024,
        },
      ],
      override: null,
      management_surface: 'llm_routing',
    },
  ],
  orphaned_overrides: [],
} satisfies ApiSchema<'AiModelSettingsResponse'>;

test('keeps compact LLM routing dropdown labels inside their controls', async ({
  page,
}) => {
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/admin/ai-model-settings', (route) =>
    route.fulfill({ json: MODEL_SETTINGS_FIXTURE }),
  );

  await page.goto('/admin/llm');

  const dropdowns = page.locator('main select');
  await expect(dropdowns).toHaveCount(4);

  const metrics = await dropdowns.evaluateAll((nodes) =>
    nodes.map((node) => {
      const select = node as HTMLSelectElement;
      const style = getComputedStyle(select);
      const probe = document.createElement('span');
      probe.textContent = select.selectedOptions[0]?.textContent ?? 'Hg';
      Object.assign(probe.style, {
        font: style.font,
        lineHeight: style.lineHeight,
        position: 'fixed',
        visibility: 'hidden',
        whiteSpace: 'nowrap',
      });
      document.body.appendChild(probe);
      const textHeight = probe.getBoundingClientRect().height;
      probe.remove();

      return {
        contentHeight:
          select.clientHeight -
          Number.parseFloat(style.paddingTop) -
          Number.parseFloat(style.paddingBottom),
        label: select.getAttribute('aria-label'),
        textHeight,
      };
    }),
  );

  for (const metric of metrics) {
    expect(
      metric.contentHeight,
      `${metric.label ?? 'dropdown'} must leave enough vertical space for its label`,
    ).toBeGreaterThanOrEqual(metric.textHeight);
  }
});
