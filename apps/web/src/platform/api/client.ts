import { i18n } from '@/src/platform/i18n';

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly payload: unknown = null,
  ) {
    super(message);
  }
}

export function jsonHeaders(
  token?: string | null,
  headers?: HeadersInit,
): HeadersInit {
  const locale = i18n.resolvedLanguage || i18n.language;
  return {
    Accept: 'application/json',
    ...(locale
      ? { 'Accept-Language': locale, 'X-Open-Work-Hub-Locale': locale }
      : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers ?? {}),
  };
}

export function jsonBodyHeaders(
  token?: string | null,
  headers?: HeadersInit,
): HeadersInit {
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
  const shouldSendJsonContentType =
    init.body != null &&
    !(typeof FormData !== 'undefined' && init.body instanceof FormData);
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(shouldSendJsonContentType
        ? jsonBodyHeaders(token)
        : jsonHeaders(token)),
      ...(init.headers ?? {}),
    },
    cache: init.cache ?? 'no-store',
  });
  return parseJsonResponse<T>(response);
}

export interface ApiBinaryResponse {
  blob: Blob;
  contentDisposition: string | null;
  contentType: string | null;
}

export async function apiFetchBinary(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<ApiBinaryResponse> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...jsonHeaders(token),
      Accept: '*/*',
      ...(init.headers ?? {}),
    },
    cache: init.cache ?? 'no-store',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiRequestError(
      response.status,
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed with ${response.status}.`,
      payload,
    );
  }
  return {
    blob: await response.blob(),
    contentDisposition: response.headers.get('content-disposition'),
    contentType: response.headers.get('content-type'),
  };
}

export async function apiFetchJsonWithMappedError<
  T,
  TError extends Error = Error,
>(
  path: string,
  token: string | null | undefined,
  init: RequestInit = {},
  mapError: (error: ApiRequestError) => TError,
): Promise<T> {
  try {
    return await apiFetchJson<T>(path, token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw mapError(error);
    }
    throw error;
  }
}
