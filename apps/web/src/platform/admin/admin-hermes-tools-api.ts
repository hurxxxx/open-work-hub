import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type AdminHermesSummary = ApiSchema<'AdminHermesSummaryResponse'>;
export type AdminHermesRuntimeHealth =
  ApiSchema<'AdminHermesRuntimeHealthResponse'>;
export type AdminHermesProfile = ApiSchema<'AdminHermesProfileResponse'>;
export type AdminHermesProfileList =
  ApiSchema<'AdminHermesProfileListResponse'>;
export type AdminHermesInventory = ApiSchema<'AdminHermesInventoryResponse'>;
export type AdminHermesResearchSettings =
  ApiSchema<'AdminHermesResearchSettingsResponse'>;
export type AdminHermesResearchSource =
  ApiSchema<'AdminHermesResearchSourceResponse'>;
export type AdminHermesResearchSourceId = AdminHermesResearchSource['id'];

export class AdminHermesToolsApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(path, token, init, (error) => {
    const detail =
      error.payload &&
      typeof error.payload === 'object' &&
      'detail' in error.payload
        ? error.payload.detail
        : null;
    const message =
      typeof detail === 'string' && detail.trim()
        ? detail
        : 'Hermes tool settings request failed.';
    return new AdminHermesToolsApiError(error.status, message);
  });
}

export function getAdminHermesSummary(
  token: string,
): Promise<AdminHermesSummary> {
  return request(token, '/api/v1/admin/hermes', { cache: 'no-store' });
}

export function getAdminHermesRuntimeHealth(
  token: string,
): Promise<AdminHermesRuntimeHealth> {
  return request(token, '/api/v1/admin/hermes/runtime-health', {
    cache: 'no-store',
  });
}

export function listAdminHermesProfiles(
  token: string,
): Promise<AdminHermesProfileList> {
  return request(token, '/api/v1/admin/hermes/profiles', {
    cache: 'no-store',
  });
}

export function getAdminHermesInventory(
  token: string,
  bindingId: string,
): Promise<AdminHermesInventory> {
  return request(
    token,
    `/api/v1/admin/hermes/profiles/${encodeURIComponent(bindingId)}/inventory`,
    { cache: 'no-store' },
  );
}

export function getAdminHermesResearchSettings(
  token: string,
): Promise<AdminHermesResearchSettings> {
  return request(token, '/api/v1/admin/hermes/research-sources', {
    cache: 'no-store',
  });
}

export function updateAdminHermesResearchSource(
  token: string,
  sourceId: AdminHermesResearchSourceId,
  enabled: boolean,
  expectedRevision: number,
): Promise<AdminHermesResearchSettings> {
  return request(
    token,
    `/api/v1/admin/hermes/research-sources/${encodeURIComponent(sourceId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled,
        expected_revision: expectedRevision,
      }),
    },
  );
}
