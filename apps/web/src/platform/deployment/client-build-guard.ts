import {
  requestCacheBustingReloadOnce,
  type StaleAssetReloadOptions,
  type StaleAssetReloadRuntime,
} from './stale-asset-reload';

export const CLIENT_BUILD_HEADER = 'X-AI-DO-Web-Build';
export const CLIENT_RELOAD_REQUIRED_HEADER = 'X-AI-DO-Reload-Required';
export const CLIENT_BUILD_WEBSOCKET_QUERY_PARAM = '__ai_do_build';
export const CLIENT_BUILD_WEBSOCKET_CLOSE_CODE = 4409;

export const WEB_BUILD_ID =
  (import.meta.env.VITE_AI_DO_BUILD_ID as string | undefined)?.trim() ?? '';

interface ClientBuildFetchRuntime extends StaleAssetReloadRuntime {
  fetch: typeof fetch;
  location: StaleAssetReloadRuntime['location'] & Pick<Location, 'origin'>;
}

interface ClientBuildBrowserRuntime extends ClientBuildFetchRuntime {
  XMLHttpRequest?: typeof XMLHttpRequest;
  WebSocket?: typeof WebSocket;
}

export interface ClientBuildGuardOptions {
  buildId?: string;
  reloadOptions?: StaleAssetReloadOptions;
}

function requestUrl(input: RequestInfo | URL, baseUrl: string): URL | null {
  try {
    if (input instanceof Request) {
      return new URL(input.url);
    }
    return new URL(String(input), baseUrl);
  } catch {
    return null;
  }
}

function isSameOriginApiRequest(url: URL | null, origin: string): boolean {
  return Boolean(
    url &&
      url.origin === origin &&
      (url.pathname === '/api' || url.pathname.startsWith('/api/')),
  );
}

function mergedRequestHeaders(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  buildId: string,
): Headers {
  const headers = new Headers(input instanceof Request ? input.headers : undefined);
  new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
  headers.set(CLIENT_BUILD_HEADER, buildId);
  return headers;
}

export function responseRequiresClientReload(
  response: Pick<Response, 'headers'>,
): boolean {
  return response.headers.get(CLIENT_RELOAD_REQUIRED_HEADER) === '1';
}

export function installClientBuildFetchGuard(
  runtime: ClientBuildFetchRuntime = window,
  options: ClientBuildGuardOptions = {},
): () => void {
  const buildId = options.buildId ?? WEB_BUILD_ID;
  if (!buildId) {
    return () => undefined;
  }

  const nativeFetch = runtime.fetch.bind(runtime);
  const guardedFetch: typeof fetch = async (input, init) => {
    const url = requestUrl(input, runtime.location.href);
    const isGuardedRequest = isSameOriginApiRequest(
      url,
      runtime.location.origin,
    );
    const requestInit = isGuardedRequest
      ? {
          ...init,
          headers: mergedRequestHeaders(input, init, buildId),
        }
      : init;
    const response = await nativeFetch(input, requestInit);
    if (isGuardedRequest && responseRequiresClientReload(response)) {
      requestCacheBustingReloadOnce(runtime, options.reloadOptions ?? {});
    }
    return response;
  };

  runtime.fetch = guardedFetch;
  return () => {
    if (runtime.fetch === guardedFetch) {
      runtime.fetch = nativeFetch;
    }
  };
}

export function installClientBuildXhrGuard(
  runtime: ClientBuildBrowserRuntime = window,
  options: ClientBuildGuardOptions = {},
): () => void {
  const buildId = options.buildId ?? WEB_BUILD_ID;
  const Xhr = runtime.XMLHttpRequest;
  if (!buildId || !Xhr) {
    return () => undefined;
  }

  const prototype = Xhr.prototype;
  const nativeOpen = prototype.open;
  const nativeSend = prototype.send;
  const apiRequests = new WeakSet<XMLHttpRequest>();

  const guardedOpen = function (
    this: XMLHttpRequest,
    method: string,
    url: string | URL,
    ...args: unknown[]
  ) {
    apiRequests.delete(this);
    if (
      isSameOriginApiRequest(
        requestUrl(url, runtime.location.href),
        runtime.location.origin,
      )
    ) {
      apiRequests.add(this);
    }
    return (nativeOpen as (...openArgs: unknown[]) => void).call(
      this,
      method,
      url,
      ...args,
    );
  } as XMLHttpRequest['open'];

  const guardedSend = function (
    this: XMLHttpRequest,
    body?: Document | XMLHttpRequestBodyInit | null,
  ) {
    if (apiRequests.has(this)) {
      this.setRequestHeader(CLIENT_BUILD_HEADER, buildId);
      this.addEventListener(
        'load',
        () => {
          if (this.getResponseHeader(CLIENT_RELOAD_REQUIRED_HEADER) === '1') {
            requestCacheBustingReloadOnce(runtime, options.reloadOptions ?? {});
          }
        },
        { once: true },
      );
    }
    return nativeSend.call(this, body);
  } as XMLHttpRequest['send'];

  prototype.open = guardedOpen;
  prototype.send = guardedSend;
  return () => {
    if (prototype.open === guardedOpen) {
      prototype.open = nativeOpen;
    }
    if (prototype.send === guardedSend) {
      prototype.send = nativeSend;
    }
  };
}

function guardedWebSocketUrl(
  input: string | URL,
  runtime: ClientBuildBrowserRuntime,
  buildId: string,
): string | URL {
  try {
    const url = new URL(String(input), runtime.location.href);
    const pageUrl = new URL(runtime.location.href);
    if (
      url.host === pageUrl.host &&
      (url.protocol === 'ws:' || url.protocol === 'wss:') &&
      (url.pathname === '/api' || url.pathname.startsWith('/api/'))
    ) {
      url.searchParams.set(CLIENT_BUILD_WEBSOCKET_QUERY_PARAM, buildId);
      return url.toString();
    }
  } catch {
    // Let the native constructor report invalid URLs.
  }
  return input;
}

export function installClientBuildWebSocketGuard(
  runtime: ClientBuildBrowserRuntime = window,
  options: ClientBuildGuardOptions = {},
): () => void {
  const buildId = options.buildId ?? WEB_BUILD_ID;
  const NativeWebSocket = runtime.WebSocket;
  if (!buildId || !NativeWebSocket) {
    return () => undefined;
  }

  class GuardedWebSocket extends NativeWebSocket {
    constructor(url: string | URL, protocols?: string | string[]) {
      const guardedUrl = guardedWebSocketUrl(url, runtime, buildId);
      if (protocols === undefined) {
        super(guardedUrl);
      } else {
        super(guardedUrl, protocols);
      }
      this.addEventListener('close', (event) => {
        if (event.code === CLIENT_BUILD_WEBSOCKET_CLOSE_CODE) {
          requestCacheBustingReloadOnce(runtime, options.reloadOptions ?? {});
        }
      });
    }
  }

  runtime.WebSocket = GuardedWebSocket;
  return () => {
    if (runtime.WebSocket === GuardedWebSocket) {
      runtime.WebSocket = NativeWebSocket;
    }
  };
}

export function installClientBuildGuards(
  runtime: ClientBuildBrowserRuntime = window,
  options: ClientBuildGuardOptions = {},
): () => void {
  const cleanups = [
    installClientBuildFetchGuard(runtime, options),
    installClientBuildXhrGuard(runtime, options),
    installClientBuildWebSocketGuard(runtime, options),
  ];
  return () => {
    for (const cleanup of cleanups.reverse()) {
      cleanup();
    }
  };
}
