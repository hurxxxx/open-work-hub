import { jsonBodyHeaders, jsonHeaders } from '@/src/platform/api/client';

export type AiModelRoute = 'local' | 'external';

export interface AiModelProviderConfig {
  provider_id: string;
  display_name: string;
  route_mode: AiModelRoute;
  credential_kind: 'none' | 'api_key';
  enabled: boolean;
  endpoint_url: string | null;
  endpoint_source: 'default' | 'custom';
  has_api_key: boolean;
  default_model_id: string | null;
  version: number;
  updated_at: string | null;
}

export interface AiModelCatalogEntry {
  id: string;
  provider_id: string;
  model_key: string;
  display_name: string;
  capabilities: string[];
  enabled: boolean;
  source: 'manual' | 'discovered';
  discovery_status: 'active' | 'stale';
  last_seen_at: string | null;
  version: number;
  updated_at: string | null;
}

export interface AiModelRouteOverride {
  route_mode: AiModelRoute;
  provider_id: string | null;
  model_ids: Record<string, string>;
  local_max_output_tokens: number | null;
  external_max_output_tokens: number | null;
  version: number;
  updated_at: string | null;
}

export interface AiModelResolvedRoute {
  model_role: string;
  provider_id: string;
  model_key: string;
  route_source: 'default' | 'override';
  config_source: 'database' | 'legacy_env' | 'database_with_legacy_env';
  max_output_tokens: number;
}

export interface AiModelWorkload {
  workload_id: string;
  task_kind: string;
  owner_domain: string;
  app_ids: string[];
  description: string;
  label_key: string;
  description_key: string;
  execution_kind: string;
  default_route: AiModelRoute;
  effective_route: AiModelRoute;
  allowed_routes: AiModelRoute[];
  allowed_providers: string[];
  required_capabilities: string[];
  model_roles: string[];
  external_data: boolean;
  local_max_output_tokens: number;
  external_max_output_tokens: number;
  ready: boolean;
  readiness_code: string | null;
  resolved_routes: AiModelResolvedRoute[];
  override: AiModelRouteOverride | null;
  management_surface: 'llm_routing' | 'document_processing';
}

export interface AiModelOrphanedOverride {
  workload_id: string;
  route_mode: AiModelRoute;
  provider_id: string | null;
  model_ids: Record<string, string>;
  local_max_output_tokens: number | null;
  external_max_output_tokens: number | null;
  version: number;
  updated_at: string | null;
}

export interface AdminAiModelSettings {
  registry_digest: string;
  providers: AiModelProviderConfig[];
  models: AiModelCatalogEntry[];
  workloads: AiModelWorkload[];
  orphaned_overrides: AiModelOrphanedOverride[];
}

export function isAiModelProviderReady(
  data: AdminAiModelSettings,
  provider: AiModelProviderConfig | undefined,
): boolean {
  if (!provider) return false;
  const hasReadyRuntimeRoute = data.workloads.some(
    (workload) =>
      workload.ready &&
      workload.resolved_routes.some(
        (route) => route.provider_id === provider.provider_id,
      ),
  );
  if (hasReadyRuntimeRoute) return true;
  if (!provider.enabled) return false;
  if (!provider.endpoint_url) return false;
  return provider.credential_kind === 'none' || provider.has_api_key;
}

export interface AiModelProviderUpdate {
  expected_registry_digest: string;
  expected_version: number | null;
  enabled: boolean;
  endpoint_url: string | null;
  default_model_id: string | null;
  api_key?: string;
  clear_api_key?: boolean;
}

export interface AiModelCatalogCreate {
  expected_registry_digest: string;
  provider_id: string;
  model_key: string;
  display_name: string;
  capabilities: string[];
  enabled: boolean;
}

export interface AiModelCatalogUpdate {
  expected_registry_digest: string;
  expected_version: number;
  model_key: string;
  display_name: string;
  capabilities: string[];
  enabled: boolean;
}

export interface AiModelRouteUpdate {
  expected_registry_digest: string;
  expected_version: number | null;
  route_mode: AiModelRoute;
  provider_id: string | null;
  model_ids: Record<string, string>;
  local_max_output_tokens: number | null;
  external_max_output_tokens: number | null;
}

export class AdminAiModelSettingsApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code: string | null = null,
  ) {
    super(message);
  }
}

async function request<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    const response = await fetch(path, {
      ...init,
      cache: 'no-store',
      headers: {
        ...(init.body ? jsonBodyHeaders(token) : jsonHeaders(token)),
        ...(init.headers ?? {}),
      },
    });
    const payload =
      response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      throw new AdminAiModelSettingsApiError(
        response.status,
        payload &&
        typeof payload === 'object' &&
        'detail' in payload &&
        typeof payload.detail === 'string'
          ? payload.detail
          : 'AI model settings request failed.',
        response.headers.get('X-Open-Work-Hub-Error-Code'),
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof AdminAiModelSettingsApiError) {
      throw error;
    }
    throw new AdminAiModelSettingsApiError(
      0,
      'AI model settings request failed.',
    );
  }
}

export function getAdminAiModelSettings(
  token: string,
): Promise<AdminAiModelSettings> {
  return request<AdminAiModelSettings>(
    token,
    '/api/v1/admin/ai-model-settings',
  );
}

export function updateAdminAiModelProvider(
  token: string,
  providerId: string,
  payload: AiModelProviderUpdate,
): Promise<AdminAiModelSettings> {
  return request<AdminAiModelSettings>(
    token,
    `/api/v1/admin/ai-model-settings/providers/${encodeURIComponent(providerId)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  );
}

export function discoverAdminAiModelProviderModels(
  token: string,
  providerId: string,
  expectedRegistryDigest: string,
): Promise<AdminAiModelSettings> {
  return request<AdminAiModelSettings>(
    token,
    `/api/v1/admin/ai-model-settings/providers/${encodeURIComponent(providerId)}/discover-models`,
    {
      method: 'POST',
      body: JSON.stringify({
        expected_registry_digest: expectedRegistryDigest,
      }),
    },
  );
}

export function createAdminAiModel(
  token: string,
  payload: AiModelCatalogCreate,
): Promise<AdminAiModelSettings> {
  return request<AdminAiModelSettings>(
    token,
    '/api/v1/admin/ai-model-settings/models',
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function updateAdminAiModel(
  token: string,
  modelId: string,
  payload: AiModelCatalogUpdate,
): Promise<AdminAiModelSettings> {
  return request<AdminAiModelSettings>(
    token,
    `/api/v1/admin/ai-model-settings/models/${encodeURIComponent(modelId)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  );
}

export function updateAdminAiModelWorkloadRoute(
  token: string,
  workloadId: string,
  payload: AiModelRouteUpdate,
): Promise<AdminAiModelSettings> {
  return request<AdminAiModelSettings>(
    token,
    `/api/v1/admin/ai-model-settings/workloads/${encodeURIComponent(workloadId)}/route`,
    { method: 'PUT', body: JSON.stringify(payload) },
  );
}

export function resetAdminAiModelWorkloadRoute(
  token: string,
  workloadId: string,
  payload: {
    expected_registry_digest: string;
    expected_version: number;
  },
): Promise<AdminAiModelSettings> {
  const params = new URLSearchParams({
    expected_registry_digest: payload.expected_registry_digest,
  });
  params.set('expected_version', String(payload.expected_version));
  return request<AdminAiModelSettings>(
    token,
    `/api/v1/admin/ai-model-settings/workloads/${encodeURIComponent(workloadId)}/route?${params.toString()}`,
    { method: 'DELETE' },
  );
}

export interface AiModelWorkloadGroup {
  appId: string;
  workloads: AiModelWorkload[];
}

export function groupAiModelWorkloadsByApp(
  workloads: AiModelWorkload[],
): AiModelWorkloadGroup[] {
  const groups = new Map<string, AiModelWorkload[]>();
  for (const workload of workloads) {
    const appIds =
      workload.app_ids.length > 0 ? workload.app_ids : ['platform'];
    for (const appId of new Set(appIds)) {
      groups.set(appId, [...(groups.get(appId) ?? []), workload]);
    }
  }
  return [...groups.entries()]
    .map(([appId, items]) => ({
      appId,
      workloads: [...items].sort((left, right) =>
        left.workload_id.localeCompare(right.workload_id),
      ),
    }))
    .sort((left, right) => left.appId.localeCompare(right.appId));
}

export function modelSupportsCapabilities(
  model: AiModelCatalogEntry,
  capabilities: string[],
): boolean {
  return capabilities.every((capability) =>
    model.capabilities.includes(capability),
  );
}

export function isConfigurableModelRoutingWorkload(
  workload: AiModelWorkload,
): boolean {
  return (
    workload.management_surface === 'llm_routing' ||
    workload.required_capabilities.includes('vision')
  );
}
