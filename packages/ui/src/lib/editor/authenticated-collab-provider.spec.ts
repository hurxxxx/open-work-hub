import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as Y from 'yjs';
import type { WebsocketProvider } from 'y-websocket';
import { createAuthenticatedCollabProvider } from './authenticated-collab-provider';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly OPEN = 1;
  readyState = 0;
  binaryType = '';
  sent: (string | Uint8Array)[] = [];
  onopen: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string | Uint8Array) {
    this.sent.push(data);
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  close() {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close', { code: 1006 }));
  }
}

const resources: { provider: WebsocketProvider; doc: Y.Doc }[] = [];
function create(token = 'session-one') {
  const doc = new Y.Doc();
  const provider = createAuthenticatedCollabProvider({
    url: 'wss://example.test/api/v1/docs/collab/ws',
    roomKey: 'room-1',
    doc,
    token,
  });
  resources.push({ provider, doc });
  return provider;
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});
afterEach(() => {
  for (const { provider, doc } of resources.splice(0)) {
    provider.destroy();
    doc.destroy();
  }
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('authenticated collaborative provider with the installed y-websocket lifecycle', () => {
  it('keeps credentials out of URLs and sends authentication before sync on every connection', async () => {
    const provider = create();
    expect(FakeWebSocket.instances).toHaveLength(0);
    provider.connect();
    const first = FakeWebSocket.instances[0];
    expect(first.url).toBe('wss://example.test/api/v1/docs/collab/ws/room-1');
    expect(provider.disableBc).toBe(true);
    expect(provider.bcconnected).toBe(false);
    first.open();
    expect(JSON.parse(first.sent[0] as string)).toEqual({
      type: 'auth',
      token: 'session-one',
    });
    expect(first.sent[1]).toBeInstanceOf(Uint8Array);
    first.close();
    await vi.advanceTimersByTimeAsync(500);
    const retry = FakeWebSocket.instances[1];
    expect(retry.url).toBe(first.url);
    retry.open();
    expect(JSON.parse(retry.sent[0] as string)).toEqual({
      type: 'auth',
      token: 'session-one',
    });
    expect(retry.sent[1]).toBeInstanceOf(Uint8Array);
  });

  it('uses a fresh token only in the replacement provider and stops the old provider', async () => {
    const old = create('old-session');
    old.connect();
    FakeWebSocket.instances[0].open();
    old.destroy();
    const current = create('current-session');
    current.connect();
    FakeWebSocket.instances[1].open();
    await vi.advanceTimersByTimeAsync(5000);
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[1].sent[0]).toBe(
      JSON.stringify({ type: 'auth', token: 'current-session' }),
    );
    expect(
      FakeWebSocket.instances.every(
        (socket) => !socket.url.includes('session'),
      ),
    ).toBe(true);
  });

  it('does not exchange source content between tabs before the server authorizes either session', async () => {
    const first = create('first-user');
    const second = create('other-user');
    first.connect();
    second.connect();
    first.doc.getMap('content').set('private', 'source body');
    await vi.advanceTimersByTimeAsync(0);
    expect(second.doc.getMap('content').get('private')).toBeUndefined();
    expect(first.bcconnected).toBe(false);
    expect(second.bcconnected).toBe(false);
  });

  it.each([
    'wss://example.test/collab?token=secret',
    'wss://example.test/collab#secret',
    'wss://user:secret@example.test/collab',
    'https://example.test/collab',
  ])('rejects a credential-bearing or invalid transport URL', (url) => {
    const doc = new Y.Doc();
    try {
      expect(() =>
        createAuthenticatedCollabProvider({
          url,
          roomKey: 'room-1',
          doc,
          token: 'session',
        }),
      ).toThrow('COLLAB_CONNECTION_PARAMETERS_INVALID');
      expect(FakeWebSocket.instances).toHaveLength(0);
    } finally {
      doc.destroy();
    }
  });
});
