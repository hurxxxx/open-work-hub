import {
  apiFetchJsonWithMappedError,
  type ApiRequestError,
} from '@/src/platform/api/client';

export interface AdminPlatformApiKeyItem {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  created_by_name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface AdminPlatformApiKeysResponse {
  available_scopes: string[];
  items: AdminPlatformApiKeyItem[];
}

export interface AdminPlatformApiKeySecretResponse {
  item: AdminPlatformApiKeyItem;
  api_key: string;
}

export interface CreateAdminPlatformApiKeyRequest {
  name: string;
  scopes: string[];
}

export class AdminPlatformApiKeysApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly payload: unknown = null,
  ) {
    super(message);
  }
}

function mapApiError(error: ApiRequestError): AdminPlatformApiKeysApiError {
  return new AdminPlatformApiKeysApiError(
    error.status,
    error.message,
    error.payload,
  );
}

export function listAdminPlatformApiKeys(
  token: string,
): Promise<AdminPlatformApiKeysResponse> {
  return apiFetchJsonWithMappedError(
    '/api/v1/admin/api-keys',
    token,
    {},
    mapApiError,
  );
}

export function createAdminPlatformApiKey(
  token: string,
  payload: CreateAdminPlatformApiKeyRequest,
): Promise<AdminPlatformApiKeySecretResponse> {
  return apiFetchJsonWithMappedError(
    '/api/v1/admin/api-keys',
    token,
    {
      body: JSON.stringify(payload),
      method: 'POST',
    },
    mapApiError,
  );
}

export function revealAdminPlatformApiKey(
  token: string,
  apiKeyId: string,
): Promise<AdminPlatformApiKeySecretResponse> {
  return apiFetchJsonWithMappedError(
    `/api/v1/admin/api-keys/${encodeURIComponent(apiKeyId)}/reveal`,
    token,
    { method: 'POST' },
    mapApiError,
  );
}

export function revokeAdminPlatformApiKey(
  token: string,
  apiKeyId: string,
): Promise<unknown> {
  return apiFetchJsonWithMappedError(
    `/api/v1/admin/api-keys/${encodeURIComponent(apiKeyId)}/revoke`,
    token,
    { method: 'POST' },
    mapApiError,
  );
}
