import { describe, expect, it, vi } from 'vitest';

import {
  CLIENT_BUILD_HEADER,
  CLIENT_BUILD_WEBSOCKET_CLOSE_CODE,
  CLIENT_BUILD_WEBSOCKET_QUERY_PARAM,
  installClientBuildFetchGuard,
  installClientBuildWebSocketGuard,
  installClientBuildXhrGuard,
} from './client-build-guard';

function makeRuntime(response: Response) {
  const fetch = vi.fn().mockResolvedValue(response);
  const replace = vi.fn();
  const storage = new Map<string, string>();
  return {
    fetch,
    replace,
    runtime: {
      fetch,
      location: {
        href: 'https://app.test/w/hq/pms',
        origin: 'https://app.test',
        replace,
      },
      history: {
        state: null,
        replaceState: vi.fn(),
      },
      sessionStorage: {
        getItem: vi.fn((key: string) => storage.get(key) ?? null),
        setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
      },
    },
  };
}

describe('client build fetch guard', () => {
  it('adds the build id to same-origin API requests and preserves headers', async () => {
    const { fetch, runtime } = makeRuntime(new Response('{}', { status: 200 }));
    installClientBuildFetchGuard(runtime, { buildId: 'build-current' });

    await runtime.fetch('/api/v1/workspaces', {
      headers: { Authorization: 'Bearer token' },
    });

    const [, init] = fetch.mock.calls[0] as [RequestInfo | URL, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get(CLIENT_BUILD_HEADER)).toBe('build-current');
    expect(headers.get('Authorization')).toBe('Bearer token');
  });

  it('does not expose the build id to external origins', async () => {
    const { fetch, runtime } = makeRuntime(new Response('{}', { status: 200 }));
    installClientBuildFetchGuard(runtime, { buildId: 'build-current' });

    await runtime.fetch('https://files.example.test/download');

    const [, init] = fetch.mock.calls[0] as [RequestInfo | URL, RequestInit | undefined];
    expect(new Headers(init?.headers).has(CLIENT_BUILD_HEADER)).toBe(false);
  });

  it('does not honor reload headers from external fetch responses', async () => {
    const response = new Response('{}', {
      headers: { 'X-Open-Work-Hub-Reload-Required': '1' },
    });
    const { replace, runtime } = makeRuntime(response);
    installClientBuildFetchGuard(runtime, { buildId: 'build-current' });

    await runtime.fetch('https://files.example.test/download');

    expect(replace).not.toHaveBeenCalled();
  });

  it('cache-busts once when the server requires a client reload', async () => {
    const response = new Response(
      JSON.stringify({ code: 'CLIENT_BUILD_MISMATCH' }),
      {
        status: 409,
        headers: { 'X-Open-Work-Hub-Reload-Required': '1' },
      },
    );
    const { replace, runtime } = makeRuntime(response);
    installClientBuildFetchGuard(runtime, {
      buildId: 'build-old',
      reloadOptions: { nowMs: () => 3000 },
    });

    await runtime.fetch('/api/v1/workspaces');
    await runtime.fetch('/api/v1/workspaces');

    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith(
      'https://app.test/w/hq/pms?__reload=3000',
    );
  });

  it('guards XMLHttpRequest API uploads and reacts to mismatch responses', () => {
    class FakeXhr extends EventTarget {
      headers = new Headers();
      responseHeaders = new Headers();
      url = '';

      open(_method: string, url: string | URL) {
        this.url = String(url);
      }

      send() {
        return undefined;
      }

      setRequestHeader(name: string, value: string) {
        this.headers.set(name, value);
      }

      getResponseHeader(name: string) {
        return this.responseHeaders.get(name);
      }
    }

    const { replace, runtime } = makeRuntime(new Response('{}'));
    const browserRuntime = Object.assign(runtime, {
      XMLHttpRequest: FakeXhr as unknown as typeof XMLHttpRequest,
    });
    installClientBuildXhrGuard(browserRuntime, {
      buildId: 'build-current',
      reloadOptions: { nowMs: () => 4000 },
    });

    const request = new browserRuntime.XMLHttpRequest() as unknown as FakeXhr;
    request.open('POST', '/api/v1/files/upload');
    request.send();
    expect(request.headers.get(CLIENT_BUILD_HEADER)).toBe('build-current');

    request.responseHeaders.set('X-Open-Work-Hub-Reload-Required', '1');
    request.dispatchEvent(new Event('load'));
    expect(replace).toHaveBeenCalledWith(
      'https://app.test/w/hq/pms?__reload=4000',
    );
  });

  it('clears API classification when an XMLHttpRequest is reused externally', () => {
    class FakeXhr extends EventTarget {
      headers = new Headers();

      open() {
        return undefined;
      }

      send() {
        return undefined;
      }

      setRequestHeader(name: string, value: string) {
        this.headers.set(name, value);
      }

      getResponseHeader() {
        return null;
      }
    }

    const { runtime } = makeRuntime(new Response('{}'));
    const browserRuntime = Object.assign(runtime, {
      XMLHttpRequest: FakeXhr as unknown as typeof XMLHttpRequest,
    });
    installClientBuildXhrGuard(browserRuntime, { buildId: 'build-current' });

    const request = new browserRuntime.XMLHttpRequest() as unknown as FakeXhr;
    request.open('POST', '/api/v1/files/upload');
    request.open('GET', 'https://files.example.test/download');
    request.send();

    expect(request.headers.has(CLIENT_BUILD_HEADER)).toBe(false);
  });

  it('pins same-origin API websockets and reloads on the guard close code', () => {
    class FakeWebSocket extends EventTarget {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;
      readonly url: string;

      constructor(url: string | URL) {
        super();
        this.url = String(url);
      }
    }

    const { replace, runtime } = makeRuntime(new Response('{}'));
    const browserRuntime = Object.assign(runtime, {
      WebSocket: FakeWebSocket as unknown as typeof WebSocket,
    });
    installClientBuildWebSocketGuard(browserRuntime, {
      buildId: 'build-current',
      reloadOptions: { nowMs: () => 5000 },
    });

    const socket = new browserRuntime.WebSocket(
      'wss://app.test/api/v1/realtime/ws?workspace=hq',
    ) as unknown as FakeWebSocket;
    const socketUrl = new URL(socket.url);
    expect(socketUrl.searchParams.get(CLIENT_BUILD_WEBSOCKET_QUERY_PARAM)).toBe(
      'build-current',
    );

    const closeEvent = new Event('close');
    Object.defineProperty(closeEvent, 'code', {
      value: CLIENT_BUILD_WEBSOCKET_CLOSE_CODE,
    });
    socket.dispatchEvent(closeEvent);
    expect(replace).toHaveBeenCalledWith(
      'https://app.test/w/hq/pms?__reload=5000',
    );
  });
});
