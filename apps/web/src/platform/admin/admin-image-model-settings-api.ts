import { jsonBodyHeaders, jsonHeaders } from '@/src/platform/api/client';

export interface ImageModelProviderConfig {
  provider_id: string;
  display_name: string;
  route_mode: 'local' | 'external';
  credential_kind: 'none' | 'api_key';
  enabled: boolean;
  endpoint_url: string | null;
  endpoint_source: 'default' | 'custom';
  has_api_key: boolean;
  supervisor_model_id: string | null;
  generation_model_id: string | null;
  ready: boolean;
  readiness_code: string | null;
  version: number;
  updated_at: string | null;
}

export interface ImageModelProfile {
  active_provider_id: string | null;
  brief_web_search_enabled: boolean;
  generation_web_search_enabled: boolean;
  max_iterations: number;
  version: number;
  updated_at: string | null;
}

export interface AdminImageModelSettings {
  registry_digest: string;
  deployment_enabled: boolean;
  ready: boolean;
  readiness_code: string | null;
  providers: ImageModelProviderConfig[];
  profile: ImageModelProfile;
}

export interface ImageModelProviderUpdate {
  expected_registry_digest: string;
  expected_version: number;
  enabled: boolean;
  endpoint_url: string | null;
  supervisor_model_id: string | null;
  generation_model_id: string | null;
  api_key?: string;
  clear_api_key?: boolean;
}

export interface ImageModelProfileUpdate {
  expected_registry_digest: string;
  expected_version: number;
  active_provider_id: string | null;
  brief_web_search_enabled: boolean;
  generation_web_search_enabled: boolean;
  max_iterations: number;
}

export class AdminImageModelSettingsApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code: string | null = null,
  ) {
    super(message);
  }
}

async function request(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<AdminImageModelSettings> {
  try {
    const response = await fetch(path, {
      ...init,
      cache: 'no-store',
      headers: {
        ...(init.body ? jsonBodyHeaders(token) : jsonHeaders(token)),
        ...(init.headers ?? {}),
      },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new AdminImageModelSettingsApiError(
        response.status,
        payload &&
        typeof payload === 'object' &&
        'detail' in payload &&
        typeof payload.detail === 'string'
          ? payload.detail
          : 'Image model settings request failed.',
        response.headers.get('X-AI-DO-Error-Code'),
      );
    }
    return payload as AdminImageModelSettings;
  } catch (error) {
    if (error instanceof AdminImageModelSettingsApiError) throw error;
    throw new AdminImageModelSettingsApiError(
      0,
      'Image model settings request failed.',
    );
  }
}

export function getAdminImageModelSettings(
  token: string,
): Promise<AdminImageModelSettings> {
  return request(token, '/api/v1/admin/image-model-settings');
}

export function updateAdminImageModelProvider(
  token: string,
  providerId: string,
  payload: ImageModelProviderUpdate,
): Promise<AdminImageModelSettings> {
  return request(
    token,
    `/api/v1/admin/image-model-settings/providers/${encodeURIComponent(providerId)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  );
}

export function updateAdminImageModelProfile(
  token: string,
  payload: ImageModelProfileUpdate,
): Promise<AdminImageModelSettings> {
  return request(token, '/api/v1/admin/image-model-settings/profile', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}
