import createClient from 'openapi-fetch';
import type { paths } from './openapi.generated';

export const apiClient = createClient<paths>({ baseUrl: '' });

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly payload: unknown = null,
  ) {
    super(message);
  }
}

export function jsonHeaders(token?: string | null, headers?: HeadersInit): HeadersInit {
  return {
    Accept: 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers ?? {}),
  };
}

export function jsonBodyHeaders(token?: string | null, headers?: HeadersInit): HeadersInit {
  return {
    ...jsonHeaders(token, headers),
    'Content-Type': 'application/json',
  };
}

export async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiRequestError(
      response.status,
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed with ${response.status}.`,
      payload,
    );
  }

  return payload as T;
}

export async function apiFetchJson<T>(
  path: string,
  token?: string | null,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body == null ? jsonHeaders(token) : jsonBodyHeaders(token)),
      ...(init.headers ?? {}),
    },
    cache: init.cache ?? 'no-store',
  });
  return parseJsonResponse<T>(response);
}
