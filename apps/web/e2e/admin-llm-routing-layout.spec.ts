import { expect, test } from '@playwright/test';
import type { ApiSchema } from '@open-work-hub/contracts/api';

import { FAKE_PLATFORM_ADMIN_USER, stubShellBackend } from './helpers';

const MODEL_SETTINGS_FIXTURE = {
  registry_digest: 'e2e-routing-layout',
  providers: [
    {
      provider_id: 'anthropic',
      provider_kind: 'anthropic',
      preset: '',
      verified: false,
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
      app_id: 'platform',
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
          connection_source: 'global',
          model_source: 'connection',
          output_cap_source: 'global',
          config_source: 'database',
          max_output_tokens: 64 * 1024,
        },
      ],
      override: null,
      management_surface: 'llm_routing',
    },
  ],
  orphaned_overrides: [],
  defaults: [],
  provider_kinds: ['anthropic'],
} satisfies ApiSchema<'AiModelSettingsResponse'>;

test('keeps compact LLM routing dropdown labels inside their controls', async ({
  page,
}) => {
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/admin/ai-model-settings', (route) =>
    route.fulfill({ json: MODEL_SETTINGS_FIXTURE }),
  );

  await page.goto('/admin/llm');

  const dropdowns = page.locator('main table select');
  await expect(dropdowns).toHaveCount(3);

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

test('saves only a workload output cap while preserving model inheritance', async ({
  page,
}) => {
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/admin/ai-model-settings', (route) =>
    route.fulfill({ json: MODEL_SETTINGS_FIXTURE }),
  );
  let saved: Record<string, unknown> | undefined;
  await page.route(
    '**/api/v1/admin/ai-model-settings/workloads/*/route?*',
    (route) => {
      expect(new URL(route.request().url()).searchParams.get('app_id')).toBe(
        'platform',
      );
      saved = route.request().postDataJSON();
      return route.fulfill({ json: MODEL_SETTINGS_FIXTURE });
    },
  );
  await page.goto('/admin/llm');
  const row = page.locator('main tbody tr').first();
  await row.locator('input[type="number"]').fill('8');
  await row.getByRole('button', { name: '저장', exact: true }).click();
  await expect
    .poll(() => saved)
    .toMatchObject({
      provider_id: null,
      model_ids: {},
      route_mode: null,
      external_max_output_tokens: 8192,
      local_max_output_tokens: null,
    });
});

test('allows changing the global external default in the administrator screen', async ({
  page,
}) => {
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/admin/ai-model-settings', (route) =>
    route.fulfill({ json: MODEL_SETTINGS_FIXTURE }),
  );
  let saved: Record<string, unknown> | undefined;
  await page.route(
    '**/api/v1/admin/ai-model-settings/defaults/external?*',
    (route) => {
      expect(new URL(route.request().url()).searchParams.get('app_id')).toBe(
        '',
      );
      saved = route.request().postDataJSON();
      return route.fulfill({ json: MODEL_SETTINGS_FIXTURE });
    },
  );
  await page.goto('/admin/llm');
  const form = page.getByRole('form', { name: '외부 API LLM', exact: true });
  await form
    .getByRole('combobox', { name: '연결', exact: true })
    .selectOption('anthropic');
  await form.locator('select').nth(1).selectOption('model-anthropic');
  await form
    .getByRole('spinbutton', { name: '출력 상한 (K)', exact: true })
    .fill('16');
  await form.getByRole('button', { name: '저장', exact: true }).click();
  await expect
    .poll(() => saved)
    .toMatchObject({
      provider_id: 'anthropic',
      model_id: 'model-anthropic',
      max_output_tokens: 16384,
      expected_version: 0,
      expected_provider_version: 1,
    });
});

test('serializes defaults and workload saves while a full snapshot is pending', async ({
  page,
}) => {
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await page.route('**/api/v1/admin/ai-model-settings', (route) =>
    route.fulfill({ json: MODEL_SETTINGS_FIXTURE }),
  );
  let releaseDefault: (() => void) | undefined;
  let releaseWorkload: (() => void) | undefined;
  const updated = {
    ...MODEL_SETTINGS_FIXTURE,
    defaults: [
      {
        app_id: '',
        route_mode: 'external',
        provider_id: 'anthropic',
        model_id: null,
        max_output_tokens: 16384,
        version: 1,
      },
    ],
  };
  await page.route(
    '**/api/v1/admin/ai-model-settings/defaults/external?*',
    async (route) => {
      await new Promise<void>((resolve) => {
        releaseDefault = resolve;
      });
      await route.fulfill({ json: updated });
    },
  );
  await page.route(
    '**/api/v1/admin/ai-model-settings/workloads/*/route?*',
    async (route) => {
      await new Promise<void>((resolve) => {
        releaseWorkload = resolve;
      });
      await route.fulfill({ json: updated });
    },
  );
  await page.goto('/admin/llm');
  const external = page.getByRole('form', {
    name: '외부 API LLM',
    exact: true,
  });
  const otherDefaultSave = page
    .getByRole('form')
    .first()
    .getByRole('button', { name: '저장', exact: true });
  const row = page.locator('main tbody tr').first();
  const workloadSave = row.getByRole('button', { name: '저장', exact: true });
  await row.locator('input[type="number"]').fill('8');
  await external
    .getByRole('combobox', { name: '연결', exact: true })
    .selectOption('anthropic');
  await external.getByRole('spinbutton').fill('16');
  await external.getByRole('button', { name: '저장', exact: true }).click();
  await expect.poll(() => Boolean(releaseDefault)).toBe(true);
  await expect(workloadSave).toBeDisabled();
  await expect(otherDefaultSave).toBeDisabled();
  if (!releaseDefault) throw new Error('Default request was not received');
  releaseDefault();
  await expect(
    external.getByRole('button', { name: '저장', exact: true }),
  ).toBeEnabled();
  await expect(external.getByRole('spinbutton')).toHaveValue('16');
  await row.locator('input[type="number"]').fill('8');
  await workloadSave.click();
  await expect.poll(() => Boolean(releaseWorkload)).toBe(true);
  await expect(
    external.getByRole('button', { name: '저장', exact: true }),
  ).toBeDisabled();
  await expect(otherDefaultSave).toBeDisabled();
  if (!releaseWorkload) throw new Error('Workload request was not received');
  releaseWorkload();
  await expect(
    external.getByRole('button', { name: '저장', exact: true }),
  ).toBeEnabled();
  await expect(external.getByRole('spinbutton')).toHaveValue('16');
});
